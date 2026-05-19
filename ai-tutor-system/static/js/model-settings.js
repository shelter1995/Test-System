(function () {
    const state = { settings: null, providers: null };

    function apiBase() {
        return window.WorkbenchAPI && WorkbenchAPI.BASE_URLS
            ? WorkbenchAPI.BASE_URLS.RAG_API
            : 'http://localhost:8003';
    }

    async function requestJson(path, options) {
        const resp = await fetch(apiBase() + path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, options || {}));
        const data = await resp.json().catch(function () { return {}; });
        if (!resp.ok) {
            throw new Error(data.detail || data.message || '请求失败');
        }
        return data;
    }

    function field(name, label, value, type) {
        return (
            '<label class="settings-field">' +
                '<span>' + label + '</span>' +
                '<input name="' + name + '" type="' + (type || 'text') + '" value="' + (value || '') + '" autocomplete="off">' +
            '</label>'
        );
    }

    function renderBlock(id, title, config) {
        var el = document.getElementById(id + '-settings');
        if (!el) return;
        el.innerHTML =
            '<h3>' + title + '</h3>' +
            field(id + '.provider', '供应商', config.provider) +
            field(id + '.base_url', '接口地址', config.base_url) +
            field(id + '.model', '模型', config.model) +
            field(id + '.api_key', 'API Key', '', 'password');
    }

    function render() {
        if (!state.settings) return;
        renderBlock('llm', '推理模型', state.settings.llm || {});
        renderBlock('embedding', '嵌入模型', state.settings.embedding || {});
        renderBlock('rerank', '重排模型', state.settings.rerank || {});
    }

    function collectForm() {
        var form = document.getElementById('model-settings-form');
        var formData = new FormData(form);
        var payload = { llm: {}, embedding: {}, rerank: {} };
        var entries = formData.entries();
        var entry = entries.next();
        while (!entry.done) {
            var key = entry.value[0];
            var value = entry.value[1];
            var parts = key.split('.');
            if (parts.length === 2 && payload[parts[0]]) {
                payload[parts[0]][parts[1]] = String(value).trim();
            }
            entry = entries.next();
        }
        return payload;
    }

    async function load() {
        state.settings = await requestJson('/settings/models');
        state.providers = await requestJson('/settings/providers');
        render();
    }

    async function save(evt) {
        evt.preventDefault();
        var saved = await requestJson('/settings/models', { method: 'PUT', body: JSON.stringify(collectForm()) });
        state.settings = saved;
        render();
        showStatus('设置已保存');
    }

    async function test() {
        var result = await requestJson('/settings/models/test', { method: 'POST', body: JSON.stringify(collectForm()) });
        showStatus(result.message || '连接测试通过');
    }

    function showStatus(text) {
        var el = document.getElementById('model-settings-status');
        if (el) el.textContent = text;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('model-settings-form');
        var testBtn = document.getElementById('test-model-settings-btn');
        if (form) form.addEventListener('submit', save);
        if (testBtn) testBtn.addEventListener('click', test);
        load().catch(function (err) { showStatus(err.message); });
    });
})();
