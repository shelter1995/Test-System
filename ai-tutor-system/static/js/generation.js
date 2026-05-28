/**
 * 内容生成模块 v3
 * 支持 2 种 RAG 增强管线：解决方案（SCQA+MECE）+ 培训材料包（讲义+考试+README）
 */
(function () {
    var _initialized = false;
    var _sessionStartTime = Date.now();
    var _activeJob = null;
    var EXAM_QUESTION_TYPES = ['选择题', '填空题', '简答题', '案例分析题', '附加题'];
    var EXAM_DEFAULT_COUNTS = { '选择题': 5, '填空题': 3, '简答题': 4, '案例分析题': 3, '附加题': 1 };
    var EXAM_MAX_PER_TYPE = 30;
    var _syncingExamConfig = false;

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
                    return '<div class="form-group form-group-full"><label>' + f.label + '</label>' +
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
        var typeRows = EXAM_QUESTION_TYPES.map(function (t, i) {
            var checked = i < 4 ? ' checked' : '';  // 默认前4种选中
            var disabled = i < 4 ? '' : ' disabled';
            var count = i < 4 ? (EXAM_DEFAULT_COUNTS[t] || 1) : 0;
            return '<div class="exam-type-row">' +
                '<label class="exam-check"><input type="checkbox" class="trnExamType" value="' + t + '"' + checked + '> ' + t + '</label>' +
                '<input type="number" class="form-control exam-count-input" id="trnExamCount_' + i + '" value="' + count + '" min="0" max="' + EXAM_MAX_PER_TYPE + '" style="width:70px" data-type="' + t + '"' + disabled + '>' +
                '<span class="exam-count-label">题</span>' +
            '</div>';
        }).join('');

        return typeRows +
            '<div class="exam-divider"></div>' +
            '<div class="form-row-3">' +
                '<div class="form-group"><label>总题量</label><input type="number" id="trnExamTotalCount" class="form-control" value="15" min="0" max="' + (EXAM_QUESTION_TYPES.length * EXAM_MAX_PER_TYPE) + '"></div>' +
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

    var _activeGenType = 'solution';

    function renderGenForm(type, dbOptions) {
        var panel = document.getElementById('genFormPanel');
        if (!panel) return;

        var cfg = GEN_TYPES[type];
        var sectionsHtml = cfg.sections.map(function (s, idx) {
            return renderSectionHtml(s, idx > 0);
        }).join('');

        panel.innerHTML =
            '<div class="gen-form-inner">' +
                '<div class="form-group">' +
                    '<label>选择知识库</label>' +
                    '<select class="form-control" id="genDbSelect">' + dbOptions + '</select>' +
                '</div>' +
                sectionsHtml +
                '<div class="gen-form-actions">' +
                    '<button class="btn-primary gen-submit-btn" id="genSubmitBtn">' +
                        '开始生成 ' + cfg.name +
                    '</button>' +
                    '<span class="gen-status" id="genStatus"></span>' +
                '</div>' +
            '</div>';

        document.getElementById('genSubmitBtn').addEventListener('click', function () {
            startGenerationJob(type);
        });
        bindExamConfigEvents();
        restoreActiveJobUi(type);
    }

    function jobProgress(stage, status) {
        if (status === 'completed') return 100;
        if (status === 'failed') return 100;
        var map = {
            init: 8,
            searching: 22,
            generating: 55,
            generating_manual: 42,
            generating_exam: 68,
            generating_readme: 86,
        };
        return map[stage] || 12;
    }

    function renderJobStatus(job) {
        var statusEl = document.getElementById('genStatus');
        var btnEl = document.getElementById('genSubmitBtn');
        if (!statusEl || !job) return;

        var stage = job.stage || 'init';
        var stageMessages = {
            'init': '⏳ 初始化...',
            'searching': '🔍 检索知识库...',
            'generating': '✍️ AI 生成中...',
            'generating_manual': '📖 正在生成培训讲义...',
            'generating_exam': '📝 正在生成考试试题...',
            'generating_readme': '📋 正在生成使用说明...',
            'done': '✅ 生成完成',
            'error': '❌ 生成失败',
        };
        var msg = stageMessages[stage] || ('⏳ ' + stage);
        var stageClass = stage.startsWith('generating') ? 'stage-generating' :
                         stage === 'searching' ? 'stage-searching' :
                         job.status === 'failed' ? 'stage-error' :
                         job.status === 'completed' ? 'stage-done' : 'stage-init';
        var progress = jobProgress(stage, job.status);
        var warnings = Array.isArray(job.warnings) && job.warnings.length
            ? '<div class="gen-warning">' + escapeHtml(job.warnings[0]) + '</div>'
            : '';
        statusEl.innerHTML =
            '<span class="gen-job-stage ' + stageClass + '">' + msg + '</span>' +
            '<span class="gen-progress"><span style="width:' + progress + '%"></span></span>' +
            warnings;
        if (btnEl) {
            var running = job.status === 'running';
            btnEl.disabled = running;
            btnEl.textContent = running ? '生成中...' : '开始生成';
        }
    }

    function restoreActiveJobUi(type) {
        if (!_activeJob || _activeJob.type !== type || _activeJob.status !== 'running') return;
        renderJobStatus(_activeJob);
    }

    function renderGenerationPage() {
        var container = document.getElementById('generationApp');
        if (!container) return;

        // 移除占位样式，让内容正常撑满宽度
        container.classList.remove('section-placeholder');

        var lastDb = (typeof knowledgeState !== 'undefined') ? knowledgeState.activeDatabase : '';
        var dbOptions = renderDatabaseOptions(lastDb);

        // 恢复上次选中的类型，或默认 solution
        if (!GEN_TYPES[_activeGenType]) _activeGenType = 'solution';

        var tabsHtml = Object.keys(GEN_TYPES).map(function (type) {
            var cfg = GEN_TYPES[type];
            var activeClass = type === _activeGenType ? ' active' : '';
            return '<button class="gen-tab' + activeClass + '" data-gen-type="' + type + '">' +
                '<span class="gen-tab-icon">' + cfg.icon + '</span>' +
                '<span class="gen-tab-label">' + cfg.name + '</span>' +
            '</button>';
        }).join('');

        container.innerHTML =
            '<div class="gen-page-header">' +
                '<h2 class="gen-page-title">内容生成</h2>' +
                '<p class="gen-page-desc">基于知识库智能检索，自动生成个性化解决方案与培训材料</p>' +
            '</div>' +
            '<div class="gen-tab-bar">' + tabsHtml + '</div>' +
            '<div class="gen-form-panel panel-card" id="genFormPanel"></div>' +
            '<div class="gen-results-section" id="genResultsSection" style="display:none">' +
                '<div class="gen-results-header">' +
                    '<h4>本次产物</h4>' +
                    '<span class="gen-results-count" id="genResultsCount"></span>' +
                '</div>' +
                '<div id="genResults" class="gen-results-list"></div>' +
            '</div>';

        // 渲染当前标签页表单
        renderGenForm(_activeGenType, dbOptions);

        // 标签页切换
        container.querySelectorAll('.gen-tab').forEach(function (tab) {
            tab.addEventListener('click', function () {
                var type = tab.getAttribute('data-gen-type');
                if (type === _activeGenType) return;
                _activeGenType = type;
                container.querySelectorAll('.gen-tab').forEach(function (t) { t.classList.remove('active'); });
                tab.classList.add('active');
                var currentDb = document.getElementById('genDbSelect');
                var dbVal = currentDb ? currentDb.value : lastDb;
                renderGenForm(type, renderDatabaseOptions(dbVal));
            });
        });

        // 加载产物
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
            if (cb.checked) {
                var value = parseInt(countInput.value, 10) || 0;
                countInput.value = value > 0 ? Math.min(value, EXAM_MAX_PER_TYPE) : (EXAM_DEFAULT_COUNTS[cb.value] || 1);
            } else {
                countInput.value = 0;
            }
        }
        updateExamTotalCount();
    };

    window.updateExamTotalCount = function () {
        if (_syncingExamConfig) return;
        var inputs = document.querySelectorAll('.trnExamType:checked');
        var total = 0;
        inputs.forEach(function (cb) {
            var el = document.querySelector('.exam-count-input[data-type="' + cb.value + '"]');
            total += el ? (parseInt(el.value, 10) || 0) : 0;
        });
        var totalEl = document.getElementById('trnExamTotalCount');
        if (totalEl) totalEl.value = total;
    };

    function clampNumber(value, min, max) {
        var num = parseInt(value, 10);
        if (isNaN(num)) num = min;
        return Math.max(min, Math.min(max, num));
    }

    function selectedExamTypes() {
        return Array.prototype.slice.call(document.querySelectorAll('.trnExamType:checked'));
    }

    function bindExamConfigEvents() {
        var section = document.getElementById('section_trnExam');
        if (!section) return;

        section.querySelectorAll('.trnExamType').forEach(function (cb) {
            cb.addEventListener('change', function () {
                toggleExamTypeCount(cb);
            });
        });

        section.querySelectorAll('.exam-count-input').forEach(function (input) {
            input.addEventListener('input', function () {
                if (_syncingExamConfig) return;
                var type = input.getAttribute('data-type');
                var cb = section.querySelector('.trnExamType[value="' + type + '"]');
                var value = clampNumber(input.value, 0, EXAM_MAX_PER_TYPE);
                input.value = value;
                if (cb) {
                    cb.checked = value > 0;
                    input.disabled = value <= 0;
                }
                updateExamTotalCount();
            });
        });

        var totalEl = document.getElementById('trnExamTotalCount');
        if (totalEl) {
            totalEl.addEventListener('input', distributeExamTotalCount);
            totalEl.addEventListener('change', distributeExamTotalCount);
        }

        updateExamTotalCount();
    }

    function distributeExamTotalCount() {
        if (_syncingExamConfig) return;
        var totalEl = document.getElementById('trnExamTotalCount');
        if (!totalEl) return;

        var target = clampNumber(totalEl.value, 0, EXAM_QUESTION_TYPES.length * EXAM_MAX_PER_TYPE);
        _syncingExamConfig = true;
        try {
            var checked = selectedExamTypes();
            if (target === 0) {
                EXAM_QUESTION_TYPES.forEach(function (type) {
                    var cb = document.querySelector('.trnExamType[value="' + type + '"]');
                    var input = document.querySelector('.exam-count-input[data-type="' + type + '"]');
                    if (cb) cb.checked = false;
                    if (input) { input.value = 0; input.disabled = true; }
                });
                totalEl.value = 0;
                return;
            }

            if (checked.length === 0) {
                EXAM_QUESTION_TYPES.slice(0, 4).forEach(function (type) {
                    var cb = document.querySelector('.trnExamType[value="' + type + '"]');
                    if (cb) cb.checked = true;
                });
                checked = selectedExamTypes();
            }

            while (target > checked.length * EXAM_MAX_PER_TYPE && checked.length < EXAM_QUESTION_TYPES.length) {
                var nextType = EXAM_QUESTION_TYPES.find(function (type) {
                    var cb = document.querySelector('.trnExamType[value="' + type + '"]');
                    return cb && !cb.checked;
                });
                if (!nextType) break;
                var nextCb = document.querySelector('.trnExamType[value="' + nextType + '"]');
                if (nextCb) nextCb.checked = true;
                checked = selectedExamTypes();
            }

            if (target < checked.length) {
                checked.forEach(function (cb, index) {
                    var input = document.querySelector('.exam-count-input[data-type="' + cb.value + '"]');
                    var keep = index < target;
                    cb.checked = keep;
                    if (input) {
                        input.value = keep ? 1 : 0;
                        input.disabled = !keep;
                    }
                });
                totalEl.value = target;
                return;
            }

            checked = selectedExamTypes();
            var capacity = checked.length * EXAM_MAX_PER_TYPE;
            target = Math.min(target, capacity);
            var remaining = target - checked.length;
            var weights = checked.map(function (cb) {
                var input = document.querySelector('.exam-count-input[data-type="' + cb.value + '"]');
                return Math.max(1, parseInt(input && input.value, 10) || EXAM_DEFAULT_COUNTS[cb.value] || 1);
            });
            var weightTotal = weights.reduce(function (sum, value) { return sum + value; }, 0) || checked.length;
            var counts = checked.map(function (_, index) {
                return 1 + Math.floor(remaining * weights[index] / weightTotal);
            });
            var allocated = counts.reduce(function (sum, value) { return sum + value; }, 0);
            var cursor = 0;
            while (allocated < target) {
                if (counts[cursor] < EXAM_MAX_PER_TYPE) {
                    counts[cursor] += 1;
                    allocated += 1;
                }
                cursor = (cursor + 1) % counts.length;
            }

            checked.forEach(function (cb, index) {
                var input = document.querySelector('.exam-count-input[data-type="' + cb.value + '"]');
                if (input) {
                    input.disabled = false;
                    input.value = counts[index];
                }
            });
            EXAM_QUESTION_TYPES.forEach(function (type) {
                var cb = document.querySelector('.trnExamType[value="' + type + '"]');
                var input = document.querySelector('.exam-count-input[data-type="' + type + '"]');
                if (cb && !cb.checked && input) {
                    input.value = 0;
                    input.disabled = true;
                }
            });
            totalEl.value = target;
        } finally {
            _syncingExamConfig = false;
        }
    }

    // ==================== 数据操作 ====================

    window.startGenerationJob = function (type) {
        var cfg = GEN_TYPES[type];
        if (!cfg) return;

        var statusEl = document.getElementById('genStatus');
        var btnEl = document.getElementById('genSubmitBtn');
        var dbSelect = document.getElementById('genDbSelect');
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
            payload['exam_question_count'] = questionConfig.reduce(function (sum, item) { return sum + item.count; }, 0);
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
        _activeJob = { job_id: '', type: type, status: 'running', stage: 'init' };
        renderJobStatus(_activeJob);

        WorkbenchAPI.postJson(
            WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/jobs',
            payload
        ).then(function (data) {
            _activeJob = { job_id: data.job_id, type: type, status: 'running', stage: 'searching' };
            renderJobStatus(_activeJob);
            pollJobStatus(data.job_id, type);
        }).catch(function (err) {
            if (statusEl) statusEl.innerHTML = '<span style="color:var(--accent-color)">生成失败: ' + err.message + '</span>';
            if (btnEl) { btnEl.disabled = false; btnEl.textContent = '开始生成'; }
            _activeJob = null;
        });
    };

    function pollJobStatus(jobId, type) {
        var statusEl = document.getElementById('genStatus');
        var btnEl = document.getElementById('genSubmitBtn');
        var maxAttempts = 900;  // 最多轮询 15 分钟（900 × 1s）

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
                    _activeJob = Object.assign({}, job, { type: type });
                    renderJobStatus(_activeJob);

                    if (job.status === 'completed') {
                        var files = (job.result && job.result.files) || [];
                        var fileCount = files.length;
                        var msg = '✅ 生成完成！共 ' + fileCount + ' 个文件';
                        if (statusEl) statusEl.innerHTML = '<span style="color:var(--success-color)">' + msg + '</span>';
                        if (btnEl) { btnEl.disabled = false; btnEl.textContent = '开始生成'; }
                        _activeJob = null;
                        loadGenerationArtifacts();
                    } else if (job.status === 'failed') {
                        if (statusEl) statusEl.innerHTML = '<span style="color:var(--accent-color)" title="' + escapeHtml(job.error || '') + '">❌ 生成失败: ' + escapeHtml(job.error || '未知错误').substring(0, 60) + '</span>';
                        if (btnEl) { btnEl.disabled = false; btnEl.textContent = '开始生成'; }
                        _activeJob = null;
                    } else {
                        check();
                    }
                }).catch(function () {
                    check();
                });
            }, 1000);
        }

        check();
    }

    // ==================== 产物列表 ====================

    async function deleteGenerationArtifact(path) {
        if (!path) return;
        if (!confirm('确定要删除这个历史产物吗？\n\n删除后无法恢复。')) return;

        var options = { method: 'DELETE' };
        try {
            await WorkbenchAPI.requestJson(
                WorkbenchAPI.BASE_URLS.TUTOR_API +
                    '/generation/artifacts?path=' + encodeURIComponent(path),
                options
            );
            loadGenerationArtifacts();
        } catch (err) {
            alert('删除失败: ' + err.message);
        }
    }

    function bindArtifactDeleteButtons(root) {
        if (!root) return;
        root.querySelectorAll('.artifact-delete-btn').forEach(function (btn) {
            if (btn.dataset.bound === 'true') return;
            btn.dataset.bound = 'true';
            btn.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                deleteGenerationArtifact(btn.dataset.artifactPath || '');
            });
        });
    }

    function renderArtifactList(artifacts) {
        var container = document.getElementById('genResults');
        var section = document.getElementById('genResultsSection');
        if (!container || !section) return;

        if (!artifacts || artifacts.length === 0) {
            section.style.display = 'none';
            return;
        }

        section.style.display = 'block';
        var countEl = document.getElementById('genResultsCount');
        if (countEl) countEl.textContent = artifacts.length + ' 个文件';

        container.innerHTML =
            artifacts.map(function (a) {
                var sizeKB = a.size ? (a.size / 1024).toFixed(1) : '?';
                var downloadUrl = WorkbenchAPI.BASE_URLS.TUTOR_API +
                    '/generation/artifacts/download?path=' + encodeURIComponent(a.path);
                return (
                    '<div class="artifact-row">' +
                        '<span class="artifact-icon">📄</span>' +
                        '<span class="artifact-name" title="' + escapeHtml(a.path || '') + '">' +
                            escapeHtml(a.name) +
                        '</span>' +
                        '<span class="artifact-meta">' + sizeKB + ' KB</span>' +
                        '<a href="' + downloadUrl + '" target="_blank" class="download-link">下载</a>' +
                        '<button type="button" class="artifact-delete-btn" data-artifact-path="' + escapeHtml(a.path || '') + '">删除</button>' +
                    '</div>'
                );
            }).join('');
        bindArtifactDeleteButtons(container);
    }

    function loadGenerationArtifacts() {
        WorkbenchAPI.requestJson(
            WorkbenchAPI.BASE_URLS.TUTOR_API + '/generation/artifacts'
        ).then(function (data) {
            var artifacts = data.artifacts || [];
            // 顶栏下拉：展示全部历史产物
            renderTopbarDropdown(artifacts);
            // 内容生成页面底部：仅展示本次会话产物
            var sessionArtifacts = artifacts.filter(function (a) {
                return new Date(a.modified).getTime() > _sessionStartTime;
            });
            renderArtifactList(sessionArtifacts);
        }).catch(function (err) {
            console.warn('加载生成产物失败:', err.message);
        });
    }

    // ==================== 顶栏历史产物下拉 ====================

    var _topbarDropdownVisible = false;

    function renderTopbarDropdown(artifacts) {
        var panel = document.getElementById('topbarHistoryDropdown');
        if (!panel) return;

        if (!artifacts || artifacts.length === 0) {
            panel.innerHTML = '<div class="topbar-dropdown-empty">暂无历史产物</div>';
            return;
        }

        panel.innerHTML =
            '<div class="topbar-dropdown-list">' +
                artifacts.map(function (a) {
                    var sizeKB = a.size ? (a.size / 1024).toFixed(1) : '?';
                    var downloadUrl = WorkbenchAPI.BASE_URLS.TUTOR_API +
                        '/generation/artifacts/download?path=' + encodeURIComponent(a.path);
                    return (
                        '<div class="topbar-dropdown-row">' +
                            '<span class="topbar-dropdown-name" title="' + escapeHtml(a.path || '') + '">' +
                                escapeHtml(a.name) +
                            '</span>' +
                            '<span class="topbar-dropdown-meta">' + sizeKB + ' KB</span>' +
                            '<a href="' + downloadUrl + '" target="_blank" class="download-link">下载</a>' +
                            '<button type="button" class="artifact-delete-btn topbar-delete-btn" data-artifact-path="' + escapeHtml(a.path || '') + '">删除</button>' +
                        '</div>'
                    );
                }).join('') +
            '</div>';
        bindArtifactDeleteButtons(panel);
    }

    function toggleTopbarDropdown() {
        var panel = document.getElementById('topbarHistoryDropdown');
        if (!panel) return;
        _topbarDropdownVisible = !_topbarDropdownVisible;
        if (_topbarDropdownVisible) {
            panel.classList.add('visible');
            loadGenerationArtifacts();
        } else {
            panel.classList.remove('visible');
        }
    }

    function initTopbarHistoryButton() {
        var btn = document.getElementById('topbarHistoryBtn');
        if (!btn) return;

        // 创建下拉面板
        var dropdown = document.createElement('div');
        dropdown.id = 'topbarHistoryDropdown';
        dropdown.className = 'topbar-history-dropdown';
        dropdown.innerHTML = '<div class="topbar-dropdown-empty">加载中...</div>';
        var topbar = document.querySelector('.topbar');
        topbar.appendChild(dropdown);

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleTopbarDropdown();
        });

        document.addEventListener('click', function (e) {
            if (_topbarDropdownVisible && !dropdown.contains(e.target) && e.target !== btn) {
                _topbarDropdownVisible = false;
                dropdown.classList.remove('visible');
            }
        });
    }

    // ==================== 初始化 ====================

    document.addEventListener('DOMContentLoaded', function () {
        if (_initialized) return;
        _initialized = true;

        initTopbarHistoryButton();

        var observer = new MutationObserver(function () {
            var genSection = document.querySelector('[data-page="generation"]');
            if (genSection && genSection.classList.contains('active')) {
                renderGenerationPage();
            }
        });

        var sections = document.querySelectorAll('.page-section');
        sections.forEach(function (section) {
            observer.observe(section, { attributes: true, attributeFilter: ['class'] });
        });
    });
})();
