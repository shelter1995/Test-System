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
    lastKnowledgeCount: null, // 最新一轮的知识库检索量
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
function showEvaluationCard(evaluation, roundNum, knowledgeCount) {
    if (!evaluation || !evaluation.overall_score) return;

    const existing = document.querySelector('.eval-card');
    if (existing) existing.remove();

    const dims = evaluation.dimension_scores || {};
    const dimBars = Object.entries(dims).map(([name, d]) => {
        const score = d.score || 0;
        const cls = score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low';
        const feedback = d.feedback || '';
        return `<div class="eval-dim" title="${feedback}">
            <span class="eval-dim-name">${name}</span>
            <span class="eval-dim-bar"><span class="eval-dim-fill ${cls}" style="width:${score}%"></span></span>
            <span class="eval-dim-score">${score}</span>
        </div>`;
    }).join('');

    const kbNote = knowledgeCount != null
        ? (knowledgeCount > 0
            ? `<div class="eval-kb-info">📚 基于 ${knowledgeCount} 条知识库内容评估</div>`
            : '<div class="eval-kb-info eval-kb-empty">⚠️ 知识库为空，使用通用标准评估</div>')
        : '';

    const card = document.createElement('div');
    card.className = 'eval-card';
    card.innerHTML = `<div class="eval-card-header">
        <span class="eval-card-round">第${roundNum}轮评分</span>
        <span class="eval-card-score">${evaluation.overall_score}分</span>
    </div>
    ${kbNote}
    <div class="eval-card-dims">${dimBars}</div>
    ${evaluation.feedback ? `<div class="eval-card-feedback">${evaluation.feedback}</div>` : ''}
    ${evaluation.suggestions && evaluation.suggestions.length ?
        `<div class="eval-card-suggestions">${evaluation.suggestions.map(s => `<span class="eval-tip">💡 ${s}</span>`).join('')}</div>` : ''}`;

    elements.chatMessages.appendChild(card);
    requestAnimationFrame(() => card.classList.add('show'));
    scrollToBottom();

    // 同步累计评分到右侧看板
    if (elements.liveScore) elements.liveScore.textContent = evaluation.overall_score;
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
                            state.lastKnowledgeCount = payload.knowledge_count;
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
                            // 独立发起评估请求，不受 SSE 中断影响
                            if (!state.pendingEval) {
                                requestEvaluation(state.currentSession);
                            }
                            break;

                        case 'evaluation':
                            // 后端流式管道不再推送评分；保留分支兼容旧服务。
                            showEvaluationCard(payload, state.currentRound, state.lastKnowledgeCount);
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
            console.log('SSE 连接已中断（用户开始新轮次）');
        } else if (error.name === 'TypeError' && error.message.includes('fetch')) {
            console.error('SSE 网络错误:', error);
            // 保留已收到的 AI 回复
            if (aiBubble && fullResponse) finalizeAIBubble(fullResponse);
            hideStageIndicator();
            setInputLocked(false);
            state.isProcessing = false;
            showToast('陪练服务连接中断，请检查服务是否运行。已收到的回复已保留。', 'error');
        } else {
            console.error('SSE 流式错误:', error);
            // 保留已收到的部分回复
            if (aiBubble && fullResponse) finalizeAIBubble(fullResponse);
            hideStageIndicator();
            setInputLocked(false);
            state.isProcessing = false;
            showToast('对话中断: ' + error.message, 'error');
        }
    }
}

/**
 * 独立评估请求 — 不受 SSE AbortController 影响
 */
async function requestEvaluation(sessionId) {
    if (state.pendingEval) return;
    state.pendingEval = new AbortController();
    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                message: '',
                is_pause: true
            }),
            signal: state.pendingEval.signal
        });
        if (!response.ok) return;
        const data = await response.json();
        if (data.evaluation && data.evaluation.overall_score) {
            showEvaluationCard(data.evaluation, state.currentRound, state.lastKnowledgeCount);
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('评估请求已取消');
        } else {
            console.warn('独立评估请求失败:', error.message);
        }
    } finally {
        state.pendingEval = null;
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

    // 五维评分条形图
    const dims = report.dimension_scores || {};
    const dimsEl = document.getElementById('reportDimensions');
    if (dimsEl && Object.keys(dims).length > 0) {
        dimsEl.innerHTML = Object.entries(dims).map(([name, d]) => {
            const s = d.score || 0;
            const cls = s >= 80 ? 'high' : s >= 60 ? 'mid' : 'low';
            return `<div class="eval-dim">
                <span class="eval-dim-name">${name}</span>
                <span class="eval-dim-bar"><span class="eval-dim-fill ${cls}" style="width:${s}%"></span></span>
                <span class="eval-dim-score">${s}</span>
            </div>
            <div class="eval-dim-feedback">${d.feedback || ''}</div>`;
        }).join('');
        dimsEl.style.display = 'block';
    } else if (dimsEl) {
        dimsEl.style.display = 'none';
    }

    elements.reportHighlights.innerHTML = (report.highlights || []).map(h => `<li>${h}</li>`).join('') || '<li>暂无</li>';
    elements.reportImprovements.innerHTML = (report.improvements || []).map(i => `<li>${i}</li>`).join('') || '<li>暂无</li>';
    elements.reportSuggestions.innerHTML = (report.suggestions || []).map(s => `<li>${s}</li>`).join('') || '<li>暂无</li>';
    showPage(elements.reportPage);
}

// ==================== 历史记录（增强版） ====================

let _historyCache = null;  // 缓存全量历史数据

function scoreColorClass(score) {
    if (score == null) return '';
    if (score >= 80) return 'color-high';
    if (score >= 60) return 'color-mid';
    return 'color-low';
}

function scoreBorderClass(score) {
    if (score == null) return '';
    if (score >= 80) return 'score-high';
    if (score >= 60) return 'score-mid';
    return 'score-low';
}

function ratingEmoji(score) {
    if (score >= 90) return '⭐';
    if (score >= 80) return '👍';
    if (score >= 60) return '📋';
    return '📝';
}

async function loadHistory() {
    const history = await getHistory();
    _historyCache = history;
    populateHistoryFilters(history);
    renderHistoryList(history);
}

function populateHistoryFilters(history) {
    const select = document.getElementById('historyFilterScenario');
    if (!select) return;
    const currentVal = select.value;
    // 收集已有场景
    const scenarios = [...new Set(history.map(h => h.scenario))];
    while (select.options.length > 1) select.remove(1);
    scenarios.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        select.appendChild(opt);
    });
    select.value = currentVal; // 保留之前的选择
}

function renderHistoryList(history) {
    if (!history || history.length === 0) {
        elements.historyList.innerHTML = '<p class="history-empty">暂无历史记录</p>';
        const countEl = document.getElementById('historyCount');
        if (countEl) countEl.textContent = '';
        return;
    }

    const searchTerm = (document.getElementById('historySearch')?.value || '').toLowerCase();
    const filterScenario = document.getElementById('historyFilterScenario')?.value || '';

    let filtered = history;
    if (searchTerm) {
        filtered = filtered.filter(h =>
            (h.client_unit || '').toLowerCase().includes(searchTerm) ||
            (h.product || '').toLowerCase().includes(searchTerm) ||
            (h.scenario || '').toLowerCase().includes(searchTerm)
        );
    }
    if (filterScenario) {
        filtered = filtered.filter(h => h.scenario === filterScenario);
    }

    const countEl = document.getElementById('historyCount');
    if (countEl) countEl.textContent = `共 ${filtered.length} 条${filtered.length !== history.length ? ` (筛选自 ${history.length} 条)` : ''}`;

    if (filtered.length === 0) {
        elements.historyList.innerHTML = '<p class="history-empty">无匹配记录</p>';
        return;
    }

    elements.historyList.innerHTML = filtered.map(item => renderHistoryItem(item)).join('');

    // 绑定展开/收起
    elements.historyList.querySelectorAll('.history-item').forEach(el => {
        el.addEventListener('click', function(e) {
            // 如果点击的是内部按钮则不处理
            if (e.target.closest('.history-view-report')) return;
            const wasExpanded = this.classList.contains('expanded');
            // 关闭其他展开项
            elements.historyList.querySelectorAll('.history-item.expanded').forEach(i => i.classList.remove('expanded'));
            if (!wasExpanded) {
                this.classList.add('expanded');
                loadHistoryDetail(this);
            }
        });
    });

    // 绑定"查看报告"按钮
    elements.historyList.querySelectorAll('.history-view-report').forEach(btn => {
        btn.addEventListener('click', async function(e) {
            e.stopPropagation();
            const sessionId = this.dataset.sessionId;
            closeHistoryPanel();
            try {
                const response = await fetch(`${CONFIG.TUTOR_API}/session/${sessionId}`);
                if (response.ok) {
                    const sessionData = await response.json();
                    if (sessionData.report) {
                        showReport(sessionData.report);
                    } else {
                        showToast('该会话暂无总结报告', 'info');
                    }
                } else {
                    showToast('加载会话详情失败', 'error');
                }
            } catch (error) {
                showToast('加载会话详情失败', 'error');
            }
        });
    });
}

function renderHistoryItem(item) {
    const score = item.score;
    const colorClass = scoreColorClass(score);
    const borderClass = scoreBorderClass(score);
    const emoji = ratingEmoji(score);
    const dateStr = item.created_at ? new Date(item.created_at).toLocaleDateString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit'
    }) : '';

    const statusBadge = item.status === 'completed'
        ? '<span class="history-status completed">已完成</span>'
        : '<span class="history-status active">进行中</span>';

    const scoreHTML = score != null
        ? `<span class="history-score ${colorClass}">${emoji} ${score}分${item.rating ? ' · ' + item.rating : ''}</span>`
        : '<span class="history-score">暂无评分</span>';

    return `<div class="history-item ${borderClass}" data-session-id="${item.session_id}" data-status="${item.status}">
        <div class="history-item-header">
            <span class="history-scenario">${item.scenario}</span>
            <span class="history-date">${dateStr}</span>
        </div>
        <div class="history-details">${item.client_unit} · ${item.product} · ${item.rounds}轮对话</div>
        <div class="history-meta">
            ${statusBadge}
            ${scoreHTML}
            <button class="history-view-report" data-session-id="${item.session_id}" style="margin-left:auto;font-size:0.75rem;padding:0.15rem 0.5rem;border:1px solid var(--border-color);border-radius:4px;background:white;cursor:pointer;">查看完整报告</button>
        </div>
        <div class="history-item-detail">
            <div class="history-detail-section" data-detail-type="loading">
                <span style="color:var(--text-light);font-size:0.8rem;">加载详情中...</span>
            </div>
        </div>
    </div>`;
}

async function loadHistoryDetail(itemEl) {
    const detailSection = itemEl.querySelector('.history-item-detail [data-detail-type]');
    const sessionId = itemEl.dataset.sessionId;

    // 如果已加载过，跳过
    if (detailSection.dataset.loaded === 'true') return;

    try {
        const response = await fetch(`${CONFIG.TUTOR_API}/session/${sessionId}`);
        if (!response.ok) throw new Error('加载失败');
        const sessionData = await response.json();

        // 对话摘要
        const messages = sessionData.messages || [];
        const convHTML = messages.slice(-6).map(m => {
            const roleClass = m.role === 'user' ? 'conv-user' : 'conv-ai';
            const roleName = m.role === 'user' ? '销售代表' : 'AI客户';
            const text = (m.content || '').substring(0, 150);
            return `<div><span class="${roleClass}">${roleName}:</span> ${text}${text.length >= 150 ? '...' : ''}</div>`;
        }).join('');

        // 维度评分
        const report = sessionData.report || {};
        const dims = report.dimension_scores || {};
        const dimBarsHTML = Object.keys(dims).length > 0
            ? Object.entries(dims).map(([name, d]) => {
                const s = d.score || 0;
                const cls = s >= 80 ? 'high' : s >= 60 ? 'mid' : 'low';
                return `<div class="eval-dim">
                    <span class="eval-dim-name">${name}</span>
                    <span class="eval-dim-bar"><span class="eval-dim-fill ${cls}" style="width:${s}%"></span></span>
                    <span class="eval-dim-score">${s}</span>
                </div>`;
            }).join('')
            : '';

        // 知识库状态
        const evalCount = sessionData.evaluations ? sessionData.evaluations.length : 0;
        const kbInfo = sessionData.database
            ? `知识库: ${sessionData.database}`
            : '知识库: 默认';

        detailSection.innerHTML = `
            <div class="history-detail-section">
                <div class="history-detail-label">最近对话</div>
                <div class="history-detail-conversation">${convHTML || '暂无对话记录'}</div>
            </div>
            ${dimBarsHTML ? `<div class="history-detail-section">
                <div class="history-detail-label">评分维度</div>
                ${dimBarsHTML}
            </div>` : ''}
            <div class="history-detail-section" style="font-size:0.78rem;color:var(--text-light);">
                ${kbInfo} · ${evalCount}次评估 · ${messages.length}条消息
            </div>
        `;
        detailSection.dataset.loaded = 'true';
    } catch (error) {
        detailSection.innerHTML = `<span style="color:#e74c3c;font-size:0.8rem;">加载详情失败</span>`;
    }
}

function filterHistory() {
    if (_historyCache) renderHistoryList(_historyCache);
}

function openHistoryPanel() {
    const container = document.getElementById('historyContainer');
    if (container) container.classList.add('active');
    const backdrop = document.getElementById('historyBackdrop');
    if (backdrop) backdrop.classList.add('active');
    loadHistory();
}

function closeHistoryPanel() {
    const container = document.getElementById('historyContainer');
    if (container) container.classList.remove('active');
    const backdrop = document.getElementById('historyBackdrop');
    if (backdrop) backdrop.classList.remove('active');
}

function isHistoryPanelOpen() {
    const container = document.getElementById('historyContainer');
    return !!(container && container.classList.contains('active'));
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
                            showEvaluationCard(payload, state.currentRound, state.lastKnowledgeCount);
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
        const report = await endSession('detailed');
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
function returnToStart() {
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
}

// 报告页顶部返回按钮（底部已移除，只保留顶部）
const reportBackBtn = document.getElementById('reportBackBtn');
if (reportBackBtn) {
    reportBackBtn.addEventListener('click', () => returnToStart());
}

// 聊天页返回按钮
const chatBackBtn = document.getElementById('chatBackBtn');
if (chatBackBtn) {
    chatBackBtn.addEventListener('click', () => {
        if (state.isProcessing || state.isChatting) {
            if (!confirm('对话进行中，确定返回设置页吗？')) return;
        }
        returnToStart();
    });
}

elements.viewHistoryBtn.addEventListener('click', () => openHistoryPanel());

elements.historyBtn.addEventListener('click', () => {
    if (isHistoryPanelOpen()) { closeHistoryPanel(); } else { openHistoryPanel(); }
});
elements.closeHistoryBtn.addEventListener('click', () => closeHistoryPanel());
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isHistoryPanelOpen()) closeHistoryPanel();
});

// 点击遮罩关闭历史抽屉
const historyBackdrop = document.getElementById('historyBackdrop');
if (historyBackdrop) {
    historyBackdrop.addEventListener('click', () => closeHistoryPanel());
}

// 历史搜索/筛选
const historySearch = document.getElementById('historySearch');
const historyFilterScenario = document.getElementById('historyFilterScenario');
if (historySearch) historySearch.addEventListener('input', filterHistory);
if (historyFilterScenario) historyFilterScenario.addEventListener('change', filterHistory);

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
