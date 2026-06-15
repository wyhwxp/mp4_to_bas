// ==UserScript==
// @name         B站 BAS弹幕批量导入发送
// @namespace    https://www.bilibili.com
// @version      2.0
// @description  按B站BAS弹幕真实流程：新建标签页→粘贴到ACE编辑器→设置时间→发送
// @author       You
// @match        https://www.bilibili.com/video/*
// @icon         https://www.bilibili.com/favicon.ico
// @grant        none
// @run-at       document-end
// ==/UserScript==

(function () {
    'use strict';

    var fileList = [], sendIndex = 0, isSending = false, interval = 5000, timer = null;
    var activeTimeout = null;  // 当前等待定时器

    // ═══════ React/Angular 值设置 ═══════
    function setNativeValue(el, value) {
        var desc = Object.getOwnPropertyDescriptor(
            Object.getPrototypeOf(el), 'value'
        );
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

    // ═══════ 精确选择器（基于用户提供的DOM） ═══════
    var SEL = {
        newTabBtn:   'span.adv-danmaku-btn-span.bas-danmaku-new-tab-btn',
        editor:      'div.bas-danmaku-editor.ace_editor.ace-crimson-editor',
        aceTextarea: 'div.bas-danmaku-editor.ace_editor textarea, div.bas-danmaku-editor.ace_editor .ace_text-input',
        sendBtn:     'span.adv-danmaku-btn-span.adv-danmaku-send-btn',
        timeInput:   'div.adv-danmaku-start-time input.bui-input-input',
        currentTime: 'span.adv-danmaku-checkbox-span.adv-danmaku-send-time.adv-danmaku-current-time',
    };

    // ═══════ 核心操作 ═══════
    function findNewTabBtn() { return document.querySelector(SEL.newTabBtn); }
    function findEditorDiv() { return document.querySelector(SEL.editor); }
    function findAceTextarea() { return document.querySelector(SEL.aceTextarea); }
    function findSendBtn() { return document.querySelector(SEL.sendBtn); }
    function findTimeInput() { return document.querySelector(SEL.timeInput); }
    function debugScan() {
        addLog('--- 扫描 ---', '');
        var items = [
            ['新建标签页', findNewTabBtn()],
            ['ACE编辑器(div)', findEditorDiv()],
            ['ACE textarea', findAceTextarea()],
            ['发送弹幕', findSendBtn()],
            ['时间输入框', findTimeInput()],
            ['当前时间', document.querySelector(SEL.currentTime)],
        ];
        for (var i = 0; i < items.length; i++) {
            var el = items[i][1];
            var visible = el && isVisible(el);
            addLog('  ' + items[i][0] + ': ' + (el ? (visible ? '可见' : '隐藏') : '未找到'),
                el && visible ? 'ok' : 'e');
        }
        addLog('--- 结束 ---', '');
    }

    // ═══════ 完整发送流程 ═══════
    function executeSend(content, timeMs, fileName) {
        // Step 1: 点击"新建标签页"
        var newTabBtn = findNewTabBtn();
        if (!newTabBtn || !isVisible(newTabBtn)) {
            addLog('  ❌ 未找到"新建标签页"按钮', 'e');
            scheduleNext();
            return;
        }
        newTabBtn.click();
        addLog('  ① 已点击"新建标签页"', '');

        // Step 2: 等待新标签页出现，点击 data-index 最大的标签页
        waitFor(function () {
            var tabs = document.querySelectorAll('ul.bas-danmaku-editor-tab li');
            if (!tabs || tabs.length === 0) return null;
            var lastTab = tabs[tabs.length - 1];
            return (lastTab && isVisible(lastTab)) ? lastTab : null;
        }, 50, 100, function (newTab) {
            if (newTab) {
                newTab.click();
                addLog('  ② 已切换到最新标签页 (data-index=' + (newTab.getAttribute('data-index') || '?') + ')', '');
            } else {
                addLog('  ⚠ 未找到标签页，直接粘贴', 'w');
            }

            // Step 3: 等待ACE编辑器出现，然后粘贴
            setTimeout(function () {
                var ta = findAceTextarea();
                if (!ta) {
                    addLog('  ❌ ACE编辑器未找到', 'e');
                    scheduleNext();
                    return;
                }
                setNativeValue(ta, content);
                addLog('  ③ 已粘贴 ' + fileName + ' (' + content.length + '字符)', 'ok');
            }, 300);

            // Step 4: 先取消"当前时间"勾选，再写入毫秒数
            setTimeout(function () {
                // 直接操作 checkbox input，确保框架感知状态变化
                var cbInput = document.querySelector(SEL.currentTime + ' input[type=checkbox]');
                if (cbInput) {
                    if (cbInput.checked) {
                        // 先取消勾选
                        cbInput.checked = false;
                        cbInput.dispatchEvent(new Event('change', { bubbles: true }));
                        cbInput.dispatchEvent(new Event('input', { bubbles: true }));
                        addLog('  ④ 已取消"当前时间"勾选', '');
                    }
                }
                var timeInput = findTimeInput();
                if (timeInput) {
                    setNativeValue(timeInput, String(timeMs));
                    addLog('  ⑤ 已写入时间: ' + timeMs + 'ms', 'ok');
                }

                // Step 5: 点击"发送弹幕"
                setTimeout(function () {
                    var sendBtn = findSendBtn();
                    if (sendBtn && isVisible(sendBtn)) {
                        sendBtn.click();
                        addLog('  ⑥ 已点击"发送弹幕" ✅', 'ok');
                    } else {
                        addLog('  ❌ 未找到"发送弹幕"按钮', 'e');
                    }
                    scheduleNext();
                }, 400);
            }, 400);
        });
    }

    // ═══════ 轮询等待 ═══════
    function waitFor(findFn, maxTries, delay, callback) {
        var tries = 0;
        function check() {
            var el = findFn();
            if (el) { callback(el); return; }
            tries++;
            if (tries >= maxTries) { callback(null); return; }
            activeTimeout = setTimeout(check, delay);
        }
        check();
    }

    function scheduleNext() {
        if (activeTimeout) { clearTimeout(activeTimeout); activeTimeout = null; }
        timer = setTimeout(processNext, interval);
    }

    // ═══════ UI ═══════
    function createPanel() {
        var d = document.createElement('div');
        d.id = 'bas-batch-panel';
        d.innerHTML =
            '<style>' +
            '#bas-batch-panel{position:fixed;top:10px;left:10px;z-index:99999;' +
            'background:#1a1a2e;color:#eee;border-radius:10px;padding:14px;' +
            'width:280px;font-family:"Microsoft YaHei",sans-serif;font-size:12px;' +
            'box-shadow:0 4px 20px rgba(0,0,0,.5);border:1px solid #333;}' +
            '#bas-batch-panel h3{margin:0 0 8px;font-size:13px;color:#00a1d6;text-align:center;}' +
            '#bas-batch-panel .row{margin-bottom:6px;}' +
            '#bas-batch-panel label{display:block;margin-bottom:2px;color:#aaa;font-size:10px;}' +
            '#bas-batch-panel input[type=number]{width:100%;box-sizing:border-box;' +
            'padding:4px 6px;background:#2a2a3e;border:1px solid #444;color:#eee;' +
            'border-radius:4px;font-size:12px;}' +
            '#bas-batch-panel .btn{width:100%;padding:6px;border:none;border-radius:4px;' +
            'cursor:pointer;font-size:12px;margin-bottom:4px;transition:.2s;color:#fff;}' +
            '#bas-batch-panel .btn-s{background:#5c7cfa;}' +
            '#bas-batch-panel .btn-g{background:#2f9e44;}' +
            '#bas-batch-panel .btn-r{background:#e03131;}' +
            '#bas-batch-panel .btn-y{background:#f08d49;}' +
            '#bas-batch-panel .btn:hover{opacity:.85;}' +
            '#bas-batch-panel .btn:disabled{opacity:.4;cursor:not-allowed;}' +
            '#bas-batch-panel .info{color:#7af;font-size:10px;min-height:24px;word-break:break-all;}' +
            '#bas-batch-panel .log{max-height:140px;overflow-y:auto;background:#111;' +
            'padding:5px;border-radius:4px;font-size:10px;color:#aaa;font-family:Consolas,monospace;}' +
            '#bas-batch-panel .log .ok{color:#2f9e44;}#bas-batch-panel .log .e{color:#e03131;}' +
            '#bas-batch-panel .log .w{color:#f08d49;}' +
            '#bas-batch-panel .btns-row{display:flex;gap:5px;}#bas-batch-panel .btns-row .btn{flex:1;}' +
            '</style>' +
            '<h3>BAS批量发送 v2</h3>' +
            '<input type="file" id="bas-finput" webkitdirectory multiple style="display:none" accept=".txt">' +
            '<div class="row"><button class="btn btn-s" id="bas-btn-sel">选择文件夹</button></div>' +
            '<div class="row"><button class="btn btn-y" id="bas-btn-scan">扫描页面</button></div>' +
            '<div class="row">' +
            '<label>每弹幕间隔(ms)</label>' +
            '<input type="number" id="bas-interval" value="10000" min="3000" step="500">' +
            '</div>' +
            '<div class="row">' +
            '<label>起始时间(ms)</label>' +
            '<input type="number" id="bas-start-ms" value="0" min="0" step="100">' +
            '</div>' +
            '<div class="btns-row">' +
            '<button class="btn btn-g" id="bas-btn-start" disabled>▶ 开始</button>' +
            '<button class="btn btn-r" id="bas-btn-stop" disabled>⏹ 停止</button>' +
            '</div>' +
            '<div class="info" id="bas-status">就绪 | 请先打开BAS弹幕面板</div>' +
            '<div class="log" id="bas-log"></div>';
        document.body.appendChild(d);

        document.getElementById('bas-btn-sel').onclick = function () { document.getElementById('bas-finput').click(); };
        document.getElementById('bas-btn-scan').onclick = debugScan;
        document.getElementById('bas-finput').onchange = handleFiles;
        document.getElementById('bas-btn-start').onclick = startSend;
        document.getElementById('bas-btn-stop').onclick = stopSend;
        document.getElementById('bas-interval').onchange = function () {
            interval = Math.max(3000, parseInt(this.value) || 10000);
            this.value = interval;
        };
    }

    // ═══════ 文件 ═══════
    function handleFiles(e) {
        var files = Array.from(e.target.files)
            .filter(function (f) { return f.name.toLowerCase().endsWith('.txt'); })
            .sort(function (a, b) {
                return a.name.localeCompare(b.name, undefined, { numeric: true });
            });
        fileList = files;
        if (!files.length) { setStatus('未找到txt文件'); return; }
        setStatus('已选 ' + files.length + ' 个文件');
        document.getElementById('bas-log').innerHTML = '';
        files.forEach(function (f, i) { addLog((i + 1) + '. ' + f.name, ''); });
        document.getElementById('bas-btn-start').disabled = false;
    }

    // ═══════ 发送调度 ═══════
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
        var timeMs = startMs;  // 所有弹幕同一时间

        setStatus('[' + (sendIndex + 1) + '/' + fileList.length + '] ' + file.name + ' @' + timeMs + 'ms');
        sendIndex++;

        var reader = new FileReader();
        reader.onload = function (ev) {
            executeSend(ev.target.result, timeMs, file.name);
        };
        reader.readAsText(file);
    }

    function done() {
        isSending = false;
        if (timer) { clearTimeout(timer); timer = null; }
        document.getElementById('bas-btn-start').disabled = false;
        document.getElementById('bas-btn-stop').disabled = true;
        setStatus('完成! 共 ' + fileList.length + ' 个');
        addLog('全部完成!', 'ok');
    }

    function setStatus(msg) {
        var el = document.getElementById('bas-status');
        if (el) el.textContent = msg;
    }

    function addLog(msg, cls) {
        var log = document.getElementById('bas-log');
        if (!log) return;
        var d = document.createElement('div');
        d.className = cls || '';
        d.textContent = '[' + new Date().toLocaleTimeString('zh-CN', {hour12:false}) + '] ' + msg;
        log.appendChild(d);
        log.scrollTop = log.scrollHeight;
    }

    // ═══════ 启动 ═══════
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createPanel);
    } else {
        createPanel();
    }
})();
