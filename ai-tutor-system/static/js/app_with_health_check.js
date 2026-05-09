/**
 * AI话术陪练系统 - 前端逻辑（带服务健康检查）
 */

// ==================== 配置 ====================
const CONFIG = {
    RAG_API: 'http://localhost:8003',
    TUTOR_API: 'http://localhost:8002',
    HEALTH_CHECK_INTERVAL: 10000,  // 每10秒检查一次服务状态
    HEALTH_CHECK_TIMEOUT: 15000,
    HEALTH_CHECK_FAILURE_THRESHOLD: 2
};

// ==================== 状态管理 ====================
const state = {
    currentSession: null,
    currentScenario: null,
    messages: [],
    isProcessing: false,
    isChatting: false,  // 是否正在聊天中
    serviceStatus: {
        rag: 'unknown',  // unknown, checking, healthy, unhealthy
        tutor: 'unknown',
        lastCheck: null,
        ragFailures: 0,
        tutorFailures: 0
    },
    healthCheckTimer: null  // 健康检查定时器
};

// ==================== DOM元素 ====================
const elements = {
    // 页面
    startPage: document.getElementById('startPage'),
    chatPage: document.getElementById('chatPage'),
    reportPage: document.getElementById('reportPage'),
    historyPage: document.getElementById('historyPage'),
    serviceAlert: document.getElementById('serviceAlert'),  // 新增：服务警告横幅

    // 开始页面
    clientUnit: document.getElementById('clientUnit'),
    productName: document.getElementById('productName'),
    scenarioType: document.getElementById('scenarioType'),
    scenarioSelect: document.getElementById('scenarioSelect'),
    tutorDatabase: document.getElementById('tutorDatabase'),
    startBtn: document.getElementById('startBtn'),

    // 对话页面
    chatMessages: document.getElementById('chatMessages'),
    messageInput: document.getElementById('messageInput'),
    sendBtn: document.getElementById('sendBtn'),
    pauseBtn: document.getElementById('pauseBtn'),
    endBtn: document.getElementById('endBtn'),
    roundIndicator: document.getElementById('roundIndicator'),

    // 信息看板
    infoClientUnit: document.getElementById('infoClientUnit'),
    infoAiRole: document.getElementById('infoAiRole'),
    infoCustomerTraits: document.getElementById('infoCustomerTraits'),
    infoProduct: document.getElementById('infoProduct'),
    infoScenarioType: document.getElementById('infoScenarioType'),
    infoSuccessCriteria: document.getElementById('infoSuccessCriteria'),
    liveScore: document.getElementById('scoreValue'),
    liveSuggestions: document.getElementById('liveSuggestions'),
    knowledgeBox: document.getElementById('knowledgeBox'),

    // 报告页面
    reportScore: document.getElementById('reportScore'),
    reportRating: document.getElementById('reportRating'),
    reportHighlights: document.getElementById('reportHighlights'),
    reportImprovements: document.getElementById('reportImprovements'),
    reportSuggestions: document.getElementById('reportSuggestions'),
    backToStartBtn: document.getElementById('backToStartBtn'),
    viewHistoryBtn: document.getElementById('viewHistoryBtn'),

    // 历史记录
    historyBtn: document.getElementById('historyBtn'),
    closeHistoryBtn: document.getElementById('closeHistoryBtn'),
    historyList: document.getElementById('historyList'),

    // 自定义场景模态框
    customScenarioModal: document.getElementById('customScenarioModal'),
    closeModalBtn: document.getElementById('closeModalBtn'),
    createScenarioBtn: document.getElementById('createScenarioBtn')
};

// ==================== 服务健康检查 ====================

/**
 * 检查RAG服务健康状态
 */
async function checkRAGHealth() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), CONFIG.HEALTH_CHECK_TIMEOUT);

        // 尝试访问健康检查端点
        const response = await fetch(`${CONFIG.RAG_API}/health`, {
            method: 'GET',
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            return { healthy: true, message: 'RAG知识库服务正常' };
        } else {
            // 如果health端点失败，尝试根路径
            try {
                const rootResponse = await fetch(`${CONFIG.RAG_API}/`, {
                    method: 'GET',
                    signal: AbortSignal.timeout(CONFIG.HEALTH_CHECK_TIMEOUT)
                });
                if (rootResponse.ok) {
                    return { healthy: true, message: 'RAG知识库服务正常' };
                }
                return { healthy: false, message: 'RAG知识库服务异常' };
            } catch (rootError) {
                return { healthy: false, message: 'RAG知识库服务异常' };
            }
        }
    } catch (error) {
        // 只有在完全无法连接时才显示"未启动"
        if (error.name === 'AbortError' || error.name === 'TypeError') {
            return {
                healthy: false,
                message: 'RAG知识库服务未启动',
                action: '启动命令: cd rag-anything-api && python start.py'
            };
        }
        return {
            healthy: false,
            message: 'RAG知识库服务异常',
            action: '请检查RAG服务状态'
        };
    }
}

/**
 * 检查TUTOR服务健康状态
 */
async function checkTutorHealth() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), CONFIG.HEALTH_CHECK_TIMEOUT);

        const response = await fetch(`${CONFIG.TUTOR_API}/api/status`, {
            method: 'GET',
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            const data = await response.json();
            return {
                healthy: true,
                message: 'AI陪练服务正常',
                rag_available: data.rag_service?.available || false
            };
        } else {
            return { healthy: false, message: 'AI陪练服务异常' };
        }
    } catch (error) {
        return {
            healthy: false,
            message: 'AI陪练服务未启动',
            action: '启动命令: python tutor_backend.py'
        };
    }
}

/**
 * 更新服务状态UI
 */
function updateServiceStatusUI() {
    const { rag, tutor } = state.serviceStatus;

    // 创建或更新警告横幅
    let alertHTML = '';

    if (tutor === 'unhealthy') {
        alertHTML += `
            <div class="alert-item critical">
                <span class="alert-icon">🔴</span>
                <div class="alert-content">
                    <strong>AI陪练服务未启动</strong>
                    <p>请先启动服务：python tutor_backend.py</p>
                </div>
            </div>
        `;
    }

    if (rag === 'unhealthy') {
        alertHTML += `
            <div class="alert-item warning">
                <span class="alert-icon">⚠️</span>
                <div class="alert-content">
                    <strong>RAG知识库服务未启动</strong>
                    <p>AI将使用通用话术。请启动RAG-Anything服务：cd rag-anything-api && python start.py</p>
                </div>
            </div>
        `;
    }

    if (rag === 'healthy' && tutor === 'healthy') {
        alertHTML = `
            <div class="alert-item success">
                <span class="alert-icon">✅</span>
                <div class="alert-content">
                    <strong>所有服务正常</strong>
                    <p>RAG知识库和AI陪练服务运行中</p>
                </div>
            </div>
        `;
    }

    elements.serviceAlert.innerHTML = alertHTML;

    // 管理has-alert类
    if (alertHTML) {
        document.body.classList.add('has-alert');
    } else {
        document.body.classList.remove('has-alert');
    }

    // 根据状态禁用/启用开始按钮
    if (tutor === 'unhealthy') {
        elements.startBtn.disabled = true;
        elements.startBtn.title = '请先启动AI陪练服务';
    } else {
        elements.startBtn.disabled = false;
        elements.startBtn.title = '';
    }
}

/**
 * 定期检查所有服务健康状态
 */
async function healthCheckLoop() {
    // 如果正在聊天中，暂停健康检查
    if (state.isChatting) {
        state.healthCheckTimer = setTimeout(healthCheckLoop, CONFIG.HEALTH_CHECK_INTERVAL);
        return;
    }

    state.serviceStatus.lastCheck = new Date();

    try {
        // 并发检查两个服务
        const [ragStatus, tutorStatus] = await Promise.all([
            checkRAGHealth(),
            checkTutorHealth()
        ]);

        // 更新状态：RAG-Anything 在生成报告或重查询时可能短暂超时，连续失败才告警。
        state.serviceStatus.ragFailures = ragStatus.healthy ? 0 : state.serviceStatus.ragFailures + 1;
        state.serviceStatus.tutorFailures = tutorStatus.healthy ? 0 : state.serviceStatus.tutorFailures + 1;
        state.serviceStatus.rag = ragStatus.healthy
            ? 'healthy'
            : (state.serviceStatus.ragFailures >= CONFIG.HEALTH_CHECK_FAILURE_THRESHOLD ? 'unhealthy' : state.serviceStatus.rag);
        state.serviceStatus.tutor = tutorStatus.healthy
            ? 'healthy'
            : (state.serviceStatus.tutorFailures >= CONFIG.HEALTH_CHECK_FAILURE_THRESHOLD ? 'unhealthy' : state.serviceStatus.tutor);

        // 更新UI
        updateServiceStatusUI();

        console.log('健康检查完成:', {
            rag: ragStatus,
            tutor: tutorStatus
        });
    } catch (error) {
        console.error('健康检查失败:', error);
    }

    // 继续下一次检查
    state.healthCheckTimer = setTimeout(healthCheckLoop, CONFIG.HEALTH_CHECK_INTERVAL);
}

// ==================== API调用 ====================

/**
 * 开始陪练会话
 */
async function startSession(scenarioId, clientUnit, product, scenarioType, database) {
    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/session/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scenario_id: scenarioId,
                client_unit: clientUnit,
                product: product,
                scenario_type: scenarioType,
                database: database || undefined
            })
        });

        if (!response.ok) {
            throw new Error('启动会话失败');
        }

        const data = await response.json();
        state.currentSession = data.session_id;
        state.currentScenario = data.scenario;
        state.messages = [];

        return data;
    } catch (error) {
        console.error('启动会话错误:', error);
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
            throw new Error('无法连接到AI陪练服务，请确认服务已启动');
        }
        throw error;
    }
}

/**
 * 发送消息
 */
async function sendMessage(message) {
    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: state.currentSession,
                message: message,
                is_pause: false
            })
        });

        if (!response.ok) {
            throw new Error('发送消息失败');
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('发送消息错误:', error);
        throw error;
    }
}

/**
 * 结束会话
 */
async function endSession(detailLevel = 'simple') {
    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/session/end`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: state.currentSession,
                detail_level: detailLevel
            })
        });

        if (!response.ok) {
            throw new Error('结束会话失败');
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('结束会话错误:', error);
        throw error;
    }
}

/**
 * 获取历史记录
 */
async function getHistory() {
    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/history`);
        if (!response.ok) {
            throw new Error('获取历史记录失败');
        }
        const data = await response.json();
        return data.history;
    } catch (error) {
        console.error('获取历史记录错误:', error);
        return [];
    }
}

// ==================== UI更新 ====================

/**
 * 显示页面
 */
function showPage(pageElement) {
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    pageElement.classList.add('active');
}

/**
 * 添加系统消息
 */
function addSystemMessage(content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message system';

    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
    });

    const messageHTML = `
        <div class="message-header">
            <div class="message-avatar">💡</div>
            <div class="message-role">系统提示</div>
            <div class="message-time">${timeStr}</div>
        </div>
        <div class="message-content system-content">${content}</div>
    `;

    messageDiv.innerHTML = messageHTML;
    elements.chatMessages.appendChild(messageDiv);

    // 滚动到底部
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

/**
 * 添加消息到对话
 */
function addMessage(role, content, evaluation = null, debugInfo = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
    });

    const avatar = role === 'ai' ? '👤' : '💁';
    const roleName = role === 'ai' ? 'AI客户' : '销售经理（您）';

    let messageHTML = `
        <div class="message-header">
            <div class="message-avatar">${avatar}</div>
            <div class="message-role">${roleName}</div>
            <div class="message-time">${timeStr}</div>
        </div>
        <div class="message-content">${content}</div>
    `;

    // 显示知识库使用情况（仅AI消息）
    if (role === 'ai' && debugInfo && debugInfo.knowledge_found !== undefined) {
        const knowledgeCount = debugInfo.knowledge_found || 0;
        const knowledgeStatus = knowledgeCount > 0 ?
            '📚 知识库' :
            '⚠️ 知识库为空';

        messageHTML += `
            <div class="message-knowledge">
                <span class="knowledge-status">${knowledgeStatus}</span>
                <span class="knowledge-detail">
                    检索到${knowledgeCount}条相关信息
                </span>
            </div>
        `;
    }

    if (evaluation && evaluation.overall_score > 0) {
        const suggestions = evaluation.suggestions || [];
        messageHTML += `
            <div class="message-evaluation">
                <span class="evaluation-score">
                    评分: ${evaluation.overall_score}分
                </span>
                ${suggestions.length > 0 ?
                    '<br>建议: ' + suggestions.join('；') : ''}
            </div>
        `;
    }

    messageDiv.innerHTML = messageHTML;
    elements.chatMessages.appendChild(messageDiv);

    // 滚动到底部
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

/**
 * 更新信息看板
 */
function updateInfoPanel(sessionInfo, scenario) {
    elements.infoClientUnit.textContent = sessionInfo.client_unit;
    elements.infoAiRole.textContent = scenario.ai_role;
    elements.infoProduct.textContent = sessionInfo.product;
    elements.infoScenarioType.textContent = sessionInfo.scenario_type;

    // 客户特点
    const traits = scenario.customer_traits || [];
    elements.infoCustomerTraits.textContent = traits.join('、');

    // 成功标准
    const criteria = scenario.success_criteria || [];
    elements.infoSuccessCriteria.innerHTML = criteria.map(c =>
        `<li>${c}</li>`
    ).join('');
}

/**
 * 更新实时建议
 */
function updateLiveSuggestions(evaluation) {
    if (!evaluation || evaluation.overall_score === 0) {
        elements.liveScore.textContent = '-';
        elements.liveSuggestions.innerHTML = '<p class="suggestion-text">开始对话后将显示实时建议</p>';
        return;
    }

    // 更新评分
    elements.liveScore.textContent = evaluation.overall_score;

    // 更新建议
    const suggestions = evaluation.suggestions || [];
    if (suggestions.length > 0) {
        elements.liveSuggestions.innerHTML = suggestions.map(s =>
            `<p class="suggestion-text">💡 ${s}</p>`
        ).join('');
    } else {
        elements.liveSuggestions.innerHTML = '<p class="suggestion-text">继续保持！</p>';
    }
}

/**
 * 更新知识库看板
 */
function updateKnowledgeBox(debugInfo) {
    if (!debugInfo) return;

    const totalFound = debugInfo.knowledge_found || 0;
    const productCount = debugInfo.product_knowledge || 0;
    const salesCount = debugInfo.sales_knowledge || 0;
    const objectionCount = debugInfo.objection_knowledge || 0;

    let knowledgeHTML = '<div class="knowledge-stats">';

    if (totalFound > 0) {
        knowledgeHTML += `
            <div class="stat-item success">
                <span class="stat-icon">✅</span>
                <span class="stat-text">知识库正常</span>
            </div>
            <div class="stat-details">
                <div class="stat-detail">
                    <span class="stat-label">产品信息：</span>
                    <span class="stat-value">${productCount}条</span>
                </div>
                <div class="stat-detail">
                    <span class="stat-label">话术技巧：</span>
                    <span class="stat-value">${salesCount}条</span>
                </div>
                <div class="stat-detail">
                    <span class="stat-label">异议处理：</span>
                    <span class="stat-value">${objectionCount}条</span>
                </div>
            </div>
        `;
    } else {
        knowledgeHTML += `
            <div class="stat-item warning">
                <span class="stat-icon">⚠️</span>
                <span class="stat-text">知识库为空</span>
            </div>
            <div class="stat-details">
                <p class="warning-text">AI将使用通用话术，请上传产品文档到知识库</p>
            </div>
        `;
    }

    knowledgeHTML += '</div>';

    elements.knowledgeBox.innerHTML = knowledgeHTML;
}

/**
 * 显示报告
 */
function showReport(report) {
    elements.reportScore.textContent = report.total_score;
    elements.reportRating.textContent = report.rating_text;

    // 亮点
    elements.reportHighlights.innerHTML = report.highlights.map(h =>
        `<li>${h}</li>`
    ).join('');

    // 待改进
    elements.reportImprovements.innerHTML = report.improvements.map(i =>
        `<li>${i}</li>`
    ).join('');

    // 建议
    elements.reportSuggestions.innerHTML = report.suggestions.map(s =>
        `<li>${s}</li>`
    ).join('');

    showPage(elements.reportPage);
}

/**
 * 加载历史记录
 */
async function loadHistory() {
    const history = await getHistory();

    if (history.length === 0) {
        elements.historyList.innerHTML = '<p class="suggestion-text">暂无历史记录</p>';
        return;
    }

    elements.historyList.innerHTML = history.map(item => {
        const scoreHTML = item.score != null
            ? `<span class="history-score">${item.score}分${item.rating ? ' · ' + item.rating : ''}</span>`
            : '';
        const statusBadge = item.status === 'completed'
            ? '<span class="history-status completed">已完成</span>'
            : '<span class="history-status active">进行中</span>';

        return `
        <div class="history-item" data-session-id="${item.session_id}" data-status="${item.status}">
            <div class="history-item-header">
                <span class="history-scenario">${item.scenario}</span>
                <span class="history-date">${new Date(item.created_at).toLocaleDateString()}</span>
            </div>
            <div class="history-details">
                ${item.client_unit} · ${item.product} · ${item.rounds}轮对话
            </div>
            <div class="history-meta">
                ${statusBadge}
                ${scoreHTML}
            </div>
        </div>
    `}).join('');

    // 添加点击事件
    document.querySelectorAll('.history-item').forEach(item => {
        item.addEventListener('click', async () => {
            const sessionId = item.dataset.sessionId;
            const status = item.dataset.status;

            // 关闭历史侧边栏
            closeHistoryPanel();

            if (status === 'completed') {
                // 已完成的会话：尝试加载报告
                try {
                    const response = await fetch(`${CONFIG.TUTOR_API}/session/${sessionId}`);
                    if (response.ok) {
                        const sessionData = await response.json();
                        if (sessionData.report) {
                            showReport(sessionData.report);
                        } else {
                            alert('该会话暂无总结报告');
                        }
                    }
                } catch (error) {
                    alert('加载会话详情失败');
                }
            } else {
                alert(`该会话未完成（${sessionId}）`);
            }
        });
    });
}

function openHistoryPanel() {
    elements.historyPage.classList.add('active');
    const container = document.querySelector('.history-container');
    if (container) container.classList.add('active');
    loadHistory();
}

function closeHistoryPanel() {
    const container = document.querySelector('.history-container');
    if (container) container.classList.remove('active');
    elements.historyPage.classList.remove('active');
}

function isHistoryPanelOpen() {
    const container = document.querySelector('.history-container');
    return Boolean(
        container &&
        container.classList.contains('active') &&
        elements.historyPage.classList.contains('active')
    );
}

// ==================== 事件处理 ====================

/**
 * 开始陪练
 */
async function handleStart() {
    const scenarioId = elements.scenarioSelect.value;
    const clientUnit = elements.clientUnit.value.trim();
    const product = elements.productName.value.trim();
    const scenarioType = elements.scenarioType.value.trim();
    const database = elements.tutorDatabase?.value || '';

    if (!scenarioId) {
        alert('请选择一个场景');
        return;
    }

    if (!clientUnit || !product || !scenarioType) {
        alert('请填写完整信息');
        return;
    }

    try {
        elements.startBtn.disabled = true;
        elements.startBtn.textContent = '启动中...';

        const data = await startSession(scenarioId, clientUnit, product, scenarioType, database);

        // 更新信息看板
        updateInfoPanel(data.session_info, data.scenario);

        // 切换到对话页面
        showPage(elements.chatPage);
        elements.roundIndicator.textContent = '第 1 轮';
        
        // 设置聊天状态，暂停健康检查
        state.isChatting = true;

        // 根据返回的数据决定谁先开始
        if (data.user_should_start) {
            // 显示系统提示，让用户先开始
            addSystemMessage(data.opening_message);
        } else {
            // AI先开始（备用逻辑）
            addMessage('ai', data.opening_message);
        }

    } catch (error) {
        alert('启动失败: ' + error.message);
    } finally {
        elements.startBtn.disabled = false;
        elements.startBtn.textContent = '开始陪练 🚀';
    }
}

/**
 * 发送消息
 */
async function handleSend() {
    const message = elements.messageInput.value.trim();

    if (!message || state.isProcessing) {
        return;
    }

    state.isProcessing = true;
    elements.sendBtn.disabled = true;
    elements.sendBtn.textContent = '发送中...';

    // 添加用户消息
    addMessage('user', message);
    elements.messageInput.value = '';

    try {
        const data = await sendMessage(message);

        // 添加AI回复（带知识库调试信息）
        addMessage('ai', data.ai_response, data.evaluation, data.debug_info);

        // 更新轮次
        elements.roundIndicator.textContent = `第 ${data.round} 轮`;

        // 更新实时建议
        updateLiveSuggestions(data.evaluation);

        // 更新知识库看板
        if (data.debug_info) {
            updateKnowledgeBox(data.debug_info);
        }

    } catch (error) {
        alert('发送失败: ' + error.message);
    } finally {
        state.isProcessing = false;
        elements.sendBtn.disabled = false;
        elements.sendBtn.textContent = '发送 🚀';
        elements.messageInput.focus();
    }
}

/**
 * 结束会话
 */
async function handleEnd() {
    if (!confirm('确定要结束当前会话吗？')) {
        return;
    }

    try {
        elements.endBtn.disabled = true;
        elements.endBtn.textContent = '生成报告中...';

        const report = await endSession('simple');
        showReport(report);
        
        // 结束聊天，恢复健康检查
        state.isChatting = false;

    } catch (error) {
        alert('结束会话失败: ' + error.message);
    } finally {
        elements.endBtn.disabled = false;
        elements.endBtn.textContent = '🏁';
    }
}

/**
 * 暂停获取反馈
 */
async function handlePause() {
    try {
        elements.pauseBtn.disabled = true;

        const response = await fetch(`${CONFIG.TUTOR_API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: state.currentSession,
                message: '',
                is_pause: true
            })
        });

        if (response.ok) {
            const data = await response.json();
            if (data.evaluation) {
                updateLiveSuggestions(data.evaluation);
                const suggestions = data.evaluation.suggestions || [];
                alert('当前评分: ' + data.evaluation.overall_score + '分\n' +
                      '建议: ' + (suggestions.length > 0 ? suggestions.join('；') : '暂无建议'));
            }
        }
    } catch (error) {
        console.error('获取反馈错误:', error);
    } finally {
        elements.pauseBtn.disabled = false;
    }
}

// ==================== 事件监听 ====================

// 开始按钮
elements.startBtn.addEventListener('click', handleStart);

// 发送按钮
elements.sendBtn.addEventListener('click', handleSend);

// 输入框快捷键
elements.messageInput.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') {
        handleSend();
    }
});

// 暂停按钮
elements.pauseBtn.addEventListener('click', handlePause);

// 结束按钮
elements.endBtn.addEventListener('click', handleEnd);

// 返回首页
elements.backToStartBtn.addEventListener('click', () => {
    showPage(elements.startPage);
    state.currentSession = null;
    state.messages = [];
    elements.chatMessages.innerHTML = '';
    // 结束聊天，恢复健康检查
    state.isChatting = false;
});

// 查看历史
elements.viewHistoryBtn.addEventListener('click', () => {
    openHistoryPanel();
});

// 历史记录按钮
elements.historyBtn.addEventListener('click', () => {
    if (isHistoryPanelOpen()) {
        closeHistoryPanel();
    } else {
        openHistoryPanel();
    }
});

// 关闭历史记录
elements.closeHistoryBtn.addEventListener('click', () => {
    closeHistoryPanel();
});

elements.historyPage.addEventListener('click', (e) => {
    if (e.target === elements.historyPage) {
        closeHistoryPanel();
    }
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && elements.historyPage.classList.contains('active')) {
        closeHistoryPanel();
    }
});

// 场景选择
elements.scenarioSelect.addEventListener('change', (e) => {
    if (e.target.value === 'custom') {
        elements.customScenarioModal.classList.add('active');
    }
});

// 关闭模态框
elements.closeModalBtn.addEventListener('click', () => {
    elements.customScenarioModal.classList.remove('active');
    elements.scenarioSelect.value = '';
});

// 创建自定义场景
elements.createScenarioBtn.addEventListener('click', async () => {
    const name = document.getElementById('customScenarioName').value.trim();
    const aiRole = document.getElementById('customAiRole').value.trim();
    const userRole = document.getElementById('customUserRole').value.trim();
    const description = document.getElementById('customScenarioDesc').value.trim();
    const customerTraits = document.getElementById('customCustomerTraits').value.trim().split('\n').filter(t => t);
    const aiStrategy = document.getElementById('customAiStrategy').value.trim().split('\n').filter(s => s);
    const successCriteria = document.getElementById('customSuccessCriteria').value.trim().split('\n').filter(s => s);

    if (!name || !aiRole || !description) {
        alert('请填写完整信息');
        return;
    }

    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/scenarios/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                ai_role: aiRole,
                user_role: userRole,
                description,
                customer_traits: customerTraits,
                ai_strategy: aiStrategy,
                success_criteria: successCriteria
            })
        });

        if (response.ok) {
            const data = await response.json();
            alert('场景创建成功！');
            elements.customScenarioModal.classList.remove('active');

            // 添加到选择列表
            const option = document.createElement('option');
            option.value = data.scenario_id;
            option.textContent = data.scenario.name;
            elements.scenarioSelect.appendChild(option);
            elements.scenarioSelect.value = data.scenario_id;
        } else {
            alert('创建场景失败');
        }
    } catch (error) {
        console.error('创建场景错误:', error);
        alert('创建场景失败');
    }
});

// 点击模态框背景关闭
elements.customScenarioModal.addEventListener('click', (e) => {
    if (e.target === elements.customScenarioModal) {
        elements.customScenarioModal.classList.remove('active');
    }
});

// ==================== 知识库下拉 ====================

/**
 * 从 RAG API 获取知识库列表并填充 tutorDatabase 下拉框
 */
async function populateTutorDatabaseDropdown() {
    const select = elements.tutorDatabase;
    if (!select) return;

    try {
        const resp = await fetch(`${CONFIG.RAG_API}/db/list`, {
            signal: AbortSignal.timeout(CONFIG.HEALTH_CHECK_TIMEOUT)
        });
        if (!resp.ok) return;

        const data = await resp.json();
        const databases = Array.isArray(data) ? data : (data.databases || []);

        // 保留第一个 "自动选择" 选项，清空其余
        while (select.options.length > 1) {
            select.remove(1);
        }

        databases.forEach(db => {
            const id = typeof db === 'string' ? db : db.id;
            const name = typeof db === 'string' ? db : (db.name || db.id);
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = name;
            select.appendChild(opt);
        });
    } catch (err) {
        console.warn('加载知识库列表失败（陪练下拉）:', err.message);
    }
}

// ==================== 初始化 ====================

console.log('AI话术陪练系统已加载（带服务健康检查）');
console.log('RAG服务:', CONFIG.RAG_API);
console.log('陪练服务:', CONFIG.TUTOR_API);

// 启动健康检查循环
healthCheckLoop();

// 填充知识库下拉
populateTutorDatabaseDropdown();
