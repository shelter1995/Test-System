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
    uploadEventSource: null,
    uploadLogState: null,  // 切换知识库时保留上传日志
};

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
        <div class="content-grid">
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

                <h3 class="panel-card-title" style="margin-top: 1.5rem;">
                    文件管理
                    ${knowledgeState.activeDatabase ? `<span class="badge-light">当前: ${escapeHtml(knowledgeState.activeDatabase)}</span>` : ''}
                    <button class="btn-log-toggle" id="logToggleBtn" onclick="toggleUploadLog()" title="上传日志">📋</button>
                </h3>
                ${knowledgeState.activeDatabase ? renderUploadSection() : '<div class="empty-state"><p>请先选择一个知识库</p></div>'}
                <div id="uploadLogContainer"></div>
                <div id="fileListContainer" style="margin-top: 0.75rem;">
                    <div class="empty-state"><p>加载中...</p></div>
                </div>
            </div>
        </div>
    `;

    // 恢复之前的上传日志
    if (knowledgeState.uploadLogState) {
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
    return `
        <div class="upload-row">
            <input type="file" id="uploadFileInput" multiple
                accept=".pdf,.doc,.docx,.txt,.md,.xlsx,.xls,.pptx,.ppt,.csv,.html,.json"
                onchange="updateFileSelection()" />
            <button class="btn-primary" id="uploadBtn" onclick="uploadKnowledgeFiles()">上传并导入</button>
        </div>
        <div id="selectedFiles" class="selected-files"></div>
        <p class="upload-hint">支持格式：PDF、Word、TXT、Markdown、Excel、PPT、CSV、HTML、JSON（可多选）</p>
    `;
}

/**
 * 选择知识库
 */
function selectDatabase(dbId) {
    // 保存当前上传日志状态
    saveUploadLogState();
    closeUploadSSE();
    knowledgeState.activeDatabase = dbId;
    renderKnowledgePage();
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
        knowledgeState.uploadLogState = null;
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
    const logEl = document.getElementById('uploadLog');
    if (logEl) {
        knowledgeState.uploadLogState = {
            html: logEl.parentElement.innerHTML,
        };
    }
}

/**
 * 恢复上传日志（切换知识库后调用）
 */
function restoreUploadLog() {
    const logContainer = document.getElementById('uploadLogContainer');
    if (!logContainer || !knowledgeState.uploadLogState) return;
    logContainer.innerHTML = knowledgeState.uploadLogState.html;

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
    const formData = new FormData();
    formData.append('database', knowledgeState.activeDatabase);
    files.forEach(f => formData.append('files', f));

    // 显示日志窗口
    showUploadLog(files);

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
        connectUploadSSE(taskId, totalFiles);
    } catch (err) {
        console.error('上传文件失败:', err);
        appendLogEntry({ type: 'error', file: '请求失败', message: err.message, error: err.message });
        finishUpload(false);
    }
}

/**
 * 显示上传日志窗口
 */
function showUploadLog(files) {
    const logContainer = document.getElementById('uploadLogContainer');
    if (!logContainer) return;

    logContainer.innerHTML = `
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

    // 确保日志容器可见
    document.getElementById('uploadLog').style.display = 'block';
    updateLogToggleBadge();
}

/**
 * 连接 SSE 进度推送
 */
function connectUploadSSE(taskId, total) {
    closeUploadSSE();

    const url = `${WorkbenchAPI.BASE_URLS.RAG_API}/ingest/progress/${taskId}`;
    const es = new EventSource(url);
    knowledgeState.uploadEventSource = es;

    let completed = 0;

    es.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'finished') {
                es.close();
                finishUpload(true);
                return;
            }

            appendLogEntry(data);

            if (data.type === 'done') {
                completed++;
            } else if (data.type === 'error') {
                completed++;
            }

            const summaryEl = document.getElementById('uploadLogSummary');
            if (summaryEl) {
                summaryEl.textContent = `${completed} / ${total} 完成`;
            }
        } catch (e) {
            console.error('解析 SSE 事件失败:', e);
        }
    };

    es.onerror = function () {
        finishUpload(true);
    };
}

/**
 * 关闭 SSE 连接
 */
function closeUploadSSE() {
    if (knowledgeState.uploadEventSource) {
        knowledgeState.uploadEventSource.close();
        knowledgeState.uploadEventSource = null;
    }
}

/**
 * 追加日志条目
 */
function appendLogEntry(data) {
    const logBody = document.getElementById('uploadLogBody');
    if (!logBody) return;

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
    entry.innerHTML = `
        <span class="log-icon">${icon}</span>
        <span class="log-file">${escapeHtml(data.file || '')}</span>
        <span class="log-msg">${escapeHtml(data.error || data.message || '')}</span>
    `;
    logBody.appendChild(entry);

    // 自动滚动到底部
    logBody.scrollTop = logBody.scrollHeight;
}

/**
 * 上传结束处理
 */
function finishUpload(success) {
    const uploadBtn = document.getElementById('uploadBtn');
    if (uploadBtn) uploadBtn.disabled = false;

    // 更新日志汇总
    const summaryEl = document.getElementById('uploadLogSummary');
    if (summaryEl && success) {
        summaryEl.textContent = '全部完成';
    }

    // 刷新文件列表
    loadKnowledgeDocuments();
    updateOverviewCounts();
}

/**
 * 清除上传日志
 */
function clearUploadLog() {
    closeUploadSSE();
    knowledgeState.uploadLogState = null;
    const logContainer = document.getElementById('uploadLogContainer');
    if (logContainer) {
        logContainer.innerHTML = '';
    }
    const uploadBtn = document.getElementById('uploadBtn');
    if (uploadBtn) uploadBtn.disabled = false;
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
async function loadKnowledgeDocuments() {
    const fileListContainer = document.getElementById('fileListContainer');
    if (!fileListContainer) return;

    if (!knowledgeState.activeDatabase) {
        fileListContainer.innerHTML = '<div class="empty-state"><p>请先选择一个知识库</p></div>';
        return;
    }

    try {
        const data = await WorkbenchAPI.requestJson(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/db/${knowledgeState.activeDatabase}/documents`
        );

        const documents = Array.isArray(data) ? data : (data.documents || []);

        if (documents.length === 0) {
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
            ${documents.map(doc => {
                const fileName = escapeHtml(doc.file_name || doc.name || '-');
                const sha256 = escapeHtml(doc.sha256 || '');
                const statusMap = { 'imported': '已导入', '已导入': '已导入', 'completed': '已完成', 'ready': '就绪', 'processing': '处理中', 'error': '失败' };
                const rawStatus = doc.status || '已导入';
                const statusText = escapeHtml(statusMap[rawStatus] || rawStatus);
                const source = escapeHtml(doc.source || doc.file_path || '-');
                const isDone = rawStatus === 'completed' || rawStatus === 'ready' || rawStatus === '已导入' || rawStatus === 'imported';
                const statusClass = isDone ? 'status-success' : 'status-pending';
                return `
                <div class="file-row">
                    <span class="file-col-name" title="${fileName}">
                        📄 ${fileName}
                    </span>
                    <span class="file-col-status">
                        <span class="status-text ${statusClass}">
                            ${statusText}
                        </span>
                    </span>
                    <span class="file-col-source">${source}</span>
                    <span class="file-col-actions">
                        <button class="btn-icon-sm btn-delete" onclick="deleteDocument('${sha256}')" title="删除">🗑️</button>
                    </span>
                </div>
            `}).join('')}
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
