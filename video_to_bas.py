<<<<<<< HEAD
# -*- coding: utf-8 -*-
"""
视频转 BAS (Bilibili Animation Script) 弹幕工具
==============================================
参考规范: https://bilibili.github.io/bas/#/guide

逐帧方案：duration（存活时间）+ zIndex（层次）层叠。
所有帧 fillAlpha=1，帧0 duration=0.1s/zIndex最高, 帧N duration最长/zIndex最低。
更高 zIndex 覆盖更低，已死帧消失，无需 set/then set。
"""

import os, sys, cv2, numpy as np
from pathlib import Path


# ============================================================
class Config:
    # 每帧保留的颜色数，越大色彩越丰富（P3 全色域建议 ≥16）
    MAX_COLORS_PER_FRAME = 24

    # 单色填充色（仅 MAX_COLORS_PER_FRAME=1）
    FILL_COLOR = "0xffffff"

    # 轮廓质量
    CONTOUR_EPSILON_RATIO = 0.004
    MIN_CONTOUR_AREA = 16
    THRESH_METHOD = "otsu"
    THRESH_INVERT = True
    ADAPTIVE_BLOCK_SIZE = 11
    ADAPTIVE_C = 5
    MORPH_KERNEL_SIZE = 3

    # 帧处理
    RESIZE_WIDTH = 0            # 0=保持原分辨率，不缩放

    # BAS 渲染
    BAS_SCALE = 0                # 0=自动计算（居中适配），>0=手动指定

    # 输出限制
    MAX_PATH_STRING_LENGTH = 80000


# ============================================================
def bgr_to_hex(b, g, r):
    return f"0x{r:02x}{g:02x}{b:02x}"


def contours_to_svg_d(contours):
    parts = []
    for cnt in contours:
        if len(cnt) < 3:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, Config.CONTOUR_EPSILON_RATIO * peri, True)
        if len(approx) < 3:
            continue
        pts = approx.reshape(-1, 2)
        cmds = [f"M{pts[0][0]},{pts[0][1]}"]
        for p in pts[1:]:
            cmds.append(f"L{p[0]},{p[1]}")
        cmds.append("Z")
        parts.append(" ".join(cmds))
    return " ".join(parts)


def mk():
    k = Config.MORPH_KERNEL_SIZE
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


# ============================================================
def process_frame_solid_fill(frame):
    """单色模式"""
    h, w = frame.shape[:2]
    fa = h * w
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    base = cv2.THRESH_BINARY_INV if Config.THRESH_INVERT else cv2.THRESH_BINARY
    if Config.THRESH_METHOD == "otsu":
        _, binary = cv2.threshold(blurred, 0, 255, base | cv2.THRESH_OTSU)
    else:
        binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        base, Config.ADAPTIVE_BLOCK_SIZE, Config.ADAPTIVE_C)
    k = mk()
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k)
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    valid = [c for c in contours
             if cv2.contourArea(c) >= Config.MIN_CONTOUR_AREA
             and not (cv2.contourArea(c) > fa * 0.95 and len(c) < 8)]
    return contours_to_svg_d(valid) if valid else ""


def process_frame_multicolor(frame):
    """
    多颜色模式：饱和度增强 + K-Means 量化 → 逐色轮廓提取。
    加深颜色：HSV空间 S通道×1.5 提纯后再量化。
    返回 [(d_str, hex_color), ...]
    """
    # 加深颜色：HSV空间提高饱和度
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.5, 0, 255)
    boosted = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    h, w = boosted.shape[:2]
    k = Config.MAX_COLORS_PER_FRAME
    pixels = boosted.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
    quantized = centers[labels.flatten()].astype(np.uint8).reshape(h, w, 3)
    unique_cols, counts = np.unique(quantized.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-counts)
    results = []
    kernel = mk()
    for idx in order:
        b, g, r = int(unique_cols[idx][0]), int(unique_cols[idx][1]), int(unique_cols[idx][2])
        if int(counts[idx]) < Config.MIN_CONTOUR_AREA:
            continue
        lower = np.array([b, g, r], dtype=np.uint8)
        upper = np.array([b, g, r], dtype=np.uint8)
        mask = cv2.inRange(quantized, lower, upper)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = [c for c in contours if cv2.contourArea(c) >= Config.MIN_CONTOUR_AREA]
        if not contours:
            continue
        d = contours_to_svg_d(contours)
        if d.strip():
            results.append((d, bgr_to_hex(b, g, r)))
    return results


# ============================================================
def build_bas_script(all_frames_data, video_width, video_height, fps, is_solid):
    """
    生成 BAS 弹幕脚本。

    利用 duration（存活时间）+ zIndex（层次优先级）实现逐帧显示：
      所有帧从 t=0 同时开始，fillAlpha=1 始终可见。
      帧0 duration=0.1s, 帧1 duration=0.2s, ..., 逐帧递增。
      zIndex 逐帧递减：帧0最高层, 帧N最低层。
      任何时候，已死帧消失，存活的最高 zIndex 帧在顶层可见。
      （BAS 官方：zIndex 值高的对象在上层，不可变属性）
      无需任何 set/then set 动画链。
    """
    frame_s = 0.1
    total = len([d for d in all_frames_data if d])
    sc = Config.BAS_SCALE

    # 自动居中缩放
    if sc <= 0:
        sc = min(1.0, 600.0 / max(video_width, 1))
    sc = round(sc, 4)
    pct_x = (100 - sc * 100) / 2
    pct_y = (100 - sc * 100 * video_height / max(video_width, 1)) / 2
    xp = f"{pct_x:.1f}%"
    yp = f"{pct_y:.1f}%"

    # 过滤有效帧
    vf = []
    for fi in range(len(all_frames_data)):
        if all_frames_data[fi]:
            vf.append(all_frames_data[fi])
    if not vf:
        return ""

    if is_solid:
        return _build_solid(vf, video_width, video_height, sc, xp, yp, frame_s, total)
    else:
        return _build_color(vf, video_width, video_height, sc, xp, yp, frame_s, total)


def _build_solid(vf, vw, vh, sc, xp, yp, frame_s, total):
    """单色：每帧一个 def path，duration 逐帧递增，zIndex 逐帧递减"""
    lines = []
    for i, d_str in enumerate(vf):
        if len(d_str) > Config.MAX_PATH_STRING_LENGTH:
            d_str = d_str[:Config.MAX_PATH_STRING_LENGTH] + " Z"
        dur = (i + 1) * frame_s
        dur_str = f"{dur:.1f}s" if dur >= 1 else f"{int(dur * 1000)}ms"
        lines.append(f"def path f{i} {{")
        lines.append(f'    d = "{d_str}"')
        lines.append(f'    viewBox="0 0 {vw} {vh}"')
        lines.append(f"    x = {xp}")
        lines.append(f"    y = {yp}")
        lines.append(f"    scale = {sc}")
        lines.append(f"    fillColor = {Config.FILL_COLOR}")
        lines.append(f"    fillAlpha = 1")
        lines.append(f"    zIndex = {total - i}")
        lines.append(f"    duration = {dur_str}")
        lines.append(f"}}")
        lines.append("")
    return "\n".join(lines)


def _build_color(vf, vw, vh, sc, xp, yp, frame_s, total):
    """
    多色：每帧每色一个 def path，duration 逐帧递增，zIndex 逐帧递减。
    同帧所有颜色层 zIndex 和 duration 相同。
    """
    lines = []
    for i, cd in enumerate(vf):
        dur = (i + 1) * frame_s
        dur_str = f"{dur:.1f}s" if dur >= 1 else f"{int(dur * 1000)}ms"
        z_idx = total - i
        for ci, (d_str, hex_color) in enumerate(cd):
            if len(d_str) > Config.MAX_PATH_STRING_LENGTH:
                d_str = d_str[:Config.MAX_PATH_STRING_LENGTH] + " Z"
            lines.append(f"def path f{i}c{ci} {{")
            lines.append(f'    d = "{d_str}"')
            lines.append(f'    viewBox="0 0 {vw} {vh}"')
            lines.append(f"    x = {xp}")
            lines.append(f"    y = {yp}")
            lines.append(f"    scale = {sc}")
            lines.append(f"    fillColor = {hex_color}")
            lines.append(f"    fillAlpha = 1")
            lines.append(f"    zIndex = {z_idx}")
            lines.append(f"    duration = {dur_str}")
            lines.append(f"}}")
            lines.append("")
    return "\n".join(lines)


# ============================================================
def read_video(video_path):
    """读取视频全部帧，采样到 10fps，保持原始分辨率。"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w0, h0 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    raw_duration_s = total_frames / fps
    print(f"\n  📹 {w0}x{h0} (原分辨率), {fps:.1f}fps, {total_frames}帧, {raw_duration_s:.1f}s")

    raw_frames = []
    for _ in range(total_frames):
        ok, f = cap.read()
        if not ok:
            break
        raw_frames.append(f)
    cap.release()

    n = len(raw_frames)
    if n == 0:
        print(f"  ⚠ 无帧\n")
        return [], fps, w0, h0

    # 采样到 10fps：总帧数 = 视频秒数 × 10
    target = int(round(raw_duration_s * 10))
    if n <= target:
        frames = raw_frames
    else:
        indices = [round(i * (n - 1) / (target - 1)) for i in range(target)]
        frames = [raw_frames[j] for j in indices]

    duration_s = len(frames) * 0.1
    print(f"  ✅ 采样 {len(frames)} 帧 (10fps, {duration_s:.1f}s)\n")
    return frames, fps, w0, h0


# ============================================================
def main():
    print()
    print("╔" + "═" * 58 + "╗")
    print("║  视频 → BAS 弹幕转换工具                           ║")
    print("║  规范: https://bilibili.github.io/bas/#/guide      ║")
    print("╚" + "═" * 58 + "╝")

    is_solid = Config.MAX_COLORS_PER_FRAME <= 1
    md = f"单色填充({Config.FILL_COLOR})" if is_solid else f"多色 {Config.MAX_COLORS_PER_FRAME}色"
    print(f"\n  {md} | 原分辨率 | 全部帧 10fps")

    while True:
        raw = input("\n请输入视频绝对路径: ").strip().strip('"').strip("'")
        if raw and os.path.isfile(raw):
            vp = raw; break
        print("  ❌ 路径无效")

    try:
        frames, fps, w, h = read_video(vp)
    except Exception as e:
        print(f"\n  ❌ {e}"); input("\n按任意键退出..."); sys.exit(1)
    if not frames:
        print("\n  ❌ 无帧"); input("\n按任意键退出..."); sys.exit(1)

    print("  🔄 逐帧转换...")
    ad = []
    for i, fr in enumerate(frames):
        ad.append(process_frame_solid_fill(fr) if is_solid else process_frame_multicolor(fr))
        if (i + 1) % 10 == 0 or i + 1 == len(frames):
            vn = sum(1 for d in ad if d)
            print(f"     {i + 1}/{len(frames)}  有效: {vn}")

    vt = sum(1 for d in ad if d)
    print(f"  ✅ {vt}/{len(frames)} 有效帧")
    if vt == 0:
        print("  ❌ 无有效数据，请调小 MIN_CONTOUR_AREA"); input("\n按任意键退出..."); sys.exit(1)

    print("  📝 生成 BAS 代码...")
    code = build_bas_script(ad, w, h, fps, is_solid)

    stem = Path(vp).stem
    out = Path(vp).parent / f"{stem}_bas弹幕.txt"
    n = 1
    while out.exists():
        out = Path(vp).parent / f"{stem}_bas弹幕_{n}.txt"; n += 1
    out.write_text(code, encoding='utf-8')

    size_kb = os.path.getsize(out) / 1024
    lc = code.count('\n') + 1
    print(f"\n╔{'═'*58}╗")
    print(f"║  ✅ 转换完成                                         ║")
    print(f"║  {out}")
    print(f"╠{'═'*58}╣")
    print(f"║  文件大小: {size_kb:>10.1f} KB                               ║")
    print(f"║  代码行数: {lc:>10}                                   ║")
    print(f"╚{'═'*58}╝")
    print("\n  💡 B站投稿 → 弹幕池 → BAS弹幕 → 代码模式 → 粘贴 → 发送")
    input("\n按任意键退出...")


if __name__ == "__main__":
    main()
=======
# -*- coding: utf-8 -*-
"""
视频转 BAS (Bilibili Animation Script) 弹幕工具
==============================================
参考规范: https://bilibili.github.io/bas/#/guide

逐帧方案：duration（存活时间）+ zIndex（层次）层叠。
所有帧 fillAlpha=1，帧0 duration=0.1s/zIndex最高, 帧N duration最长/zIndex最低。
更高 zIndex 覆盖更低，已死帧消失，无需 set/then set。
"""

import os, sys, cv2, numpy as np
from pathlib import Path


# ============================================================
class Config:
    # 每帧保留的颜色数，越大色彩越丰富（P3 全色域建议 ≥16）
    MAX_COLORS_PER_FRAME = 24

    # 单色填充色（仅 MAX_COLORS_PER_FRAME=1）
    FILL_COLOR = "0xffffff"

    # 轮廓质量
    CONTOUR_EPSILON_RATIO = 0.004
    MIN_CONTOUR_AREA = 16
    THRESH_METHOD = "otsu"
    THRESH_INVERT = True
    ADAPTIVE_BLOCK_SIZE = 11
    ADAPTIVE_C = 5
    MORPH_KERNEL_SIZE = 3

    # 帧处理
    RESIZE_WIDTH = 0            # 0=保持原分辨率，不缩放

    # BAS 渲染
    BAS_SCALE = 0                # 0=自动计算（居中适配），>0=手动指定

    # 输出限制
    MAX_PATH_STRING_LENGTH = 80000


# ============================================================
def bgr_to_hex(b, g, r):
    return f"0x{r:02x}{g:02x}{b:02x}"


def contours_to_svg_d(contours):
    parts = []
    for cnt in contours:
        if len(cnt) < 3:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, Config.CONTOUR_EPSILON_RATIO * peri, True)
        if len(approx) < 3:
            continue
        pts = approx.reshape(-1, 2)
        cmds = [f"M{pts[0][0]},{pts[0][1]}"]
        for p in pts[1:]:
            cmds.append(f"L{p[0]},{p[1]}")
        cmds.append("Z")
        parts.append(" ".join(cmds))
    return " ".join(parts)


def mk():
    k = Config.MORPH_KERNEL_SIZE
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


# ============================================================
def process_frame_solid_fill(frame):
    """单色模式"""
    h, w = frame.shape[:2]
    fa = h * w
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    base = cv2.THRESH_BINARY_INV if Config.THRESH_INVERT else cv2.THRESH_BINARY
    if Config.THRESH_METHOD == "otsu":
        _, binary = cv2.threshold(blurred, 0, 255, base | cv2.THRESH_OTSU)
    else:
        binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        base, Config.ADAPTIVE_BLOCK_SIZE, Config.ADAPTIVE_C)
    k = mk()
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k)
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    valid = [c for c in contours
             if cv2.contourArea(c) >= Config.MIN_CONTOUR_AREA
             and not (cv2.contourArea(c) > fa * 0.95 and len(c) < 8)]
    return contours_to_svg_d(valid) if valid else ""


def process_frame_multicolor(frame):
    """
    多颜色模式：饱和度增强 + K-Means 量化 → 逐色轮廓提取。
    加深颜色：HSV空间 S通道×1.5 提纯后再量化。
    返回 [(d_str, hex_color), ...]
    """
    # 加深颜色：HSV空间提高饱和度
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.5, 0, 255)
    boosted = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    h, w = boosted.shape[:2]
    k = Config.MAX_COLORS_PER_FRAME
    pixels = boosted.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
    quantized = centers[labels.flatten()].astype(np.uint8).reshape(h, w, 3)
    unique_cols, counts = np.unique(quantized.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-counts)
    results = []
    kernel = mk()
    for idx in order:
        b, g, r = int(unique_cols[idx][0]), int(unique_cols[idx][1]), int(unique_cols[idx][2])
        if int(counts[idx]) < Config.MIN_CONTOUR_AREA:
            continue
        lower = np.array([b, g, r], dtype=np.uint8)
        upper = np.array([b, g, r], dtype=np.uint8)
        mask = cv2.inRange(quantized, lower, upper)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = [c for c in contours if cv2.contourArea(c) >= Config.MIN_CONTOUR_AREA]
        if not contours:
            continue
        d = contours_to_svg_d(contours)
        if d.strip():
            results.append((d, bgr_to_hex(b, g, r)))
    return results


# ============================================================
def build_bas_script(all_frames_data, video_width, video_height, fps, is_solid):
    """
    生成 BAS 弹幕脚本。

    利用 duration（存活时间）+ zIndex（层次优先级）实现逐帧显示：
      所有帧从 t=0 同时开始，fillAlpha=1 始终可见。
      帧0 duration=0.1s, 帧1 duration=0.2s, ..., 逐帧递增。
      zIndex 逐帧递减：帧0最高层, 帧N最低层。
      任何时候，已死帧消失，存活的最高 zIndex 帧在顶层可见。
      （BAS 官方：zIndex 值高的对象在上层，不可变属性）
      无需任何 set/then set 动画链。
    """
    frame_s = 0.1
    total = len([d for d in all_frames_data if d])
    sc = Config.BAS_SCALE

    # 自动居中缩放
    if sc <= 0:
        sc = min(1.0, 600.0 / max(video_width, 1))
    sc = round(sc, 4)
    pct_x = (100 - sc * 100) / 2
    pct_y = (100 - sc * 100 * video_height / max(video_width, 1)) / 2
    xp = f"{pct_x:.1f}%"
    yp = f"{pct_y:.1f}%"

    # 过滤有效帧
    vf = []
    for fi in range(len(all_frames_data)):
        if all_frames_data[fi]:
            vf.append(all_frames_data[fi])
    if not vf:
        return ""

    if is_solid:
        return _build_solid(vf, video_width, video_height, sc, xp, yp, frame_s, total)
    else:
        return _build_color(vf, video_width, video_height, sc, xp, yp, frame_s, total)


def _build_solid(vf, vw, vh, sc, xp, yp, frame_s, total):
    """单色：每帧一个 def path，duration 逐帧递增，zIndex 逐帧递减"""
    lines = []
    for i, d_str in enumerate(vf):
        if len(d_str) > Config.MAX_PATH_STRING_LENGTH:
            d_str = d_str[:Config.MAX_PATH_STRING_LENGTH] + " Z"
        dur = (i + 1) * frame_s
        dur_str = f"{dur:.1f}s" if dur >= 1 else f"{int(dur * 1000)}ms"
        lines.append(f"def path f{i} {{")
        lines.append(f'    d = "{d_str}"')
        lines.append(f'    viewBox="0 0 {vw} {vh}"')
        lines.append(f"    x = {xp}")
        lines.append(f"    y = {yp}")
        lines.append(f"    scale = {sc}")
        lines.append(f"    fillColor = {Config.FILL_COLOR}")
        lines.append(f"    fillAlpha = 1")
        lines.append(f"    zIndex = {total - i}")
        lines.append(f"    duration = {dur_str}")
        lines.append(f"}}")
        lines.append("")
    return "\n".join(lines)


def _build_color(vf, vw, vh, sc, xp, yp, frame_s, total):
    """
    多色：每帧每色一个 def path，duration 逐帧递增，zIndex 逐帧递减。
    同帧所有颜色层 zIndex 和 duration 相同。
    """
    lines = []
    for i, cd in enumerate(vf):
        dur = (i + 1) * frame_s
        dur_str = f"{dur:.1f}s" if dur >= 1 else f"{int(dur * 1000)}ms"
        z_idx = total - i
        for ci, (d_str, hex_color) in enumerate(cd):
            if len(d_str) > Config.MAX_PATH_STRING_LENGTH:
                d_str = d_str[:Config.MAX_PATH_STRING_LENGTH] + " Z"
            lines.append(f"def path f{i}c{ci} {{")
            lines.append(f'    d = "{d_str}"')
            lines.append(f'    viewBox="0 0 {vw} {vh}"')
            lines.append(f"    x = {xp}")
            lines.append(f"    y = {yp}")
            lines.append(f"    scale = {sc}")
            lines.append(f"    fillColor = {hex_color}")
            lines.append(f"    fillAlpha = 1")
            lines.append(f"    zIndex = {z_idx}")
            lines.append(f"    duration = {dur_str}")
            lines.append(f"}}")
            lines.append("")
    return "\n".join(lines)


# ============================================================
def read_video(video_path):
    """读取视频全部帧，采样到 10fps，保持原始分辨率。"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w0, h0 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    raw_duration_s = total_frames / fps
    print(f"\n  📹 {w0}x{h0} (原分辨率), {fps:.1f}fps, {total_frames}帧, {raw_duration_s:.1f}s")

    raw_frames = []
    for _ in range(total_frames):
        ok, f = cap.read()
        if not ok:
            break
        raw_frames.append(f)
    cap.release()

    n = len(raw_frames)
    if n == 0:
        print(f"  ⚠ 无帧\n")
        return [], fps, w0, h0

    # 采样到 10fps：总帧数 = 视频秒数 × 10
    target = int(round(raw_duration_s * 10))
    if n <= target:
        frames = raw_frames
    else:
        indices = [round(i * (n - 1) / (target - 1)) for i in range(target)]
        frames = [raw_frames[j] for j in indices]

    duration_s = len(frames) * 0.1
    print(f"  ✅ 采样 {len(frames)} 帧 (10fps, {duration_s:.1f}s)\n")
    return frames, fps, w0, h0


# ============================================================
def main():
    print()
    print("╔" + "═" * 58 + "╗")
    print("║  视频 → BAS 弹幕转换工具                           ║")
    print("║  规范: https://bilibili.github.io/bas/#/guide      ║")
    print("╚" + "═" * 58 + "╝")

    is_solid = Config.MAX_COLORS_PER_FRAME <= 1
    md = f"单色填充({Config.FILL_COLOR})" if is_solid else f"多色 {Config.MAX_COLORS_PER_FRAME}色"
    print(f"\n  {md} | 原分辨率 | 全部帧 10fps")

    while True:
        raw = input("\n请输入视频绝对路径: ").strip().strip('"').strip("'")
        if raw and os.path.isfile(raw):
            vp = raw; break
        print("  ❌ 路径无效")

    try:
        frames, fps, w, h = read_video(vp)
    except Exception as e:
        print(f"\n  ❌ {e}"); input("\n按任意键退出..."); sys.exit(1)
    if not frames:
        print("\n  ❌ 无帧"); input("\n按任意键退出..."); sys.exit(1)

    print("  🔄 逐帧转换...")
    ad = []
    for i, fr in enumerate(frames):
        ad.append(process_frame_solid_fill(fr) if is_solid else process_frame_multicolor(fr))
        if (i + 1) % 10 == 0 or i + 1 == len(frames):
            vn = sum(1 for d in ad if d)
            print(f"     {i + 1}/{len(frames)}  有效: {vn}")

    vt = sum(1 for d in ad if d)
    print(f"  ✅ {vt}/{len(frames)} 有效帧")
    if vt == 0:
        print("  ❌ 无有效数据，请调小 MIN_CONTOUR_AREA"); input("\n按任意键退出..."); sys.exit(1)

    print("  📝 生成 BAS 代码...")
    code = build_bas_script(ad, w, h, fps, is_solid)

    stem = Path(vp).stem
    out = Path(vp).parent / f"{stem}_bas弹幕.txt"
    n = 1
    while out.exists():
        out = Path(vp).parent / f"{stem}_bas弹幕_{n}.txt"; n += 1
    out.write_text(code, encoding='utf-8')

    size_kb = os.path.getsize(out) / 1024
    lc = code.count('\n') + 1
    print(f"\n╔{'═'*58}╗")
    print(f"║  ✅ 转换完成                                         ║")
    print(f"║  {out}")
    print(f"╠{'═'*58}╣")
    print(f"║  文件大小: {size_kb:>10.1f} KB                               ║")
    print(f"║  代码行数: {lc:>10}                                   ║")
    print(f"╚{'═'*58}╝")
    print("\n  💡 B站投稿 → 弹幕池 → BAS弹幕 → 代码模式 → 粘贴 → 发送")
    input("\n按任意键退出...")


if __name__ == "__main__":
    main()
>>>>>>> b0b4fa8af00ced9ce3f3f7b7c2e2124f415d1cd5
