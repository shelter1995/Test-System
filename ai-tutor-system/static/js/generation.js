/**
 * 内容生成模块 v3
 * 支持 2 种 RAG 增强管线：解决方案（SCQA+MECE）+ 培训材料包（讲义+考试+README）
 */
(function () {
    var _initialized = false;

    // ==================== 类型配置 ====================

    var GEN_TYPES = {
        solution: {
            name: '解决方案',
            icon: '📋',
            desc: '基于SCQA MECE架构，为客户定制个性化产品解决方案。自动检索知识库获取产品信息、行业场景和成功案例。',
            sections: [
                {
                    id: 'solBasic',
                    title: '📌 基本信息',
                    fields: [
                        { id: 'solClientUnit', key: 'client_unit', label: '客户单位', placeholder: '例如：阳光电源股份有限公司', type: 'text' },
                        { id: 'solDecisionRole', key: 'decision_maker_role', label: '决策人职位', placeholder: '例如：市场总监', type: 'text' },
                        { id: 'solRelation', key: 'relationship_level', label: '客情关系', type: 'select', options: ['初次接触', '一般关系', '良好关系', '密切关系'] },
                    ]
                },
                {
                    id: 'solPain',
                    title: '😣 客户痛点',
                    fields: [
                        { id: 'solPainChallenges', key: 'pain_challenges', label: '主要挑战', type: 'textarea', placeholder: '客户目前在企业宣传/客户沟通方面遇到哪些主要挑战？例如：宣传效果不佳、客户转化率低、品牌形象不突出等' },
                        { id: 'solPainScenarios', key: 'pain_scenarios', label: '潜在应用场景', type: 'textarea', placeholder: '客户的核心业务流程中，哪些环节可以应用此产品？例如：客户咨询、业务办理、产品推广、售后服务等' },
                        { id: 'solPainDissatisfaction', key: 'pain_dissatisfaction', label: '对现状不满意之处', type: 'textarea', placeholder: '客户对现有通信或宣传方式有哪些不满意的地方？例如：传统方式单一、缺乏互动性、无法量化效果等' },
                    ]
                },
                {
                    id: 'solDecision',
                    title: '⚖️ 决策偏好',
                    fields: [
                        { id: 'solDecisionFocus', key: 'decision_focus', label: '决策关注点', type: 'select', options: ['成本因素', '效果导向', '技术领先', '服务保障', '品牌形象'] },
                        { id: 'solDecisionProcess', key: 'decision_process', label: '决策流程', type: 'select', options: ['个人决策', '部门决策', '高层决策', '招标采购'] },
                        { id: 'solDecisionTimeline', key: 'decision_timeline', label: '决策时间', type: 'select', options: ['紧急（1-2周）', '常规（1-2个月）', '长期（3个月以上）'] },
                    ]
                }
            ]
        },
        training: {
            name: '培训材料包',
            icon: '📖',
            desc: '自动生成培训讲义+考试题目+使用说明完整套件（基于Gagne九段教学法、Kolb循环、Bloom分类）。',
            sections: [
                {
                    id: 'trnDemand',
                    title: '📋 培训需求',
                    fields: [
                        { id: 'trnTheme', key: 'training_theme', label: '培训主题', type: 'select', options: ['产品培训', '销售培训', '技术培训'] },
                        { id: 'trnCustomerGroup', key: 'target_customer_group', label: '目标客户群', placeholder: '例如：政务客户 + 教育客户', type: 'text' },
                        { id: 'trnLevel', key: 'trainee_level', label: '培训对象水平', type: 'select', options: ['新入职人员', '有经验人员', '销售经理', '混合群体'] },
                        { id: 'trnBase', key: 'trainee_base', label: '学员基础', placeholder: '例如：对产品有一定了解，1-3年经验', type: 'text' },
                        { id: 'trnDuration', key: 'duration', label: '培训时长', type: 'select', options: ['1-2小时', '半天（3-4小时）', '1天', '2天'] },
                        { id: 'trnGoals', key: 'training_goals', label: '培训目标', type: 'select', options: ['了解产品', '熟悉产品', '能够介绍产品', '能够销售产品', '能够解决问题'] },
                        { id: 'trnFocus', key: 'focus_areas', label: '重点内容', placeholder: '例如：客户痛点挖掘 + 销售话术和技巧 + 成功案例分享', type: 'text' },
                    ]
                },
                {
                    id: 'trnExam',
                    title: '📝 考试配置',
                    type: 'examConfig',
                    fields: []
                }
            ]
        }
    };

    // ==================== 渲染函数 ====================

    function renderDatabaseOptions(selected) {
        var databases = (typeof knowledgeState !== 'undefined') ? knowledgeState.databases : [];
        if (databases.length === 0) {
            return '<option value="">请先创建知识库</option>';
        }
        var sel = selected || '';
        return databases.map(function (db) {
            var id = typeof db === 'string' ? db : (db.id || db.name || '');
            var name = typeof db === 'string' ? db : (db.name || db.id || '');
            var selectedAttr = (id && id === sel) ? ' selected' : '';
            return '<option value="' + escapeHtml(id) + '"' + selectedAttr + '>' + escapeHtml(name) + '</option>';
        }).join('');
    }

    function renderSectionHtml(section, collapsed) {
        var collapsedClass = collapsed ? ' collapsed' : '';
        var bodyHtml = '';

        if (section.type === 'examConfig') {
            bodyHtml = renderExamConfigHtml();
        } else {
            bodyHtml = section.fields.map(function (f) {
                if (f.type === 'select') {
                    var optionsHtml = (f.options || []).map(function (o) {
                        return '<option value="' + escapeHtml(o) + '">' + escapeHtml(o) + '</option>';
                    }).join('');
                    return '<div class="form-group"><label>' + f.label + '</label>' +
                        '<select class="form-control" id="' + f.id + '">' + optionsHtml + '</select></div>';
                }
                if (f.type === 'textarea') {
                    return '<div class="form-group"><label>' + f.label + '</label>' +
                        '<textarea class="form-textarea" id="' + f.id + '" placeholder="' + escapeHtml(f.placeholder || '') + '" rows="3"></textarea></div>';
                }
                var valueAttr = f.value !== undefined ? ' value="' + f.value + '"' : '';
                var minAttr = f.min !== undefined ? ' min="' + f.min + '"' : '';
                var maxAttr = f.max !== undefined ? ' max="' + f.max + '"' : '';
                return '<div class="form-group"><label>' + f.label + '</label>' +
                    '<input type="' + f.type + '" id="' + f.id + '" placeholder="' + escapeHtml(f.placeholder || '') + '"' + valueAttr + minAttr + maxAttr + ' class="form-control" /></div>';
            }).join('');
        }

        return '<div class="gen-section' + collapsedClass + '" id="section_' + section.id + '">' +
            '<div class="gen-section-header" onclick="toggleGenSection(\'' + section.id + '\')"><span>' + section.title + '</span></div>' +
            '<div class="gen-section-body">' + bodyHtml + '</div></div>';
    }

    function renderExamConfigHtml() {
        var questionTypes = ['选择题', '填空题', '简答题', '案例分析题', '附加题'];
        var defaultCounts = { '选择题': 5, '填空题': 3, '简答题': 4, '案例分析题': 3, '附加题': 1 };
        var typeRows = questionTypes.map(function (t, i) {
            var checked = i < 4 ? ' checked' : '';  // 默认前4种选中
            return '<div class="exam-type-row">' +
                '<label class="exam-check"><input type="checkbox" class="trnExamType" value="' + t + '"' + checked + ' onchange="toggleExamTypeCount(this)"> ' + t + '</label>' +
                '<input type="number" class="form-control exam-count-input" id="trnExamCount_' + i + '" value="' + (defaultCounts[t] || 1) + '" min="1" max="30" style="width:70px" data-type="' + t + '">' +
                '<span class="exam-count-label">题</span>' +
            '</div>';
        }).join('');

        return typeRows +
            '<div class="exam-divider"></div>' +
            '<div class="form-row-3">' +
                '<div class="form-group"><label>总题量</label><input type="number" id="trnExamTotalCount" class="form-control" value="16" readonly></div>' +
                '<div class="form-group"><label>总分</label><input type="number" id="trnExamTotalScore" class="form-control" value="100" min="10" max="500"></div>' +
                '<div class="form-group"><label>合格线</label><input type="number" id="trnExamPassScore" class="form-control" value="80" min="0" max="500"></div>' +
            '</div>' +
            '<div class="exam-divider"></div>' +
            '<div class="form-group"><label>难度分布</label></div>' +
            '<div class="form-row-3">' +
                '<div class="form-group"><label>基础</label><input type="number" id="trnExamBasic" class="form-control" value="50" min="0" max="100"><span class="input-suffix">%</span></div>' +
                '<div class="form-group"><label>进阶</label><input type="number" id="trnExamAdv" class="form-control" value="30" min="0" max="100"><span class="input-suffix">%</span></div>' +
                '<div class="form-group"><label>挑战</label><input type="number" id="trnExamChallenge" class="form-control" value="20" min="0" max="100"><span class="input-suffix">%</span></div>' +
            '</div>';
    }

    function renderGenerationPage() {
        var container = document.getElementById('generationApp');
        if (!container) return;

        // 获取上次选中的知识库（跨卡片复用）
        var lastDb = (typeof knowledgeState !== 'undefined') ? knowledgeState.activeDatabase : '';
        var dbOptions = renderDatabaseOptions(lastDb);

        var cardsHtml = Object.keys(GEN_TYPES).map(function (type) {
            var cfg = GEN_TYPES[type];
            var sectionsHtml = cfg.sections.map(function (s, idx) {
                return renderSectionHtml(s, idx > 0);  // 第一个 section 展开，其余折叠
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
                        '<select class="form-control gen-db-select" id="genDb_' + type + '" data-type="' + type + '">' + dbOptions + '</select>' +
                    '</div>' +
                    sectionsHtml +
                '</div>' +
                '<div class="gen-card-footer">' +
                    '<button class="btn-primary" id="genBtn_' + type + '" onclick="startGenerationJob(\'' + type + '\')">开始生成</button>' +
                    '<span class="gen-status" id="genStatus_' + type + '"></span>' +
                '</div>' +
            '</div>';
        }).join('');

        container.innerHTML =
            '<div class="gen-type-row">' + cardsHtml + '</div>' +
            '<div class="gen-history-section panel-card panel-pad">' +
                '<div class="gen-history-header">' +
                    '<span class="gen-history-icon">📁</span>' +
                    '<h3>历史产物</h3>' +
                '</div>' +
                '<div id="genResults">' +
                    '<div class="empty-state"><p>暂无生成产物</p></div>' +
                '</div>' +
            '</div>';

        // 初始化时加载产物列表
        loadGenerationArtifacts();
    }

    // ==================== 折叠面板 ====================

    window.toggleGenSection = function (sectionId) {
        var section = document.getElementById('section_' + sectionId);
        if (section) { section.classList.toggle('collapsed'); }
    };

    window.toggleExamTypeCount = function (cb) {
        var countInput = document.querySelector('.exam-count-input[data-type="' + cb.value + '"]');
        if (countInput) {
            countInput.disabled = !cb.checked;
            if (!cb.checked) countInput.value = 0;
        }
        updateExamTotalCount();
    };

    window.updateExamTotalCount = function () {
        var inputs = document.querySelectorAll('.exam-count-input');
        var total = 0;
        inputs.forEach(function (el) { total += parseInt(el.value) || 0; });
        var totalEl = document.getElementById('trnExamTotalCount');
        if (totalEl) totalEl.value = total;
    };

    // ==================== 数据操作 ====================

    window.startGenerationJob = function (type) {
        var cfg = GEN_TYPES[type];
        if (!cfg) return;

        var statusEl = document.getElementById('genStatus_' + type);
        var btnEl = document.getElementById('genBtn_' + type);
        var dbSelect = document.getElementById('genDb_' + type);
        var database = dbSelect ? dbSelect.value.trim() : '';

        if (!database) {
            if (statusEl) statusEl.innerHTML = '<span style="color:var(--accent-color)">请先选择一个知识库</span>';
            return;
        }

        // 收集表单数据：使用显式 key 映射
        var payload = { type: type, database: database };
        cfg.sections.forEach(function (section) {
            section.fields.forEach(function (f) {
                var el = document.getElementById(f.id);
                if (!el) return;
                var rawValue = el.value !== undefined ? String(el.value).trim() : '';
                if (f.type === 'number') {
                    var num = parseInt(rawValue, 10);
                    payload[f.key] = isNaN(num) ? (f.value || 0) : num;
                } else {
                    payload[f.key] = rawValue || '';
                }
            });
        });

        // 培训类型：收集考试配置
        if (type === 'training') {
            // 题型+数量
            var questionConfig = [];
            var checkboxes = document.querySelectorAll('.trnExamType:checked');
            checkboxes.forEach(function (cb) {
                var countEl = document.querySelector('.exam-count-input[data-type="' + cb.value + '"]');
                var count = countEl ? parseInt(countEl.value) || 0 : 0;
                if (count > 0) {
                    questionConfig.push({ type: cb.value, count: count });
                }
            });
            if (questionConfig.length === 0) {
                questionConfig = [
                    { type: '选择题', count: 5 }, { type: '填空题', count: 3 },
                    { type: '简答题', count: 4 }, { type: '案例分析题', count: 3 }
                ];
            }
            payload['exam_question_config'] = questionConfig;
            payload['exam_total_score'] = parseInt(document.getElementById('trnExamTotalScore')?.value) || 100;
            payload['exam_pass_score'] = parseInt(document.getElementById('trnExamPassScore')?.value) || 80;
            var basic = parseInt(document.getElementById('trnExamBasic')?.value) || 50;
            var adv = parseInt(document.getElementById('trnExamAdv')?.value) || 30;
            var challenge = parseInt(document.getElementById('trnExamChallenge')?.value) || 20;
            var total = basic + adv + challenge;
            if (total > 0 && total !== 100) { basic = Math.round(basic/total*100); adv = Math.round(adv/total*100); challenge = 100-basic-adv; }
            payload['exam_difficulty_distribution'] = { '基础': basic, '进阶': adv, '挑战': challenge };
        }

        // UI 禁用
        if (btnEl) { btnEl.disabled = true; btnEl.textContent = '生成中...'; }
        if (statusEl) statusEl.innerHTML = '<span class="gen-job-stage stage-init">⏳ 初始化...</span>';

        WorkbenchAPI.postJson(
            WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/jobs',
            payload
        ).then(function (data) {
            if (statusEl) statusEl.innerHTML = '<span class="gen-job-stage stage-searching">🔍 检索知识库...</span>';
            pollJobStatus(data.job_id, type);
        }).catch(function (err) {
            if (statusEl) statusEl.innerHTML = '<span style="color:var(--accent-color)">生成失败: ' + err.message + '</span>';
            if (btnEl) { btnEl.disabled = false; btnEl.textContent = '开始生成'; }
        });
    };

    function pollJobStatus(jobId, type) {
        var statusEl = document.getElementById('genStatus_' + type);
        var btnEl = document.getElementById('genBtn_' + type);
        var maxAttempts = 120;  // 最多轮询 10 分钟（120 × 5s）

        function check() {
            if (maxAttempts-- <= 0) {
                if (statusEl) statusEl.innerHTML = '<span style="color:var(--warning-color)">⚠️ 生成超时，请稍后查看历史产物</span>';
                if (btnEl) { btnEl.disabled = false; btnEl.textContent = '开始生成'; }
                return;
            }

            setTimeout(function () {
                WorkbenchAPI.requestJson(
                    WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/jobs/' + jobId
                ).then(function (job) {
                    // 更新阶段显示
                    var stage = job.stage || '';
                    if (stage === 'searching' && statusEl) {
                        statusEl.innerHTML = '<span class="gen-job-stage stage-searching">🔍 检索知识库...</span>';
                    } else if (stage === 'generating' && statusEl) {
                        statusEl.innerHTML = '<span class="gen-job-stage stage-generating">✍️ AI 生成中...</span>';
                    } else if (job.status === 'completed') {
                        var files = (job.result && job.result.files) || [];
                        var fileCount = files.length;
                        var msg = '✅ 生成完成！共 ' + fileCount + ' 个文件';
                        if (statusEl) statusEl.innerHTML = '<span style="color:var(--success-color)">' + msg + '</span>';
                        if (btnEl) { btnEl.disabled = false; btnEl.textContent = '开始生成'; }
                        loadGenerationArtifacts();
                    } else if (job.status === 'failed') {
                        if (statusEl) statusEl.innerHTML = '<span style="color:var(--accent-color)" title="' + escapeHtml(job.error || '') + '">❌ 生成失败: ' + escapeHtml(job.error || '未知错误').substring(0, 60) + '</span>';
                        if (btnEl) { btnEl.disabled = false; btnEl.textContent = '开始生成'; }
                    } else {
                        check();
                    }
                }).catch(function () {
                    check();
                });
            }, 5000);
        }

        check();
    }

    // ==================== 产物列表 ====================

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
                '<div class="panel-card panel-pad gen-history-section">' +
                    '<div class="gen-history-header">' +
                        '<span class="gen-history-icon">📁</span>' +
                        '<h3>历史产物</h3>' +
                    '</div>' +
                    '<div class="empty-state">' +
                        '<p>暂无历史产物</p>' +
                    '</div>' +
                '</div>';
            return;
        }

        container.innerHTML =
            '<div class="panel-card panel-pad gen-history-section">' +
                '<div class="gen-history-header">' +
                    '<span class="gen-history-icon">📁</span>' +
                    '<h3>历史产物 <span class="badge">' + artifacts.length + '</span></h3>' +
                '</div>' +
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

    // ==================== 初始化 ====================

    document.addEventListener('DOMContentLoaded', function () {
        if (_initialized) return;
        _initialized = true;

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
})();
