# -*- coding: utf-8 -*-
"""
BAS 弹幕代码切割工具
功能：输入任意 BAS txt 文件路径，智能按 def path 块边界切割，
      每段约 300k 字符，保持 def path 块完整，输出到新建文件夹。
"""
import os, re
from pathlib import Path

# ── 配置 ──
CHUNK_SIZE = 300000          # 每段约 300k 字符

# ── 输入文件路径 ──
while True:
    raw = input("请输入 BAS txt 文件路径: ").strip().strip('"').strip("'")
    if raw and os.path.isfile(raw):
        bas_file = raw
        break
    print("  ❌ 文件不存在，请重新输入。")

# ── 读取 ──
with open(bas_file, "r", encoding="utf-8") as f:
    text = f.read()

print(f"\n原始文件: {len(text)} 字符 ({len(text.encode('utf-8'))/1024:.1f} KB)")

# ── 按 def path 块切割 ──
blocks = re.split(r"(?=def path )", text)
blocks = [b.strip() for b in blocks if b.strip()]
print(f"def path 块总数: {len(blocks)}")

# 检测是否有 set/then set 动画链
has_animation = False
anim_section = ""
anim_match = re.search(r"\n(set |then set )", text)
if anim_match:
    has_animation = True
    parts = re.split(r"\n(?=set |then set )", text, maxsplit=1)
    if len(parts) == 2:
        def_section = parts[0]
        anim_section = parts[1]
        blocks = re.split(r"(?=def path )", def_section)
        blocks = [b.strip() for b in blocks if b.strip()]
        print(f"  检测到动画链 ({len(anim_section)} 字符)")

if has_animation and anim_section:
    # 有动画链 → def 块分组切，动画链放最后一段
    chunk_items = []
    current_chunk = []
    current_size = 0

    for block in blocks:
        sz = len(block) + 1
        if current_size + sz > CHUNK_SIZE and current_chunk:
            chunk_items.append(current_chunk)
            current_chunk = [block]
            current_size = sz
        else:
            current_chunk.append(block)
            current_size += sz

    if current_chunk:
        chunk_items.append(current_chunk)

    out_dir = Path(bas_file).parent / (Path(bas_file).stem + "_split")
    out_dir.mkdir(exist_ok=True)

    for i, chunk in enumerate(chunk_items):
        content = "\n\n".join(chunk)
        if i == len(chunk_items) - 1:
            content += "\n" + anim_section
        out_path = out_dir / f"part_{i+1:03d}.txt"
        out_path.write_text(content, encoding="utf-8")
        size_kb = len(content.encode('utf-8')) / 1024
        print(f"  part_{i+1:03d}.txt  →  {len(content)} 字符 ({size_kb:.1f} KB)  [{len(chunk)} 块]")
else:
    # 纯 def，无动画链
    chunk_items = []
    current_chunk = []
    current_size = 0

    for block in blocks:
        sz = len(block) + 1
        if current_size + sz > CHUNK_SIZE and current_chunk:
            chunk_items.append(current_chunk)
            current_chunk = [block]
            current_size = sz
        else:
            current_chunk.append(block)
            current_size += sz

    if current_chunk:
        chunk_items.append(current_chunk)

    out_dir = Path(bas_file).parent / (Path(bas_file).stem + "_split")
    out_dir.mkdir(exist_ok=True)

    for i, chunk in enumerate(chunk_items):
        content = "\n\n".join(chunk)
        out_path = out_dir / f"part_{i+1:03d}.txt"
        out_path.write_text(content, encoding="utf-8")
        size_kb = len(content.encode('utf-8')) / 1024
        print(f"  part_{i+1:03d}.txt  →  {len(content)} 字符 ({size_kb:.1f} KB)  [{len(chunk)} 块]")

print(f"\n✅ 完成! 输出目录: {out_dir}")
print(f"   共 {len(chunk_items)} 个文件")
input("\n按任意键退出...")
