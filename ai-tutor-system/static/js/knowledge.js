/**
 * 知识库管理模块
 * 管理知识库的创建、选择、文件上传和文档列表
 */
/**
 * 转义 HTML 特殊字符，防止 XSS
 */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

const knowledgeState = {
    databases: [],
    activeDatabase: '',
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

        // 默认选中第一个
        if (knowledgeState.databases.length > 0 && !knowledgeState.activeDatabase) {
            knowledgeState.activeDatabase = knowledgeState.databases[0].id || knowledgeState.databases[0];
        }

        renderKnowledgePage();

        if (knowledgeState.activeDatabase) {
            loadKnowledgeDocuments();
        }

        // 同步总览计数
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
 * 渲染知识库页面
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

            <!-- 右侧：知识库列表 -->
            <div class="panel-card panel-pad">
                <h3 class="panel-card-title">知识库列表 <span class="badge">${knowledgeState.databases.length}</span></h3>
                <div id="dbListContainer">
                    ${renderDatabaseList()}
                </div>
            </div>
        </div>

        <!-- 下方：文件上传 + 文件列表 -->
        <div class="panel-card panel-pad" style="margin-top: 1.25rem;">
            <h3 class="panel-card-title">
                文件管理
                ${knowledgeState.activeDatabase ? `<span class="badge-light">当前: ${escapeHtml(knowledgeState.activeDatabase)}</span>` : ''}
            </h3>
            ${knowledgeState.activeDatabase ? renderUploadSection() : '<div class="empty-state"><p>请先选择一个知识库</p></div>'}
            <div id="fileListContainer" style="margin-top: 1rem;">
                <div class="empty-state"><p>加载中...</p></div>
            </div>
        </div>
    `;
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
                ${isActive ? '<span class="db-item-check">✓</span>' : ''}
            </div>
        `;
    }).join('');
}

/**
 * 渲染上传区域
 */
function renderUploadSection() {
    return `
        <div class="upload-row">
            <input type="file" id="uploadFileInput" accept=".pdf,.doc,.docx,.txt,.md,.xlsx,.xls,.pptx,.ppt,.csv,.html,.json" />
            <button class="btn-primary" onclick="uploadKnowledgeFile()">上传并导入</button>
        </div>
        <p class="upload-hint">支持格式：PDF、Word、TXT、Markdown、Excel、PPT、CSV、HTML、JSON</p>
    `;
}

/**
 * 选择知识库
 */
function selectDatabase(dbId) {
    knowledgeState.activeDatabase = dbId;
    renderKnowledgePage();
    loadKnowledgeDocuments();
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
        // 清空表单
        if (idInput) idInput.value = '';
        if (nameInput) nameInput.value = '';
        if (descInput) descInput.value = '';
        // 刷新列表
        knowledgeState.activeDatabase = id;
        loadKnowledgeBases();
    } catch (err) {
        console.error('创建知识库失败:', err);
        alert('创建失败: ' + err.message);
    }
}

/**
 * 上传文件到知识库
 */
async function uploadKnowledgeFile() {
    const fileInput = document.getElementById('uploadFileInput');
    if (!fileInput || !fileInput.files.length) {
        alert('请选择要上传的文件');
        return;
    }

    if (!knowledgeState.activeDatabase) {
        alert('请先选择一个知识库');
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('database', knowledgeState.activeDatabase);
    formData.append('file', file);

    // 显示上传中状态
    const fileListContainer = document.getElementById('fileListContainer');
    if (fileListContainer) {
        fileListContainer.innerHTML = `
            <div class="empty-state">
                <div class="placeholder-icon">⏳</div>
                <p>正在上传并导入，RAG-Anything 解析可能需要较长时间...</p>
            </div>
        `;
    }

    try {
        const resp = await fetch(
            `${WorkbenchAPI.BASE_URLS.RAG_API}/ingest/upload`,
            { method: 'POST', body: formData }
        );
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        alert('文件上传成功！');
        // 清空文件选择
        fileInput.value = '';
        // 刷新文件列表
        loadKnowledgeDocuments();
        // 更新总览计数
        updateOverviewCounts();
    } catch (err) {
        console.error('上传文件失败:', err);
        alert('上传失败: ' + err.message);
        if (fileListContainer) {
            fileListContainer.innerHTML = `
                <div class="empty-state">
                    <p>上传失败，请重试</p>
                </div>
            `;
        }
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
            </div>
            ${documents.map(doc => {
                const fileName = escapeHtml(doc.file_name || doc.name || '-');
                const status = escapeHtml(doc.status || '已导入');
                const source = escapeHtml(doc.source || doc.file_path || '-');
                const statusClass = (doc.status === 'completed' || doc.status === 'ready') ? 'status-success' : 'status-pending';
                return `
                <div class="file-row">
                    <span class="file-col-name" title="${fileName}">
                        📄 ${fileName}
                    </span>
                    <span class="file-col-status">
                        <span class="status-text ${statusClass}">
                            ${status}
                        </span>
                    </span>
                    <span class="file-col-source">${source}</span>
                </div>
            `}).join('')}
        `;

        // 更新总览计数
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

    // 文件计数通过当前文档列表获取
    const fileRows = document.querySelectorAll('#fileListContainer .file-row');
    if (fileCountEl) {
        fileCountEl.textContent = fileRows.length;
    }
}

// 页面加载时自动初始化
document.addEventListener('DOMContentLoaded', function () {
    // 当切换到知识库页面时加载数据
    const observer = new MutationObserver(function () {
        const knowledgeSection = document.querySelector('[data-page="knowledge"]');
        if (knowledgeSection && knowledgeSection.classList.contains('active')) {
            loadKnowledgeBases();
        }
    });

    // 监听页面切换
    const sections = document.querySelectorAll('.page-section');
    sections.forEach(section => {
        observer.observe(section, { attributes: true, attributeFilter: ['class'] });
    });
});
