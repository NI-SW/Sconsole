/**
 * Sconsole Console - JavaScript Application v3
 * 工作空间架构：工作空间 → Agents (重构版)
 */
// ─── State ──────────────────────────────────────────────────────────
const state = {
    ws: null,
    consoleId: 'console-' + Math.random().toString(36).substr(2, 9),
    connected: false,
    activeView: 'dashboard',
    activeChatAgentId: null,       // agent ID for active chat
    activeChatInstanceId: null,    // workspace ID for active chat
    chatPollTimer: null,
    lastResponseTimestamp: 0,
    chatMessages: [],
    configs: [],
    instances: [],
    containers: [],
    nodes: [],
    selectedAgents: new Set(),
    instanceAgentCache: {},
};

// ─── DOM Helpers ────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ─── WebSocket ──────────────────────────────────────────────────────
function connectWebSocket() { const p = location.protocol === 'https:' ? 'wss:' : 'ws:'; state.ws = new WebSocket(`${p}//${location.host}/ws/console/${state.consoleId}`); state.ws.onopen = () => { state.connected = true; updateServerStatus(true); addLog('已连接到服务器', 'success'); refreshAll(); }; state.ws.onclose = () => { state.connected = false; updateServerStatus(false); addLog('连接断开，正在重连...', 'error'); setTimeout(connectWebSocket, 3000); }; state.ws.onmessage = e => { const d = JSON.parse(e.data); handleWSMessage(d); }; }
function handleWSMessage(data) {
    switch (data.type) {
        case 'agent_output':
            if (state.activeChatAgentId === data.agent_id || state.activeChatInstanceId === data.instance_id)
                addChatMessage('agent', data.content);
            break;
        case 'agent_status':
            addLog(`Agent #${data.agent_id || data.instance_id} 状态: ${data.status}`, 'system');
            // Only full-refresh if status actually changed from what we know
            if (data.agent_id && data.instance_id) {
                const cached = state.instanceAgentCache[data.instance_id];
                if (cached) {
                    const agent = cached.find(a => a.id === data.agent_id);
                    if (agent && agent.status === data.status) {
                        // Status unchanged, skip full refresh to avoid collapsing expanded cards
                        break;
                    }
                }
            }
            refreshInstances();
            break;
        case 'agent_log': addLog(`Agent #${data.instance_id}: ${JSON.stringify(data.data)}`, 'system'); break;
        case 'node_list': state.nodes = data.nodes; renderNodes(); break;
        case 'instance_list': state.instances = data.instances; renderInstances(); updateStats(); break;
        case 'workspace_list': state.instances = data.workspaces; renderInstances(); updateStats(); break;
    }
}
function sendWS(msg) { if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(msg)); }

// ─── Navigation ─────────────────────────────────────────────────────
function initNavigation() {
    $$('.nav-item').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
}
function switchView(view) {
    state.activeView = view;
    localStorage.setItem('sconsole-active-view', view);
    location.hash = '#' + view;
    $$('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === view));
    $$('.view').forEach(v => v.classList.remove('active'));
    const t = $(`#view-${view}`); if (t) t.classList.add('active');
    refreshView(view);
}
function refreshView(view) {
    switch (view) {
        case 'dashboard': refreshDashboard(); break;
        case 'agents': refreshInstances(); break;
        case 'chat':
            // If user was in an active conversation, restore it directly
            if (state.activeChatAgentId && state.activeChatInstanceId && state.chatMessages.length > 0) {
                // Restore chat-active view from current state
                $('#chat-empty').classList.add('hidden');
                $('#chat-active').classList.remove('hidden');
                $('#chat-messages').innerHTML = '';
                state.chatMessages.forEach(msg => {
                    addChatMessage(msg.role === 'user' ? 'user' : 'agent', msg.content);
                });
                renderConvSidebar(state.activeChatInstanceId, state.activeChatAgentId);
                // Focus input
                setTimeout(() => { const inp = $('#chat-input'); if (inp) inp.focus(); }, 100);
            } else {
                refreshChatSelector();
            }
            break;
        case 'configs': refreshConfigs(); break;
        case 'nodes': refreshNodes(); break;
                case 'skills': refreshSkills(); break;
        case 'create-workspace':
            refreshNodeSelector();
            if (document.getElementById('sub-agent-rows').children.length === 0) {
                addSubAgentRow();
            }
            break;
        case 'add-agent': break;
    }
}
function refreshAll() { refreshView(state.activeView); }

// ─── Server Status ──────────────────────────────────────────────────
function updateServerStatus(online) {
    $('#server-status').className = 'status-dot ' + (online ? 'online' : 'offline');
    $('#status-text').textContent = online ? '已连接' : '未连接';
}

// ─── Log ────────────────────────────────────────────────────────────
function addLog(msg, cls) {
    cls = cls || 'system';
    const d = document.createElement('div');
    d.className = `log-entry ${cls}`;
    d.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    const log = $('#activity-log'); log.prepend(d);
    if (log.children.length > 100) log.lastChild.remove();
}

// ─── Dashboard ──────────────────────────────────────────────────────
function refreshDashboard() {
    if (state.connected) { sendWS({ type: 'list_nodes' }); sendWS({ type: 'list_instances' });
        fetchAPI('/api/configs').then(d => { state.configs = d.configs || []; updateStats(); }); }
}
function updateStats() {
    const onlineN = state.nodes.filter(n => n.status === 'online').length;
    $('#stat-nodes').textContent = onlineN;
    $('#stat-agents').textContent = state.instances.length;
    $('#stat-configs').textContent = state.configs.length;
    $('#node-count').textContent = `${onlineN} 节点`;
}

// ─── API Helpers ────────────────────────────────────────────────────
async function fetchAPI(path, options) {
    options = options || {};
    try {
        const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
        if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || `HTTP ${res.status}`); }
        return await res.json();
    } catch (e) { addLog(`API 错误: ${e.message}`, 'error'); return null; }
}

// ═══════════════════════════════════════════════════════════════════════
// 工作空间视图 — 两层结构：工作空间 → Agents
// ═══════════════════════════════════════════════════════════════════════

async function refreshInstances() {
    const data = await fetchAPI('/api/workspaces');
    if (data) state.instances = data.workspaces || [];
    const cData = await fetchAPI('/api/containers');
    if (cData) state.containers = cData.containers || [];
    // Clear workspace agents cache so next access re-fetches
    state._workspaceAgents = {};
    renderInstances();
    updateStats();
}

function renderInstances() {
    const container = $('#agent-list');
    const items = [];

    // Remember which workspaces are currently expanded
    const expandedInstances = new Set();
    document.querySelectorAll('.agent-children:not(.hidden)').forEach(el => {
        const id = el.id.replace('agents-inst-', '');
        if (id) expandedInstances.add(parseInt(id));
    });

    state.selectedAgents.clear();
    updateBatchBar();

    const containerMap = {};
    state.containers.forEach(c => {
        const iid = parseInt(c.instance_id);
        if (!isNaN(iid)) {
            if (!containerMap[iid]) containerMap[iid] = [];
            containerMap[iid].push(c);
        }
    });

    state.instances.forEach(inst => {
        const childContainers = containerMap[inst.id] || [];
        const agentCount = inst.agent_count || 0;
        const totalChildren = agentCount + (childContainers.length > agentCount ? childContainers.length - agentCount : 0);
        const selKey = 'inst-' + inst.id;

        items.push(`<div class="agent-group">
            <div class="agent-card agent-instance" data-instance="${inst.id}">
                <input type="checkbox" class="agent-check" data-agt="${selKey}" onchange="toggleAgentSelect(event,'${selKey}')" onclick="event.stopPropagation()">
                <div class="card-info" onclick="toggleInstanceAgents(${inst.id})">
                    <div class="card-name">
                        <span class="group-chevron" id="chevron-inst-${inst.id}">&#9654;</span>
                        ${esc(inst.name || ('工作空间 #'+inst.id))}
                        ${totalChildren > 0 ? `<span class="status-badge" style="background:rgba(88,166,255,0.15);color:#58a6ff;">${totalChildren} 个 Agent</span>` : ''}
                    </div>
                    <div class="card-meta">ID: #${inst.id} | 节点: ${inst.node_id || 'N/A'} | 创建: ${inst.created_at} | master_id: ${inst.master_agent_id || 'N/A'}</div>
                </div>
                <div class="card-actions">
                    <button class="btn btn-sm" onclick="event.stopPropagation();openAgentChat(${inst.id},${inst.master_agent_id},'${esc(inst.name)}')">对话</button>
                    <button class="btn btn-sm" onclick="event.stopPropagation();openWorkspaceFiles(${inst.id})">📁 文件</button>
                    <button class="btn btn-sm" onclick="event.stopPropagation();openWSConfig(${inst.id})">⚙️ 配置</button>
                    <button class="btn btn-sm btn-primary" onclick="event.stopPropagation();openAddAgent(${inst.id})">+ Agent</button>
                    <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteInstance(${inst.id})">删除</button>
                </div>
            </div>
            <div class="agent-children hidden" id="agents-inst-${inst.id}">
                <div class="agent-loading" id="loading-inst-${inst.id}">正在加载 Agent 列表...</div>
            </div>
        </div>`);
    });

    if (!items.length) {
        container.innerHTML = '<div class="empty-state">暂无工作空间，请创建一个开始使用。</div>';
    } else {
        container.innerHTML = items.join('');
    }

    // Restore previously expanded workspaces
    expandedInstances.forEach(instId => {
        const children = document.getElementById('agents-inst-' + instId);
        const chevron = document.getElementById('chevron-inst-' + instId);
        if (children) {
            children.classList.remove('hidden');
            if (chevron) chevron.innerHTML = '&#9660;';
            loadInstanceAgents(instId);
        }
    });
}

async function toggleInstanceAgents(instanceId) {
    const children = document.getElementById('agents-inst-' + instanceId);
    const chevron = document.getElementById('chevron-inst-' + instanceId);
    if (!children || !chevron) return;
    const isHidden = children.classList.contains('hidden');
    if (isHidden) {
        children.classList.remove('hidden');
        chevron.innerHTML = '&#9660;';
        await loadInstanceAgents(instanceId);
    } else {
        children.classList.add('hidden');
        chevron.innerHTML = '&#9654;';
    }
}

async function loadInstanceAgents(instanceId) {
    const children = document.getElementById('agents-inst-' + instanceId);
    if (!children) return;

    children.innerHTML = '<div class="agent-loading">正在加载 Agent 列表...</div>';

    const data = await fetchAPI(`/api/workspaces/${instanceId}/agents`);
    const agents = data ? data.agents || [] : [];
    state.instanceAgentCache[instanceId] = agents;

    const orphanContainers = state.containers.filter(c =>
        parseInt(c.instance_id) === instanceId && parseInt(c.agent_id) === 0
    );

    const items = [];

    agents.forEach(agent => {
        const selKey = `agent-${instanceId}-${agent.id}`;
        const isMaster = agent.role === 'master';
        const masterBadge = isMaster ? '<span class="status-badge" style="background:rgba(255,193,7,0.15);color:#f0a500;">主控</span>' : '';
        items.push(`<div class="agent-card agent-child${isMaster ? ' agent-master' : ''}">
            <input type="checkbox" class="agent-check" data-agt="${selKey}" onchange="toggleAgentSelect(event,'${selKey}')">
            <div class="card-info">
                <div class="card-name">
                    ${esc(agent.name)} ${masterBadge} <span class="status-badge status-${agent.status}">${agent.status}</span>
                </div>
                <div class="card-meta">容器: ${(agent.container_id || '').substring(0,12) || 'N/A'} | 端口: :${agent.host_port || 'N/A'} | 创建: ${agent.created_at}</div>
            </div>
            <div class="card-actions">
                ${agent.status === 'running' ? `<button class="btn btn-sm" onclick="openAgentChat(${instanceId},${agent.id},'${esc(agent.name)}')">对话</button>` : ''}
                ${agent.status === 'running' ? `<button class="btn btn-sm" onclick="openMonitor(${instanceId},${agent.id})">监控</button>` : ''}
                ${agent.status === 'running' ? `<button class="btn btn-sm" onclick="openAgentLogs(${instanceId},${agent.id})">日志</button>` : ''}
                ${isMaster && agent.status === 'pending' ? `<button class="btn btn-sm btn-primary" onclick="deployMaster(${instanceId},${agent.id})">部署主控</button>` : ''}
                ${agent.status !== 'stopped' ? `<button class="btn btn-sm btn-danger" onclick="stopAgent(${instanceId},${agent.id})">停止</button>` : ''}
                ${!isMaster ? `<button class="btn btn-sm btn-danger" onclick="deleteAgent(${instanceId},${agent.id})">删除</button>` : ''}
            </div>
        </div>`);
    });

    orphanContainers.forEach(c => {
        if (agents.some(a => a.container_id && c.container_id.includes(a.container_id.substring(0, 8)))) return;
        const selKey = `container-${c.name}`;
        items.push(`<div class="agent-card agent-child">
            <input type="checkbox" class="agent-check" data-agt="${selKey}" onchange="toggleAgentSelect(event,'${selKey}')">
            <div class="card-info">
                <div class="card-name">${esc(c.name)} <span class="status-badge status-running">running</span> <span class="status-badge" style="background:rgba(88,166,255,0.15);color:#58a6ff;">container</span></div>
                <div class="card-meta">容器: ${c.container_id.substring(0,12)} | 镜像: ${c.image} | 端口: ${c.host_port || 'N/A'}</div>
            </div>
            <div class="card-actions">
                <button class="btn btn-sm btn-danger" onclick="stopContainer('${esc(c.name)}')">停止</button>
            </div>
        </div>`);
    });

    if (!items.length) {
        children.innerHTML = '<div class="agent-child-empty">此工作空间暂无 Agent，点击「+ Agent」部署一个。</div>';
    } else {
        children.innerHTML = items.join('');
    }
}

async function stopAgent(instanceId, agentId) {
    if (!confirm(`停止 Agent #${agentId}?`)) return;
    await fetchAPI(`/api/workspaces/${instanceId}/agents/${agentId}/stop`, { method: 'POST' });
    loadInstanceAgents(instanceId);
    refreshInstances();
}

async function deleteAgent(instanceId, agentId) {
    if (!confirm(`删除 Agent #${agentId}?`)) return;
    await fetchAPI(`/api/workspaces/${instanceId}/agents/${agentId}`, { method: 'DELETE' });
    loadInstanceAgents(instanceId);
    refreshInstances();
}

async function stopContainer(name) {
    if (!confirm(`停止容器 ${name}?`)) return;
    const result = await fetchAPI(`/api/containers/${encodeURIComponent(name)}/stop`, { method: 'POST' });
    if (result) { addLog(`容器 ${name}: ${result.message}`, result.message.includes('Failed') ? 'error' : 'success'); refreshInstances(); }
}

async function deleteInstance(instanceId) {
    if (!confirm(`删除工作空间 #${instanceId} 及其所有 Agent？此操作不可撤销！`)) return;
    await fetchAPI(`/api/workspaces/${instanceId}`, { method: 'DELETE' });
    refreshInstances();
}

// ═══════════════════════════════════════════════════════════════════════
// 对话 — 工作空间内 Agent 对话
// ═══════════════════════════════════════════════════════════════════════

async function openAgentChat(instanceId, agentId, agentName) {
    // Abort any in-progress streaming request
    if (state._abortController) {
        state._abortController.abort();
        state._abortController = null;
    }

    // Use cached agent info if re-entering the same agent
    const cached = state._lastAgent;
    let agent = null;
    if (cached && cached.instanceId === instanceId && cached.agentId === agentId
        && cached.port && cached.apiKey) {
        agent = {
            id: agentId, host_port: cached.port, api_key: cached.apiKey,
            name: cached.name || agentName, role: cached.role || 'master',
            status: 'running',
        };
    } else {
        // Fetch agent info from API
        try {
            const resp = await fetch(`/api/workspaces/${instanceId}/agents/${agentId}`);
            if (resp.ok) agent = await resp.json();
        } catch (e) { /* ignore */ }
    }

    if (!agent || agent.status !== 'running') {
        alert('该 Agent 未运行，无法对话');
        return;
    }

    // Reset chat state for this agent (unless reopening the same one)
    const sameAgent = state.activeChatAgentId === agentId && state.activeChatInstanceId === instanceId;
    state.activeChatInstanceId = instanceId;
    state.activeChatAgentId = agentId;
    state._chatAgentPort = agent.host_port || 0;
    state._chatAgentApiKey = agent.api_key || '';
    state._shownConversationIds = new Set();
    if (!sameAgent) {
        state.chatMessages = [];
    }
    if (state.chatPollTimer) { clearInterval(state.chatPollTimer); state.chatPollTimer = null; }

    // Try to restore last conversation from cookie
    renderConvSidebar(instanceId, agentId);
    const convList = loadConvList(instanceId, agentId);
    if (convList.length > 0 && convList[0].id) {
        state._conversationId = convList[0].id;
    } else {
        state._conversationId = 'conv_' + Date.now() + '_' + Math.random().toString(36).substr(2, 8);
    }

    // Update UI
    $('#chat-agent-name').textContent = agentName || agent.name || `Agent #${agentId}`;
    $('#chat-agent-name').dataset.agentId = agentId;

    if (sameAgent && state.chatMessages.length > 0) {
        // Re-render existing messages from state (streaming may still be in progress)
        $('#chat-messages').innerHTML = '';
        state.chatMessages.forEach(msg => {
            addChatMessage(msg.role === 'user' ? 'user' : 'agent', msg.content);
        });
    } else {
        $('#chat-messages').innerHTML = '';
        addChatMessage('system', `正在加载 ${agentName || agent.name} 的历史对话...`);

        // Load from localStorage
        const storageKey = `sconsole-chat-ws-${instanceId}-agent-${agentId}`;
        try {
            const stored = localStorage.getItem(storageKey);
            if (stored) {
                $('#chat-messages').innerHTML = '';
                JSON.parse(stored).forEach(msg => {
                    addChatMessage(msg.role === 'user' ? 'user' : 'agent', msg.content);
                    state.chatMessages.push(msg);
                });
            }
        } catch (e) { /* ignore */ }

        // Load from DB for restored conversation
        if (convList.length > 0 && convList[0].id) {
            try {
                const resp = await fetch(`/api/workspaces/${instanceId}/agents/${agentId}/conversations?limit=200`);
                if (resp.ok) {
                    const data = await resp.json();
                    const dbConvs = (data.conversations || []).filter(c => c.conversation_id === state._conversationId);
                    if (dbConvs.length > 0) {
                        $('#chat-messages').innerHTML = '';
                        state.chatMessages = [];
                        for (const conv of dbConvs) {
                        if (state._shownConversationIds.has(conv.id)) continue;
                        if (conv.user_input) {
                            addChatMessage('user', conv.user_input);
                            state.chatMessages.push({ role: 'user', content: conv.user_input });
                        }
                        let text = '';
                        for (const step of (conv.output || [])) {
                            if (step.type === 'message' && step.content) {
                                for (const part of step.content) {
                                    if (part.text) text += part.text;
                                }
                            }
                        }
                        if (text) {
                            addChatMessage('agent', text);
                            state.chatMessages.push({ role: 'assistant', content: text });
                        } else if (conv.error_msg) {
                            addChatMessage('system', `⚠️ ${conv.error_msg.substring(0, 200)}`);
                        }
                        state._shownConversationIds.add(conv.id);
                    }
                }
            }
        } catch (e) { /* ignore */ }
    }

    if (state.chatMessages.length === 0) {
        $('#chat-messages').innerHTML = '';
        addChatMessage('system', `与 ${agentName || agent.name} 对话中。发送消息开始。`);
    }

    // Re-render sidebar with current conversation highlighted
    renderConvSidebar(instanceId, agentId);

    // Show chat view (don't use switchView — it calls refreshChatSelector which resets the UI)
    $$('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === 'chat'));
    $$('.view').forEach(v => v.classList.remove('active'));
    const chatView = $('#view-chat'); if (chatView) chatView.classList.add('active');
    $('#chat-empty').classList.add('hidden');
    $('#chat-active').classList.remove('hidden');

    // Update agent info header
    const isMaster = agent.role === 'master';
    $('#chat-agent-model').textContent = isMaster ? '主控 Agent' : '子 Agent';
    $('#chat-agent-port').textContent = `:${agent.host_port || 0}`;
    const dot = document.querySelector('.chat-agent-status');
    dot.className = 'chat-agent-status status-dot online';

    saveChatToStorage();
    setTimeout(() => { const inp = $('#chat-input'); if (inp) inp.focus(); }, 100);
    } // close the else block from sameAgent check
}

async function deployMaster(instanceId, masterId) {
    const configs = await fetchAPI('/api/configs');
    if (!configs || !configs.configs.length) { alert('请先创建一个配置。'); return; }
    const result = await fetchAPI(`/api/workspaces/${instanceId}/agents/${masterId}/deploy`, {
        method: 'POST',
        body: JSON.stringify({ config_id: configs.configs[0].id }),
    });
    if (result) { addLog('主控 Agent 部署已开始', 'success'); loadInstanceAgents(instanceId); refreshInstances(); }
}

function closeChatView() {
    // Abort any in-progress streaming request
    if (state._abortController) {
        state._abortController.abort();
        state._abortController = null;
    }
    // Save agent info for quick re-entry
    state._lastAgent = {
        instanceId: state.activeChatInstanceId,
        agentId: state.activeChatAgentId,
        port: state._chatAgentPort,
        apiKey: state._chatAgentApiKey,
        name: $('#chat-agent-name').textContent,
        role: $('#chat-agent-model').textContent,
    };
    state.activeChatAgentId = null;
    state.activeChatInstanceId = null;
    state.chatMessages = [];
    state._chatAgentPort = 0;
    state._chatAgentApiKey = '';
    state._conversationId = '';
    state._shownConversationIds = new Set();
    state._convCache = {};
    if (state.chatPollTimer) { clearInterval(state.chatPollTimer); state.chatPollTimer = null; }
    $('#chat-active').classList.add('hidden');
    $('#chat-empty').classList.remove('hidden');
    refreshChatSelector();
}

// ─── Cookie helpers ───────────────────────────────────────────────

function cookieSet(name, value, days) {
    const d = new Date();
    d.setTime(d.getTime() + (days || 365) * 86400000);
    document.cookie = name + '=' + encodeURIComponent(value) + ';path=/;expires=' + d.toUTCString();
}
function cookieGet(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
}

// ─── Conversation list (cookie-backed sidebar) ─────────────────────

function getConvCookieKey(workspaceId, agentId) {
    return 'sconsole-convs-' + workspaceId + '-' + (agentId || 0);
}

function loadConvList(workspaceId, agentId) {
    const raw = cookieGet(getConvCookieKey(workspaceId, agentId));
    if (raw) {
        try { return JSON.parse(raw); } catch (e) {}
    }
    return [];
}

function saveConvList(workspaceId, agentId, list) {
    cookieSet(getConvCookieKey(workspaceId, agentId), JSON.stringify(list), 365);
}

function addConvToCookie(workspaceId, convId, preview) {
    if (!convId) return;
    const agentId = state.activeChatAgentId || 0;
    const list = loadConvList(workspaceId, agentId);
    // Remove existing entry with same convId
    const filtered = list.filter(c => c.id !== convId);
    // Add to front
    filtered.unshift({ id: convId, preview: preview.substring(0, 80), time: new Date().toISOString() });
    // Keep max 50 entries
    if (filtered.length > 50) filtered.length = 50;
    saveConvList(workspaceId, agentId, filtered);
}

function renderConvSidebar(workspaceId, agentId) {
    const list = loadConvList(workspaceId, agentId);
    const container = document.getElementById('chat-conv-list');
    if (!container) return;

    const currentId = state._conversationId || '';
    const isWorker = agentId > 0;

    let html = '';
    // Show agent label in sidebar
    if (isWorker) {
        html += `<div class="chat-sidebar-label">🤖 Agent 对话</div>`;
    } else {
        html += `<div class="chat-sidebar-label">🎛️ 主控 Agent 对话</div>`;
    }

    // Current session entry
    const currentActive = !currentId ? ' active' : '';
    html += `<div class="chat-conv-item${currentActive}" data-conv-id="" onclick="switchConversation('', ${workspaceId})">`;
    html += `<span class="chat-conv-click">`;
    html += `<div class="chat-conv-preview">当前会话</div>`;
    html += `</span>`;
    html += `</div>`;

    for (const conv of list) {
        if (!conv.id) continue;
        const isActive = (conv.id === currentId) ? ' active' : '';
        const preview = (conv.preview || '(无内容)').substring(0, 60);
        const timeStr = conv.time ? new Date(conv.time).toLocaleDateString() : '';
        html += `<div class="chat-conv-item${isActive}" data-conv-id="${esc(conv.id)}">`;
        html += `<span class="chat-conv-click" onclick="switchConversation('${esc(conv.id)}', ${workspaceId})">`;
        html += `<div class="chat-conv-preview" title="${esc(conv.preview || '')}">${esc(preview)}</div>`;
        if (timeStr) html += `<div class="chat-conv-time">${timeStr}</div>`;
        html += `</span>`;
        html += `<button class="chat-conv-del" onclick="event.stopPropagation();deleteConversation('${esc(conv.id)}', ${workspaceId})" title="删除此会话">×</button>`;
        html += `</div>`;
    }

    container.innerHTML = html;
}

async function switchConversation(convId, workspaceId) {
    if (!workspaceId) workspaceId = state.activeChatInstanceId;
    if (!workspaceId) return;

    // Save current conversation to cache before switching away
    const oldConvId = state._conversationId;
    if (oldConvId && state.chatMessages.length > 0) {
        if (!state._convCache) state._convCache = {};
        state._convCache[oldConvId] = state.chatMessages.slice();
    }

    // Update sidebar active state
    document.querySelectorAll('.chat-conv-item').forEach(el => {
        el.classList.toggle('active', el.dataset.convId === convId);
    });

    state._conversationId = convId || '';
    state._shownConversationIds = new Set();

    // Check cache first
    if (!state._convCache) state._convCache = {};
    const cached = convId ? state._convCache[convId] : null;
    if (cached && cached.length > 0) {
        state.chatMessages = cached;
        $('#chat-messages').innerHTML = '';
        cached.forEach(msg => {
            addChatMessage(msg.role === 'user' ? 'user' : 'agent', msg.content);
        });
        return;
    }

    state.chatMessages = [];
    $('#chat-messages').innerHTML = '';

    if (convId) {
        // Load messages for this conversation from DB
        addChatMessage('system', '正在加载会话...');
        try {
            const agentId = state.activeChatAgentId || await getMasterAgentId(workspaceId);
            const resp = await fetch(`/api/workspaces/${workspaceId}/agents/${agentId}/conversations?limit=200`);
            if (resp.ok) {
                const data = await resp.json();
                const matching = (data.conversations || []).filter(c => c.conversation_id === convId);
                $('#chat-messages').innerHTML = '';
                if (matching.length > 0) {
                    for (const conv of matching) {
                        if (conv.user_input) {
                            addChatMessage('user', conv.user_input);
                            state.chatMessages.push({ role: 'user', content: conv.user_input });
                        }
                        let text = '';
                        for (const step of (conv.output || [])) {
                            if (step.type === 'message' && step.content) {
                                for (const part of step.content) {
                                    if (part.text) text += part.text;
                                }
                            }
                        }
                        if (text) {
                            addChatMessage('agent', text);
                            state.chatMessages.push({ role: 'assistant', content: text });
                        } else if (conv.error_msg) {
                            addChatMessage('system', `⚠️ ${conv.error_msg.substring(0, 200)}`);
                        }
                        state._shownConversationIds.add(conv.id);
                    }
                } else {
                    addChatMessage('system', '未找到该会话记录。');
                }
            }
        } catch (e) {
            addChatMessage('system', '加载失败: ' + e.message);
        }
    } else {
        addChatMessage('system', '新会话已开始，发送消息开始对话。');
    }
    saveChatToStorage();
}

function newConversation() {
    // Generate a stable UUID for this conversation session
    state._conversationId = 'conv_' + Date.now() + '_' + Math.random().toString(36).substr(2, 8);
    state._shownConversationIds = new Set();
    state.chatMessages = [];
    $('#chat-messages').innerHTML = '';
    addChatMessage('system', '新会话已开始，发送消息开始对话。');
    // Update sidebar: "current" is active
    document.querySelectorAll('.chat-conv-item').forEach(el => {
        el.classList.toggle('active', el.dataset.convId === '');
    });
    saveChatToStorage();
}

async function deleteConversation(convId, workspaceId) {
    if (!convId) return;
    if (!confirm('删除此会话及其所有关联记录？此操作不可撤销！')) return;

    try {
        // Delete all DB records for this conversation_id
        const resp = await fetch(`/api/conversations/by-conv-id/${encodeURIComponent(convId)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) throw new Error('删除失败');

        // Remove from cookie
        const agentId = state.activeChatAgentId || 0;
        const list = loadConvList(workspaceId, agentId).filter(c => c.id !== convId);
        saveConvList(workspaceId, agentId, list);

        // If we're currently viewing this conversation, switch to fresh
        if (state._conversationId === convId) {
            state._conversationId = '';
            state._shownConversationIds = new Set();
            state.chatMessages = [];
            $('#chat-messages').innerHTML = '';
            addChatMessage('system', '该会话已删除。点击 [+] 开始新会话。');
        }

        // Refresh sidebar
        renderConvSidebar(workspaceId, state.activeChatAgentId);
    } catch (e) {
        alert('删除失败: ' + (e.message || '未知错误'));
    }
}

async function refreshChatSelector() {
    const ctr = $('#chat-agent-selector');
    const data = await fetchAPI('/api/workspaces');
    const instances = data ? data.workspaces || [] : [];
    if (!instances.length) { ctr.innerHTML = '<p class="text-muted">暂无工作空间，请从「工作空间」页面创建一个。</p>'; return; }

    // Pre-fetch agents for each workspace
    if (!state._workspaceAgents) state._workspaceAgents = {};
    const fetches = instances.map(async inst => {
        try {
            const resp = await fetchAPI(`/api/workspaces/${inst.id}/agents`);
            if (resp && resp.agents) {
                state._workspaceAgents[inst.id] = resp.agents;
            }
        } catch (e) { /* ignore */ }
    });
    await Promise.all(fetches);

    // Render buttons for each running agent (master first, then workers)
    let html = '';
    for (const inst of instances) {
        const agents = state._workspaceAgents[inst.id] || [];
        const running = agents.filter(a => a.status === 'running');
        if (!running.length) continue;

        const master = running.find(a => a.role === 'master');
        const workers = running.filter(a => a.role !== 'master');

        if (master) {
            html += `<button class="agent-option" onclick="openAgentChat(${inst.id},${master.id},'${esc(master.name)}')">
                <span>${esc(inst.name)} · ${esc(master.name)} <span style="color:var(--success)">&#9679;</span></span>
                <span class="opt-port">#主控 :${master.host_port || 'N/A'}</span>
            </button>`;
        }
        for (const w of workers) {
            html += `<button class="agent-option" onclick="openAgentChat(${inst.id},${w.id},'${esc(w.name)}')">
                <span>${esc(inst.name)} · ${esc(w.name)}</span>
                <span class="opt-port">#子 Agent :${w.host_port || 'N/A'}</span>
            </button>`;
        }
    }
    if (!html) html = '<p class="text-muted">暂无运行中的 Agent。</p>';
    ctr.innerHTML = html;
}

async function handleChatFileUpload(input) {
    const file = input.files[0];
    if (!file || !state.activeChatInstanceId || !state.activeChatAgentId) {
        input.value = ''; return;
    }

    const wsId = state.activeChatInstanceId;
    const agentId = state.activeChatAgentId;

    // Show pending in chat
    addChatMessage('system', `📎 正在上传: ${file.name}...`);

    try {
        const formData = new FormData();
        formData.append('file', file);
        const resp = await fetch(`/api/workspaces/${wsId}/agents/${agentId}/upload-file`, {
            method: 'POST',
            body: formData,
        });
        const result = await resp.json();
        if (resp.ok) {
            const sharedPath = result.path || `/agent/shared/${result.filename}`;
            addChatMessage('system',
                `✅ ${file.name} (${(file.size/1024).toFixed(1)}KB) 已上传到 ${sharedPath}`);
            // Also push to chatMessages so it persists
            state.chatMessages.push({ role: 'system', content: `📎 已上传: ${file.name} → ${sharedPath}` });
            saveChatToStorage();
        } else {
            addChatMessage('system', `⚠️ 上传失败: ${result.detail || result.message || '未知错误'}`);
        }
    } catch (e) {
        addChatMessage('system', `⚠️ 上传失败: ${e.message}`);
    }
    input.value = '';
}

async function sendChatMessage() {
    const input = $('#chat-input');
    const content = input.value.trim();
    if (!content || !state.activeChatInstanceId) return;

    if (!state._chatAgentPort || !state._chatAgentApiKey) {
        addChatMessage('system', '错误: 未连接到 Agent。请重新打开对话。');
        return;
    }

    addChatMessage('user', content);
    state.chatMessages.push({ role: 'user', content: content });
    saveChatToStorage();
    input.value = ''; input.style.height = 'auto'; input.focus();

    if (!state._shownConversationIds) state._shownConversationIds = new Set();

    const msgContainer = $('#chat-messages');
    const pendingEl = document.createElement('div');
    pendingEl.className = 'chat-msg system';
    pendingEl.textContent = '思考中...';
    pendingEl.id = 'chat-pending-msg';
    msgContainer.appendChild(pendingEl);
    msgContainer.scrollTop = msgContainer.scrollHeight;

    // Register conversation in sidebar immediately
    if (!state._conversationId) {
        state._conversationId = 'conv_' + Date.now() + '_' + Math.random().toString(36).substr(2, 8);
    }
    addConvToCookie(state.activeChatInstanceId, state._conversationId, content);
    renderConvSidebar(state.activeChatInstanceId, state.activeChatAgentId);

    // ── SSE streaming mode ──
    let streamingEl = null;
    let fullReply = '';
    let streamDone = false;

    // Create AbortController for this request
    state._abortController = new AbortController();

    try {
        const resp = await fetch('/api/communicate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: state._abortController.signal,
            body: JSON.stringify({
                agent_port: state._chatAgentPort,
                api_key: state._chatAgentApiKey,
                input: content,
                conversation_id: state._conversationId || '',
                store: true,
                stream: true,
            }),
        });

        if (!resp.ok) {
            if (pendingEl.parentNode) pendingEl.remove();
            const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
            addChatMessage('system', `⚠️ ${esc((err.error || err.detail || `HTTP ${resp.status}`).substring(0, 300))}`);
            saveChatToStorage();
            return;
        }

        // Read SSE stream
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE events (separated by double newline)
            while (buffer.includes('\n\n')) {
                const idx = buffer.indexOf('\n\n');
                const block = buffer.substring(0, idx);
                buffer = buffer.substring(idx + 2);

                const lines = block.split('\n');
                let eventName = '';
                let eventData = '';

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventName = line.substring(7).trim();
                    } else if (line.startsWith('data: ')) {
                        eventData = line.substring(6);
                    }
                }

                if (!eventData) continue;

                let data = null;
                try { data = JSON.parse(eventData); } catch (e) { continue; }

                switch (eventName) {
                    case 'response.output_item.added': {
                        const item = data.item || {};
                        if (item.type === 'function_call') {
                            if (pendingEl.parentNode) {
                                pendingEl.textContent = '调用: ' + (item.name || 'tool');
                                msgContainer.scrollTop = msgContainer.scrollHeight;
                            }
                        } else if (item.type === 'function_call_output') {
                            if (pendingEl.parentNode) {
                                pendingEl.textContent = '处理中...';
                                msgContainer.scrollTop = msgContainer.scrollHeight;
                            }
                        }
                        break;
                    }
                    case 'response.output_item.done': {
                        const item = data.item || {};
                        if (item.type === 'function_call_output' && pendingEl.parentNode) {
                            pendingEl.textContent = '整理回复...';
                            msgContainer.scrollTop = msgContainer.scrollHeight;
                        }
                        break;
                    }
                    case 'response.output_text.delta': {
                        const delta = data.delta || '';
                        fullReply += delta;
                        if (pendingEl.parentNode) pendingEl.remove();
                        if (!streamingEl) {
                            streamingEl = document.createElement('div');
                            streamingEl.className = 'chat-msg agent';
                            msgContainer.appendChild(streamingEl);
                            // Push agent reply placeholder to state on first delta
                            state.chatMessages.push({ role: 'assistant', content: fullReply });
                        } else {
                            // Update the last message (agent's streaming reply) in-place
                            const last = state.chatMessages[state.chatMessages.length - 1];
                            if (last && last.role === 'assistant') last.content = fullReply;
                        }
                        streamingEl.textContent = fullReply;
                        msgContainer.scrollTop = msgContainer.scrollHeight;
                        saveChatToStorage();
                        break;
                    }
                    case 'response.output_text.done': {
                        if (data.text && data.text !== fullReply) {
                            fullReply = data.text;
                            if (streamingEl) streamingEl.textContent = fullReply;
                            const last = state.chatMessages[state.chatMessages.length - 1];
                            if (last && last.role === 'assistant') last.content = fullReply;
                            saveChatToStorage();
                        }
                        break;
                    }
                    case 'response.completed': {
                        streamDone = true;
                        if (pendingEl.parentNode) pendingEl.remove();
                        break;
                    }
                    case 'error': {
                        if (pendingEl.parentNode) pendingEl.remove();
                        if (streamingEl) streamingEl.remove();
                        addChatMessage('system', '错误: ' + (data.error || '未知').substring(0, 300));
                        break;
                    }
                }
            }
        }
    } catch (e) {
        // Ignore AbortError (user switched to another conversation)
        if (e.name !== 'AbortError') {
            if (pendingEl.parentNode) pendingEl.remove();
            addChatMessage('system', '连接中断: ' + esc(e.message));
        }
    }

    // Cleanup
    state._abortController = null;
    if (pendingEl.parentNode) pendingEl.remove();

    // Save to state (if streaming already pushed the assistant message, just update it)
    if (fullReply) {
        const last = state.chatMessages[state.chatMessages.length - 1];
        if (last && last.role === 'assistant') {
            last.content = fullReply;  // update in-place from streaming
        } else {
            state.chatMessages.push({ role: 'assistant', content: fullReply });
        }
        state._lastHttpReply = fullReply;
    }

    // Quick DB sync for any missed content
    await syncConversationFromDB(
        state.activeChatInstanceId,
        state.activeChatAgentId || 0,
        null,
        fullReply,
    );

    saveChatToStorage();
}
async function syncConversationFromDB(instanceId, masterAgentId, pendingEl, httpReply) {
    if (!instanceId) return;

    try {
        // Determine which agent to query — use master agent
        const agentId = masterAgentId || await getMasterAgentId(instanceId);
        if (!agentId) return;

        const resp = await fetch(`/api/workspaces/${instanceId}/agents/${agentId}/conversations?limit=10`);
        if (!resp.ok) return;
        const data = await resp.json();
        const conversations = data.conversations || [];
        if (!conversations.length) return;

        // Only show conversations matching the current conversation_id
        const currentConvId = state._conversationId || '';
        const filtered = currentConvId
            ? conversations.filter(c => c.conversation_id === currentConvId)
            : conversations;

        // Show only conversations that are new (not already shown)
        let foundNew = false;

        for (const conv of filtered) {
            const convId = conv.id;
            if (state._shownConversationIds.has(convId)) continue;

            // Extract text from output
            let text = '';
            for (const step of (conv.output || [])) {
                if (step.type === 'message' && step.content) {
                    for (const part of step.content) {
                        if (part.text) text += part.text;
                    }
                }
            }

            if (text && text !== httpReply) {
                // New conversation with content — show in chat
                if (pendingEl && pendingEl.parentNode) pendingEl.remove();
                addChatMessage('agent', text);
                state.chatMessages.push({ role: 'assistant', content: text });
                state._shownConversationIds.add(convId);
                foundNew = true;
            } else if (conv.error_msg && !httpReply) {
                // Error conversation — show warning
                if (pendingEl && pendingEl.parentNode) {
                    pendingEl.className = 'chat-msg system chat-timeout-msg';
                    pendingEl.innerHTML = `⚠️ ${esc(conv.error_msg.substring(0, 200))}`;
                }
                state._shownConversationIds.add(convId);
                foundNew = true;
            } else {
                // Mark as seen even if no new content
                state._shownConversationIds.add(convId);
            }
        }

        if (!foundNew && !httpReply) {
            // No new content from DB and no HTTP reply
            if (pendingEl && pendingEl.parentNode) {
                pendingEl.className = 'chat-msg system chat-timeout-msg';
                pendingEl.innerHTML = '⏰ 暂无回复。Agent 可能仍在处理中，请稍后重试或查看「监控」页面。';
            }
        }

    } catch (e) {
        // DB sync failed — non-fatal
        if (!httpReply && pendingEl && pendingEl.parentNode) {
            pendingEl.className = 'chat-msg system chat-timeout-msg';
            pendingEl.innerHTML = '⏰ 无法获取回复。请稍后重试或查看「监控」页面。';
        }
    }
}

async function getMasterAgentId(instanceId) {
    try {
        const resp = await fetch(`/api/workspaces/${instanceId}/agents`);
        const data = await resp.json();
        const master = (data.agents || []).find(a => a.role === 'master');
        return master ? master.id : 0;
    } catch (e) {
        return 0;
    }
}

function handleChatKey(event) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendChatMessage(); }
    setTimeout(() => { const ta = event.target; ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'; }, 0);
}

function addChatMessage(type, content) {
    const div = document.createElement('div');
    div.className = `chat-msg ${type}`;
    div.textContent = content;
    const ctr = $('#chat-messages'); ctr.appendChild(div); ctr.scrollTop = ctr.scrollHeight;
}

function saveChatToStorage() {
    if (!state.activeChatInstanceId) return;
    try {
        const agentId = state.activeChatAgentId || 0;
        localStorage.setItem(`sconsole-chat-ws-${state.activeChatInstanceId}-agent-${agentId}`, JSON.stringify(state.chatMessages));
    } catch (e) {}
}

// ═══════════════════════════════════════════════════════════════════════
// 批量操作
// ═══════════════════════════════════════════════════════════════════════

function toggleAgentSelect(event, key) {
    if (event.target.checked) state.selectedAgents.add(key); else { state.selectedAgents.delete(key); $('#check-all').checked = false; }
    updateBatchBar();
}

function toggleSelectAll() {
    const master = $('#check-all');
    const all = $$('.agent-check');
    state.selectedAgents.clear();
    all.forEach(cb => { cb.checked = master.checked; if (master.checked) state.selectedAgents.add(cb.dataset.agt); });
    updateBatchBar();
}

function updateBatchBar() {
    const bar = $('#agent-batch-bar');
    const count = $('#batch-count');
    const n = state.selectedAgents.size;
    if (n > 0) {
        bar.classList.remove('hidden');
        count.textContent = n + ' 已选择';
        const total = $$('.agent-check').length;
        $('#check-all').checked = (n >= total && total > 0);
    } else { bar.classList.add('hidden'); count.textContent = '0 已选择'; $('#check-all').checked = false; }
}

async function batchStop() {
    const selected = [...state.selectedAgents];
    if (!selected.length) return;
    if (!confirm(`停止 ${selected.length} 个选中的 Agent？`)) return;
    let stopped = 0, failed = 0;
    for (const key of selected) {
        try {
            if (key.startsWith('agent-')) {
                const parts = key.split('-');
                await fetchAPI(`/api/workspaces/${parts[1]}/agents/${parts[2]}/stop`, { method: 'POST' });
                stopped++;
            } else if (key.startsWith('container-')) {
                await fetchAPI(`/api/containers/${encodeURIComponent(key.replace('container-',''))}/stop`, { method: 'POST' });
                stopped++;
            } else if (key.startsWith('inst-')) {
                const iid = key.replace('inst-', '');
                const agData = await fetchAPI(`/api/workspaces/${iid}/agents`);
                if (agData) for (const a of (agData.agents || [])) {
                    if (a.status === 'running') await fetchAPI(`/api/workspaces/${iid}/agents/${a.id}/stop`, { method: 'POST' });
                }
                stopped++;
            }
        } catch (e) { failed++; }
    }
    addLog(`批量停止: ${stopped} 成功, ${failed} 失败`, failed ? 'error' : 'success');
    refreshInstances();
}

async function batchDelete() {
    const selected = [...state.selectedAgents];
    if (!selected.length) return;
    if (!confirm(`删除 ${selected.length} 个选中项？此操作不可撤销！`)) return;
    let deleted = 0, failed = 0;
    for (const key of selected) {
        try {
            if (key.startsWith('agent-')) {
                const parts = key.split('-');
                await fetchAPI(`/api/workspaces/${parts[1]}/agents/${parts[2]}`, { method: 'DELETE' });
                deleted++;
            } else if (key.startsWith('container-')) {
                await fetchAPI(`/api/containers/${encodeURIComponent(key.replace('container-',''))}/stop`, { method: 'POST' });
                deleted++;
            } else if (key.startsWith('inst-')) {
                await fetchAPI(`/api/workspaces/${key.replace('inst-','')}`, { method: 'DELETE' });
                deleted++;
            }
        } catch (e) { failed++; }
    }
    addLog(`批量删除: ${deleted} 成功, ${failed} 失败`, failed ? 'error' : 'success');
    refreshInstances();
}

// ═══════════════════════════════════════════════════════════════════════
// 配置视图
// ═══════════════════════════════════════════════════════════════════════

async function refreshConfigs() {
    const data = await fetchAPI('/api/configs');
    if (data) { state.configs = data.configs || []; renderConfigs(); }
}

function renderConfigs() {
    const container = $('#config-list');
    if (!state.configs.length) { container.innerHTML = '<div class="empty-state">暂无配置。</div>'; return; }
    container.innerHTML = state.configs.map(cfg => {
        const providerLabel = cfg.model_provider ? ` | 供应商: ${esc(cfg.model_provider)}` : '';
        return `<div class="config-card">
            <div class="card-info">
                <div class="card-name">${esc(cfg.name)} (#${cfg.id})</div>
                <div class="card-meta">模型: ${cfg.model_name || 'N/A'}${providerLabel} | 技能: ${(cfg.skills || []).length}</div>
            </div>
            <div class="card-actions">
                <button class="btn btn-sm" onclick="editConfig(${cfg.id})">编辑</button>
                <button class="btn btn-sm btn-danger" onclick="deleteConfig(${cfg.id})">删除</button>
            </div>
        </div>
        <div class="config-files" id="config-files-${cfg.id}">
            <div class="config-files-header">
                <span class="config-files-label">附件文件</span>
                <label class="btn btn-sm btn-primary config-upload-btn">
                    上传
                    <input type="file" multiple onchange="uploadConfigFiles(${cfg.id}, this)" style="display:none">
                </label>
            </div>
            <div class="config-files-list" id="config-files-list-${cfg.id}">加载中...</div>
        </div>`;
    }).join('');

    state.configs.forEach(cfg => loadConfigFiles(cfg.id));
}

function showConfigForm() { $('#config-form').reset(); $('#config-form').elements.config_id.value = ''; $('#config-form-title').textContent = '创建配置'; $('#config-form-panel').classList.remove('hidden'); setTimeout(()=>{const el=$('#config-form').elements.name; if(el)el.focus();},100); }
function onProviderChange(provider) {
    const urlInput = $('#config-form').elements.model_url;
    if (provider && PROVIDER_DEFAULT_URLS[provider] && !urlInput.value) {
        urlInput.value = PROVIDER_DEFAULT_URLS[provider];
    }
}
function hideConfigForm() { $('#config-form-panel').classList.add('hidden'); }

async function loadConfigFiles(configId) {
    const list = document.getElementById('config-files-list-' + configId);
    if (!list) return;
    const data = await fetchAPI(`/api/configs/${configId}/files`);
    const files = data ? data.files || [] : [];
    if (!files.length) {
        list.innerHTML = '<span class="text-muted" style="font-size:12px">暂无上传文件</span>';
    } else {
        list.innerHTML = files.map(f => `
            <span class="config-file-item">
                ${esc(f)}
                <button class="btn-file-del" onclick="deleteConfigFile(${configId},'${esc(f)}')" title="删除">×</button>
            </span>
        `).join('');
    }
}

async function uploadConfigFiles(configId, input) {
    const files = input.files;
    if (!files.length) return;
    const formData = new FormData();
    for (const f of files) formData.append('files', f);
    const res = await fetch(`/api/configs/${configId}/files`, { method: 'POST', body: formData });
    if (res.ok) {
        addLog(`${files.length} 个文件已上传到配置 #${configId}`, 'success');
        loadConfigFiles(configId);
    }
    input.value = '';
}

async function deleteConfigFile(configId, filename) {
    if (!confirm(`从配置 #${configId} 中删除 "${filename}"？`)) return;
    await fetchAPI(`/api/configs/${configId}/files/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    loadConfigFiles(configId);
}

async function editConfig(id) {
    const cfg = await fetchAPI(`/api/configs/${id}`); if (!cfg) return;
    const f = $('#config-form');
    f.elements.config_id.value = cfg.id; f.elements.name.value = cfg.name; f.elements.soul_file.value = cfg.soul_file;
    f.elements.memory_file.value = cfg.memory_file; f.elements.tech_docs.value = cfg.tech_docs;
    f.elements.model_url.value = cfg.model_url; f.elements.model_name.value = cfg.model_name;
    f.elements.model_provider.value = cfg.model_provider || '';
    f.elements.proxy.value = cfg.proxy || '';
    f.elements.model_api_key.value = cfg.model_api_key;
    f.elements.skills_str.value = (cfg.skills || []).join(', ');
    $('#config-form-title').textContent = `编辑配置 #${id}`;
    $('#config-form-panel').classList.remove('hidden');
    setTimeout(()=>{const el=f.elements.name; if(el)el.focus();},100);
}

async function saveConfig(event) {
    event.preventDefault();
    const f = event.target;
    const configId = f.elements.config_id.value;
    const skills = f.elements.skills_str.value.split(',').map(s => s.trim()).filter(Boolean);
    const data = { name: f.elements.name.value, soul_file: f.elements.soul_file.value, memory_file: f.elements.memory_file.value,
        tech_docs: f.elements.tech_docs.value, model_url: f.elements.model_url.value, model_api_key: f.elements.model_api_key.value,
        model_name: f.elements.model_name.value, model_provider: f.elements.model_provider.value,
        proxy: f.elements.proxy.value,
        skills: skills };
    let r;
    if (configId) r = await fetchAPI(`/api/configs/${configId}`, { method: 'PUT', body: JSON.stringify(data) });
    else r = await fetchAPI('/api/configs', { method: 'POST', body: JSON.stringify(data) });
    if (r) { addLog('配置已保存', 'success'); hideConfigForm(); refreshConfigs(); }
}

async function deleteConfig(configId) {
    if (!confirm(`删除配置 #${configId}？`)) return;
    await fetchAPI(`/api/configs/${configId}`, { method: 'DELETE' });
    refreshConfigs();
}

// ═══════════════════════════════════════════════════════════════════════
// 节点视图
// ═══════════════════════════════════════════════════════════════════════

async function refreshNodes() {
    const data = await fetchAPI('/api/nodes');
    if (data) { state.nodes = data.nodes || []; renderNodes(); updateStats(); }
}

async function refreshNodeSelector() {
    const sel = document.getElementById('ws-node-select');
    if (!sel) return;
    const data = await fetchAPI('/api/nodes');
    const nodes = data ? data.nodes || [] : [];
    const online = nodes.filter(n => n.status === 'online');
    sel.innerHTML = '<option value="">-- Auto (first online) --</option>' +
        online.map(n => `<option value="${esc(n.node_id)}">${esc(n.hostname || n.node_id)} (${n.ip_address || ''})</option>`).join('');
}

function renderNodes() {
    const container = $('#node-list');
    if (!state.nodes.length) { container.innerHTML = '<div class="empty-state">无连接节点。</div>'; return; }
    container.innerHTML = state.nodes.map(node => `
        <div class="node-card">
            <div class="card-info">
                <div class="card-name">${esc(node.hostname || node.node_id)} <span class="status-badge status-${node.status}">${node.status}</span></div>
                <div class="card-meta">ID: ${node.node_id} | IP: ${node.ip_address} | 容器引擎: ${node.docker_version || 'N/A'} | CPU: ${node.cpu_count} | 内存: ${node.memory_mb}MB</div>
            </div>
            <div class="card-actions">
                <button class="btn btn-sm btn-danger" onclick="deleteNode('${node.node_id}')">移除</button>
            </div>
        </div>
    `).join('');
}

async function deleteNode(nodeId) {
    if (!confirm(`移除节点 ${nodeId}？`)) return;
    await fetchAPI(`/api/nodes/${nodeId}`, { method: 'DELETE' });
    refreshNodes();
}

// ═══════════════════════════════════════════════════════════════════════
// 技能与预设
// ═══════════════════════════════════════════════════════════════════════

function refreshSkills() {
    fetchAPI('/api/skills').then(data => {
        const c = $('#skill-list');
        const skills = data ? data.skills || [] : [];
        if (!skills.length) { c.innerHTML = '<div class="empty-state">暂无安装的技能。</div>'; return; }
        c.innerHTML = skills.map(s => `<div class="agent-card"><div class="card-info"><div class="card-name">${esc(s.name)}</div><div class="card-meta">v${s.version} | ${s.source}</div></div></div>`).join('');
    });
}
function showSkillInstall() { $('#skill-install-panel').classList.remove('hidden'); }
function hideSkillInstall() { $('#skill-install-panel').classList.add('hidden'); }
function installSkill(event) { event.preventDefault(); fetchAPI('/api/skills/install', { method: 'POST', body: JSON.stringify({ name: event.target.elements.skill_name.value, source: event.target.elements.skill_source.value }) }).then(r => { if (r) { addLog(`技能安装中: ${event.target.elements.skill_name.value}`, 'success'); hideSkillInstall(); } }); }

// ═══════════════════════════════════════════════════════════════════════
// Agent 日志弹窗
// ═══════════════════════════════════════════════════════════════════════

async function openAgentLogs(instanceId, agentId) {
    const modal = document.getElementById('logs-modal');
    const title = document.getElementById('logs-modal-title');
    const body = document.getElementById('logs-modal-body');

    // Clear any previous timer
    if (window._logsTimer) { clearInterval(window._logsTimer); window._logsTimer = null; }

    title.textContent = `Agent #${agentId} — 日志`;
    body.innerHTML = '<div class="logs-loading">正在加载日志...</div>';
    modal.classList.remove('hidden');

    const data = await fetchAPI(`/api/workspaces/${instanceId}/agents/${agentId}/logs?tail=300`);
    const logs = data ? (data.logs || data.error || '暂无日志') : '获取日志失败';
    body.innerHTML = `<pre class="logs-content">${esc(logs)}</pre>`;
    // Scroll to bottom after DOM reflow completes
    setTimeout(() => { body.scrollTop = body.scrollHeight; }, 50);

    window._logsTimer = setInterval(async () => {
        const d = await fetchAPI(`/api/workspaces/${instanceId}/agents/${agentId}/logs?tail=300`);
        if (d) {
            const savedScroll = body.scrollTop;
            const wasAtBottom = body.scrollTop + body.clientHeight >= body.scrollHeight - 50;
            const newContent = esc(d.logs || d.error || '');
            body.innerHTML = `<pre class="logs-content">${newContent}</pre>`;
            // Delay scroll restoration to after browser reflow
            setTimeout(() => {
                if (wasAtBottom) {
                    body.scrollTop = body.scrollHeight;
                } else if (savedScroll > 0) {
                    body.scrollTop = Math.min(savedScroll, body.scrollHeight);
                }
            }, 50);
        }
    }, 3000);
}

function closeLogsModal() {
    document.getElementById('logs-modal').classList.add('hidden');
    if (window._logsTimer) { clearInterval(window._logsTimer); window._logsTimer = null; }
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeLogsModal(); closeMonitor(); closeFilesModal(); closeWSConfig(); } });

// ─── 工作空间文件浏览 ─────────────────────────────────

function openWorkspaceFiles(workspaceId) {
    state._filesWorkspaceId = workspaceId;
    const inst = state.instances.find(i => i.id === workspaceId);
    const name = inst ? inst.name : `工作空间 #${workspaceId}`;
    $('#files-modal-title').textContent = `文件 - ${name}`;
    $('#files-modal-body').innerHTML = '<div class="files-loading">正在加载...</div>';
    $('#files-modal').classList.remove('hidden');
    loadWorkspaceFiles(workspaceId);
}

async function loadWorkspaceFiles(workspaceId) {
    try {
        const resp = await fetch(`/api/workspaces/${workspaceId}/files`);
        const data = await resp.json();
        const files = data.files || [];
        if (!files.length) {
            $('#files-modal-body').innerHTML = '<div class="files-empty">暂无上传文件</div>';
            return;
        }
        let html = '<table class="files-table"><thead><tr><th>文件名</th><th>大小</th><th>操作</th></tr></thead><tbody>';
        for (const f of files) {
            const sizeStr = f.size < 1024 ? f.size + ' B' :
                f.size < 1048576 ? (f.size / 1024).toFixed(1) + ' KB' :
                (f.size / 1048576).toFixed(1) + ' MB';
            html += `<tr>
                <td title="${esc(f.name)}">${esc(f.name.length > 40 ? f.name.substring(0,40)+'...' : f.name)}</td>
                <td>${sizeStr}</td>
                <td class="files-actions">
                    <a href="/api/workspaces/${workspaceId}/files/${encodeURIComponent(f.name)}" class="btn btn-sm" download>下载</a>
                    <button class="btn btn-sm btn-danger" onclick="deleteWorkspaceFile(${workspaceId},'${esc(f.name)}')">删除</button>
                </td>
            </tr>`;
        }
        html += '</tbody></table>';
        $('#files-modal-body').innerHTML = html;
    } catch (e) {
        $('#files-modal-body').innerHTML = `<div class="files-error">加载失败: ${esc(e.message)}</div>`;
    }
}

async function deleteWorkspaceFile(workspaceId, filename) {
    if (!confirm(`删除 ${filename}？`)) return;
    try {
        await fetch(`/api/workspaces/${workspaceId}/files/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        loadWorkspaceFiles(workspaceId);
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

function closeFilesModal() {
    $('#files-modal').classList.add('hidden');
}

// ─── 工作空间配置查看 ─────────────────────────────────

async function openWSConfig(workspaceId) {
    const inst = state.instances.find(i => i.id === workspaceId);
    const name = inst ? inst.name : `工作空间 #${workspaceId}`;
    $('#wsconfig-modal-title').textContent = `配置 - ${name}`;
    $('#wsconfig-modal-body').innerHTML = '<div class="files-loading">正在加载...</div>';
    $('#wsconfig-modal').classList.remove('hidden');

    try {
        const resp = await fetch(`/api/workspaces/${workspaceId}/config`);
        const data = await resp.json();
        const agents = data.agents || [];
        let html = '';
        for (const a of agents) {
            const cfg = a.config || {};
            const roleBadge = a.role === 'master'
                ? '<span style="color:#f0a500;white-space:nowrap">[主控]</span>'
                : '<span style="color:#58a6ff;white-space:nowrap">[子 Agent]</span>';
            const skillsCount = (cfg.skills || []).length;
            const skillsPreview = (cfg.skills || []).slice(0, 3).map(s => {
                const name = s.split('/').pop() || s;
                return name.length > 25 ? name.substring(0, 25) + '...' : name;
            }).join(', ');
            html += `<div class="wsconfig-card">
                <div class="wsconfig-card-header">
                    <span class="wsconfig-agent-name">${esc(a.agent_name)}</span>
                    ${roleBadge}
                    <span class="status-badge status-${a.status}">${a.status}</span>
                    <span class="wsconfig-port">:${a.host_port || 'N/A'}</span>
                </div>
                <div class="wsconfig-card-body">
                    <div class="wsconfig-row"><span class="wsconfig-label">模型</span><span class="wsconfig-value">${esc(cfg.model_name || 'N/A')}</span></div>
                    <div class="wsconfig-row"><span class="wsconfig-label">供应商</span><span class="wsconfig-value">${esc(cfg.model_provider || 'N/A')}</span></div>
                    <div class="wsconfig-row"><span class="wsconfig-label">URL</span><span class="wsconfig-value wsconfig-mono">${esc(cfg.model_url || '-')}</span></div>
                    <div class="wsconfig-row"><span class="wsconfig-label">代理</span><span class="wsconfig-value wsconfig-mono">${esc(cfg.proxy || '-')}</span></div>
                    <div class="wsconfig-row"><span class="wsconfig-label">技能</span><span class="wsconfig-value">${skillsCount > 0 ? esc(skillsPreview) + (skillsCount > 3 ? ' ...' : '') : '-'}</span></div>
                </div>
            </div>`;
        }
        if (!html) html = '<div class="files-empty">暂无 Agent</div>';
        $('#wsconfig-modal-body').innerHTML = html;
    } catch (e) {
        $('#wsconfig-modal-body').innerHTML = `<div class="files-error">加载失败: ${esc(e.message)}</div>`;
    }
}

function closeWSConfig() {
    $('#wsconfig-modal').classList.add('hidden');
}

// ═══════════════════════════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════════════════════════

function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(ts) {
    if (!ts) return 'N/A';
    try { return new Date(ts).toLocaleString(); } catch (e) { return String(ts); }
}

// ═══════════════════════════════════════════════════════════════════════
// 工作空间与 Agent 创建表单
// ═══════════════════════════════════════════════════════════════════════

let subAgentCounter = 0;

async function addSubAgentRow(name, configId, desc) {
    subAgentCounter++;
    const configs = await fetchAPI('/api/configs');
    const options = configs ? configs.configs.map(c => `<option value="${c.id}">${esc(c.name)} (#${c.id})</option>`).join('') : '';
    const row = document.createElement('div');
    row.className = 'sub-agent-row';
    row.innerHTML = `
        <div class="sub-agent-fields">
            <input type="text" class="form-input" placeholder="Agent 名称" value="${esc(name || '')}" data-field="name">
            <select class="form-select" data-field="config_id">
                <option value="">-- 模板 --</option>
                ${options}
            </select>
            <input type="text" class="form-input" placeholder="此 Agent 做什么？(例如：Python 后端、代码审查)" value="${esc(desc || '')}" data-field="desc">
        </div>
        <button type="button" class="btn btn-sm btn-danger" onclick="this.closest('.sub-agent-row').remove()">×</button>
    `;
    if (configId) {
        setTimeout(() => { row.querySelector(`[data-field="config_id"]`).value = configId; }, 50);
    }
    document.getElementById('sub-agent-rows').appendChild(row);
}

async function submitWorkspace(event) {
    event.preventDefault();
    const form = event.target;
    const name = form.ws_name.value.trim();
    if (!name) return;

    const subAgents = [];
    document.querySelectorAll('.sub-agent-row').forEach(row => {
        const nameEl = row.querySelector('[data-field="name"]');
        const cfgEl = row.querySelector('[data-field="config_id"]');
        const descEl = row.querySelector('[data-field="desc"]');
        if (nameEl && nameEl.value.trim()) {
            subAgents.push({
                name: nameEl.value.trim(),
                config_id: cfgEl ? parseInt(cfgEl.value) || 0 : 0,
                desc: descEl ? descEl.value.trim() : '',
            });
        }
    });

    const deployMaster = form.deploy_master.checked;
    const nodeId = form.ws_node.value.trim();

    // 1) 创建工作空间
    const wsResult = await fetchAPI('/api/workspaces', {
        method: 'POST',
        body: JSON.stringify({ name: name, description: form.ws_desc.value.trim(), node_id: nodeId }),
    });
    if (!wsResult) return;
    const wsId = wsResult.workspace_id;
    const masterId = wsResult.master_agent_id;
    addLog(`工作空间「${name}」已创建 (#${wsId})`, 'success');

    // 2) 部署子 Agent
    const workerDescriptions = {};
    for (const sa of subAgents) {
        const r = await fetchAPI(`/api/workspaces/${wsId}/agents`, {
            method: 'POST',
            body: JSON.stringify({ name: sa.name, config_id: sa.config_id || 2 }),
        });
        if (r && sa.desc) {
            workerDescriptions[r.agent_id] = sa.desc;
        }
    }

    // 3) 部署主控 Agent
    if (deployMaster) {
        const firstConfig = subAgents.find(s => s.config_id > 0);
        const cfgId = firstConfig ? firstConfig.config_id : 2;
        const body = { config_id: cfgId };
        if (Object.keys(workerDescriptions).length > 0) {
            body.worker_descriptions = workerDescriptions;
        }
        await fetchAPI(`/api/workspaces/${wsId}/agents/${masterId}/deploy`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
        addLog('主控 Agent 部署已开始', 'success');
    }

    form.reset();
    document.getElementById('sub-agent-rows').innerHTML = '';
    subAgentCounter = 0;
    switchView('agents');
    setTimeout(() => refreshInstances(), 500);
}

function openAddAgent(instanceId) {
    document.getElementById('add-agent-instance-id').value = instanceId;
    const inst = state.instances.find(i => i.id === instanceId);
    document.getElementById('add-agent-title').textContent = `添加 Agent 到 ${inst ? inst.name : '工作空间'}`;

    fetchAPI('/api/configs').then(data => {
        const sel = document.getElementById('add-agent-config-select');
        sel.innerHTML = '<option value="">-- 选择模板 --</option>' +
            (data ? data.configs.map(c => `<option value="${c.id}">${esc(c.name)} (#${c.id})</option>`).join('') : '');
    });

    document.getElementById('add-agent-form').reset();
    switchView('add-agent');
    setTimeout(() => { const inp = document.querySelector('#add-agent-form [name="agent_name"]'); if (inp) inp.focus(); }, 200);
}

async function submitAddAgent(event) {
    event.preventDefault();
    const form = event.target;
    const instanceId = parseInt(form.instance_id.value);
    const name = form.agent_name.value.trim();
    const configId = parseInt(form.config_id.value);
    const desc = form.agent_desc.value.trim();

    if (!name || !configId || !instanceId) return;

    const r = await fetchAPI(`/api/workspaces/${instanceId}/agents`, {
        method: 'POST',
        body: JSON.stringify({ name: name, config_id: configId }),
    });
    if (!r) return;

    addLog(`Agent「${name}」部署已开始`, 'success');

    if (desc) {
        await fetchAPI(`/api/workspaces/${instanceId}/agents`, {
            method: 'POST',
            body: JSON.stringify({ name: name + '_desc', config_id: configId }),
        }).catch(() => {});
    }

    form.reset();
    switchView('agents');
    setTimeout(() => refreshInstances(), 500);
}

// ─── 监控 (Agent 对话历史查看器) ──────────────────────────────────

function openMonitor(instanceId, agentId) {
    state._monitorInstanceId = instanceId;
    state._monitorAgentId = agentId;
    $('#monitor-modal-title').textContent = `监控 – Agent ${agentId}`;
    $('#monitor-modal-body').innerHTML = '<div class="monitor-loading">正在加载对话历史...</div>';
    $('#monitor-modal').classList.remove('hidden');
    loadMonitorConversations(instanceId, agentId);
    // Auto-refresh every 5 seconds
    if (state._monitorTimer) clearInterval(state._monitorTimer);
    state._monitorTimer = setInterval(() => {
        if (state._monitorInstanceId && state._monitorAgentId) {
            loadMonitorConversations(state._monitorInstanceId, state._monitorAgentId);
        }
    }, 5000);
}

function closeMonitor() {
    $('#monitor-modal').classList.add('hidden');
    state._monitorInstanceId = null;
    state._monitorAgentId = null;
    state._monitorConversations = [];
    state._monitorSelected = new Set();
    if (state._monitorTimer) { clearInterval(state._monitorTimer); state._monitorTimer = null; }
}

async function loadMonitorConversations(instanceId, agentId) {
    // Save expanded state AND modal scroll position before refresh
    const wasExpanded = new Set();
    const modalBody = document.getElementById('monitor-modal-body');
    const modalScrollTop = modalBody ? modalBody.scrollTop : 0;
    document.querySelectorAll('.monitor-collapse-body').forEach(b => {
        if (!b.classList.contains('hidden')) {
            const cid = b.dataset.convId || '';
            if (cid) wasExpanded.add(cid);
        }
    });

    state._monitorConversations = [];
    state._monitorSelected = new Set();
    try {
        const resp = await fetch(`/api/workspaces/${instanceId}/agents/${agentId}/conversations`);

        if (!resp.ok) {
            let errDetail = `HTTP ${resp.status} ${resp.statusText}`;
            try {
                const errData = await resp.json();
                errDetail = errData.detail || errData.message || errDetail;
            } catch (_) {
                const text = await resp.text().catch(() => '');
                if (text.includes('Internal Server Error')) {
                    errDetail = '服务器错误 – 对话表可能还不存在。请运行数据库迁移: sql_files/003_refactor_v3.sql';
                } else {
                    errDetail = text.substring(0, 200) || errDetail;
                }
            }
            $('#monitor-modal-body').innerHTML = `<div class="monitor-error">${esc(errDetail)}</div>`;
            return;
        }

        const data = await resp.json();

        if (!data.conversations || data.conversations.length === 0) {
            $('#monitor-modal-body').innerHTML = '<div class="monitor-empty">此 Agent 暂无对话历史。</div>';
            return;
        }

        state._monitorConversations = data.conversations;
        renderTimeline(data.conversations);

        // Restore expanded state
        if (wasExpanded.size > 0) {
            document.querySelectorAll('.monitor-collapse-body').forEach(b => {
                const cid = b.dataset.convId || '';
                if (wasExpanded.has(cid)) {
                    b.classList.remove('hidden');
                    const icon = document.getElementById(b.id.replace('-body', '-icon'));
                    if (icon) icon.innerHTML = '&#9660;';
                    const preview = document.getElementById(b.id.replace('-body', '-preview'));
                    if (preview) preview.classList.add('hidden');
                }
            });
            // Restore modal scroll position after browser reflow
            if (modalScrollTop > 0) {
                setTimeout(() => {
                    const mb = document.getElementById('monitor-modal-body');
                    if (mb) mb.scrollTop = modalScrollTop;
                }, 80);
            }
        }
    } catch (err) {
        $('#monitor-modal-body').innerHTML = `<div class="monitor-error">加载失败: ${esc(err.message)}</div>`;
    }
}

// ─── Monitor batch operations ─────────────────────────────────────

function monitorToggleSelectAll() {
    const master = document.getElementById('monitor-check-all');
    const groupCbs = document.querySelectorAll('.monitor-group-cb');
    state._monitorSelected.clear();
    groupCbs.forEach(cb => {
        cb.checked = master.checked;
        if (master.checked) {
            let ids = [];
            try { ids = JSON.parse(cb.dataset.groupIds); } catch (e) {}
            ids.forEach(id => state._monitorSelected.add(id));
        }
    });
    monitorUpdateBatchBar();
}

function monitorToggleOne(convId, checked) {
    if (checked) state._monitorSelected.add(convId);
    else state._monitorSelected.delete(convId);
    const master = document.getElementById('monitor-check-all');
    if (master) master.checked = state._monitorSelected.size === document.querySelectorAll('.monitor-cb').length;
    monitorUpdateBatchBar();
}

function monitorUpdateBatchBar() {
    const bar = document.getElementById('monitor-batch-bar');
    const count = document.getElementById('monitor-batch-count');
    if (!bar || !count) return;
    const n = state._monitorSelected.size;
    if (n > 0) {
        bar.classList.remove('hidden');
        count.textContent = `已选 ${n} 条`;
    } else {
        bar.classList.add('hidden');
        count.textContent = '已选 0 条';
    }
}

function monitorToggleGroupSelect(cb) {
    // Select/deselect all conversations in a group
    let ids = [];
    try { ids = JSON.parse(cb.dataset.groupIds); } catch (e) { return; }
    if (cb.checked) {
        ids.forEach(id => state._monitorSelected.add(id));
    } else {
        ids.forEach(id => state._monitorSelected.delete(id));
    }
    // Update master checkbox
    const master = document.getElementById('monitor-check-all');
    if (master) master.checked = state._monitorSelected.size === document.querySelectorAll('.monitor-cb').length;
    monitorUpdateBatchBar();
}

async function monitorDeleteGroup(groupIdsJson) {
    let ids = [];
    try { ids = JSON.parse(groupIdsJson); } catch (e) { return; }
    if (!ids.length) return;
    if (!confirm(`删除此对话组的 ${ids.length} 条记录？`)) return;
    try {
        const resp = await fetch('/api/conversations/batch-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids }),
        });
        if (resp.ok) {
            const iid = state._monitorInstanceId;
            const aid = state._monitorAgentId;
            if (iid && aid) loadMonitorConversations(iid, aid);
        } else {
            alert('删除失败');
        }
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

async function monitorDeleteOne(convId) {
    if (!confirm(`删除这条对话记录？`)) return;
    try {
        const resp = await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
        if (resp.ok) {
            const iid = state._monitorInstanceId;
            const aid = state._monitorAgentId;
            if (iid && aid) loadMonitorConversations(iid, aid);
        } else {
            alert('删除失败');
        }
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

async function monitorBatchDelete() {
    const ids = Array.from(state._monitorSelected);
    if (!ids.length) return;
    if (!confirm(`确认删除选中的 ${ids.length} 条对话记录？此操作不可撤销！`)) return;
    try {
        const resp = await fetch('/api/conversations/batch-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids }),
        });
        if (resp.ok) {
            const iid = state._monitorInstanceId;
            const aid = state._monitorAgentId;
            if (iid && aid) loadMonitorConversations(iid, aid);
        } else {
            alert('批量删除失败');
        }
    } catch (e) {
        alert('批量删除失败: ' + e.message);
    }
}

function renderTimeline(conversations) {
    // Group by conversation_id
    const groups = {};
    for (const c of conversations) {
        const cid = c.conversation_id || 'direct';
        if (!groups[cid]) groups[cid] = { id: cid, items: [], created_at: c.created_at };
        groups[cid].items.push(c);
    }

    // Build toolbar + timeline HTML
    let html = '';

    // ── Batch toolbar ──
    html += `<div id="monitor-batch-bar" class="monitor-batch-bar hidden">`;
    html += `<label class="monitor-check-all-label"><input type="checkbox" id="monitor-check-all" onchange="monitorToggleSelectAll()"> 全选</label>`;
    html += `<span id="monitor-batch-count">已选 0 条</span>`;
    html += `<button class="btn btn-sm btn-danger" onclick="monitorBatchDelete()">删除所选</button>`;
    html += `</div>`;

    // ── Expand/Collapse all ──
    html += `<div class="monitor-expand-bar">`;
    html += `<button class="btn btn-sm" onclick="monitorExpandAll()">展开全部</button>`;
    html += `<button class="btn btn-sm" onclick="monitorCollapseAll()">折叠全部</button>`;
    html += `</div>`;

    let groupIdx = 0;
    for (const [cid, group] of Object.entries(groups)) {
        groupIdx++;
        const groupId = `monitor-group-${groupIdx}`;
        const shortCid = cid.length > 30 ? cid.substring(0, 30) + '...' : cid;

        // Collect conversation IDs in this group
        const groupConvIds = group.items.map(it => it.id);
        const groupIdsJson = JSON.stringify(groupConvIds);

        // Collect user inputs for collapsed preview
        const inputs = group.items
            .map(it => it.user_input || '')
            .filter(Boolean)
            .slice(0, 3);
        const preview = inputs.map(s => s.substring(0, 80)).join(' | ') || '(无用户输入)';
        const moreHint = inputs.length >= 3 || group.items.filter(it => it.user_input).length > 3
            ? ' ...' : '';

        html += `<div class="monitor-conv-group">`;
        // Header with checkbox + collapse toggle + delete
        html += `<div class="monitor-conv-header monitor-collapse-toggle">`;
        // Group checkbox
        html += `<input type="checkbox" class="monitor-cb monitor-group-cb"
            data-group-ids='${esc(groupIdsJson)}'
            onchange="monitorToggleGroupSelect(this)"
            onclick="event.stopPropagation()">`;
        // Collapse area (clickable)
        html += `<span class="monitor-collapse-click" onclick="monitorToggleGroup('${groupId}')">`;
        html += `<span class="monitor-collapse-icon" id="${groupId}-icon">&#9654;</span>`;
        html += `<span class="monitor-conv-id">${esc(shortCid)}</span>`;
        html += `<span class="monitor-conv-time">${formatDate(group.created_at)}</span>`;
        html += `<span class="monitor-conv-count">${group.items.length} 轮</span>`;
        html += `</span>`;
        // Group delete button
        html += `<button class="btn btn-sm btn-danger monitor-del-btn"
            onclick="event.stopPropagation();monitorDeleteGroup('${esc(groupIdsJson)}')"
            title="删除此对话组">×</button>`;
        html += `</div>`;
        // Collapsed preview
        html += `<div class="monitor-collapsed-preview" id="${groupId}-preview">`;
        html += `<span class="monitor-preview-text">${esc(preview)}${moreHint}</span>`;
        html += `</div>`;
        // Expandable body
        html += `<div class="monitor-collapse-body hidden" id="${groupId}-body" data-conv-id="${esc(cid)}">`;
        html += `<div class="monitor-timeline">`;

        group.items.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));

        for (const item of group.items) {
            const isError = item.status === 'error' || item.error_msg;
            const turnClass = isError ? 'error' : 'outgoing';

            html += `<div class="monitor-turn ${turnClass}">`;
            html += `<div class="monitor-turn-head">`;
            html += `<span class="monitor-turn-dir">${isError ? '错误' : '轮次'}</span>`;
            html += `<span class="monitor-turn-time">${formatDate(item.created_at)}</span>`;
            html += `<span class="monitor-turn-status ${item.status || ''}">${esc(item.status || 'completed')}</span>`;
            html += `</div>`;
            html += `<div class="monitor-turn-body">`;

            const userInput = item.user_input || '';
            if (userInput) {
                const displayInput = userInput.length > 3000 ? userInput.substring(0, 3000) + '...' : userInput;
                html += `<div class="monitor-section monitor-user-input">`;
                html += `<div class="monitor-section-label">&#128172; 用户提问</div>`;
                html += `<pre class="monitor-pre monitor-input-text">${esc(displayInput)}</pre>`;
                html += `</div>`;
            }

            if (item.output && Array.isArray(item.output) && item.output.length > 0) {
                html += `<div class="monitor-section">`;
                html += `<div class="monitor-section-label">&#129302; 模型输出 (${item.output.length} 步骤)</div>`;
                let stepIdx = 0;
                for (const step of item.output) {
                    const stepId = `step-${item.id}-${stepIdx}`;
                    html += `<div class="monitor-step">`;
                    html += `<span class="monitor-step-type ${step.type || ''}">${esc(step.type || 'unknown')}</span>`;
                    if (step.type === 'function_call') {
                        html += `<span class="monitor-step-fn">${esc(step.name || '')}</span>`;
                        html += `<button class="monitor-toggle-btn" onclick="monitorToggleStep('${stepId}')" id="${stepId}-btn">▶</button>`;
                        html += `<pre class="monitor-pre monitor-args hidden" id="${stepId}">${esc(typeof step.arguments === 'string' ? step.arguments : JSON.stringify(step.arguments, null, 2))}</pre>`;
                    } else if (step.type === 'function_call_output') {
                        html += `<span class="monitor-step-callid">call_id: ${esc((step.call_id || '').substring(0, 30))}...</span>`;
                        html += `<button class="monitor-toggle-btn" onclick="monitorToggleStep('${stepId}')" id="${stepId}-btn">▶</button>`;
                        const outStr = step.output ? (typeof step.output === 'string' ? step.output : JSON.stringify(step.output, null, 2)) : '';
                        const truncated = outStr.length > 2000 ? outStr.substring(0, 2000) + '...' : outStr;
                        html += `<pre class="monitor-pre hidden" id="${stepId}">${esc(truncated)}</pre>`;
                    } else if (step.type === 'message') {
                        const role = step.role || 'unknown';
                        const content = step.content || [];
                        html += `<span class="monitor-step-role">${esc(role)}</span>`;
                        for (const part of (Array.isArray(content) ? content : [content])) {
                            if (part && part.text) {
                                const text = typeof part.text === 'string' ? part.text : JSON.stringify(part.text);
                                html += `<div class="monitor-message-text">${esc(text.substring(0, 1500))}${text.length > 1500 ? '...' : ''}</div>`;
                            }
                        }
                    } else if (step.text || step.content) {
                        const text = typeof step.text === 'string' ? step.text : (typeof step.content === 'string' ? step.content : JSON.stringify(step));
                        html += `<pre class="monitor-pre">${esc(text.substring(0, 2000))}${text.length > 2000 ? '...' : ''}</pre>`;
                    } else {
                        html += `<pre class="monitor-pre">${esc(JSON.stringify(step, null, 2).substring(0, 2000))}</pre>`;
                    }
                    html += `</div>`;
                    stepIdx++;
                }
                html += `</div>`;
            } else if (item.output && typeof item.output === 'string' && item.output) {
                html += `<div class="monitor-section">`;
                html += `<div class="monitor-section-label">&#129302; 模型输出</div>`;
                html += `<pre class="monitor-pre">${esc(item.output.substring(0, 5000))}${item.output.length > 5000 ? '...' : ''}</pre>`;
                html += `</div>`;
            }

            if (item.usage_info && typeof item.usage_info === 'object' && Object.keys(item.usage_info).length > 0) {
                html += `<div class="monitor-section">`;
                html += `<div class="monitor-section-label">&#9881; 用量</div>`;
                html += `<pre class="monitor-pre">${esc(JSON.stringify(item.usage_info, null, 2))}</pre>`;
                html += `</div>`;
            }

            if (item.error_msg) {
                html += `<div class="monitor-section">`;
                html += `<div class="monitor-section-label error">&#9888; 错误</div>`;
                html += `<pre class="monitor-pre monitor-error-text">${esc(item.error_msg)}</pre>`;
                html += `</div>`;
            }

            html += `</div></div>`;
        }

        html += `</div></div></div>`;  // timeline, collapse-body, conv-group
    }

    $('#monitor-modal-body').innerHTML = html;
    monitorUpdateBatchBar();
}

// ── Collapse/Expand helpers ───────────────────────────────────────

function monitorToggleGroup(groupId) {
    const body = document.getElementById(groupId + '-body');
    const icon = document.getElementById(groupId + '-icon');
    const preview = document.getElementById(groupId + '-preview');
    if (!body || !icon) return;
    const isHidden = body.classList.contains('hidden');
    if (isHidden) {
        body.classList.remove('hidden');
        if (preview) preview.classList.add('hidden');
        icon.innerHTML = '&#9660;';
    } else {
        body.classList.add('hidden');
        if (preview) preview.classList.remove('hidden');
        icon.innerHTML = '&#9654;';
    }
}

function monitorExpandAll() {
    document.querySelectorAll('.monitor-collapse-body').forEach(b => b.classList.remove('hidden'));
    document.querySelectorAll('.monitor-collapse-icon').forEach(i => i.innerHTML = '&#9660;');
    document.querySelectorAll('.monitor-collapsed-preview').forEach(p => p.classList.add('hidden'));
}

function monitorCollapseAll() {
    document.querySelectorAll('.monitor-collapse-body').forEach(b => b.classList.add('hidden'));
    document.querySelectorAll('.monitor-collapse-icon').forEach(i => i.innerHTML = '&#9654;');
    document.querySelectorAll('.monitor-collapsed-preview').forEach(p => p.classList.remove('hidden'));
}

function monitorToggleStep(stepId) {
    const el = document.getElementById(stepId);
    const btn = document.getElementById(stepId + '-btn');
    if (!el || !btn) return;
    const isHidden = el.classList.contains('hidden');
    if (isHidden) {
        el.classList.remove('hidden');
        btn.innerHTML = '▼';
    } else {
        el.classList.add('hidden');
        btn.innerHTML = '▶';
    }
}

// ─── 初始化 ───────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    const validViews = ['dashboard', 'agents', 'chat', 'configs', 'nodes', 'skills', 'create-workspace', 'add-agent'];
    const hashView = location.hash.replace('#', '');
    const savedView = localStorage.getItem('sconsole-active-view');
    const initialView = validViews.includes(hashView) ? hashView : validViews.includes(savedView) ? savedView : 'dashboard';
    switchView(initialView);
    window.addEventListener('hashchange', () => {
        const v = location.hash.replace('#', '');
        if (validViews.includes(v) && v !== state.activeView) switchView(v);
    });
    connectWebSocket();
});
// Provider default URLs
const PROVIDER_DEFAULT_URLS = {
    openai: 'https://api.openai.com/v1',
    openrouter: 'https://openrouter.ai/api/v1',
    deepseek: 'https://api.deepseek.com/v1',
    anthropic: 'https://api.anthropic.com/v1',
    xai: 'https://api.x.ai/v1',
    google: 'https://generativelanguage.googleapis.com/v1beta',
    kimi: 'https://api.kimi.com/coding',
    alibaba: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    minimax: 'https://api.minimax.chat/v1',
    glm: 'https://open.bigmodel.cn/api/paas/v4',
    custom: '',
};
