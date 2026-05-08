/**
 * AI话术陪练系统 - 前端逻辑
 */

// ==================== 配置 ====================
const CONFIG = {
    RAG_API: 'http://localhost:8003',
    TUTOR_API: 'http://localhost:8002'
};

// ==================== 状态管理 ====================
const state = {
    currentSession: null,
    currentScenario: null,
    messages: [],
    isProcessing: false
};

// ==================== DOM元素 ====================
const elements = {
    // 页面
    startPage: document.getElementById('startPage'),
    chatPage: document.getElementById('chatPage'),
    reportPage: document.getElementById('reportPage'),
    historyPage: document.getElementById('historyPage'),

    // 开始页面
    clientUnit: document.getElementById('clientUnit'),
    productName: document.getElementById('productName'),
    scenarioType: document.getElementById('scenarioType'),
    scenarioSelect: document.getElementById('scenarioSelect'),
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

// ==================== API调用 ====================

/**
 * 开始陪练会话
 */
async function startSession(scenarioId, clientUnit, product, scenarioType) {
    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/session/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scenario_id: scenarioId,
                client_unit: clientUnit,
                product: product,
                scenario_type: scenarioType
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
        alert('启动会话失败，请检查服务是否正常运行');
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
            const container = document.querySelector('.history-container');
            if (container) container.classList.remove('active');

            if (status === 'completed') {
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
    const container = document.querySelector('.history-container');
    if (container) container.classList.add('active');
    loadHistory();
}

function closeHistoryPanel() {
    const container = document.querySelector('.history-container');
    if (container) container.classList.remove('active');
}

function isHistoryPanelOpen() {
    const container = document.querySelector('.history-container');
    return Boolean(container && container.classList.contains('active'));
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

        const data = await startSession(scenarioId, clientUnit, product, scenarioType);

        // 更新信息看板
        updateInfoPanel(data.session_info, data.scenario);

        // 切换到对话页面
        showPage(elements.chatPage);
        elements.roundIndicator.textContent = '第 1 轮';

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

        const report = await endSession('detailed');
        showReport(report);

    } catch (error) {
        alert('结束会话失败: ' + error.message);
    } finally {
        elements.endBtn.disabled = false;
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

// ==================== 初始化 ====================

console.log('AI话术陪练系统已加载');
console.log('RAG服务:', CONFIG.RAG_API);
console.log('陪练服务:', CONFIG.TUTOR_API);
