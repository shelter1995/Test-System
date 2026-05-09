/**
 * 内容生成模块
 * 基于知识库生成话术、方案和培训材料
 * 同时管理历史产物页面
 */

// ==================== 渲染 ====================

/**
 * 渲染内容生成页面
 */
function renderGenerationPage() {
    var container = document.getElementById('generationApp');
    if (!container) return;

    // 获取知识库列表（从 knowledge.js 的共享状态）
    var databases = (typeof knowledgeState !== 'undefined') ? knowledgeState.databases : [];

    container.innerHTML =
        '<div class="content-grid">' +
            '<div class="panel-card panel-pad">' +
                '<h3 class="panel-card-title">内容生成</h3>' +
                '<div class="form-group">' +
                    '<label>选择知识库</label>' +
                    '<select id="genDatabase" class="form-control">' +
                        (databases.length === 0
                            ? '<option value="">暂无可用知识库</option>'
                            : databases.map(function (db) {
                                var id = typeof db === 'string' ? db : db.id;
                                var name = typeof db === 'string' ? db : (db.name || db.id);
                                return '<option value="' + escapeHtml(id) + '">' + escapeHtml(name) + '</option>';
                            }).join('')) +
                    '</select>' +
                '</div>' +
                '<div class="form-group">' +
                    '<label>客户单位</label>' +
                    '<input type="text" id="genClientUnit" placeholder="例如：某某科技有限公司">' +
                '</div>' +
                '<div class="form-group">' +
                    '<label>产品名称</label>' +
                    '<input type="text" id="genProduct" placeholder="例如：商务视频彩铃">' +
                '</div>' +
                '<button id="genStartBtn" class="btn-primary">开始生成</button>' +
                '<div id="genStatus" class="status-text" style="margin-top:1rem"></div>' +
            '</div>' +
            '<div class="panel-card panel-pad">' +
                '<h3 class="panel-card-title">生成结果</h3>' +
                '<div id="genResults">' +
                    '<div class="empty-state"><p>暂无生成产物</p></div>' +
                '</div>' +
            '</div>' +
        '</div>';

    var startBtn = document.getElementById('genStartBtn');
    if (startBtn) {
        startBtn.addEventListener('click', startGenerationJob);
    }

    loadGenerationArtifacts();
}

/**
 * 渲染历史产物页面
 */
function renderHistoryPage(artifacts) {
    var container = document.getElementById('historyApp');
    if (!container) return;

    if (!artifacts || artifacts.length === 0) {
        container.innerHTML =
            '<div class="panel-card panel-pad">' +
                '<h3 class="panel-card-title">历史产物</h3>' +
                '<div class="empty-state">' +
                    '<div class="placeholder-icon">📁</div>' +
                    '<p>暂无历史产物</p>' +
                '</div>' +
            '</div>';
        return;
    }

    container.innerHTML =
        '<div class="panel-card panel-pad">' +
            '<h3 class="panel-card-title">历史产物 <span class="badge">' + artifacts.length + '</span></h3>' +
            '<div class="artifact-list">' +
                artifacts.map(function (a) {
                    var sizeKB = a.size ? (a.size / 1024).toFixed(1) : '?';
                    var downloadUrl = WorkbenchAPI.BASE_URLS.TUTOR_API +
                        '/generation/artifacts/download?path=' + encodeURIComponent(a.path);
                    return (
                        '<div class="artifact-row">' +
                            '<span class="artifact-name" title="' + escapeHtml(a.path || '') + '">' +
                                escapeHtml(a.name) +
                            '</span>' +
                            '<span class="artifact-meta">' + sizeKB + ' KB</span>' +
                            '<a href="' + downloadUrl + '" target="_blank" class="download-link">下载</a>' +
                        '</div>'
                    );
                }).join('') +
            '</div>' +
        '</div>';
}

/**
 * 渲染生成页面内的产物列表
 */
function renderArtifactList(artifacts) {
    var container = document.getElementById('genResults');
    if (!container) return;

    if (!artifacts || artifacts.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>暂无生成产物</p></div>';
        return;
    }

    container.innerHTML =
        '<div class="artifact-list">' +
            artifacts.map(function (a) {
                var downloadUrl = WorkbenchAPI.BASE_URLS.TUTOR_API +
                    '/generation/artifacts/download?path=' + encodeURIComponent(a.path);
                return (
                    '<div class="artifact-row">' +
                        '<span class="artifact-name" title="' + escapeHtml(a.path || '') + '">' +
                            escapeHtml(a.name) +
                        '</span>' +
                        '<a href="' + downloadUrl + '" target="_blank" class="download-link">下载</a>' +
                    '</div>'
                );
            }).join('') +
        '</div>';
}

// ==================== 数据操作 ====================

/**
 * 启动内容生成任务
 */
async function startGenerationJob() {
    var btn = document.getElementById('genStartBtn');
    var status = document.getElementById('genStatus');
    var dbSelect = document.getElementById('genDatabase');
    var clientUnitInput = document.getElementById('genClientUnit');
    var productInput = document.getElementById('genProduct');

    var database = dbSelect ? dbSelect.value : '';
    if (!database) {
        if (status) status.textContent = '请先选择一个知识库';
        return;
    }

    var clientUnit = clientUnitInput ? clientUnitInput.value.trim() : '';
    var product = productInput ? productInput.value.trim() : '';

    if (btn) { btn.disabled = true; btn.textContent = '生成中...'; }
    if (status) status.textContent = '正在生成材料，通常需要数分钟...';

    try {
        var data = await WorkbenchAPI.postJson(
            WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/jobs',
            {
                database: database,
                client_unit: clientUnit,
                product: product
            }
        );
        if (status) status.textContent = '任务已创建: ' + data.job_id;
        // 轮询任务状态
        pollJobStatus(data.job_id);
    } catch (err) {
        if (status) status.textContent = '生成失败: ' + err.message;
        if (btn) { btn.disabled = false; btn.textContent = '开始生成'; }
    }
}

/**
 * 轮询任务状态直到完成或超时
 */
async function pollJobStatus(jobId) {
    var status = document.getElementById('genStatus');
    var btn = document.getElementById('genStartBtn');
    var maxAttempts = 60;

    for (var i = 0; i < maxAttempts; i++) {
        await new Promise(function (r) { setTimeout(r, 5000); });
        try {
            var job = await WorkbenchAPI.requestJson(
                WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/jobs/' + jobId
            );
            if (job.status === 'completed') {
                if (status) status.textContent = '生成完成！';
                if (btn) { btn.disabled = false; btn.textContent = '开始生成'; }
                loadGenerationArtifacts();
                return;
            } else if (job.status === 'failed') {
                if (status) status.textContent = '生成失败: ' + (job.error || '未知错误');
                if (btn) { btn.disabled = false; btn.textContent = '开始生成'; }
                return;
            }
        } catch (err) {
            // 网络抖动，继续轮询
        }
    }

    if (status) status.textContent = '生成超时，请稍后查看历史产物';
    if (btn) { btn.disabled = false; btn.textContent = '开始生成'; }
}

/**
 * 加载生成产物列表（同时刷新生成页面和历史页面）
 */
async function loadGenerationArtifacts() {
    try {
        var data = await WorkbenchAPI.requestJson(
            WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/artifacts'
        );
        var artifacts = data.artifacts || [];
        renderArtifactList(artifacts);
        renderHistoryPage(artifacts);
    } catch (err) {
        // 服务不可用时静默失败
        console.warn('加载生成产物失败:', err.message);
    }
}

// ==================== 页面初始化 ====================

document.addEventListener('DOMContentLoaded', function () {
    // 监听页面切换，当进入生成/历史页面时加载数据
    var observer = new MutationObserver(function () {
        var genSection = document.querySelector('[data-page="generation"]');
        if (genSection && genSection.classList.contains('active')) {
            renderGenerationPage();
        }
        var histSection = document.querySelector('[data-page="history"]');
        if (histSection && histSection.classList.contains('active')) {
            loadGenerationArtifacts();
        }
    });

    var sections = document.querySelectorAll('.page-section');
    sections.forEach(function (section) {
        observer.observe(section, { attributes: true, attributeFilter: ['class'] });
    });
});
