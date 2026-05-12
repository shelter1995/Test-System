/**
 * AI话术陪练系统 — 前端逻辑（SSE 流式 v2.1）
 */
// ==================== 配置 ====================
const CONFIG = {
    RAG_API: 'http://localhost:8003',
    TUTOR_API: 'http://localhost:8002',
    HEALTH_CHECK_INTERVAL: 10000,
    HEALTH_CHECK_TIMEOUT: 15000,
    HEALTH_CHECK_FAILURE_THRESHOLD: 2
};

// ==================== 状态 ====================
const state = {
    currentSession: null,
    currentScenario: null,
    messages: [],
    isProcessing: false,
    isChatting: false,
    abortController: null,    // SSE 连接控制
    currentRound: 0,          // 当前轮次
    pendingEval: null,        // 待处理的评分（AbortController）
    serviceStatus: {
        rag: 'unknown',
        tutor: 'unknown',
        lastCheck: null,
        ragFailures: 0,
        tutorFailures: 0
    },
    healthCheckTimer: null
};

// ==================== DOM ====================
const elements = {
    startPage: document.getElementById('startPage'),
    chatPage: document.getElementById('chatPage'),
    reportPage: document.getElementById('reportPage'),
    historyPage: document.getElementById('historyPage'),
    serviceAlert: document.getElementById('serviceAlert'),

    clientUnit: document.getElementById('clientUnit'),
    productName: document.getElementById('productName'),
    scenarioType: document.getElementById('scenarioType'),
    scenarioSelect: document.getElementById('scenarioSelect'),
    tutorDatabase: document.getElementById('tutorDatabase'),
    startBtn: document.getElementById('startBtn'),

    chatMessages: document.getElementById('chatMessages'),
    messageInput: document.getElementById('messageInput'),
    sendBtn: document.getElementById('sendBtn'),
    pauseBtn: document.getElementById('pauseBtn'),
    endBtn: document.getElementById('endBtn'),
    roundIndicator: document.getElementById('roundIndicator'),

    infoClientUnit: document.getElementById('infoClientUnit'),
    infoAiRole: document.getElementById('infoAiRole'),
    infoCustomerTraits: document.getElementById('infoCustomerTraits'),
    infoProduct: document.getElementById('infoProduct'),
    infoScenarioType: document.getElementById('infoScenarioType'),
    infoSuccessCriteria: document.getElementById('infoSuccessCriteria'),
    liveScore: document.getElementById('scoreValue'),
    liveSuggestions: document.getElementById('liveSuggestions'),
    knowledgeBox: document.getElementById('knowledgeBox'),

    reportScore: document.getElementById('reportScore'),
    reportRating: document.getElementById('reportRating'),
    reportHighlights: document.getElementById('reportHighlights'),
    reportImprovements: document.getElementById('reportImprovements'),
    reportSuggestions: document.getElementById('reportSuggestions'),
    backToStartBtn: document.getElementById('backToStartBtn'),
    viewHistoryBtn: document.getElementById('viewHistoryBtn'),

    historyBtn: document.getElementById('historyBtn'),
    closeHistoryBtn: document.getElementById('closeHistoryBtn'),
    historyList: document.getElementById('historyList'),

    customScenarioModal: document.getElementById('customScenarioModal'),
    closeModalBtn: document.getElementById('closeModalBtn'),
    createScenarioBtn: document.getElementById('createScenarioBtn'),

    // 新增：SSE 流式 UI
    stageIndicator: document.getElementById('stageIndicator'),
    toastContainer: document.getElementById('toastContainer')
};

// ==================== 健康检查（不变） ====================

async function checkRAGHealth() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), CONFIG.HEALTH_CHECK_TIMEOUT);
        const response = await fetch(`${CONFIG.RAG_API}/health`, {
            method: 'GET', signal: controller.signal
        });
        clearTimeout(timeoutId);
        if (response.ok) return { healthy: true, message: 'RAG知识库服务正常' };
        try {
            const rootResp = await fetch(`${CONFIG.RAG_API}/`, {
                method: 'GET', signal: AbortSignal.timeout(CONFIG.HEALTH_CHECK_TIMEOUT)
            });
            if (rootResp.ok) return { healthy: true, message: 'RAG知识库服务正常' };
            return { healthy: false, message: 'RAG知识库服务异常' };
        } catch (e) {
            return { healthy: false, message: 'RAG知识库服务异常' };
        }
    } catch (error) {
        if (error.name === 'AbortError' || error.name === 'TypeError') {
            return { healthy: false, message: 'RAG知识库服务未启动',
                     action: '启动命令: cd rag-anything-api && python start.py' };
        }
        return { healthy: false, message: 'RAG知识库服务异常' };
    }
}

async function checkTutorHealth() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), CONFIG.HEALTH_CHECK_TIMEOUT);
        const response = await fetch(`${CONFIG.TUTOR_API}/api/status`, {
            method: 'GET', signal: controller.signal
        });
        clearTimeout(timeoutId);
        if (response.ok) {
            const data = await response.json();
            return { healthy: true, message: 'AI陪练服务正常',
                     rag_available: data.rag_service?.available || false };
        }
        return { healthy: false, message: 'AI陪练服务异常' };
    } catch (error) {
        return { healthy: false, message: 'AI陪练服务未启动',
                 action: '启动命令: python tutor_backend.py' };
    }
}

function updateServiceStatusUI() {
    const { rag, tutor } = state.serviceStatus;
    let alertHTML = '';
    if (tutor === 'unhealthy') {
        alertHTML += `<div class="alert-item critical"><span class="alert-icon">🔴</span>
            <div class="alert-content"><strong>AI陪练服务未启动</strong>
            <p>请先启动服务：python tutor_backend.py</p></div></div>`;
    }
    if (rag === 'unhealthy') {
        alertHTML += `<div class="alert-item warning"><span class="alert-icon">⚠️</span>
            <div class="alert-content"><strong>RAG知识库服务未启动</strong>
            <p>AI将使用通用话术。请启动RAG-Anything服务</p></div></div>`;
    }
    if (rag === 'healthy' && tutor === 'healthy') {
        alertHTML = `<div class="alert-item success"><span class="alert-icon">✅</span>
            <div class="alert-content"><strong>所有服务正常</strong>
            <p>RAG知识库和AI陪练服务运行中</p></div></div>`;
    }
    elements.serviceAlert.innerHTML = alertHTML;
    document.body.classList.toggle('has-alert', !!alertHTML);
    elements.startBtn.disabled = (tutor === 'unhealthy');
    elements.startBtn.title = tutor === 'unhealthy' ? '请先启动AI陪练服务' : '';
}

async function healthCheckLoop() {
    if (state.isChatting) {
        state.healthCheckTimer = setTimeout(healthCheckLoop, CONFIG.HEALTH_CHECK_INTERVAL);
        return;
    }
    state.serviceStatus.lastCheck = new Date();
    try {
        const [ragStatus, tutorStatus] = await Promise.all([checkRAGHealth(), checkTutorHealth()]);
        state.serviceStatus.ragFailures = ragStatus.healthy ? 0 : state.serviceStatus.ragFailures + 1;
        state.serviceStatus.tutorFailures = tutorStatus.healthy ? 0 : state.serviceStatus.tutorFailures + 1;
        state.serviceStatus.rag = ragStatus.healthy ? 'healthy'
            : (state.serviceStatus.ragFailures >= CONFIG.HEALTH_CHECK_FAILURE_THRESHOLD ? 'unhealthy' : state.serviceStatus.rag);
        state.serviceStatus.tutor = tutorStatus.healthy ? 'healthy'
            : (state.serviceStatus.tutorFailures >= CONFIG.HEALTH_CHECK_FAILURE_THRESHOLD ? 'unhealthy' : state.serviceStatus.tutor);
        updateServiceStatusUI();
    } catch (error) {
        console.error('健康检查失败:', error);
    }
    state.healthCheckTimer = setTimeout(healthCheckLoop, CONFIG.HEALTH_CHECK_INTERVAL);
}

// ==================== API ====================

async function startSession(scenarioId, clientUnit, product, scenarioType, database) {
    const response = await fetch(`${CONFIG.TUTOR_API}/session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            scenario_id: scenarioId, client_unit: clientUnit,
            product: product, scenario_type: scenarioType, database: database || undefined
        })
    });
    if (!response.ok) throw new Error('启动会话失败');
    const data = await response.json();
    state.currentSession = data.session_id;
    state.currentScenario = data.scenario;
    state.messages = [];
    return data;
}

async function endSession(detailLevel = 'simple') {
    const response = await fetch(`${CONFIG.TUTOR_API}/session/end`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: state.currentSession, detail_level: detailLevel })
    });
    if (!response.ok) throw new Error('结束会话失败');
    return await response.json();
}

async function getHistory() {
    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/history`);
        if (!response.ok) throw new Error('获取历史记录失败');
        const data = await response.json();
        return data.history;
    } catch (error) {
        console.error('获取历史记录错误:', error);
        return [];
    }
}

// ==================== SSE 流式对话 ====================

/**
 * 设置输入锁定状态
 */
function setInputLocked(locked) {
    elements.sendBtn.disabled = locked;
    elements.sendBtn.textContent = locked ? '生成中...' : '发送';
    elements.messageInput.disabled = locked;
    if (!locked) elements.messageInput.focus();
}

/**
 * 显示阶段指示器
 */
function showStageIndicator(stage, message) {
    let el = elements.stageIndicator;
    if (!el) {
        el = document.createElement('div');
        el.id = 'stageIndicator';
        el.className = 'stage-indicator';
        elements.chatMessages.appendChild(el);
        elements.stageIndicator = el;
    }
    const icons = {
        rag_searching: '📚', rag_complete: '✅',
        ai_generating: '💭', done: ''
    };
    const icon = icons[stage] || '⏳';
    el.innerHTML = `<span class="stage-icon">${icon}</span>
        <span class="stage-text">${message}</span>
        <span class="stage-bar"><span class="stage-bar-fill"></span></span>`;
    el.className = 'stage-indicator active';
    el.style.display = 'block';
}

function hideStageIndicator() {
    const el = elements.stageIndicator;
    if (el) {
        el.classList.add('fade-out');
        setTimeout(() => { el.style.display = 'none'; el.classList.remove('fade-out', 'active'); }, 300);
    }
}

/**
 * Toast 通知
 */
function showToast(message, type = 'info') {
    let container = elements.toastContainer;
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
        elements.toastContainer = container;
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

/**
 * 创建/获取 AI 消息气泡（用于流式追加）
 */
function createOrGetAIBubble() {
    let bubble = document.querySelector('.message.ai.streaming');
    if (bubble) return bubble;

    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ai streaming';
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    messageDiv.innerHTML = `<div class="message-header">
        <div class="message-avatar">👤</div>
        <div class="message-role">AI客户</div>
        <div class="message-time">${timeStr}</div>
    </div>
    <div class="message-content"></div>
    <span class="typing-cursor">|</span>`;
    elements.chatMessages.appendChild(messageDiv);
    scrollToBottom();
    return messageDiv;
}

function finalizeAIBubble(content) {
    const bubble = document.querySelector('.message.ai.streaming');
    if (!bubble) return;
    bubble.classList.remove('streaming');
    const cursor = bubble.querySelector('.typing-cursor');
    if (cursor) cursor.remove();
    // 设置最终内容
    bubble.querySelector('.message-content').textContent = content;
    state.messages.push({ role: 'ai', content: content });
}

/**
 * 显示评分卡片
 */
function showEvaluationCard(evaluation, roundNum) {
    if (!evaluation || !evaluation.overall_score) return;

    const existing = document.querySelector('.eval-card');
    if (existing) existing.remove();

    const dims = evaluation.dimension_scores || {};
    const dimBars = Object.entries(dims).map(([name, d]) => {
        const score = d.score || 0;
        const cls = score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low';
        return `<div class="eval-dim">
            <span class="eval-dim-name">${name}</span>
            <span class="eval-dim-bar"><span class="eval-dim-fill ${cls}" style="width:${score}%"></span></span>
            <span class="eval-dim-score">${score}</span>
        </div>`;
    }).join('');

    const card = document.createElement('div');
    card.className = 'eval-card';
    card.innerHTML = `<div class="eval-card-header">
        <span class="eval-card-round">第${roundNum}轮评分</span>
        <span class="eval-card-score">${evaluation.overall_score}分</span>
    </div>
    <div class="eval-card-dims">${dimBars}</div>
    ${evaluation.feedback ? `<div class="eval-card-feedback">${evaluation.feedback}</div>` : ''}
    ${evaluation.suggestions && evaluation.suggestions.length ?
        `<div class="eval-card-suggestions">${evaluation.suggestions.map(s => `<span class="eval-tip">💡 ${s}</span>`).join('')}</div>` : ''}`;

    elements.chatMessages.appendChild(card);
    requestAnimationFrame(() => card.classList.add('show'));
    scrollToBottom();

    // 同步到右侧信息看板
    if (elements.liveScore) elements.liveScore.textContent = evaluation.overall_score;
    if (elements.liveSuggestions && evaluation.suggestions) {
        elements.liveSuggestions.innerHTML = evaluation.suggestions.map(s => `<p class="suggestion-text">💡 ${s}</p>`).join('');
    }
}

function scrollToBottom() {
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

/**
 * 发送消息 — SSE 流式版本
 */
async function handleSend() {
    const message = elements.messageInput.value.trim();
    if (!message || state.isProcessing) return;

    state.isProcessing = true;
    state.abortController = new AbortController();

    // 添加用户消息
    addUserMessage(message);
    elements.messageInput.value = '';
    setInputLocked(true);
    showStageIndicator('rag_searching', '检索知识库中...');

    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: state.currentSession,
                message: message,
                is_pause: false
            }),
            signal: state.abortController.signal
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || `请求失败 (${response.status})`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentEvent = '';
        let aiBubble = null;
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // 按行解析 SSE
            while (true) {
                const newlineIdx = buffer.indexOf('\n');
                if (newlineIdx === -1) break;

                const line = buffer.substring(0, newlineIdx).trim();
                buffer = buffer.substring(newlineIdx + 1);

                if (line.startsWith('event: ')) {
                    currentEvent = line.substring(7).trim();
                } else if (line.startsWith('data: ')) {
                    const dataStr = line.substring(6);
                    if (!currentEvent) continue;

                    let payload;
                    try {
                        payload = JSON.parse(dataStr);
                    } catch (e) {
                        continue;
                    }

                    switch (currentEvent) {
                        case 'status':
                            showStageIndicator(payload.stage, payload.message);
                            if (payload.stage === 'ai_generating' && !aiBubble) {
                                aiBubble = createOrGetAIBubble();
                            }
                            break;

                        case 'token':
                            if (!aiBubble) aiBubble = createOrGetAIBubble();
                            fullResponse += payload.delta;
                            aiBubble.querySelector('.message-content').textContent = fullResponse;
                            scrollToBottom();
                            break;

                        case 'done':
                            state.currentRound = payload.round;
                            // 更新知识库看板
                            if (payload.knowledge_count !== undefined) {
                                updateKnowledgeBox({ knowledge_found: payload.knowledge_count });
                            }
                            // 释放输入框
                            hideStageIndicator();
                            if (aiBubble) finalizeAIBubble(fullResponse);
                            setInputLocked(false);
                            elements.roundIndicator.textContent = `第 ${payload.round} 轮`;
                            state.isProcessing = false;
                            break;

                        case 'evaluation':
                            showEvaluationCard(payload, state.currentRound);
                            break;

                        case 'error':
                            showToast(payload.message || '未知错误', 'error');
                            break;
                    }
                    currentEvent = '';
                }
            }
        }

    } catch (error) {
        if (error.name === 'AbortError') {
            // 用户中断（开始新消息），静默处理
            console.log('SSE 连接已中断（用户开始新轮次）');
        } else {
            console.error('SSE 流式错误:', error);
            showToast('发送失败: ' + error.message, 'error');
            hideStageIndicator();
            setInputLocked(false);
            state.isProcessing = false;
        }
    }
}

function addUserMessage(content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    messageDiv.innerHTML = `<div class="message-header">
        <div class="message-avatar">💁</div>
        <div class="message-role">销售经理（您）</div>
        <div class="message-time">${timeStr}</div>
    </div>
    <div class="message-content">${content}</div>`;
    elements.chatMessages.appendChild(messageDiv);
    state.messages.push({ role: 'user', content: content });
    scrollToBottom();
}

// ==================== 其余 UI（保持不变，略作调整） ====================

function showPage(pageElement) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    pageElement.classList.add('active');
}

function addSystemMessage(content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message system';
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    messageDiv.innerHTML = `<div class="message-header">
        <div class="message-avatar">💡</div>
        <div class="message-role">系统提示</div>
        <div class="message-time">${timeStr}</div>
    </div>
    <div class="message-content system-content">${content}</div>`;
    elements.chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

function updateInfoPanel(sessionInfo, scenario) {
    elements.infoClientUnit.textContent = sessionInfo.client_unit;
    elements.infoAiRole.textContent = scenario.ai_role;
    elements.infoProduct.textContent = sessionInfo.product;
    elements.infoScenarioType.textContent = sessionInfo.scenario_type;
    const traits = scenario.customer_traits || [];
    elements.infoCustomerTraits.textContent = traits.join('、');
    const criteria = scenario.success_criteria || [];
    elements.infoSuccessCriteria.innerHTML = criteria.map(c => `<li>${c}</li>`).join('');
}

function updateKnowledgeBox(debugInfo) {
    if (!debugInfo) return;
    const totalFound = debugInfo.knowledge_found || 0;
    let html = '<div class="knowledge-stats">';
    if (totalFound > 0) {
        html += `<div class="stat-item success"><span class="stat-icon">✅</span>
            <span class="stat-text">知识库正常 · 检索到${totalFound}条</span></div>`;
    } else {
        html += `<div class="stat-item warning"><span class="stat-icon">⚠️</span>
            <span class="stat-text">知识库为空 · AI使用通用话术</span></div>`;
    }
    html += '</div>';
    elements.knowledgeBox.innerHTML = html;
}

function showReport(report) {
    elements.reportScore.textContent = report.total_score;
    elements.reportRating.textContent = report.rating_text;
    elements.reportHighlights.innerHTML = (report.highlights || []).map(h => `<li>${h}</li>`).join('');
    elements.reportImprovements.innerHTML = (report.improvements || []).map(i => `<li>${i}</li>`).join('');
    elements.reportSuggestions.innerHTML = (report.suggestions || []).map(s => `<li>${s}</li>`).join('');
    showPage(elements.reportPage);
}

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
        return `<div class="history-item" data-session-id="${item.session_id}" data-status="${item.status}">
            <div class="history-item-header">
                <span class="history-scenario">${item.scenario}</span>
                <span class="history-date">${new Date(item.created_at).toLocaleDateString()}</span>
            </div>
            <div class="history-details">${item.client_unit} · ${item.product} · ${item.rounds}轮对话</div>
            <div class="history-meta">${statusBadge}${scoreHTML}</div>
        </div>`;
    }).join('');

    document.querySelectorAll('.history-item').forEach(item => {
        item.addEventListener('click', async () => {
            const sessionId = item.dataset.sessionId;
            const status = item.dataset.status;
            closeHistoryPanel();
            if (status === 'completed') {
                try {
                    const response = await fetch(`${CONFIG.TUTOR_API}/session/${sessionId}`);
                    if (response.ok) {
                        const sessionData = await response.json();
                        if (sessionData.report) {
                            showReport(sessionData.report);
                        } else {
                            showToast('该会话暂无总结报告', 'info');
                        }
                    }
                } catch (error) {
                    showToast('加载会话详情失败', 'error');
                }
            } else {
                showToast('该会话未完成', 'info');
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
    return !!(container && container.classList.contains('active') && elements.historyPage.classList.contains('active'));
}

// ==================== 事件处理 ====================

async function handleStart() {
    const scenarioId = elements.scenarioSelect.value;
    const clientUnit = elements.clientUnit.value.trim();
    const product = elements.productName.value.trim();
    const scenarioType = elements.scenarioType.value.trim();
    const database = elements.tutorDatabase?.value || '';

    if (!scenarioId) { showToast('请选择一个场景', 'error'); return; }
    if (!clientUnit || !product || !scenarioType) { showToast('请填写完整信息', 'error'); return; }

    try {
        elements.startBtn.disabled = true;
        elements.startBtn.textContent = '启动中...';
        const data = await startSession(scenarioId, clientUnit, product, scenarioType, database);
        updateInfoPanel(data.session_info, data.scenario);
        showPage(elements.chatPage);
        elements.roundIndicator.textContent = '第 1 轮';
        state.isChatting = true;
        if (data.user_should_start) {
            addSystemMessage(data.opening_message);
        } else {
            addSystemMessage(data.opening_message);
        }
    } catch (error) {
        showToast('启动失败: ' + error.message, 'error');
    } finally {
        elements.startBtn.disabled = false;
        elements.startBtn.textContent = '开始陪练';
    }
}

async function handlePause() {
    try {
        elements.pauseBtn.disabled = true;
        const response = await fetch(`${CONFIG.TUTOR_API}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: state.currentSession,
                message: '',
                is_pause: true
            })
        });
        if (response.ok) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const newlineIdx = buffer.indexOf('\n');
                if (newlineIdx !== -1) {
                    const line = buffer.substring(0, newlineIdx).trim();
                    buffer = buffer.substring(newlineIdx + 1);
                    if (line.startsWith('data: ')) {
                        const payload = JSON.parse(line.substring(6));
                        if (payload.overall_score) {
                            showEvaluationCard(payload, state.currentRound);
                            showToast(`当前评分: ${payload.overall_score}分`, 'info');
                        }
                    }
                }
            }
        }
    } catch (error) {
        console.error('获取反馈错误:', error);
        showToast('获取反馈失败', 'error');
    } finally {
        elements.pauseBtn.disabled = false;
    }
}

async function handleEnd() {
    if (!confirm('确定要结束当前会话吗？')) return;
    try {
        elements.endBtn.disabled = true;
        elements.endBtn.textContent = '生成报告中...';
        const report = await endSession('simple');
        showReport(report);
        state.isChatting = false;
    } catch (error) {
        showToast('结束会话失败: ' + error.message, 'error');
    } finally {
        elements.endBtn.disabled = false;
        elements.endBtn.textContent = '🏁';
    }
}

// ==================== 事件监听 ====================

elements.startBtn.addEventListener('click', handleStart);
elements.sendBtn.addEventListener('click', handleSend);

elements.messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});

elements.pauseBtn.addEventListener('click', handlePause);
elements.endBtn.addEventListener('click', handleEnd);
elements.backToStartBtn.addEventListener('click', () => {
    // 中断进行中的 SSE 连接
    if (state.abortController) {
        state.abortController.abort();
        state.abortController = null;
    }
    showPage(elements.startPage);
    state.currentSession = null;
    state.messages = [];
    state.currentRound = 0;
    elements.chatMessages.innerHTML = '';
    state.isChatting = false;
    state.isProcessing = false;
    setInputLocked(false);
});

elements.viewHistoryBtn.addEventListener('click', () => openHistoryPanel());

elements.historyBtn.addEventListener('click', () => {
    if (isHistoryPanelOpen()) { closeHistoryPanel(); } else { openHistoryPanel(); }
});
elements.closeHistoryBtn.addEventListener('click', () => closeHistoryPanel());
elements.historyPage.addEventListener('click', (e) => {
    if (e.target === elements.historyPage) closeHistoryPanel();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && elements.historyPage.classList.contains('active')) closeHistoryPanel();
});

elements.scenarioSelect.addEventListener('change', (e) => {
    if (e.target.value === 'custom') elements.customScenarioModal.classList.add('active');
});
elements.closeModalBtn.addEventListener('click', () => {
    elements.customScenarioModal.classList.remove('active');
    elements.scenarioSelect.value = '';
});
elements.createScenarioBtn.addEventListener('click', async () => {
    const name = document.getElementById('customScenarioName').value.trim();
    const aiRole = document.getElementById('customAiRole').value.trim();
    const userRole = document.getElementById('customUserRole').value.trim();
    const description = document.getElementById('customScenarioDesc').value.trim();
    const customerTraits = document.getElementById('customCustomerTraits').value.trim().split('\n').filter(t => t);
    const aiStrategy = document.getElementById('customAiStrategy').value.trim().split('\n').filter(s => s);
    const successCriteria = document.getElementById('customSuccessCriteria').value.trim().split('\n').filter(s => s);

    if (!name || !aiRole || !description) { showToast('请填写完整信息', 'error'); return; }
    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/scenarios/create`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, ai_role: aiRole, user_role: userRole,
                description, customer_traits: customerTraits,
                ai_strategy: aiStrategy, success_criteria: successCriteria })
        });
        if (response.ok) {
            const data = await response.json();
            showToast('场景创建成功！', 'success');
            elements.customScenarioModal.classList.remove('active');
            const option = document.createElement('option');
            option.value = data.scenario_id;
            option.textContent = data.scenario.name;
            elements.scenarioSelect.appendChild(option);
            elements.scenarioSelect.value = data.scenario_id;
        } else {
            showToast('创建场景失败', 'error');
        }
    } catch (error) {
        showToast('创建场景失败', 'error');
    }
});
elements.customScenarioModal.addEventListener('click', (e) => {
    if (e.target === elements.customScenarioModal) {
        elements.customScenarioModal.classList.remove('active');
    }
});

// ==================== 知识库下拉 ====================

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
        while (select.options.length > 1) select.remove(1);
        databases.forEach(db => {
            const id = typeof db === 'string' ? db : db.id;
            const name = typeof db === 'string' ? db : (db.name || db.id);
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = name;
            select.appendChild(opt);
        });
    } catch (err) {
        console.warn('加载知识库列表失败:', err.message);
    }
}

// ==================== 初始化 ====================

console.log('AI话术陪练系统已加载（SSE 流式 v2.1）');
console.log('RAG服务:', CONFIG.RAG_API);
console.log('陪练服务:', CONFIG.TUTOR_API);

healthCheckLoop();
populateTutorDatabaseDropdown();
