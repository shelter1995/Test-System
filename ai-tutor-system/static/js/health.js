/**
 * 工作台服务健康检查
 * 在顶栏渲染 RAG / 陪练 服务状态徽章
 */
(function () {
    var urls = WorkbenchAPI.BASE_URLS;
    var TIMEOUT = 5000;

    /**
     * 更新状态徽章
     */
    function setBadge(el, online, label) {
        if (!el) return;
        if (online) {
            el.className = 'status-badge online';
            el.textContent = label + ': 在线';
        } else {
            el.className = 'status-badge offline';
            el.textContent = label + ': 离线';
        }
    }

    /**
     * 检查 RAG 服务
     */
    async function checkRAG() {
        try {
            var ctrl = new AbortController();
            var tid = setTimeout(function () { ctrl.abort(); }, TIMEOUT);
            var resp = await fetch(urls.RAG_API + '/health', { signal: ctrl.signal });
            clearTimeout(tid);
            return resp.ok;
        } catch (_) {
            return false;
        }
    }

    /**
     * 检查陪练服务
     */
    async function checkTutor() {
        try {
            var ctrl = new AbortController();
            var tid = setTimeout(function () { ctrl.abort(); }, TIMEOUT);
            var resp = await fetch(urls.TUTOR_API + '/api/status', { signal: ctrl.signal });
            clearTimeout(tid);
            return resp.ok;
        } catch (_) {
            return false;
        }
    }

    /**
     * 执行一轮检查
     */
    async function poll() {
        var ragEl = document.getElementById('ragStatus');
        var tutorEl = document.getElementById('tutorStatus');

        var results = await Promise.all([checkRAG(), checkTutor()]);
        setBadge(ragEl, results[0], 'RAG');
        setBadge(tutorEl, results[1], '陪练');
    }

    // 首次检查 + 每 15 秒轮询
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { poll(); });
    } else {
        poll();
    }
    setInterval(poll, 15000);
})();
