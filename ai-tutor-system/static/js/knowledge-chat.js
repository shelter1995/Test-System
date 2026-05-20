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
        latestFallback: '',
        pending: false,
        turns: [],
        maxTurns: 4,
        mounted: false,
        dropdownOpen: false,
    };

    function esc(text) {
        if (typeof escapeHtml === 'function') {
            return escapeHtml(text || '');
        }
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    function renderInlineMarkdown(text) {
        return esc(text)
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>');
    }

    function renderMarkdown(text) {
        const lines = String(text || '').replace(/\r/g, '').split('\n');
        const html = [];
        let inList = false;
        let inCode = false;
        let codeLines = [];

        function closeList() {
            if (inList) {
                html.push('</ul>');
                inList = false;
            }
        }

        lines.forEach(function (line) {
            if (/^\s*```/.test(line)) {
                if (inCode) {
                    html.push('<pre><code>' + esc(codeLines.join('\n')) + '</code></pre>');
                    codeLines = [];
                    inCode = false;
                } else {
                    closeList();
                    inCode = true;
                }
                return;
            }
            if (inCode) {
                codeLines.push(line);
                return;
            }

            const trimmed = line.trim();
            if (!trimmed) {
                closeList();
                return;
            }
            const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
            if (heading) {
                closeList();
                const level = Math.min(heading[1].length + 2, 6);
                html.push('<h' + level + '>' + renderInlineMarkdown(heading[2]) + '</h' + level + '>');
                return;
            }
            const bullet = trimmed.match(/^[-*]\s+(.+)$/);
            if (bullet) {
                if (!inList) {
                    html.push('<ul>');
                    inList = true;
                }
                html.push('<li>' + renderInlineMarkdown(bullet[1]) + '</li>');
                return;
            }
            closeList();
            html.push('<p>' + renderInlineMarkdown(trimmed) + '</p>');
        });

        if (inCode) {
            html.push('<pre><code>' + esc(codeLines.join('\n')) + '</code></pre>');
        }
        closeList();
        return html.join('');
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
                        '<div id="kbChatDbPicker" class="kbchat-db-picker">' +
                            '<button id="kbChatDbButton" class="kbchat-db-button" type="button" aria-haspopup="listbox" aria-expanded="false">' +
                                '<span id="kbChatDbButtonText">选择知识库</span>' +
                                '<span class="kbchat-db-caret">⌄</span>' +
                            '</button>' +
                            '<div id="kbChatDbMenu" class="kbchat-db-menu" role="listbox"></div>' +
                        '</div>' +
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

    function getActiveDatabaseName() {
        const active = state.databases.find(function (db) { return db.id === state.activeDatabase; });
        return active ? active.name : '';
    }

    function setDropdownOpen(open) {
        state.dropdownOpen = Boolean(open);
        const picker = document.getElementById('kbChatDbPicker');
        const button = document.getElementById('kbChatDbButton');
        if (picker) picker.classList.toggle('open', state.dropdownOpen);
        if (button) button.setAttribute('aria-expanded', state.dropdownOpen ? 'true' : 'false');
    }

    function renderDatabaseOptions() {
        const button = document.getElementById('kbChatDbButton');
        const buttonText = document.getElementById('kbChatDbButtonText');
        const menu = document.getElementById('kbChatDbMenu');
        if (!button || !buttonText || !menu) return;
        if (!state.databases.length) {
            buttonText.textContent = '暂无可用知识库';
            button.disabled = true;
            menu.innerHTML = '';
            setDropdownOpen(false);
            return;
        }
        button.disabled = false;
        buttonText.textContent = getActiveDatabaseName() || '选择知识库';
        menu.innerHTML = state.databases
            .map(function (db) {
                const selected = db.id === state.activeDatabase;
                return '<button class="kbchat-db-option ' + (selected ? 'active' : '') + '" type="button" role="option" aria-selected="' + (selected ? 'true' : 'false') + '" data-db-id="' + esc(db.id) + '">' + esc(db.name) + '</button>';
            })
            .join('');
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
            const fallbackHint = msg.role === 'assistant' && msg.fallback
                ? '<div class="kbchat-msg-warning">提示：本次使用本地文本兜底检索，答案可信度取决于召回片段，请核对右侧来源。</div>'
                : '';
            const body = msg.role === 'assistant'
                ? '<div class="kbchat-answer-label">回答</div>' +
                  '<div class="kbchat-markdown">' + renderMarkdown(msg.text) + '</div>' +
                  fallbackHint
                : esc(msg.text);
            return '<div class="' + klass + '">' + body + sourceMeta + '</div>';
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

        var fallbackWarning = '';
        if (state.latestFallback) {
            fallbackWarning = '<div class="kbchat-sources-fallback">本次使用本地文本兜底检索，请核对来源</div>';
        }

        box.innerHTML = fallbackWarning + list.map(function (item, index) {
            var scoreText = item.score ? (Math.round(item.score * 100) / 100).toFixed(2) : '';
            var scoreHtml = scoreText
                ? '<span class="kbchat-source-score">相关度 ' + esc(scoreText) + '</span>'
                : '';
            var engineLabel = item.engine
                ? '<span class="kbchat-source-engine">' + esc(item.engine) + '</span>'
                : '';
            var metaHtml = (scoreHtml || engineLabel)
                ? '<div class="kbchat-source-meta">' + engineLabel + scoreHtml + '</div>'
                : '';
            return '' +
                '<div class="kbchat-source-item">' +
                    '<div class="kbchat-source-file"><span class="kbchat-source-number">来源 ' + (index + 1) + '</span>' + esc(item.fileName || '知识库资料') + '</div>' +
                    '<div class="kbchat-source-snippet">' + esc(item.snippet || '已命中该来源，未返回可展示片段。') + '</div>' +
                    metaHtml +
                '</div>';
        }).join('');
    }

    function setPending(pending) {
        state.pending = pending;
        const sendBtn = document.getElementById('kbChatSendBtn');
        const input = document.getElementById('kbChatInput');
        const newSessionBtn = document.getElementById('kbChatNewSessionBtn');
        const dbButton = document.getElementById('kbChatDbButton');
        if (sendBtn) {
            sendBtn.disabled = pending || !state.activeDatabase;
            sendBtn.textContent = pending ? '查询中...' : '发送';
        }
        if (input) input.disabled = pending || !state.activeDatabase;
        if (newSessionBtn) newSessionBtn.disabled = pending;
        if (dbButton) dbButton.disabled = pending || !state.databases.length;
        if (pending) setDropdownOpen(false);
    }

    function addMessage(role, text, sources, meta) {
        state.messages.push({
            role: role,
            text: String(text || '').trim() || '（空）',
            sources: Array.isArray(sources) ? sources : [],
            fallback: Boolean(meta && meta.fallback),
        });
    }

    function resetSession(withSystemMessage) {
        state.messages = [];
        state.latestSources = [];
        state.latestFallback = '';
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
                        score: typeof item.score === 'number' ? item.score : 0,
                        engine: String((item && item.engine) || '').trim(),
                    };
                })
                : [];

            var fallback = String((data && data.fallback) || '').trim();
            var sourcesFallback = String((data && data.sources_fallback) || '').trim();
            var effectiveFallback = fallback || sourcesFallback;
            addMessage('assistant', answer || '当前知识库未找到相关资料。', sources, { fallback: Boolean(effectiveFallback) });
            state.latestSources = sources;
            state.latestFallback = effectiveFallback;

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
            state.latestFallback = '';
            console.error('知识库问答请求失败:', err);
        } finally {
            renderMessages();
            renderSources();
            setPending(false);
            if (input) input.focus();
        }
    }

    function bindEvents() {
        const dbButton = document.getElementById('kbChatDbButton');
        const dbMenu = document.getElementById('kbChatDbMenu');
        const dbPicker = document.getElementById('kbChatDbPicker');
        const sendBtn = document.getElementById('kbChatSendBtn');
        const input = document.getElementById('kbChatInput');
        const newSessionBtn = document.getElementById('kbChatNewSessionBtn');

        if (dbButton) {
            dbButton.addEventListener('click', function () {
                if (!state.databases.length || state.pending) return;
                setDropdownOpen(!state.dropdownOpen);
            });
        }

        if (dbMenu) {
            dbMenu.addEventListener('click', function (event) {
                const option = event.target.closest('.kbchat-db-option');
                if (!option) return;
                const nextDb = String(option.dataset.dbId || '').trim();
                if (!nextDb) return;
                state.activeDatabase = nextDb;
                setDropdownOpen(false);
                renderDatabaseOptions();
                resetSession('已切换知识库：' + (getActiveDatabaseName() || state.activeDatabase || '未选择'));
                setPending(false);
            });
        }

        document.addEventListener('click', function (event) {
            if (!state.dropdownOpen || !dbPicker) return;
            if (!dbPicker.contains(event.target)) {
                setDropdownOpen(false);
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && state.dropdownOpen) {
                setDropdownOpen(false);
            }
        });

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

        if (!state.mounted || !document.getElementById('kbChatMessages')) {
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
