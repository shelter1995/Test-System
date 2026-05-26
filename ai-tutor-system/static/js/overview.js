/**
 * 统一工作台总览启动页
 * 聚合服务状态、知识库、生成产物和陪练记录，提供常用动作入口。
 */
(function () {
    const urls = WorkbenchAPI.BASE_URLS;
    const REQUEST_TIMEOUT = 5000;
    const MAX_RECENT_ITEMS = 4;
    let refreshTimer = null;
    let lastRefreshAt = 0;

    function html(value) {
        if (typeof escapeHtml === 'function') return escapeHtml(String(value ?? ''));
        const div = document.createElement('div');
        div.textContent = String(value ?? '');
        return div.innerHTML;
    }

    function withTimeout(url, options) {
        const ctrl = new AbortController();
        const tid = setTimeout(function () { ctrl.abort(); }, REQUEST_TIMEOUT);
        return fetch(url, Object.assign({}, options || {}, { signal: ctrl.signal }))
            .finally(function () { clearTimeout(tid); });
    }

    async function requestJson(url) {
        const resp = await withTimeout(url);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return resp.json();
    }

    function formatDate(value, withTime) {
        if (!value) return '';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: withTime ? '2-digit' : undefined,
            minute: withTime ? '2-digit' : undefined,
            hour12: false,
        });
    }

    function formatFileSize(bytes) {
        const n = Number(bytes || 0);
        if (!Number.isFinite(n) || n <= 0) return '-';
        if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
        return (n / 1024).toFixed(1) + ' KB';
    }

    function setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function isOverviewActive() {
        const section = document.querySelector('.page-section[data-page="overview"]');
        return !!(section && section.classList.contains('active'));
    }

    async function loadServiceStatus() {
        const statusEl = document.getElementById('overviewServiceStatus');
        if (!statusEl) return;

        const checks = await Promise.allSettled([
            withTimeout(urls.RAG_API + '/health'),
            withTimeout(urls.TUTOR_API + '/api/status'),
        ]);

        const ragOnline = checks[0].status === 'fulfilled' && checks[0].value.ok;
        const tutorOnline = checks[1].status === 'fulfilled' && checks[1].value.ok;
        let tutorMeta = '陪练、报告和内容生成';
        if (tutorOnline) {
            try {
                const data = await checks[1].value.clone().json();
                tutorMeta = data.ai_model ? 'MiniMax · ' + data.ai_model : '陪练服务已就绪';
            } catch (_) {
                tutorMeta = '陪练服务已就绪';
            }
        }

        statusEl.innerHTML = [
            renderServiceRow('RAG 知识库', ragOnline, ragOnline ? '检索、问答和文档导入可用' : '请先启动 8003 服务'),
            renderServiceRow('陪练系统', tutorOnline, tutorOnline ? tutorMeta : '请先启动 8002 服务'),
        ].join('');
    }

    function renderServiceRow(label, online, meta) {
        return (
            '<div class="overview-service-row">' +
                '<span class="overview-dot ' + (online ? 'online' : 'offline') + '"></span>' +
                '<div><strong>' + html(label) + '</strong><span>' + html(meta) + '</span></div>' +
                '<em>' + (online ? '在线' : '离线') + '</em>' +
            '</div>'
        );
    }

    function normalizeDocuments(data) {
        return Array.isArray(data) ? data : (data.documents || []);
    }

    function documentBucket(doc) {
        const status = String((doc && doc.status) || '').toLowerCase();
        const stage = String((doc && doc.stage) || '').toLowerCase();
        if (status === 'error' || status === 'partial_success' || stage === 'interrupted') return 'error';
        if (status === 'processing' || stage === 'queued' || stage === 'indexing' || stage === 'rag_ingest') return 'processing';
        return 'ready';
    }

    async function loadKnowledgeStats() {
        const listEl = document.getElementById('overviewKnowledgeStats');
        if (!listEl) return;

        try {
            const data = await requestJson(urls.RAG_API + '/db/list');
            const databases = Array.isArray(data) ? data : (data.databases || []);
            const activeDb = (typeof knowledgeState !== 'undefined' && knowledgeState.activeDatabase)
                ? knowledgeState.activeDatabase
                : (databases[0] && (databases[0].id || databases[0]));

            const detailResults = await Promise.allSettled(databases.map(function (db) {
                const id = typeof db === 'string' ? db : db.id;
                return requestJson(urls.RAG_API + '/db/' + encodeURIComponent(id) + '/documents')
                    .then(function (docData) {
                        return { id: id, documents: normalizeDocuments(docData) };
                    });
            }));

            const docsByDb = {};
            detailResults.forEach(function (result) {
                if (result.status === 'fulfilled') docsByDb[result.value.id] = result.value.documents;
            });

            let totalFiles = 0;
            let readyFiles = 0;
            let processingFiles = 0;
            let errorFiles = 0;

            const rows = databases.map(function (db) {
                const id = typeof db === 'string' ? db : db.id;
                const name = typeof db === 'string' ? db : (db.name || db.id);
                const docs = docsByDb[id] || [];
                const fallbackCount = Number((db && db.documents_count) || 0);
                const fileCount = docs.length || fallbackCount;
                const buckets = docs.reduce(function (acc, doc) {
                    acc[documentBucket(doc)] += 1;
                    return acc;
                }, { ready: 0, processing: 0, error: 0 });
                if (!docs.length && fallbackCount > 0) buckets.ready = fallbackCount;

                totalFiles += fileCount;
                readyFiles += buckets.ready;
                processingFiles += buckets.processing;
                errorFiles += buckets.error;

                return {
                    id: id,
                    name: name,
                    engine: typeof db === 'string' ? '' : (db.engine || ''),
                    fileCount: fileCount,
                    ready: buckets.ready,
                    processing: buckets.processing,
                    error: buckets.error,
                    active: id === activeDb,
                };
            });

            setText('knowledgeCount', String(databases.length));
            setText('fileCount', String(totalFiles));
            setText('overviewIndexedCount', readyFiles + ' 已就绪 · ' + processingFiles + ' 处理中' + (errorFiles ? ' · ' + errorFiles + ' 异常' : ''));
            setText('overviewActiveDb', activeDb ? '当前: ' + activeDb : '未选择知识库');

            if (!rows.length) {
                listEl.innerHTML = '<div class="overview-empty">暂无知识库。先创建知识库并上传资料。</div>';
                return;
            }

            listEl.innerHTML = rows.slice(0, 6).map(renderDbRow).join('') +
                (rows.length > 6 ? '<div class="overview-more">还有 ' + (rows.length - 6) + ' 个知识库，可进入知识库页查看。</div>' : '');
        } catch (err) {
            setText('knowledgeCount', '0');
            setText('fileCount', '0');
            setText('overviewIndexedCount', '统计失败');
            const listEl = document.getElementById('overviewKnowledgeStats');
            if (listEl) listEl.innerHTML = '<div class="overview-empty error">知识库统计加载失败：' + html(err.message) + '</div>';
        }
    }

    function renderDbRow(row) {
        const statusText = row.error
            ? row.error + ' 异常'
            : (row.processing ? row.processing + ' 处理中' : row.ready + ' 已就绪');
        const statusClass = row.error ? 'error' : (row.processing ? 'pending' : 'ready');
        return (
            '<button class="overview-db-row" data-overview-db="' + html(row.id) + '">' +
                '<div class="overview-db-main">' +
                    '<strong>' + html(row.name) + '</strong>' +
                    '<span>' + html(row.id) + (row.engine ? ' · ' + html(row.engine) : '') + '</span>' +
                '</div>' +
                '<div class="overview-db-meta">' +
                    '<span>' + row.fileCount + ' 文件</span>' +
                    '<em class="' + statusClass + '">' + html(statusText) + '</em>' +
                '</div>' +
                (row.active ? '<span class="overview-db-active">当前</span>' : '') +
            '</button>'
        );
    }

    async function loadArtifacts() {
        const listEl = document.getElementById('overviewArtifacts');
        if (!listEl) return;

        try {
            const data = await requestJson(urls.TUTOR_API + '/generation/artifacts');
            const artifacts = (data.artifacts || []).slice(0, MAX_RECENT_ITEMS);
            if (!artifacts.length) {
                listEl.innerHTML = '<div class="overview-empty">暂无生成产物。</div>';
                return;
            }
            listEl.innerHTML = artifacts.map(function (item) {
                const downloadUrl = urls.TUTOR_API + '/generation/artifacts/download?path=' + encodeURIComponent(item.path || '');
                return (
                    '<div class="overview-list-row">' +
                        '<div class="overview-list-main">' +
                            '<strong title="' + html(item.path || '') + '">' + html(item.name || '未命名文件') + '</strong>' +
                            '<span>' + html(formatDate(item.modified, true)) + ' · ' + html(formatFileSize(item.size)) + '</span>' +
                        '</div>' +
                        '<a class="overview-mini-btn" href="' + downloadUrl + '" target="_blank" rel="noopener">下载</a>' +
                    '</div>'
                );
            }).join('');
        } catch (err) {
            listEl.innerHTML = '<div class="overview-empty error">最近产物加载失败：' + html(err.message) + '</div>';
        }
    }

    async function loadTutorHistory() {
        const listEl = document.getElementById('overviewTutorHistory');
        if (!listEl) return;

        try {
            const data = await requestJson(urls.TUTOR_API + '/history');
            const history = data.history || [];
            setText('overviewSessionCount', String(history.length));
            setText('overviewLastSession', history[0] ? formatDate(history[0].created_at, false) : '暂无记录');

            if (!history.length) {
                listEl.innerHTML = '<div class="overview-empty">暂无陪练记录。</div>';
                return;
            }

            listEl.innerHTML = history.slice(0, MAX_RECENT_ITEMS).map(function (item) {
                const score = item.score == null ? '未评分' : item.score + '分';
                const statusClass = item.status === 'completed' ? 'ready' : 'pending';
                return (
                    '<button class="overview-list-row overview-history-row" data-session-id="' + html(item.session_id) + '">' +
                        '<div class="overview-list-main">' +
                            '<strong>' + html(item.scenario || '未命名场景') + '</strong>' +
                            '<span>' + html(item.client_unit || '-') + ' · ' + html(item.product || '-') + ' · ' + (item.rounds || 0) + '轮</span>' +
                        '</div>' +
                        '<div class="overview-list-side">' +
                            '<em class="' + statusClass + '">' + (item.status === 'completed' ? '已完成' : '进行中') + '</em>' +
                            '<strong>' + html(score) + '</strong>' +
                        '</div>' +
                    '</button>'
                );
            }).join('');
        } catch (err) {
            setText('overviewSessionCount', '0');
            setText('overviewLastSession', '加载失败');
            listEl.innerHTML = '<div class="overview-empty error">陪练记录加载失败：' + html(err.message) + '</div>';
        }
    }

    async function refresh(force) {
        const now = Date.now();
        if (!force && now - lastRefreshAt < 10000) return;
        lastRefreshAt = now;
        await Promise.allSettled([
            loadServiceStatus(),
            loadKnowledgeStats(),
            loadArtifacts(),
            loadTutorHistory(),
        ]);
        bindDynamicRows();
    }

    function navigate(pageId) {
        if (typeof showWorkbenchPage === 'function') showWorkbenchPage(pageId);
    }

    function handleAction(action) {
        if (action === 'knowledge') {
            navigate('knowledge');
        } else if (action === 'knowledge-chat') {
            navigate('knowledge-chat');
        } else if (action === 'generation') {
            navigate('generation');
        } else if (action === 'tutor') {
            navigate('tutor');
            setTimeout(function () {
                const product = document.getElementById('productName');
                if (product) product.focus();
            }, 80);
        } else if (action === 'upload') {
            navigate('knowledge');
            setTimeout(function () {
                const input = document.getElementById('uploadFileInput');
                if (input) {
                    input.classList.add('overview-focus-ring');
                    input.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    setTimeout(function () { input.classList.remove('overview-focus-ring'); }, 1800);
                }
            }, 200);
        } else if (action === 'history') {
            navigate('tutor');
            setTimeout(function () {
                if (typeof openHistoryPanel === 'function') openHistoryPanel();
            }, 80);
        }
    }

    function bindStaticActions() {
        document.querySelectorAll('[data-overview-action]').forEach(function (btn) {
            if (btn.dataset.overviewBound === 'true') return;
            btn.dataset.overviewBound = 'true';
            btn.addEventListener('click', function () {
                handleAction(btn.getAttribute('data-overview-action'));
            });
        });
    }

    function bindDynamicRows() {
        document.querySelectorAll('[data-overview-db]').forEach(function (row) {
            if (row.dataset.overviewBound === 'true') return;
            row.dataset.overviewBound = 'true';
            row.addEventListener('click', function () {
                const dbId = row.getAttribute('data-overview-db');
                if (typeof selectDatabase === 'function' && dbId) selectDatabase(dbId);
                navigate('knowledge');
            });
        });

        document.querySelectorAll('.overview-history-row[data-session-id]').forEach(function (row) {
            if (row.dataset.overviewBound === 'true') return;
            row.dataset.overviewBound = 'true';
            row.addEventListener('click', function () {
                navigate('tutor');
                setTimeout(function () {
                    if (typeof openHistoryPanel === 'function') openHistoryPanel();
                }, 80);
            });
        });
    }

    function init() {
        bindStaticActions();
        refresh(true);

        document.querySelectorAll('.page-section').forEach(function (section) {
            new MutationObserver(function () {
                if (isOverviewActive()) refresh(false);
            }).observe(section, { attributes: true, attributeFilter: ['class'] });
        });

        refreshTimer = setInterval(function () {
            if (isOverviewActive()) refresh(false);
        }, 30000);
    }

    window.OverviewDashboard = {
        refresh: function () { return refresh(true); },
        stop: function () {
            if (refreshTimer) clearInterval(refreshTimer);
            refreshTimer = null;
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
