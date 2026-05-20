/**
 * 知识库管理模块
 * 管理知识库的创建、选择、文件上传和文档列表
 */

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

const knowledgeState = {
    databases: [],
    activeDatabase: '',
    uploadStates: {},      // 按知识库隔离上传日志、SSE 和处理中队列
    retryingDocuments: new Set(),
    documentRefreshTimer: null,
};

function getActiveDatabaseItem() {
    return knowledgeState.databases.find(db => {
        const id = typeof db === 'string' ? db : db.id;
        return id === knowledgeState.activeDatabase;
    }) || null;
}

function formatBeijingTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    });
}

function normalizeUploadMessage(data, dbId) {
    const message = String(data.error || data.message || '');
    if (data.type === 'parsing') {
        if (!message) {
            return '正在解析并索引';
        }
        if (/正在/.test(message) && /(RAG|解析|分块|索引|图谱)/i.test(message)) {
            return '正在解析并索引';
        }
        if (/(RAG|解析|分块|索引|图谱)/i.test(message)) {
            return `正在解析并索引：${message}`;
        }
    }
    return message;
}

function isStaleProcessing(doc) {
    const status = String((doc && doc.status) || '').toLowerCase();
    const updatedAt = (doc && (doc.updated_at || doc.imported_at)) || '';
    const updatedAtMs = updatedAt ? Date.parse(updatedAt) : NaN;
    return status === 'processing'
        && Number.isFinite(updatedAtMs)
        && Date.now() - updatedAtMs > 10 * 60 * 1000;
}

function getUploadState(dbId) {
    const key = String(dbId || knowledgeState.activeDatabase || '').trim();
    if (!key) {
        return { uploadEventSource: null, uploadLogState: null, uploadingFiles: [] };
    }
    if (!knowledgeState.uploadStates[key]) {
        knowledgeState.uploadStates[key] = {
            uploadEventSource: null,
            uploadLogState: null,
            uploadingFiles: [],
        };
    }
    return knowledgeState.uploadStates[key];
}

function canRetryDocument(doc) {
    const status = String((doc && doc.status) || '').toLowerCase();
    const stage = String((doc && doc.stage) || '').toLowerCase();
    return status === 'error' || status === 'partial_success' || stage === 'interrupted' || isStaleProcessing(doc);
}

function clearDocumentRefreshTimer() {
    if (knowledgeState.documentRefreshTimer) {
        clearTimeout(knowledgeState.documentRefreshTimer);
        knowledgeState.documentRefreshTimer = null;
    }
}

function scheduleDocumentRefresh(dbId) {
    clearDocumentRefreshTimer();
    knowledgeState.documentRefreshTimer = setTimeout(() => {
        if (dbId === knowledgeState.activeDatabase) {
            loadKnowledgeDocuments();
        }
    }, 15000);
}

/**
 * 加载知识库列表
 */
async function loadKnowledgeBases() {
    try {
        const data = await WorkbenchAPI.requestJson(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/db/list`
        );
        knowledgeState.databases = Array.isArray(data) ? data : (data.databases || []);

        if (knowledgeState.databases.length > 0 && !knowledgeState.activeDatabase) {
            knowledgeState.activeDatabase = knowledgeState.databases[0].id || knowledgeState.databases[0];
        }

        renderKnowledgePage();

        if (knowledgeState.activeDatabase) {
            loadKnowledgeDocuments();
        }

        updateOverviewCounts();
    } catch (err) {
        console.error('加载知识库列表失败:', err);
        const container = document.getElementById('knowledgeApp');
        if (container) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="placeholder-icon">⚠️</div>
                    <h3>无法加载知识库</h3>
                    <p>RAG 服务可能未启动，请检查服务状态。</p>
                    <button class="btn-primary" onclick="loadKnowledgeBases()">重试</button>
                </div>
            `;
        }
    }
}

/**
 * 渲染知识库页面 — 左栏：创建知识库，右栏：知识库列表 + 文件管理
 */
function renderKnowledgePage() {
    const container = document.getElementById('knowledgeApp');
    if (!container) return;

    container.innerHTML = `
        <div class="content-grid knowledge-grid">
            <!-- 左侧：创建知识库 -->
            <div class="panel-card panel-pad">
                <h3 class="panel-card-title">创建知识库</h3>
                <div class="form-group">
                    <label>知识库 ID</label>
                    <input type="text" id="newDbId" placeholder="例如：product_kb" />
                </div>
                <div class="form-group">
                    <label>知识库名称</label>
                    <input type="text" id="newDbName" placeholder="例如：产品知识库" />
                </div>
                <div class="form-group">
                    <label>描述</label>
                    <textarea id="newDbDesc" rows="3" placeholder="简要描述该知识库的用途"></textarea>
                </div>
                <button class="btn-primary" onclick="createKnowledgeBase()">创建</button>
            </div>

            <!-- 右侧：知识库列表 + 文件管理 -->
            <div class="panel-card panel-pad">
                <h3 class="panel-card-title">知识库列表 <span class="badge">${knowledgeState.databases.length}</span></h3>
                <div id="dbListContainer">
                    ${renderDatabaseList()}
                </div>

                <h3 class="panel-card-title knowledge-files-title" style="margin-top: 1.5rem;">
                    文件管理
                    ${knowledgeState.activeDatabase ? `<span class="badge-light">当前: ${escapeHtml(knowledgeState.activeDatabase)}</span>` : ''}
                    <button class="btn-log-toggle" id="logToggleBtn" onclick="toggleUploadLog()" title="上传日志">📋</button>
                </h3>
                <div id="uploadSectionContainer">
                    ${knowledgeState.activeDatabase ? renderUploadSection() : '<div class="empty-state"><p>请先选择一个知识库</p></div>'}
                </div>
                <div id="uploadLogContainer"></div>
                <div id="fileListContainer" style="margin-top: 0.75rem;">
                    <div class="empty-state"><p>加载中...</p></div>
                </div>
            </div>
        </div>
    `;

    // 恢复之前的上传日志
    if (getUploadState().uploadLogState) {
        restoreUploadLog();
    }
}

function refreshKnowledgeSelection() {
    const dbList = document.getElementById('dbListContainer');
    if (dbList) dbList.innerHTML = renderDatabaseList();

    const title = document.querySelector('.knowledge-files-title');
    if (title) {
        title.innerHTML = `
            文件管理
            ${knowledgeState.activeDatabase ? `<span class="badge-light">当前: ${escapeHtml(knowledgeState.activeDatabase)}</span>` : ''}
            <button class="btn-log-toggle" id="logToggleBtn" onclick="toggleUploadLog()" title="上传日志">📋</button>
        `;
    }

    const uploadSection = document.getElementById('uploadSectionContainer');
    if (uploadSection) {
        uploadSection.innerHTML = knowledgeState.activeDatabase
            ? renderUploadSection()
            : '<div class="empty-state"><p>请先选择一个知识库</p></div>';
    }

    const logContainer = document.getElementById('uploadLogContainer');
    if (logContainer) logContainer.innerHTML = '';
    if (getUploadState().uploadLogState) {
        restoreUploadLog();
    }
}

/**
 * 渲染知识库列表
 */
function renderDatabaseList() {
    if (knowledgeState.databases.length === 0) {
        return '<div class="empty-state"><p>暂无知识库，请在左侧创建</p></div>';
    }

    return knowledgeState.databases.map(db => {
        const id = typeof db === 'string' ? db : db.id;
        const name = typeof db === 'string' ? db : (db.name || db.id);
        const isActive = id === knowledgeState.activeDatabase;
        return `
            <div class="db-item ${isActive ? 'active' : ''}" data-db-id="${escapeHtml(id)}" onclick="selectDatabase(this.dataset.dbId)">
                <span class="db-item-icon">📚</span>
                <div class="db-item-info">
                    <div class="db-item-name">${escapeHtml(name)}</div>
                    <div class="db-item-id">${escapeHtml(id)}</div>
                </div>
                <div class="db-item-actions">
                    <button class="btn-icon-sm btn-edit" onclick="event.stopPropagation();editDatabase('${escapeHtml(id)}')" title="编辑">✏️</button>
                    <button class="btn-icon-sm btn-delete" onclick="event.stopPropagation();deleteDatabase('${escapeHtml(id)}')" title="删除">🗑️</button>
                </div>
                ${isActive ? '<span class="db-item-check">✓</span>' : ''}
            </div>
        `;
    }).join('');
}

/**
 * 渲染上传区域（支持多文件选择）
 */
function renderUploadSection() {
    const accept = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.markdown,.csv,.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp,.mp3,.wav,.flac,.aac,.ogg,.m4a,.mp4,.avi,.mkv,.mov,.webm,.mpeg,.mpg,.m4v';
    const hint = '支持格式：PDF、Word(.doc/.docx)、Excel(.xls/.xlsx)、PPT(.ppt/.pptx)、TXT、Markdown、CSV、图片(.png/.jpg/.jpeg/.bmp/.tiff/.webp)、音频、视频';
    return `
        <div class="upload-row">
            <input type="file" id="uploadFileInput" multiple
                accept="${accept}"
                onchange="updateFileSelection()" />
            <button class="btn-primary" id="uploadBtn" onclick="uploadKnowledgeFiles()">上传并导入</button>
        </div>
        <div id="selectedFiles" class="selected-files"></div>
        <p class="upload-hint">${hint}</p>
    `;
}

/**
 * 选择知识库
 */
function selectDatabase(dbId) {
    // 保存当前上传日志状态
    saveUploadLogState();
    knowledgeState.activeDatabase = dbId;
    refreshKnowledgeSelection();
    loadKnowledgeDocuments();
}

/**
 * 编辑知识库信息
 */
async function editDatabase(dbId) {
    const db = knowledgeState.databases.find(d => (typeof d === 'string' ? d : d.id) === dbId);
    const currentName = typeof db === 'string' ? db : (db?.name || dbId);
    const currentDesc = typeof db === 'string' ? '' : (db?.description || '');

    const name = prompt('知识库名称:', currentName);
    if (name === null) return;
    const description = prompt('知识库描述:', currentDesc);
    if (description === null) return;

    try {
        await fetch(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/db/${encodeURIComponent(dbId)}`,
            {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description }),
            }
        );
        loadKnowledgeBases();
    } catch (err) {
        console.error('修改知识库失败:', err);
        alert('修改失败: ' + err.message);
    }
}

/**
 * 删除知识库
 */
async function deleteDatabase(dbId) {
    const uploadState = getUploadState(dbId);
    if (uploadState.uploadEventSource || uploadState.uploadingFiles.length) {
        alert('该知识库有文件正在上传处理中，请等待完成后再删除。');
        return;
    }

    if (!confirm(`确定要删除知识库 "${dbId}" 吗？\n\n此操作将删除该知识库及其所有文件，且无法恢复。`)) return;

    try {
        const resp = await fetch(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/db/${encodeURIComponent(dbId)}`,
            { method: 'DELETE' }
        );
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        if (knowledgeState.activeDatabase === dbId) {
            knowledgeState.activeDatabase = '';
        }
        delete knowledgeState.uploadStates[dbId];
        loadKnowledgeBases();
    } catch (err) {
        console.error('删除知识库失败:', err);
        alert('删除失败: ' + err.message);
    }
}

/**
 * 创建知识库
 */
async function createKnowledgeBase() {
    const idInput = document.getElementById('newDbId');
    const nameInput = document.getElementById('newDbName');
    const descInput = document.getElementById('newDbDesc');

    const id = idInput ? idInput.value.trim() : '';
    const name = nameInput ? nameInput.value.trim() : '';
    const description = descInput ? descInput.value.trim() : '';

    if (!id) {
        alert('请输入知识库 ID');
        return;
    }
    if (!/^[a-zA-Z0-9_\-一-龥]+$/.test(id)) {
        alert('知识库ID只能包含字母、数字、下划线、短横线和中文');
        return;
    }
    if (!name) {
        alert('请输入知识库名称');
        return;
    }

    try {
        await WorkbenchAPI.postJson(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/db/register`,
            { id, name, description }
        );
        alert('知识库创建成功！');
        if (idInput) idInput.value = '';
        if (nameInput) nameInput.value = '';
        if (descInput) descInput.value = '';
        knowledgeState.activeDatabase = id;
        loadKnowledgeBases();
    } catch (err) {
        console.error('创建知识库失败:', err);
        alert('创建失败: ' + err.message);
    }
}

/**
 * 显示已选择的文件名
 */
function updateFileSelection() {
    const input = document.getElementById('uploadFileInput');
    const display = document.getElementById('selectedFiles');
    if (!input || !display) return;

    if (!input.files.length) {
        display.innerHTML = '';
        return;
    }

    const names = Array.from(input.files).map(f => f.name);
    if (names.length <= 3) {
        display.innerHTML = '已选择: ' + names.map(n => escapeHtml(n)).join(', ');
    } else {
        display.innerHTML = '已选择 ' + names.length + ' 个文件: '
            + names.slice(0, 3).map(n => escapeHtml(n)).join(', ') + ' ...';
    }
}

/**
 * 保存上传日志状态（切换知识库前调用）
 */
function saveUploadLogState() {
    const uploadState = getUploadState();
    const logEl = document.getElementById('uploadLog');
    if (logEl) {
        uploadState.uploadLogState = {
            html: logEl.parentElement.innerHTML,
        };
    }
}

/**
 * 恢复上传日志（切换知识库后调用）
 */
function restoreUploadLog() {
    const uploadState = getUploadState();
    const logContainer = document.getElementById('uploadLogContainer');
    if (!logContainer || !uploadState.uploadLogState) return;
    logContainer.innerHTML = uploadState.uploadLogState.html;

    // 更新关闭按钮事件
    const closeBtn = logContainer.querySelector('.btn-log-clear');
    if (closeBtn) {
        closeBtn.onclick = clearUploadLog;
    }
    updateLogToggleBadge();
    // 恢复后默认显示
    const logEl = document.getElementById('uploadLog');
    if (logEl) logEl.style.display = 'block';
}

/**
 * 批量上传文件到知识库
 */
async function uploadKnowledgeFiles() {
    const fileInput = document.getElementById('uploadFileInput');
    if (!fileInput || !fileInput.files.length) {
        alert('请选择要上传的文件');
        return;
    }

    if (!knowledgeState.activeDatabase) {
        alert('请先选择一个知识库');
        return;
    }

    const files = Array.from(fileInput.files);
    const uploadDb = knowledgeState.activeDatabase;
    const formData = new FormData();
    formData.append('database', uploadDb);
    files.forEach(f => formData.append('files', f));

    // 显示日志窗口
    showUploadLog(files, uploadDb);

    // 禁用上传按钮
    const uploadBtn = document.getElementById('uploadBtn');
    if (uploadBtn) uploadBtn.disabled = true;
    fileInput.value = '';

    try {
        const resp = await fetch(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/ingest/upload`,
            { method: 'POST', body: formData }
        );
        if (!resp.ok) throw new Error('HTTP ' + resp.status);

        const result = await resp.json();
        const taskId = result.task_id;
        const totalFiles = files.length;

        // 连接 SSE 获取实时进度
        connectUploadSSE(taskId, totalFiles, uploadDb);
    } catch (err) {
        console.error('上传文件失败:', err);
        appendLogEntry({ type: 'error', file: '请求失败', message: err.message, error: err.message }, uploadDb);
        finishUpload(false, uploadDb);
    }
}

/**
 * 显示上传日志窗口
 */
function showUploadLog(files, dbId) {
    const uploadState = getUploadState(dbId);
    const logContainer = document.getElementById('uploadLogContainer');
    const isActiveDb = dbId === knowledgeState.activeDatabase;

    const html = `
        <div class="upload-log" id="uploadLog">
            <div class="upload-log-header">
                <span>上传日志</span>
                <span id="uploadLogSummary">0 / ${files.length} 完成</span>
                <button class="btn-log-clear" onclick="clearUploadLog()">关闭</button>
            </div>
            <div class="upload-log-body" id="uploadLogBody">
                <div class="log-entry log-info">
                    <span class="log-msg">已提交 ${files.length} 个文件，后台处理中...</span>
                </div>
            </div>
        </div>
    `;
    uploadState.uploadLogState = { html };

    if (logContainer && isActiveDb) {
        logContainer.innerHTML = html;
    }

    // 记录正在上传的文件名
    uploadState.uploadingFiles = Array.from(files).map(f => f.name);

    // 刷新文件列表，让"处理中"状态显示出来
    if (isActiveDb) {
        refreshFileListWithProgress();

        // 确保日志容器可见
        const logEl = document.getElementById('uploadLog');
        if (logEl) logEl.style.display = 'block';
        updateLogToggleBadge();
    }
}

function ensureUploadLog(dbId, title = '处理日志') {
    const uploadState = getUploadState(dbId);
    const isActiveDb = dbId === knowledgeState.activeDatabase;
    if (uploadState.uploadLogState) {
        if (isActiveDb && !document.getElementById('uploadLog')) {
            restoreUploadLog();
        }
        return;
    }

    const html = `
        <div class="upload-log" id="uploadLog">
            <div class="upload-log-header">
                <span>${escapeHtml(title)}</span>
                <span id="uploadLogSummary">处理中</span>
                <button class="btn-log-clear" onclick="clearUploadLog()">关闭</button>
            </div>
            <div class="upload-log-body" id="uploadLogBody"></div>
        </div>
    `;
    uploadState.uploadLogState = { html };

    if (isActiveDb) {
        const logContainer = document.getElementById('uploadLogContainer');
        if (logContainer) logContainer.innerHTML = html;
        const logEl = document.getElementById('uploadLog');
        if (logEl) logEl.style.display = 'block';
        updateLogToggleBadge();
    }
}

/**
 * 连接 SSE 进度推送
 */
function connectUploadSSE(taskId, total, dbId) {
    closeUploadSSE(dbId);

    const url = `${WorkbenchAPI.BASE_URLS.RAG_API}/ingest/progress/${taskId}`;
    const es = new EventSource(url);
    const uploadState = getUploadState(dbId);
    uploadState.uploadEventSource = es;

    let completed = 0;
    let lastEventKey = '';
    let finished = false;

    es.onmessage = function (event) {
        if (finished) return;
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'finished') {
                finished = true;
                es.close();
                finishUpload(true, dbId);
                return;
            }

            // 去重：跳过 SSE 重连导致的重复事件
            const eventKey = data.type + '|' + data.file + '|' + data.message;
            if (eventKey === lastEventKey) return;
            lastEventKey = eventKey;

            appendLogEntry(data, dbId);

            if (data.type === 'parsing' && dbId === knowledgeState.activeDatabase) {
                loadKnowledgeDocuments();
            }

            if (data.type === 'done' || data.type === 'error') {
                // 从处理中列表移除，刷新文件列表
                uploadState.uploadingFiles = uploadState.uploadingFiles.filter(f => f !== data.file);
                if (dbId === knowledgeState.activeDatabase) {
                    loadKnowledgeDocuments();
                }
                if (data.type === 'done') completed++;
                else if (data.type === 'error') completed++;
            }

            const summaryEl = document.getElementById('uploadLogSummary');
            if (summaryEl && dbId === knowledgeState.activeDatabase) {
                summaryEl.textContent = `${completed} / ${total} 完成`;
            }
        } catch (e) {
            console.error('解析 SSE 事件失败:', e);
        }
    };

    es.onerror = function () {
        if (!finished) {
            finished = true;
            es.close();
            finishUpload(true, dbId);
        }
    };
}

/**
 * 关闭 SSE 连接
 */
function closeUploadSSE(dbId) {
    const uploadState = getUploadState(dbId);
    if (uploadState.uploadEventSource) {
        uploadState.uploadEventSource.close();
        uploadState.uploadEventSource = null;
    }
}

/**
 * 追加日志条目
 */
function appendLogEntry(data, dbId) {
    const uploadState = getUploadState(dbId);
    let icon, cssClass;
    switch (data.type) {
        case 'parsing':
            icon = '⏳';
            cssClass = 'log-parsing';
            break;
        case 'done':
            icon = '✅';
            cssClass = 'log-done';
            break;
        case 'error':
            icon = '❌';
            cssClass = 'log-error';
            break;
        default:
            icon = 'ℹ️';
            cssClass = 'log-info';
            break;
    }

    const entry = document.createElement('div');
    entry.className = `log-entry ${cssClass}`;
    const message = normalizeUploadMessage(data, dbId);
    entry.innerHTML = `
        <span class="log-icon">${icon}</span>
        <span class="log-file">${escapeHtml(data.file || '')}</span>
        <span class="log-msg">${escapeHtml(message)}</span>
    `;

    const wrapper = document.createElement('div');
    wrapper.innerHTML = (uploadState.uploadLogState && uploadState.uploadLogState.html) || '';
    const savedBody = wrapper.querySelector('#uploadLogBody');
    if (savedBody) {
        savedBody.appendChild(entry.cloneNode(true));
        uploadState.uploadLogState = { html: wrapper.innerHTML };
    }

    if (dbId !== knowledgeState.activeDatabase) return;
    const logBody = document.getElementById('uploadLogBody');
    if (!logBody) return;
    logBody.appendChild(entry);
    logBody.scrollTop = logBody.scrollHeight;
}

/**
 * 上传结束处理
 */
function finishUpload(success, dbId) {
    const uploadState = getUploadState(dbId);
    const isActiveDb = dbId === knowledgeState.activeDatabase;
    const uploadBtn = isActiveDb ? document.getElementById('uploadBtn') : null;
    if (uploadBtn) uploadBtn.disabled = false;

    // 更新日志汇总
    const summaryEl = isActiveDb ? document.getElementById('uploadLogSummary') : null;
    if (summaryEl && success) {
        summaryEl.textContent = '全部完成';
    }

    // 清理处理中状态并刷新
    uploadState.uploadingFiles = [];
    uploadState.uploadEventSource = null;
    if (isActiveDb) {
        loadKnowledgeDocuments();
        updateOverviewCounts();
    }
}

/**
 * 清除上传日志
 */
function clearUploadLog() {
    closeUploadSSE();
    const uploadState = getUploadState();
    uploadState.uploadLogState = null;
    uploadState.uploadingFiles = [];
    const logContainer = document.getElementById('uploadLogContainer');
    if (logContainer) {
        logContainer.innerHTML = '';
    }
    const uploadBtn = document.getElementById('uploadBtn');
    if (uploadBtn) uploadBtn.disabled = false;
    loadKnowledgeDocuments();
    updateLogToggleBadge();
}

/**
 * 切换上传日志窗口显示/隐藏
 */
function toggleUploadLog() {
    const logEl = document.getElementById('uploadLog');
    if (!logEl) return;

    if (logEl.style.display === 'none') {
        logEl.style.display = 'block';
    } else {
        logEl.style.display = 'none';
    }
}

/**
 * 更新日志切换按钮状态
 */
function updateLogToggleBadge() {
    const toggle = document.getElementById('logToggleBtn');
    if (!toggle) return;
    const logEl = document.getElementById('uploadLog');
    if (logEl) {
        toggle.classList.add('has-log');
    } else {
        toggle.classList.remove('has-log');
    }
}

/**
 * 重试导入文件
 */
async function retryDocument(sha256, buttonEl) {
    if (!knowledgeState.activeDatabase || !sha256) return;
    const dbId = knowledgeState.activeDatabase;
    const retryKey = `${dbId}|${sha256}`;
    if (knowledgeState.retryingDocuments.has(retryKey)) return;

    const row = buttonEl && buttonEl.closest ? buttonEl.closest('.file-row') : null;
    const fileName = row ? (row.getAttribute('data-file-name') || '文件') : '文件';
    knowledgeState.retryingDocuments.add(retryKey);
    ensureUploadLog(dbId, '重试日志');
    appendLogEntry({ type: 'parsing', file: fileName, message: '已提交重试，正在重新导入...' }, dbId);
    if (typeof showToast === 'function') showToast('已提交重试，正在处理...', 'info');
    await loadKnowledgeDocuments();

    try {
        const resp = await fetch(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/db/${encodeURIComponent(dbId)}/documents/${encodeURIComponent(sha256)}/retry`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ strategy: 'markdown_segments', max_chars: 12000 })
            }
        );
        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            throw new Error(data.detail || ('HTTP ' + resp.status));
        }
        appendLogEntry({ type: 'done', file: fileName, message: '重试完成，已刷新文件状态' }, dbId);
        if (typeof showToast === 'function') showToast('重试完成', 'success');
        await loadKnowledgeDocuments();
    } catch (err) {
        console.error('重试导入失败:', err);
        appendLogEntry({ type: 'error', file: fileName, message: '重试失败: ' + err.message, error: err.message }, dbId);
        if (typeof showToast === 'function') showToast('重试失败: ' + err.message, 'error');
        else alert('重试失败: ' + err.message);
    } finally {
        knowledgeState.retryingDocuments.delete(retryKey);
        if (dbId === knowledgeState.activeDatabase) {
            await loadKnowledgeDocuments();
        }
    }
}

/**
 * 删除文件
 */
async function deleteDocument(sha256) {
    if (!confirm('确定要删除此文件吗？')) return;
    if (!knowledgeState.activeDatabase) return;

    try {
        const resp = await fetch(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/db/${encodeURIComponent(knowledgeState.activeDatabase)}/documents/${sha256}`,
            { method: 'DELETE' }
        );
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        loadKnowledgeDocuments();
        updateOverviewCounts();
    } catch (err) {
        console.error('删除文件失败:', err);
        alert('删除失败: ' + err.message);
    }
}

/**
 * 加载知识库文档列表
 */
/**
 * 渲染一个文件行（已导入 or 处理中）
 */
function _renderFileRow(item, isUploading) {
    const fileName = escapeHtml(item.file_name || item.name || '-');
    const sha256 = isUploading ? '' : escapeHtml(item.sha256 || '');
    const statusMap = {
        'imported': '已导入',
        '已导入': '已导入',
        'completed': '已完成',
        'ready': '就绪',
        'processing': '处理中',
        'partial_success': '部分成功',
        'error': '失败'
    };
    const stageMap = {
        'queued': '排队中',
        'uploaded': '已上传',
        'indexing': '索引构建中',
        'rag_ingest': '解析并索引中',
        'graph_enrichment': '解析并索引中',
        'interrupted': '已中断',
        'done': '已完成',
        'error': '失败'
    };
    const rawStatus = isUploading ? 'processing' : (item.status || '已导入');
    const rawStage = isUploading ? 'queued' : (item.stage || '');
    const updatedAt = item.updated_at || item.imported_at || '';
    const isStale = !isUploading && isStaleProcessing(item);
    const retryKey = `${knowledgeState.activeDatabase}|${sha256}`;
    const isRetrying = !isUploading && knowledgeState.retryingDocuments.has(retryKey);
    const statusText = escapeHtml(isStale
        ? '疑似卡住'
        : (isRetrying
            ? '重试中'
        : (rawStatus === 'processing' && rawStage
            ? (stageMap[rawStage] || rawStage)
            : (statusMap[rawStatus] || rawStatus))));
    const progressText = item.segments_total
        ? `分段: ${item.segments_done || 0}/${item.segments_total}, 失败: ${item.segments_failed || 0}`
        : '';
    const indexText = item.chunk_count
        ? `分块: ${item.chunk_count} · 索引: ${item.index_status || 'indexed'}`
        : (item.index_status ? `索引: ${item.index_status}` : '');
    const stageText = rawStage ? `阶段: ${stageMap[rawStage] || rawStage}` : '';
    const updatedText = updatedAt ? `最后更新: ${formatBeijingTime(updatedAt)}` : '';
    const titleText = escapeHtml([stageText, updatedText, progressText, indexText, item.error || ''].filter(Boolean).join(' | '));
    const detailText = escapeHtml([indexText, progressText, updatedText].filter(Boolean).join(' · '));
    const source = isUploading ? '—' : escapeHtml(item.source || item.file_path || '-');
    const isDone = !isUploading && (rawStatus === 'completed' || rawStatus === 'ready' || rawStatus === '已导入' || rawStatus === 'imported');
    const isError = !isUploading && rawStatus === 'error';
    const isPartial = !isUploading && rawStatus === 'partial_success';
    const statusClass = isRetrying ? 'status-pending'
        : (isDone ? 'status-success'
        : (isError ? 'status-error'
            : (isPartial ? 'status-partial'
                : (isStale ? 'status-stale' : 'status-pending'))));
    const retryBtn = sha256 && canRetryDocument(item)
        ? `<button class="btn-icon-sm btn-retry ${isRetrying ? 'retrying' : ''}" onclick="retryDocument('${sha256}', this)" title="${isRetrying ? '重试中' : '重试'}" ${isRetrying ? 'disabled' : ''}>↻</button>`
        : '';
    const deleteBtn = sha256
        ? `<button class="btn-icon-sm btn-delete" onclick="deleteDocument('${sha256}')" title="删除">🗑️</button>`
        : '';
    return `
    <div class="file-row" data-doc-sha="${sha256}" data-file-name="${fileName}">
        <span class="file-col-name" title="${fileName}">
            ${isUploading ? '⏳' : '📄'} ${fileName}
        </span>
        <span class="file-col-status">
            <span class="status-text ${statusClass}" title="${titleText}">
                ${statusText}
            </span>
            ${detailText ? `<span class="file-status-detail">${detailText}</span>` : ''}
        </span>
        <span class="file-col-source">${source}</span>
        <span class="file-col-actions">${retryBtn}${deleteBtn}</span>
    </div>`;
}

async function loadKnowledgeDocuments() {
    const fileListContainer = document.getElementById('fileListContainer');
    if (!fileListContainer) return;

    if (!knowledgeState.activeDatabase) {
        clearDocumentRefreshTimer();
        fileListContainer.innerHTML = '<div class="empty-state"><p>请先选择一个知识库</p></div>';
        return;
    }

    const uploading = getUploadState().uploadingFiles.filter(f => f);

    try {
        const data = await WorkbenchAPI.requestJson(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/db/${encodeURIComponent(knowledgeState.activeDatabase)}/documents`
        );
        const documents = Array.isArray(data) ? data : (data.documents || []);

        // 后端已有记录时优先显示真实行，保留 sha256，失败/处理中也能删除。
        const documentNames = new Set(documents.map(d => d.file_name || d.name || '').filter(Boolean));
        const pendingUploads = uploading.filter(fn => !documentNames.has(fn));
        const hasProcessingDocs = documents.some(d => d.status === 'processing');
        if (hasProcessingDocs || pendingUploads.length) {
            scheduleDocumentRefresh(knowledgeState.activeDatabase);
        } else {
            clearDocumentRefreshTimer();
        }

        // 构建行：先显示处理中的，再显示已导入的
        const processingRows = pendingUploads.map(fn => _renderFileRow({ file_name: fn }, true));
        const docRows = documents.map(d => _renderFileRow(d, false));
        const allRows = [...processingRows, ...docRows];

        if (allRows.length === 0) {
            fileListContainer.innerHTML = '<div class="empty-state"><p>暂无文件，请上传文档</p></div>';
            updateOverviewCounts();
            return;
        }

        fileListContainer.innerHTML = `
            <div class="file-list-header">
                <span class="file-col-name">文件名</span>
                <span class="file-col-status">状态</span>
                <span class="file-col-source">来源</span>
                <span class="file-col-actions"></span>
            </div>
            ${allRows.join('')}
        `;

        updateOverviewCounts();
    } catch (err) {
        console.error('加载文档列表失败:', err);
        fileListContainer.innerHTML = `
            <div class="empty-state">
                <p>加载文档列表失败</p>
            </div>
        `;
    }
}

/**
 * 合并处理中文件的列表刷新（上传时调用）
 */
function refreshFileListWithProgress() {
    loadKnowledgeDocuments();
}

/**
 * 更新总览页面的知识库和文件计数
 */
function updateOverviewCounts() {
    const knowledgeCountEl = document.getElementById('knowledgeCount');
    const fileCountEl = document.getElementById('fileCount');

    if (knowledgeCountEl) {
        knowledgeCountEl.textContent = knowledgeState.databases.length;
    }

    const fileRows = document.querySelectorAll('#fileListContainer .file-row');
    if (fileCountEl) {
        fileCountEl.textContent = fileRows.length;
    }
}

// 页面加载时自动初始化
document.addEventListener('DOMContentLoaded', function () {
    // 立即加载知识库数据，供总览和内容生成页面使用
    loadKnowledgeBases();

    const observer = new MutationObserver(function () {
        const knowledgeSection = document.querySelector('[data-page="knowledge"]');
        if (knowledgeSection && knowledgeSection.classList.contains('active')) {
            loadKnowledgeBases();
        }
    });

    const sections = document.querySelectorAll('.page-section');
    sections.forEach(section => {
        observer.observe(section, { attributes: true, attributeFilter: ['class'] });
    });
});
