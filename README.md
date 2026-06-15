# mp4\_to\_bas

mp4 转 bilibili BAS 弹幕

将 mp4 视频逐帧转换为 B站 BAS 弹幕代码，在视频弹幕池中以 SVG 路径动画的形式"重播"视频画面。

## 工作流程

```
mp4 视频
  → video_to_bas.py（逐帧提取轮廓，生成 BAS 代码）
    → xxx_bas弹幕.txt（单个大文件，约 1~10 MB）
      → split_bas.py（按 ~300KB 切割）
        → xxx_bas弹幕_split/part_001.txt ~ part_00N.txt
          → 油猴脚本（浏览器内逐个发送到 BAS 弹幕面板）
```

## 文件说明

| 文件                       | 用途                                       |
| ------------------------ | ---------------------------------------- |
| `video_to_bas.py`        | 主程序：读取 mp4 → 逐帧颜色量化 → 生成 BAS 代码          |
| `split_bas.py`           | 切割工具：将大 txt 按 \~300KB 切分，保持 def path 块完整 |
| `bas_batch_send.user.js` | 油猴脚本：在 B站播放页自动批量发送切割后的 txt               |
| `install_deps.bat`       | 一键安装 opencv-python 和 numpy               |
| `requirements.txt`       | pip 依赖声明                                 |

## 快速开始

### 1. 安装依赖

双击 `install_deps.bat`，或手动执行：

```bash
pip install opencv-python>=4.5.0 numpy>=1.20.0
```

### 2. 生成 BAS 代码

```bash
python video_to_bas.py
```

输入 mp4 文件的绝对路径，等待处理完成。输出文件在同目录下，名为 `视频文件名_bas弹幕.txt`。

配置项（修改 `video_to_bas.py` 顶部的 `Config` 类）：

| 参数                     | 默认值 | 说明               |
| ---------------------- | --- | ---------------- |
| `MAX_COLORS_PER_FRAME` | 24  | 每帧保留的颜色数，越大色彩越丰富 |
| `RESIZE_WIDTH`         | 0   | 缩放宽度，0=保持原分辨率    |
| `BAS_SCALE`            | 0   | 渲染缩放，0=自动居中计算    |

### 3. 切割大文件

B站 BAS 弹幕编辑器对单次粘贴的代码量有限制（实测约 300KB 以内可发送）。

```bash
python split_bas.py
```

输入 txt 路径，输出到同目录下的 `文件名_split/` 文件夹。

### 4. 发送到 B站

1. 安装 [Tampermonkey](https://www.tampermonkey.net/) 浏览器扩展
2. 新建脚本，粘贴 `bas_batch_send.user.js` 全部内容，保存
3. 打开你的视频页面，点击弹幕池 → **BAS弹幕** → 切换到面板
4. 点击油猴脚本面板的 **"扫描页面"** 确认能找到编辑器
5. **"选择文件夹"** → 选 `_split` 文件夹 → 设间隔 → **"开始"**

脚本会自动执行：新建标签页 → 切换到最新标签 → 粘贴代码 → 取消当前时间 → 写入时间 → 点击发送。

## 关于 BAS 弹幕接口

B站官方客服曾表示 BAS 弹幕发送功能已移除，但实测在 B站播放器的 BAS 弹幕面板中仍可正常发送(<300kb)和显示。

<br />

## 油猴脚本代码

以下为 `bas_batch_send.user.js` 的完整内容，也可直接安装项目目录下的同名文件：

```javascript
// ==UserScript==
// @name         B站 BAS弹幕批量导入发送
// @namespace    https://www.bilibili.com
// @version      2.0
// @description  按B站BAS弹幕真实流程：新建标签页→粘贴到ACE编辑器→设置时间→发送
// @author       爱整活的干饭人
// @match        https://www.bilibili.com/video/*
// @icon         https://www.bilibili.com/favicon.ico
// @grant        none
// @run-at       document-end
// ==/UserScript==

(function () {
    'use strict';

    var fileList = [], sendIndex = 0, isSending = false, interval = 5000, timer = null;
    var activeTimeout = null;

    function setNativeValue(el, value) {
        var desc = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
        if (desc && desc.set) { desc.set.call(el, value); }
        else { el.value = value; }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
        el.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true }));
    }

    function isVisible(el) {
        if (!el || !el.offsetParent) return false;
        var s = getComputedStyle(el);
        return s.display !== 'none' && s.visibility !== 'hidden';
    }

    var SEL = {
        newTabBtn:   'span.adv-danmaku-btn-span.bas-danmaku-new-tab-btn',
        aceTextarea: 'div.bas-danmaku-editor.ace_editor textarea, div.bas-danmaku-editor.ace_editor .ace_text-input',
        sendBtn:     'span.adv-danmaku-btn-span.adv-danmaku-send-btn',
        timeInput:   'div.adv-danmaku-start-time input.bui-input-input',
        currentTime: 'span.adv-danmaku-checkbox-span.adv-danmaku-send-time.adv-danmaku-current-time',
    };

    function findNewTabBtn() { return document.querySelector(SEL.newTabBtn); }
    function findAceTextarea() { return document.querySelector(SEL.aceTextarea); }
    function findSendBtn() { return document.querySelector(SEL.sendBtn); }
    function findTimeInput() { return document.querySelector(SEL.timeInput); }

    function debugScan() {
        addLog('--- 扫描 ---', '');
        var items = [
            ['新建标签页', findNewTabBtn()],
            ['ACE textarea', findAceTextarea()],
            ['发送弹幕', findSendBtn()],
            ['时间输入框', findTimeInput()],
            ['当前时间', document.querySelector(SEL.currentTime)],
        ];
        for (var i = 0; i < items.length; i++) {
            var el = items[i][1];
            var visible = el && isVisible(el);
            addLog('  ' + items[i][0] + ': ' + (el ? (visible ? '可见' : '隐藏') : '未找到'), el && visible ? 'ok' : 'e');
        }
        addLog('--- 结束 ---', '');
    }

    function executeSend(content, timeMs, fileName) {
        var newTabBtn = findNewTabBtn();
        if (!newTabBtn || !isVisible(newTabBtn)) {
            addLog('  ✗ 未找到"新建标签页"按钮', 'e');
            scheduleNext(); return;
        }
        newTabBtn.click();
        addLog('  ① 已点击"新建标签页"', '');

        waitFor(function () {
            var tabs = document.querySelectorAll('ul.bas-danmaku-editor-tab li');
            if (!tabs || tabs.length === 0) return null;
            var lastTab = tabs[tabs.length - 1];
            return (lastTab && isVisible(lastTab)) ? lastTab : null;
        }, 50, 100, function (newTab) {
            if (newTab) {
                newTab.click();
                addLog('  ② 已切换到最新标签页 (data-index=' + (newTab.getAttribute('data-index') || '?') + ')', '');
            } else { addLog('  ⚠ 未找到标签页，直接粘贴', 'w'); }

            setTimeout(function () {
                var ta = findAceTextarea();
                if (!ta) { addLog('  ✗ ACE编辑器未找到', 'e'); scheduleNext(); return; }
                setNativeValue(ta, content);
                addLog('  ③ 已粘贴 ' + fileName + ' (' + content.length + '字符)', 'ok');
            }, 300);

            setTimeout(function () {
                var cbInput = document.querySelector(SEL.currentTime + ' input[type=checkbox]');
                if (cbInput && cbInput.checked) {
                    cbInput.checked = false;
                    cbInput.dispatchEvent(new Event('change', { bubbles: true }));
                    cbInput.dispatchEvent(new Event('input', { bubbles: true }));
                    addLog('  ④ 已取消"当前时间"勾选', '');
                }
                var timeInput = findTimeInput();
                if (timeInput) { setNativeValue(timeInput, String(timeMs)); addLog('  ⑤ 已写入时间: ' + timeMs + 'ms', 'ok'); }
                setTimeout(function () {
                    var sendBtn = findSendBtn();
                    if (sendBtn && isVisible(sendBtn)) { sendBtn.click(); addLog('  ⑥ 已点击"发送弹幕" ✓', 'ok'); }
                    else { addLog('  ✗ 未找到"发送弹幕"按钮', 'e'); }
                    scheduleNext();
                }, 400);
            }, 400);
        });
    }

    function waitFor(findFn, maxTries, delay, callback) {
        var tries = 0;
        function check() { var el = findFn(); if (el) { callback(el); return; } tries++; if (tries >= maxTries) { callback(null); return; } activeTimeout = setTimeout(check, delay); }
        check();
    }

    function scheduleNext() { if (activeTimeout) { clearTimeout(activeTimeout); activeTimeout = null; } timer = setTimeout(processNext, interval); }

    function createPanel() {
        var d = document.createElement('div'); d.id = 'bas-batch-panel';
        d.innerHTML = '<style>' +
            '#bas-batch-panel{position:fixed;top:10px;left:10px;z-index:99999;background:#1a1a2e;color:#eee;border-radius:10px;padding:14px;width:280px;font-family:"Microsoft YaHei",sans-serif;font-size:12px;box-shadow:0 4px 20px rgba(0,0,0,.5);border:1px solid #333;}' +
            '#bas-batch-panel h3{margin:0 0 8px;font-size:13px;color:#00a1d6;text-align:center;}' +
            '#bas-batch-panel .row{margin-bottom:6px;}' +
            '#bas-batch-panel label{display:block;margin-bottom:2px;color:#aaa;font-size:10px;}' +
            '#bas-batch-panel input[type=number]{width:100%;box-sizing:border-box;padding:4px 6px;background:#2a2a3e;border:1px solid #444;color:#eee;border-radius:4px;font-size:12px;}' +
            '#bas-batch-panel .btn{width:100%;padding:6px;border:none;border-radius:4px;cursor:pointer;font-size:12px;margin-bottom:4px;transition:.2s;color:#fff;}' +
            '#bas-batch-panel .btn-s{background:#5c7cfa;}#bas-batch-panel .btn-g{background:#2f9e44;}#bas-batch-panel .btn-r{background:#e03131;}#bas-batch-panel .btn-y{background:#f08d49;}' +
            '#bas-batch-panel .btn:hover{opacity:.85;}#bas-batch-panel .btn:disabled{opacity:.4;cursor:not-allowed;}' +
            '#bas-batch-panel .info{color:#7af;font-size:10px;min-height:24px;word-break:break-all;}' +
            '#bas-batch-panel .log{max-height:140px;overflow-y:auto;background:#111;padding:5px;border-radius:4px;font-size:10px;color:#aaa;font-family:Consolas,monospace;}' +
            '#bas-batch-panel .log .ok{color:#2f9e44;}#bas-batch-panel .log .e{color:#e03131;}#bas-batch-panel .log .w{color:#f08d49;}' +
            '#bas-batch-panel .btns-row{display:flex;gap:5px;}#bas-batch-panel .btns-row .btn{flex:1;}' +
            '</style><h3>BAS批量发送 v2</h3>' +
            '<input type="file" id="bas-finput" webkitdirectory multiple style="display:none" accept=".txt">' +
            '<div class="row"><button class="btn btn-s" id="bas-btn-sel">选择文件夹</button></div>' +
            '<div class="row"><button class="btn btn-y" id="bas-btn-scan">扫描页面</button></div>' +
            '<div class="row"><label>每弹幕间隔(ms)</label><input type="number" id="bas-interval" value="10000" min="3000" step="500"></div>' +
            '<div class="row"><label>起始时间(ms)</label><input type="number" id="bas-start-ms" value="0" min="0" step="100"></div>' +
            '<div class="btns-row"><button class="btn btn-g" id="bas-btn-start" disabled>▶ 开始</button><button class="btn btn-r" id="bas-btn-stop" disabled>⏹ 停止</button></div>' +
            '<div class="info" id="bas-status">就绪 | 请先打开BAS弹幕面板</div><div class="log" id="bas-log"></div>';
        document.body.appendChild(d);
        document.getElementById('bas-btn-sel').onclick = function () { document.getElementById('bas-finput').click(); };
        document.getElementById('bas-btn-scan').onclick = debugScan;
        document.getElementById('bas-finput').onchange = handleFiles;
        document.getElementById('bas-btn-start').onclick = startSend;
        document.getElementById('bas-btn-stop').onclick = stopSend;
        document.getElementById('bas-interval').onchange = function () { interval = Math.max(3000, parseInt(this.value) || 10000); this.value = interval; };
    }

    function handleFiles(e) {
        var files = Array.from(e.target.files).filter(function (f) { return f.name.toLowerCase().endsWith('.txt'); })
            .sort(function (a, b) { return a.name.localeCompare(b.name, undefined, { numeric: true }); });
        fileList = files;
        if (!files.length) { setStatus('未找到txt文件'); return; }
        setStatus('已选 ' + files.length + ' 个文件');
        document.getElementById('bas-log').innerHTML = '';
        files.forEach(function (f, i) { addLog((i + 1) + '. ' + f.name, ''); });
        document.getElementById('bas-btn-start').disabled = false;
    }

    function startSend() {
        if (!fileList.length) return;
        interval = Math.max(3000, parseInt(document.getElementById('bas-interval').value) || 10000);
        sendIndex = 0; isSending = true;
        document.getElementById('bas-btn-start').disabled = true;
        document.getElementById('bas-btn-stop').disabled = false;
        addLog('开始批量发送...', 'ok');
        processNext();
    }

    function stopSend() {
        isSending = false;
        if (timer) { clearTimeout(timer); timer = null; }
        if (activeTimeout) { clearTimeout(activeTimeout); activeTimeout = null; }
        document.getElementById('bas-btn-start').disabled = false;
        document.getElementById('bas-btn-stop').disabled = true;
        setStatus('已停止 (' + sendIndex + '/' + fileList.length + ')');
        addLog('手动停止', 'e');
    }

    function processNext() {
        if (!isSending || sendIndex >= fileList.length) { done(); return; }
        var file = fileList[sendIndex];
        var startMs = parseInt(document.getElementById('bas-start-ms').value) || 0;
        setStatus('[' + (sendIndex + 1) + '/' + fileList.length + '] ' + file.name + ' @' + startMs + 'ms');
        sendIndex++;
        var reader = new FileReader();
        reader.onload = function (ev) { executeSend(ev.target.result, startMs, file.name); };
        reader.readAsText(file);
    }

    function done() {
        isSending = false; if (timer) { clearTimeout(timer); timer = null; }
        document.getElementById('bas-btn-start').disabled = false;
        document.getElementById('bas-btn-stop').disabled = true;
        setStatus('完成! 共 ' + fileList.length + ' 个');
        addLog('全部完成!', 'ok');
    }

    function setStatus(msg) { var el = document.getElementById('bas-status'); if (el) el.textContent = msg; }
    function addLog(msg, cls) {
        var log = document.getElementById('bas-log'); if (!log) return;
        var d = document.createElement('div'); d.className = cls || '';
        d.textContent = '[' + new Date().toLocaleTimeString('zh-CN', {hour12:false}) + '] ' + msg;
        log.appendChild(d); log.scrollTop = log.scrollHeight;
    }

    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', createPanel); }
    else { createPanel(); }
})();
```

## 注意事项

- 生成 10 帧/s 的 BAS 代码，处理大视频耗时较长（每 10 帧反馈进度）
- BAS 弹幕仅 Web 端播放器可渲染，移动端无法观看
- 代码全程由 AI（DeepSeek）辅助完成，人工调试修改
- B站连续发送约70条弹幕后会进行限制

## 免责声明

1. 本项目仅供学习交流使用，严禁用于任何违法违规用途。
2. 使用者需自行遵守 B站用户协议及社区规范，因使用本项目产生的任何后果（包括但不限于账号受限、弹幕被删除、视频下架等）由使用者自行承担。
3. 输入的视频内容版权归原作者所有，请勿使用本项目传播侵权，违法内容。

