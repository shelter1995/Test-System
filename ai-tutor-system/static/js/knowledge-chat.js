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

    function normalizeText(text) {
        if (text === undefined || text === null) return '';
        const normalized = String(text).trim();
        if (!normalized || normalized.toLowerCase() === 'undefined' || normalized.toLowerCase() === 'null') {
            return '';
        }
        return normalized;
    }

    function sourceRefNumber(item, index) {
        const raw = item && item.sourceId;
        if (typeof raw === 'number' && Number.isFinite(raw)) {
            return String(raw);
        }
        const text = String(raw || '').trim();
        const match = text.match(/^(?:来源\s*)?(.+)$/);
        return match && match[1] ? match[1].trim() : String(index + 1);
    }

    function sourceRefLabel(item, index, compact) {
        const number = sourceRefNumber(item, index);
        return compact ? '来源' + number : '来源 ' + number;
    }

    function renderSourceRefs(html) {
        return String(html || '').replace(/(<code>.*?<\/code>)|([\[［]来源\s*(\d+)[\]］])/g, function (match, code, sourceRef, number) {
            if (code) return code;
            return '<span class="kbchat-source-ref" title="来源 ' + esc(number) + '">' + sourceRef + '</span>';
        });
    }

    function renderInlineMarkdown(text) {
        const html = esc(text)
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>');
        return renderSourceRefs(html);
    }

    function renderAnswerSources(sources) {
        const list = Array.isArray(sources) ? sources : [];
        if (!list.length) return '';
        const rows = list.map(function (item, index) {
            const label = sourceRefLabel(item, index, true);
            const fileName = normalizeText(item && item.fileName) || '知识库资料';
            return '<li>' + esc(label) + '：' + esc(fileName) + '</li>';
        }).join('');
        return '' +
            '<div class="kbchat-answer-sources" aria-label="回答来源">' +
                '<div class="kbchat-answer-sources-title">来源</div>' +
                '<ul>' + rows + '</ul>' +
            '</div>';
    }

    function renderAssistantBody(msg) {
        const fallbackHint = msg && msg.fallback
            ? '<div class="kbchat-msg-warning">提示：本次使用本地文本兜底检索，答案可信度取决于召回片段，请核对右侧来源。</div>'
            : '';
        const sourcesHtml = msg && msg.complete !== false
            ? renderAnswerSources(msg.sources)
            : '';
        return '<div class="kbchat-answer-label">回答</div>' +
            '<div class="kbchat-markdown">' + renderMarkdown(msg && msg.text) + '</div>' +
            fallbackHint +
            sourcesHtml;
    }

    function splitMarkdownTableRow(line) {
        return String(line || '')
            .trim()
            .replace(/^\|/, '')
            .replace(/\|$/, '')
            .split('|')
            .map(function (cell) { return cell.trim(); });
    }

    function isMarkdownTableDelimiter(line) {
        const cells = splitMarkdownTableRow(line);
        return cells.length > 1 && cells.every(function (cell) {
            return /^:?-{3,}:?$/.test(cell);
        });
    }

    function isMarkdownTableRow(line) {
        const trimmed = String(line || '').trim();
        return trimmed.indexOf('|') !== -1 && /^\|?.+\|.+\|?$/.test(trimmed);
    }

    function renderTable(headerLine, delimiterLine, bodyLines) {
        const headers = splitMarkdownTableRow(headerLine);
        const alignments = splitMarkdownTableRow(delimiterLine).map(function (cell) {
            if (/^:-{3,}:$/.test(cell)) return 'center';
            if (/^-{3,}:$/.test(cell)) return 'right';
            return '';
        });
        const headHtml = headers.map(function (cell, index) {
            const align = alignments[index] ? ' style="text-align:' + alignments[index] + '"' : '';
            return '<th' + align + '>' + renderInlineMarkdown(cell) + '</th>';
        }).join('');
        const bodyHtml = bodyLines.map(function (line) {
            const cells = splitMarkdownTableRow(line);
            const rowHtml = headers.map(function (_, index) {
                const align = alignments[index] ? ' style="text-align:' + alignments[index] + '"' : '';
                return '<td' + align + '>' + renderInlineMarkdown(cells[index] || '') + '</td>';
            }).join('');
            return '<tr>' + rowHtml + '</tr>';
        }).join('');
        return '<table><thead><tr>' + headHtml + '</tr></thead><tbody>' + bodyHtml + '</tbody></table>';
    }

    function renderMarkdown(text) {
        const lines = String(text || '').replace(/\r/g, '').split('\n');
        const html = [];
        let inList = false;
        let inOrderedList = false;
        let inCode = false;
        let codeLines = [];

        function closeList() {
            if (inList) {
                html.push('</ul>');
                inList = false;
            }
            if (inOrderedList) {
                html.push('</ol>');
                inOrderedList = false;
            }
        }

        for (let i = 0; i < lines.length; i += 1) {
            const line = lines[i];
            if (/^\s*```/.test(line)) {
                if (inCode) {
                    html.push('<pre><code>' + esc(codeLines.join('\n')) + '</code></pre>');
                    codeLines = [];
                    inCode = false;
                } else {
                    closeList();
                    inCode = true;
                }
                continue;
            }
            if (inCode) {
                codeLines.push(line);
                continue;
            }

            const trimmed = line.trim();
            if (!trimmed) {
                closeList();
                continue;
            }
            if (
                i + 1 < lines.length &&
                isMarkdownTableRow(trimmed) &&
                isMarkdownTableDelimiter(lines[i + 1])
            ) {
                closeList();
                const bodyLines = [];
                i += 2;
                while (i < lines.length && isMarkdownTableRow(lines[i].trim())) {
                    bodyLines.push(lines[i]);
                    i += 1;
                }
                i -= 1;
                html.push(renderTable(trimmed, lines[i - bodyLines.length], bodyLines));
                continue;
            }
            const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
            if (heading) {
                closeList();
                const level = Math.min(heading[1].length + 2, 6);
                html.push('<h' + level + '>' + renderInlineMarkdown(heading[2]) + '</h' + level + '>');
                continue;
            }
            const bullet = trimmed.match(/^[-*]\s+(.+)$/);
            if (bullet) {
                if (inOrderedList) {
                    html.push('</ol>');
                    inOrderedList = false;
                }
                if (!inList) {
                    html.push('<ul>');
                    inList = true;
                }
                html.push('<li>' + renderInlineMarkdown(bullet[1]) + '</li>');
                continue;
            }
            const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
            if (ordered) {
                if (inList) {
                    html.push('</ul>');
                    inList = false;
                }
                if (!inOrderedList) {
                    html.push('<ol>');
                    inOrderedList = true;
                }
                html.push('<li>' + renderInlineMarkdown(ordered[1]) + '</li>');
                continue;
            }
            const quote = trimmed.match(/^>\s+(.+)$/);
            if (quote) {
                closeList();
                html.push('<blockquote>' + renderInlineMarkdown(quote[1]) + '</blockquote>');
                continue;
            }
            closeList();
            html.push('<p>' + renderInlineMarkdown(trimmed) + '</p>');
        }

        if (inCode) {
            html.push('<pre><code>' + esc(codeLines.join('\n')) + '</code></pre>');
        }
        closeList();
        return html.join('');
    }

    if (typeof window !== 'undefined') {
        window.KnowledgeChatMarkdown = {
            render: renderMarkdown,
            renderAnswerSources: renderAnswerSources,
            renderAssistantBody: renderAssistantBody,
        };
    }

    function parseSseBlock(block) {
        const lines = String(block || '').split('\n');
        let type = '';
        const dataLines = [];
        lines.forEach(function (line) {
            const clean = line.replace(/\r$/, '');
            if (clean.startsWith('event:')) {
                type = clean.slice(6).trim();
            } else if (clean.startsWith('data:')) {
                dataLines.push(clean.slice(5).trimStart());
            }
        });
        if (!type || !dataLines.length) return null;
        try {
            return {
                type: type,
                payload: JSON.parse(dataLines.join('\n')),
            };
        } catch (err) {
            console.warn('知识库问答流式事件解析失败:', err);
            return null;
        }
    }

    function parseSseChunk(chunk, buffer, onEvent) {
        let nextBuffer = String(buffer || '') + String(chunk || '');
        nextBuffer = nextBuffer.replace(/\r\n/g, '\n');
        while (true) {
            const boundary = nextBuffer.indexOf('\n\n');
            if (boundary === -1) break;
            const block = nextBuffer.slice(0, boundary);
            nextBuffer = nextBuffer.slice(boundary + 2);
            const event = parseSseBlock(block);
            if (event && typeof onEvent === 'function') {
                onEvent(event);
            }
        }
        return nextBuffer;
    }

    function streamTokenText(payload) {
        if (!payload || typeof payload !== 'object') return '';
        const value = payload.delta ?? payload.token ?? payload.content ?? '';
        if (value === undefined || value === null) return '';
        const text = String(value);
        if (text.toLowerCase() === 'undefined' || text.toLowerCase() === 'null') return '';
        return text;
    }

    if (typeof window !== 'undefined') {
        window.KnowledgeChatStream = {
            parseChunk: parseSseChunk,
            tokenText: streamTokenText,
        };
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
                                '<span class="kbchat-db-caret" aria-hidden="true"></span>' +
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
            const body = msg.role === 'assistant'
                ? renderAssistantBody(msg)
                : esc(msg.text);
            return '<div class="' + klass + '">' + body + '</div>';
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
            var rerankScoreText = (typeof item.rerankScore === 'number' && Number.isFinite(item.rerankScore))
                ? (Math.round(item.rerankScore * 100) / 100).toFixed(2)
                : '';
            var rerankScoreHtml = rerankScoreText
                ? '<span class="kbchat-source-score">重排分 ' + esc(rerankScoreText) + '</span>'
                : '';
            var sourceIdLabel = sourceRefLabel(item, index, false);
            var sourceIdHtml = sourceIdLabel
                ? '<span class="kbchat-source-engine">' + esc(sourceIdLabel) + '</span>'
                : '';
            var metaHtml = (sourceIdHtml || scoreHtml || rerankScoreHtml)
                ? '<div class="kbchat-source-meta">' + sourceIdHtml + scoreHtml + rerankScoreHtml + '</div>'
                : '';
            return '' +
                '<div class="kbchat-source-item">' +
                    '<div class="kbchat-source-file"><span class="kbchat-source-number">' + esc(sourceIdLabel) + '</span>' + esc(item.fileName || '知识库资料') + '</div>' +
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
            text: normalizeText(text) || '（空）',
            sources: Array.isArray(sources) ? sources : [],
            fallback: Boolean(meta && meta.fallback),
            complete: !meta || !Object.prototype.hasOwnProperty.call(meta, 'complete')
                ? true
                : Boolean(meta.complete),
        });
    }

    function updateMessage(index, text, sources, meta) {
        if (!state.messages[index]) return;
        state.messages[index].text = normalizeText(text) || '（空）';
        if (Array.isArray(sources)) {
            state.messages[index].sources = sources;
        }
        if (meta && Object.prototype.hasOwnProperty.call(meta, 'fallback')) {
            state.messages[index].fallback = Boolean(meta.fallback);
        }
        if (meta && Object.prototype.hasOwnProperty.call(meta, 'complete')) {
            state.messages[index].complete = Boolean(meta.complete);
        }
    }

    function mapSources(data) {
        return Array.isArray(data && data.sources)
            ? data.sources.map(function (item) {
                return {
                    sourceId: String((item && item.source_id) || '').trim(),
                    fileName: String((item && item.file_name) || '').trim() || '知识库资料',
                    snippet: String((item && item.snippet) || '').trim() || '已命中该来源，未返回可展示片段。',
                    score: typeof item.score === 'number' ? item.score : 0,
                    rerankScore: typeof item.rerank_score === 'number' ? item.rerank_score : null,
                };
            })
            : [];
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

    async function askQuestionFallback(payload) {
        const data = await WorkbenchAPI.postJson(
            WorkbenchAPI.BASE_URLS.RAG_API + '/kb/chat',
            payload
        );
        const answer = normalizeText(data && data.answer);
        const sources = mapSources(data);
        var fallback = normalizeText(data && data.fallback);
        var sourcesFallback = normalizeText(data && data.sources_fallback);
        return {
            answer: answer || '当前知识库未找到相关资料。',
            sources: sources,
            effectiveFallback: fallback || sourcesFallback,
        };
    }

    async function askQuestionStream(payload) {
        const assistantIndex = state.messages.length;
        addMessage('assistant', '正在检索知识库...', [], { fallback: false, complete: false });
        renderMessages();

        const response = await fetch(WorkbenchAPI.BASE_URLS.RAG_API + '/kb/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!response.ok || !response.body) {
            throw new Error('HTTP ' + response.status);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let answer = '';
        let sources = [];
        let effectiveFallback = '';
        let streamError = '';

        function applyEvent(event) {
            const payloadData = event.payload || {};
            if (event.type === 'status') {
                if (!answer) {
                    updateMessage(assistantIndex, payloadData.message || '正在处理...', sources, {
                        fallback: Boolean(effectiveFallback),
                        complete: false,
                    });
                    renderMessages();
                }
                return;
            }
            if (event.type === 'sources') {
                sources = mapSources(payloadData);
                effectiveFallback = normalizeText(payloadData.fallback) || normalizeText(payloadData.sources_fallback);
                state.latestSources = sources;
                state.latestFallback = effectiveFallback;
                updateMessage(assistantIndex, answer || '正在生成回答...', sources, {
                    fallback: Boolean(effectiveFallback),
                    complete: false,
                });
                renderMessages();
                renderSources();
                return;
            }
            if (event.type === 'token') {
                const delta = streamTokenText(payloadData);
                if (!delta) return;
                answer += delta;
                updateMessage(assistantIndex, answer, sources, {
                    fallback: Boolean(effectiveFallback),
                    complete: false,
                });
                renderMessages();
                return;
            }
            if (event.type === 'error') {
                streamError = payloadData.message || '流式回答失败';
                return;
            }
            if (event.type === 'done') {
                const doneAnswer = normalizeText(payloadData.answer);
                if (doneAnswer) answer = doneAnswer;
                sources = mapSources(payloadData);
                effectiveFallback = normalizeText(payloadData.fallback) || normalizeText(payloadData.sources_fallback);
                return;
            }
        }

        while (true) {
            const result = await reader.read();
            if (result.done) break;
            buffer = parseSseChunk(decoder.decode(result.value, { stream: true }), buffer, applyEvent);
        }
        buffer = parseSseChunk(decoder.decode(), buffer, applyEvent);

        if (!answer && streamError) {
            throw new Error(streamError);
        }

        const finalAnswer = answer || '当前知识库未找到相关资料。';
        updateMessage(assistantIndex, finalAnswer, sources, {
            fallback: Boolean(effectiveFallback),
            complete: true,
        });
        state.latestSources = sources;
        state.latestFallback = effectiveFallback;
        renderMessages();
        renderSources();
        return {
            answer: finalAnswer,
            sources: sources,
            effectiveFallback: effectiveFallback,
        };
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
            let result;
            try {
                result = await askQuestionStream(payload);
            } catch (streamErr) {
                console.warn('知识库问答流式请求失败，改用普通请求:', streamErr);
                const last = state.messages[state.messages.length - 1];
                if (last && last.role === 'assistant' && /^正在/.test(last.text || '')) {
                    state.messages.pop();
                }
                result = await askQuestionFallback(payload);
                addMessage('assistant', result.answer, result.sources, { fallback: Boolean(result.effectiveFallback) });
                state.latestSources = result.sources;
                state.latestFallback = result.effectiveFallback;
            }

            state.turns.push({
                q: question,
                a: result.answer || '当前知识库未找到相关资料。',
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
