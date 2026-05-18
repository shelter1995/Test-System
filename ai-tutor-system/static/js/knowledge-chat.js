/**
 * 知识库问答模块
 * 目标用户：业务人员（先选库、多轮问答、展示来源依据）
 */
(function () {
    const state = {
        databases: [],
        activeDatabase: '',
        messages: [],
        latestSources: [],
        pending: false,
        turns: [],
        maxTurns: 4,
        mounted: false,
    };

    function esc(text) {
        if (typeof escapeHtml === 'function') {
            return escapeHtml(text || '');
        }
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    function getContainer() {
        return document.getElementById('knowledgeChatApp');
    }

    function normalizeDatabases(data) {
        const list = Array.isArray(data) ? data : (data && data.databases) || [];
        return list
            .map(function (db) {
                if (typeof db === 'string') {
                    return { id: db, name: db };
                }
                return {
                    id: String(db.id || '').trim(),
                    name: String(db.name || db.id || '').trim(),
                };
            })
            .filter(function (db) { return db.id; });
    }

    async function loadDatabases() {
        const data = await WorkbenchAPI.requestJson(
            WorkbenchAPI.BASE_URLS.RAG_API + '/db/list'
        );
        state.databases = normalizeDatabases(data);
        if (!state.activeDatabase || !state.databases.some(function (db) { return db.id === state.activeDatabase; })) {
            state.activeDatabase = state.databases.length ? state.databases[0].id : '';
        }
    }

    function renderShell() {
        const container = getContainer();
        if (!container) return;

        container.classList.remove('section-placeholder');
        container.innerHTML = '' +
            '<div class="kbchat-page">' +
                '<div class="kbchat-card kbchat-main">' +
                    '<div class="kbchat-toolbar">' +
                        '<span class="kbchat-toolbar-title">知识库问答</span>' +
                        '<select id="kbChatDbSelect" class="form-control kbchat-db-select"></select>' +
                        '<button id="kbChatNewSessionBtn" class="kbchat-btn" type="button">新会话</button>' +
                    '</div>' +
                    '<div id="kbChatMessages" class="kbchat-messages"></div>' +
                    '<div class="kbchat-input-wrap">' +
                        '<textarea id="kbChatInput" class="kbchat-input" rows="3" placeholder="请输入资料查询问题，例如：商务视频彩铃的办理流程是什么？"></textarea>' +
                        '<div class="kbchat-input-row">' +
                            '<span class="kbchat-hint">Enter 发送 · Shift+Enter 换行</span>' +
                            '<button id="kbChatSendBtn" class="kbchat-send" type="button">发送</button>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                '<aside class="kbchat-card kbchat-sources">' +
                    '<div class="kbchat-sources-header">' +
                        '<div class="kbchat-sources-title">来源依据</div>' +
                        '<div class="kbchat-sources-subtitle" id="kbChatSourceCount">0 条</div>' +
                    '</div>' +
                    '<div id="kbChatSources" class="kbchat-sources-list"></div>' +
                '</aside>' +
            '</div>';

        bindEvents();
    }

    function renderDatabaseOptions() {
        const select = document.getElementById('kbChatDbSelect');
        if (!select) return;
        if (!state.databases.length) {
            select.innerHTML = '<option value="">暂无可用知识库</option>';
            select.value = '';
            return;
        }
        select.innerHTML = state.databases
            .map(function (db) {
                return '<option value="' + esc(db.id) + '">' + esc(db.name) + '</option>';
            })
            .join('');
        select.value = state.activeDatabase;
    }

    function renderMessages() {
        const box = document.getElementById('kbChatMessages');
        if (!box) return;

        if (!state.messages.length) {
            box.innerHTML = '' +
                '<div class="kbchat-empty">' +
                    '<div class="placeholder-icon">💬</div>' +
                    '<p>请选择知识库并开始提问</p>' +
                '</div>';
            return;
        }

        box.innerHTML = state.messages.map(function (msg) {
            const klass = 'kbchat-msg ' + msg.role;
            const sourceMeta = msg.role === 'assistant' && Array.isArray(msg.sources) && msg.sources.length
                ? '<div class="kbchat-msg-meta">来源 ' + msg.sources.length + ' 条</div>'
                : '';
            return '<div class="' + klass + '">' + esc(msg.text) + sourceMeta + '</div>';
        }).join('');
        box.scrollTop = box.scrollHeight;
    }

    function renderSources() {
        const box = document.getElementById('kbChatSources');
        const countEl = document.getElementById('kbChatSourceCount');
        if (!box || !countEl) return;

        const list = Array.isArray(state.latestSources) ? state.latestSources : [];
        countEl.textContent = list.length + ' 条';

        if (!list.length) {
            box.innerHTML = '<div class="kbchat-sources-empty">回答后会在这里显示来源文件和片段</div>';
            return;
        }

        box.innerHTML = list.map(function (item) {
            return '' +
                '<div class="kbchat-source-item">' +
                    '<div class="kbchat-source-file">' + esc(item.fileName || '知识库资料') + '</div>' +
                    '<div class="kbchat-source-snippet">' + esc(item.snippet || '已命中该来源，未返回可展示片段。') + '</div>' +
                '</div>';
        }).join('');
    }

    function setPending(pending) {
        state.pending = pending;
        const sendBtn = document.getElementById('kbChatSendBtn');
        const input = document.getElementById('kbChatInput');
        const newSessionBtn = document.getElementById('kbChatNewSessionBtn');
        if (sendBtn) {
            sendBtn.disabled = pending || !state.activeDatabase;
            sendBtn.textContent = pending ? '查询中...' : '发送';
        }
        if (input) input.disabled = pending || !state.activeDatabase;
        if (newSessionBtn) newSessionBtn.disabled = pending;
    }

    function addMessage(role, text, sources) {
        state.messages.push({
            role: role,
            text: String(text || '').trim() || '（空）',
            sources: Array.isArray(sources) ? sources : [],
        });
    }

    function resetSession(withSystemMessage) {
        state.messages = [];
        state.latestSources = [];
        state.turns = [];
        if (withSystemMessage) {
            addMessage('system', withSystemMessage);
        }
        renderMessages();
        renderSources();
    }

    async function askQuestion() {
        if (state.pending) return;
        if (!state.activeDatabase) {
            addMessage('system', '请先选择一个知识库。');
            renderMessages();
            return;
        }

        const input = document.getElementById('kbChatInput');
        if (!input) return;
        const question = String(input.value || '').trim();
        if (!question) return;
        input.value = '';

        addMessage('user', question);
        renderMessages();
        setPending(true);

        const payload = {
            database: state.activeDatabase,
            query: question,
            n_results: 5,
            history: state.turns.slice(-state.maxTurns),
        };

        try {
            const data = await WorkbenchAPI.postJson(
                WorkbenchAPI.BASE_URLS.RAG_API + '/kb/chat',
                payload
            );
            const answer = String((data && data.answer) || '').trim();
            const sources = Array.isArray(data && data.sources)
                ? data.sources.map(function (item) {
                    return {
                        fileName: String((item && item.file_name) || '').trim() || '知识库资料',
                        snippet: String((item && item.snippet) || '').trim() || '已命中该来源，未返回可展示片段。',
                    };
                })
                : [];

            var fallback = String((data && data.fallback) || '').trim();
            var note = fallback
                ? '\n\n（提示：本次使用本地文本兜底检索，答案可信度取决于召回片段，请核对来源。）'
                : '';
            addMessage('assistant', (answer || '当前知识库未找到相关资料。') + note, sources);
            state.latestSources = sources;

            state.turns.push({
                q: question,
                a: answer || '当前知识库未找到相关资料。',
            });
            if (state.turns.length > state.maxTurns) {
                state.turns = state.turns.slice(-state.maxTurns);
            }
        } catch (err) {
            addMessage('system', '查询失败，请稍后重试或联系管理员检查知识库服务。');
            state.latestSources = [];
            console.error('知识库问答请求失败:', err);
        } finally {
            renderMessages();
            renderSources();
            setPending(false);
            if (input) input.focus();
        }
    }

    function bindEvents() {
        const select = document.getElementById('kbChatDbSelect');
        const sendBtn = document.getElementById('kbChatSendBtn');
        const input = document.getElementById('kbChatInput');
        const newSessionBtn = document.getElementById('kbChatNewSessionBtn');

        if (select) {
            select.addEventListener('change', function () {
                state.activeDatabase = String(select.value || '').trim();
                resetSession('已切换知识库：' + (state.activeDatabase || '未选择'));
                setPending(false);
            });
        }

        if (sendBtn) {
            sendBtn.addEventListener('click', askQuestion);
        }

        if (newSessionBtn) {
            newSessionBtn.addEventListener('click', function () {
                resetSession('新会话已开始。');
                const inputEl = document.getElementById('kbChatInput');
                if (inputEl) inputEl.focus();
            });
        }

        if (input) {
            input.addEventListener('keydown', function (event) {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    askQuestion();
                }
            });
        }
    }

    function refreshRender() {
        renderDatabaseOptions();
        renderMessages();
        renderSources();
        setPending(state.pending);
    }

    async function mountOrRefresh() {
        const container = getContainer();
        if (!container) return;

        if (!state.mounted) {
            renderShell();
            state.mounted = true;
        }

        try {
            await loadDatabases();
            refreshRender();
        } catch (err) {
            console.error('加载知识库列表失败:', err);
            state.databases = [];
            state.activeDatabase = '';
            refreshRender();
            addMessage('system', '无法加载知识库列表，请检查 RAG 服务是否启动。');
            renderMessages();
        }
    }

    function observePageActivation() {
        const section = document.querySelector('.page-section[data-page="knowledge-chat"]');
        if (!section) return;

        const observer = new MutationObserver(function () {
            if (section.classList.contains('active')) {
                mountOrRefresh();
            }
        });
        observer.observe(section, { attributes: true, attributeFilter: ['class'] });
    }

    document.addEventListener('DOMContentLoaded', function () {
        observePageActivation();
        const section = document.querySelector('.page-section[data-page="knowledge-chat"]');
        if (section && section.classList.contains('active')) {
            mountOrRefresh();
        }
    });
})();
