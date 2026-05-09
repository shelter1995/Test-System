/**
 * 内容生成模块 v2
 * 支持4种独立内容类型：解决方案、培训教案、考试题目、使用说明
 */

// ==================== 类型配置 ====================

var GEN_TYPES = {
    solution: {
        name: '解决方案',
        icon: '📋',
        desc: '为客户定制的产品解决方案文档',
        fields: [
            { id: 'solClientUnit', label: '客户单位', placeholder: '例如：某某科技有限公司' },
            { id: 'solProduct', label: '产品名称', placeholder: '例如：商务视频彩铃' },
            { id: 'solTargetAudience', label: '汇报对象 / 目标受众', placeholder: '例如：技术总监、采购经理' },
        ]
    },
    training: {
        name: '培训教案',
        icon: '📖',
        desc: '面向销售团队的产品培训材料',
        fields: [
            { id: 'trnProduct', label: '产品名称', placeholder: '例如：商务视频彩铃' },
            { id: 'trnTargetAudience', label: '目标受众', placeholder: '例如：新入职销售代表' },
            { id: 'trnDuration', label: '培训时长', placeholder: '例如：2小时' },
        ]
    },
    exam: {
        name: '考试题目',
        icon: '📝',
        desc: '产品知识考核试题',
        fields: [
            { id: 'exmProduct', label: '产品名称', placeholder: '例如：商务视频彩铃' },
            { id: 'exmQuestionCount', label: '题量', placeholder: '例如：20', type: 'number' },
            { id: 'exmQuestionTypes', label: '题目类型', placeholder: '例如：单选、多选、简答' },
        ]
    },
    readme: {
        name: '使用说明',
        icon: '📘',
        desc: '产品使用指南文档',
        fields: [
            { id: 'rdmProduct', label: '产品名称', placeholder: '例如：商务视频彩铃' },
            { id: 'rdmUseCases', label: '适用场景', placeholder: '例如：企业内部培训、客户演示' },
        ]
    }
};

// ==================== 渲染 ====================

function renderGenerationPage() {
    var container = document.getElementById('generationApp');
    if (!container) return;

    var databases = (typeof knowledgeState !== 'undefined') ? knowledgeState.databases : [];

    var dbOptions = databases.length === 0
        ? '<option value="">暂无可用知识库</option>'
        : databases.map(function (db) {
            var id = typeof db === 'string' ? db : db.id;
            var name = typeof db === 'string' ? db : (db.name || db.id);
            return '<option value="' + escapeHtml(id) + '">' + escapeHtml(name) + '</option>';
        }).join('');

    var cardsHtml = Object.keys(GEN_TYPES).map(function (type) {
        var cfg = GEN_TYPES[type];
        var fieldsHtml = cfg.fields.map(function (f) {
            var inputType = f.type || 'text';
            return '<div class="form-group">' +
                '<label>' + f.label + '</label>' +
                '<input type="' + inputType + '" id="' + f.id + '" placeholder="' + f.placeholder + '" />' +
            '</div>';
        }).join('');

        return '<div class="panel-card panel-pad gen-card">' +
            '<div class="gen-card-header">' +
                '<span class="gen-card-icon">' + cfg.icon + '</span>' +
                '<div>' +
                    '<h3 class="gen-card-title">' + cfg.name + '</h3>' +
                    '<p class="gen-card-desc">' + cfg.desc + '</p>' +
                '</div>' +
            '</div>' +
            '<div class="gen-card-body">' +
                '<div class="form-group">' +
                    '<label>选择知识库</label>' +
                    '<select class="form-control gen-db-select" data-type="' + type + '">' + dbOptions + '</select>' +
                '</div>' +
                fieldsHtml +
            '</div>' +
            '<div class="gen-card-footer">' +
                '<button class="btn-primary" onclick="startGenerationJob(\'' + type + '\')">开始生成</button>' +
                '<span class="gen-status" id="genStatus_' + type + '"></span>' +
            '</div>' +
        '</div>';
    }).join('');

    container.innerHTML =
        '<div class="gen-grid">' + cardsHtml + '</div>' +
        '<div class="panel-card panel-pad" style="margin-top:1.25rem;">' +
            '<h3 class="panel-card-title">历史产物</h3>' +
            '<div id="genResults">' +
                '<div class="empty-state"><p>暂无生成产物</p></div>' +
            '</div>' +
        '</div>';

    loadGenerationArtifacts();
}

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
        '</div>';
}

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

// ==================== 数据操作 ====================

function startGenerationJob(type) {
    var cfg = GEN_TYPES[type];
    if (!cfg) return;

    var statusEl = document.getElementById('genStatus_' + type);
    var dbSelect = document.querySelector('.gen-db-select[data-type="' + type + '"]');
    var database = dbSelect ? dbSelect.value : '';

    if (!database) {
        if (statusEl) statusEl.textContent = '请先选择一个知识库';
        return;
    }

    // 收集表单数据
    var payload = { type: type, database: database };
    cfg.fields.forEach(function (f) {
        var el = document.getElementById(f.id);
        if (el) {
            var key = f.id.replace(/^(sol|trn|exm|rdm)/, '').toLowerCase();
            payload[key] = el.value.trim();
        }
    });

    // 禁用按钮
    var btn = statusEl ? statusEl.previousElementSibling : null;
    if (btn && btn.tagName === 'BUTTON') {
        btn.disabled = true;
        btn.textContent = '生成中...';
    }
    if (statusEl) statusEl.textContent = '正在生成，请稍候...';

    WorkbenchAPI.postJson(
        WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/jobs',
        payload
    ).then(function (data) {
        if (statusEl) statusEl.textContent = '任务已创建: ' + data.job_id;
        pollJobStatus(data.job_id, type);
    }).catch(function (err) {
        if (statusEl) statusEl.textContent = '生成失败: ' + err.message;
        if (btn && btn.tagName === 'BUTTON') {
            btn.disabled = false;
            btn.textContent = '开始生成';
        }
    });
}

function pollJobStatus(jobId, type) {
    var statusEl = document.getElementById('genStatus_' + type);
    var btn = statusEl ? statusEl.previousElementSibling : null;
    var maxAttempts = 60;

    function check() {
        if (maxAttempts-- <= 0) {
            if (statusEl) statusEl.textContent = '生成超时，请稍后查看历史产物';
            if (btn && btn.tagName === 'BUTTON') {
                btn.disabled = false;
                btn.textContent = '开始生成';
            }
            return;
        }

        setTimeout(function () {
            WorkbenchAPI.requestJson(
                WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/jobs/' + jobId
            ).then(function (job) {
                if (job.status === 'completed') {
                    if (statusEl) statusEl.textContent = '✅ 生成完成！';
                    if (btn && btn.tagName === 'BUTTON') {
                        btn.disabled = false;
                        btn.textContent = '开始生成';
                    }
                    loadGenerationArtifacts();
                } else if (job.status === 'failed') {
                    if (statusEl) statusEl.textContent = '❌ 生成失败: ' + (job.error || '未知错误');
                    if (btn && btn.tagName === 'BUTTON') {
                        btn.disabled = false;
                        btn.textContent = '开始生成';
                    }
                } else {
                    if (statusEl) statusEl.textContent = '⏳ 生成中...';
                    check();
                }
            }).catch(function () {
                check();
            });
        }, 5000);
    }

    check();
}

function loadGenerationArtifacts() {
    WorkbenchAPI.requestJson(
        WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/artifacts'
    ).then(function (data) {
        var artifacts = data.artifacts || [];
        renderArtifactList(artifacts);
        renderHistoryPage(artifacts);
    }).catch(function (err) {
        console.warn('加载生成产物失败:', err.message);
    });
}

// ==================== 页面初始化 ====================

document.addEventListener('DOMContentLoaded', function () {
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
