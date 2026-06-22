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

    function esc(text) {
        if (typeof escapeHtml === 'function') return escapeHtml(text || '');
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    function providerOptions(section, selected) {
        const providers = (state.providers && state.providers.providers) || {};
        const list = Array.isArray(providers[section]) ? providers[section] : [];
        const current = String(selected || '').trim();
        const values = list.indexOf(current) >= 0 || !current ? list : list.concat([current]);
        return values.map(function (item) {
            return '<option value="' + esc(item) + '"' + (item === current ? ' selected' : '') + '>' + esc(item) + '</option>';
        }).join('');
    }

    function modelOptions(section, selected, providerOverride) {
        const providers = (state.providers && state.providers.providers) || {};
        const defaults = providers.defaults || {};
        const models = providers.models || {};
        const config = (state.settings && state.settings[section]) || {};
        const provider = String(providerOverride || config.provider || '').trim();
        const list = Array.isArray(models[section] && models[section][provider])
            ? models[section][provider].slice()
            : [];
        const defaultModel = defaults[section] && defaults[section].model;
        if (defaultModel && list.indexOf(defaultModel) < 0) list.unshift(defaultModel);
        const current = String(selected || '').trim();
        const isCustom = Boolean(current && list.indexOf(current) < 0);
        const values = list;
        return values.map(function (item) {
            return '<option value="' + esc(item) + '"' + (item === current ? ' selected' : '') + '>' + esc(item) + '</option>';
        }).join('') + '<option value="__custom__"' + (isCustom ? ' selected' : '') + '>手动填写...</option>';
    }

    function field(name, label, value, type, extraAttrs) {
        return (
            '<label class="settings-field">' +
                '<span>' + esc(label) + '</span>' +
                '<input name="' + esc(name) + '" type="' + (type || 'text') + '" value="' + esc(value || '') + '" autocomplete="off" ' + (extraAttrs || '') + '>' +
            '</label>'
        );
    }

    function providerField(section, value) {
        return '<label class="settings-field">' +
            '<span>供应商</span>' +
            '<select class="provider-choice" data-section="' + section + '" name="' + section + '.provider">' + providerOptions(section, value) + '</select>' +
            '</label>';
    }

    function modelField(section, value) {
        const providers = (state.providers && state.providers.providers) || {};
        const models = providers.models || {};
        const config = (state.settings && state.settings[section]) || {};
        const provider = String(config.provider || '').trim();
        const list = Array.isArray(models[section] && models[section][provider])
            ? models[section][provider]
            : [];
        const current = String(value || '').trim();
        const isCustom = current && list.indexOf(current) < 0;
        return '<label class="settings-field">' +
            '<span>模型</span>' +
            '<select class="model-choice" data-section="' + section + '">' + modelOptions(section, value) + '</select>' +
            '<input class="model-custom-input" name="' + section + '.model" value="' + esc(current) + '" placeholder="输入自定义模型名称" autocomplete="off" style="' + (isCustom ? '' : 'display:none') + '">' +
            '</label>';
    }

    function renderBlock(id, title, config) {
        var el = document.getElementById(id + '-settings');
        if (!el) return;
        const keyStatus = config.has_api_key ? '<span class="settings-key-state">已配置密钥</span>' : '<span class="settings-key-state muted">未检测到密钥</span>';
        const keyPlaceholder = config.has_api_key ? '已保存，留空继续使用；填写新值会覆盖' : '请输入 API Key';
        el.innerHTML =
            '<h3>' + esc(title) + keyStatus + '</h3>' +
            providerField(id, config.provider) +
            field(id + '.base_url', '接口地址', config.base_url) +
            modelField(id, config.model) +
            field(id + '.api_key', 'API Key', '', 'password', 'placeholder="' + esc(keyPlaceholder) + '"');
    }

    function render() {
        if (!state.settings) return;
        renderBlock('llm', '推理模型', state.settings.llm || {});
        renderBlock('embedding', '嵌入模型', state.settings.embedding || {});
        renderBlock('rerank', '重排模型', state.settings.rerank || {});
        bindProviderSelectors();
        bindModelSelectors();
    }

    function updateModelSelector(section) {
        const providerSelect = document.querySelector('.provider-choice[data-section="' + section + '"]');
        const modelSelect = document.querySelector('.model-choice[data-section="' + section + '"]');
        const input = document.querySelector('input[name="' + section + '.model"]');
        if (!providerSelect || !modelSelect || !input) return;
        modelSelect.innerHTML = modelOptions(section, input.value, providerSelect.value);
        bindModelSelectors();
    }

    function bindProviderSelectors() {
        document.querySelectorAll('.provider-choice').forEach(function (select) {
            const section = select.getAttribute('data-section');
            select.addEventListener('change', function () {
                updateModelSelector(section);
            });
        });
    }

    function bindModelSelectors() {
        document.querySelectorAll('.model-choice').forEach(function (select) {
            const section = select.getAttribute('data-section');
            const input = document.querySelector('input[name="' + section + '.model"]');
            if (!input) return;
            function sync() {
                if (select.value === '__custom__') {
                    input.style.display = '';
                    if (!input.value) input.focus();
                } else {
                    input.value = select.value;
                    input.style.display = 'none';
                }
            }
            select.addEventListener('change', sync);
            sync();
        });
    }

    function collectForm() {
        var form = document.getElementById('model-settings-form');
        var formData = new FormData(form);
        var payload = { llm: {}, embedding: {}, rerank: {} };
        var hasApiKey = false;
        var entries = formData.entries();
        var entry = entries.next();
        while (!entry.done) {
            var key = entry.value[0];
            var value = entry.value[1];
            var parts = key.split('.');
            if (parts.length === 2 && payload[parts[0]]) {
                var text = String(value).trim();
                payload[parts[0]][parts[1]] = text;
                if (parts[1] === 'api_key' && text) {
                    hasApiKey = true;
                }
            }
            entry = entries.next();
        }
        if (hasApiKey) {
            payload.persist_api_key = true;
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
        showStatus('正在保存设置...', 'info');
        try {
            var saved = await requestJson('/settings/models', { method: 'PUT', body: JSON.stringify(collectForm()) });
            state.settings = saved;
            render();
            window.dispatchEvent(new CustomEvent('model-settings:saved', { detail: saved }));
            showStatus('设置已保存。页面配置会写入本地配置文件；环境变量仍作为未填写密钥时的后备来源。', 'success');
        } catch (err) {
            showStatus('保存失败：' + err.message, 'error');
        }
    }

    async function test() {
        const targetEl = document.getElementById('model-test-target');
        const payload = collectForm();
        payload.target = targetEl ? targetEl.value : 'llm';
        showStatus('正在测试 ' + payload.target + ' 连接...', 'info');
        try {
            var result = await requestJson('/settings/models/test', { method: 'POST', body: JSON.stringify(payload) });
            showStatus('连接测试通过：' + (result.message || result.target || 'OK') + '。测试使用当前表单值；如需应用到上传/重试，请点击保存设置。', 'success');
        } catch (err) {
            showStatus('连接测试失败：' + err.message, 'error');
        }
    }

    function showStatus(text, type) {
        var el = document.getElementById('model-settings-status');
        if (!el) return;
        el.className = 'settings-status ' + (type || 'info');
        el.textContent = text;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('model-settings-form');
        var testBtn = document.getElementById('test-model-settings-btn');
        if (form) form.addEventListener('submit', save);
        if (testBtn) testBtn.addEventListener('click', test);
        load().then(function () {
            showStatus('当前页面设置优先用于传统 RAG；未填写 API Key 时使用后端环境变量。', 'info');
        }).catch(function (err) { showStatus(err.message, 'error'); });
    });
})();
