}

// ============ Approvals & Policies ============
var _selectedPolicyAgent = '';  // agent id for policy config

function renderApprovals() {
  var c = document.getElementById('content');
  var pending = (approvals||[]).filter(function(a){ return a.status === 'pending'; });
  var history = (approvals||[]).filter(function(a){ return a.status !== 'pending'; }).slice(0, 20);

  // Build agent selector options
  var agentOpts = agents.map(function(a) {
    return '<option value="' + a.id + '"' + (_selectedPolicyAgent === a.id ? ' selected' : '') + '>' + esc((a.role||'general') + '-' + a.name) + '</option>';
  }).join('');

  // Get the currently selected agent's profile
  var selAgent = agents.find(function(a){ return a.id === _selectedPolicyAgent; });
  var prof = selAgent ? (selAgent.profile || {}) : {};
  var execPolicy = prof.exec_policy || 'ask';
  var execBlacklist = prof.exec_blacklist || [];
  var execWhitelist = prof.exec_whitelist || [];

  c.innerHTML = '' +
    '<div style="margin-bottom:28px">' +
      '<h2 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:28px;font-weight:800;letter-spacing:-0.5px">Tool Approvals & Policies</h2>' +
      '<p style="color:var(--text2);font-size:14px;margin-top:4px">Configure per-agent execution policies and manage pending tool approval requests.</p>' +
    '</div>' +

    '<!-- Agent Selector -->' +
    '<div style="margin-bottom:20px;display:flex;align-items:center;gap:12px">' +
      '<span class="material-symbols-outlined" style="font-size:20px;color:var(--primary)">smart_toy</span>' +
      '<span style="font-size:13px;font-weight:600">Configure Policy for:</span>' +
      '<select id="policy-agent-select" onchange="switchPolicyAgent(this.value)" style="padding:8px 14px;background:var(--surface);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;min-width:200px">' +
        '<option value="">-- Select Agent --</option>' +
        agentOpts +
      '</select>' +
    '</div>' +

    (selAgent ? (
    '<!-- Per-Agent Policy Config -->' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:32px">' +
      '<div style="background:var(--surface);border-radius:12px;padding:24px;border:1px solid var(--border-light)">' +
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px"><span class="material-symbols-outlined" style="font-size:22px;color:var(--primary)">security</span><span style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:15px;font-weight:700">' + esc(selAgent.name) + ' — Execution Policy</span></div>' +
        '<p style="font-size:12px;color:var(--text3);margin-bottom:16px">Control how this agent handles tool execution requests.</p>' +
        '<div style="display:flex;flex-direction:column;gap:8px">' +
          _policyRadio('full', execPolicy, 'Full Access', 'Execute all allowed tools automatically', 'var(--success)') +
          _policyRadio('ask', execPolicy, 'Ask Before Execute', 'Require human approval for each tool invocation', 'var(--warning)') +
          _policyRadio('deny', execPolicy, 'Deny All', 'Block all tool execution requests', 'var(--error)') +
        '</div>' +
      '</div>' +

      '<div style="background:var(--surface);border-radius:12px;padding:24px;border:1px solid var(--border-light)">' +
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px"><span class="material-symbols-outlined" style="font-size:22px;color:var(--primary)">terminal</span><span style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:15px;font-weight:700">' + esc(selAgent.name) + ' — Command Rules</span></div>' +
        '<div style="margin-bottom:16px">' +
          '<div style="margin-bottom:8px"><span style="font-size:10px;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);font-weight:700">Blacklist (Blocked Commands)</span></div>' +
          '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px">' +
            execBlacklist.map(function(cmd){ return '<span style="background:rgba(248,81,73,0.1);color:var(--error);padding:4px 10px;border-radius:6px;font-size:11px;font-family:monospace;display:flex;align-items:center;gap:4px">' + esc(cmd) + ' <span style="cursor:pointer;font-size:14px" onclick="removeAgentBlacklist(\'' + esc(cmd) + '\')">&times;</span></span>'; }).join('') +
          '</div>' +
          '<div style="display:flex;gap:6px"><input id="new-blacklist" placeholder="Add blocked command..." style="flex:1;padding:6px 10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:12px;font-family:monospace" onkeydown="if(event.key===\'Enter\'&&!event.isComposing)addAgentBlacklist()"><button class="btn btn-sm btn-danger" onclick="addAgentBlacklist()">+ Add</button></div>' +
        '</div>' +
        '<div>' +
          '<div style="margin-bottom:8px"><span style="font-size:10px;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);font-weight:700">Whitelist (Always Allowed)</span></div>' +
          '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px">' +
            execWhitelist.map(function(cmd){ return '<span style="background:rgba(63,185,80,0.1);color:var(--success);padding:4px 10px;border-radius:6px;font-size:11px;font-family:monospace;display:flex;align-items:center;gap:4px">' + esc(cmd) + ' <span style="cursor:pointer;font-size:14px" onclick="removeAgentWhitelist(\'' + esc(cmd) + '\')">&times;</span></span>'; }).join('') +
          '</div>' +
          '<div style="display:flex;gap:6px"><input id="new-whitelist" placeholder="Add allowed command..." style="flex:1;padding:6px 10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:12px;font-family:monospace" onkeydown="if(event.key===\'Enter\'&&!event.isComposing)addAgentWhitelist()"><button class="btn btn-sm btn-success" onclick="addAgentWhitelist()">+ Add</button></div>' +
        '</div>' +
      '</div>' +
    '</div>' +
    '<!-- Workspace Access -->' +
    '<div style="background:var(--surface);border-radius:12px;padding:24px;border:1px solid var(--border-light);margin-bottom:32px">' +
      '<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px"><span class="material-symbols-outlined" style="font-size:22px;color:var(--primary)">folder_shared</span><span style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:15px;font-weight:700">' + esc(selAgent.name) + ' — Workspace Access</span></div>' +
      '<div style="font-size:12px;color:var(--text3);margin-bottom:12px">Working Directory: <code style="color:var(--primary)">' + esc((selAgent.profile||{}).working_dir || selAgent.working_dir || 'Not set') + '</code></div>' +
      '<div id="authorized-ws-list-policy"></div>' +
      '<div style="display:flex;gap:8px;margin-top:10px">' +
        '<select id="ws-auth-select-policy" class="input" style="flex:1;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px">' +
          '<option value="">-- Select Agent --</option>' +
        '</select>' +
        '<button class="btn btn-primary" style="padding:8px 16px;cursor:pointer" onclick="authorizeWorkspacePolicy()">Authorize</button>' +
      '</div>' +
    '</div>'
    ) : '<div style="padding:32px;background:var(--surface);border-radius:12px;border:1px solid var(--border-light);text-align:center;color:var(--text3);margin-bottom:32px"><span class="material-symbols-outlined" style="font-size:36px;display:block;margin-bottom:8px">arrow_upward</span>Select an agent above to configure its execution policy.</div>') +

    '<!-- Pending Approvals -->' +
    '<div style="margin-bottom:24px">' +
      '<h3 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:15px;font-weight:700;margin-bottom:14px">Pending Approvals (' + pending.length + ')</h3>' +
      (pending.length === 0 ? '<div style="color:var(--text3);padding:16px;background:var(--surface);border-radius:8px;border:1px solid var(--border-light)">No pending approvals.</div>' : '') +
      pending.map(function(a){
        var ts = (a.created_at || a.timestamp || 0) * 1000;
        var tsText = ts ? new Date(ts).toLocaleString() : '—';
        var args = a.arguments || {};
        var argsStr = JSON.stringify(args);
        // Build human-readable action description
        var actionDesc = '';
        if (a.tool_name === 'bash' || a.tool_name === 'exec') {
          actionDesc = '<span style="color:var(--text2)">Command:</span> <code style="background:var(--bg);padding:2px 6px;border-radius:4px;font-size:11px">' + esc((args.command||'').substring(0,300)) + '</code>';
        } else if (a.tool_name === 'write_file') {
          actionDesc = '<span style="color:var(--text2)">Write to:</span> <code style="background:var(--bg);padding:2px 6px;border-radius:4px;font-size:11px">' + esc(args.path||'') + '</code>' + (args.content ? ' <span style="color:var(--text3)">(' + args.content.length + ' chars)</span>' : '');
        } else if (a.tool_name === 'edit_file') {
          actionDesc = '<span style="color:var(--text2)">Edit:</span> <code style="background:var(--bg);padding:2px 6px;border-radius:4px;font-size:11px">' + esc(args.path||'') + '</code>';
        } else if (a.tool_name === 'read_file') {
          actionDesc = '<span style="color:var(--text2)">Read:</span> <code style="background:var(--bg);padding:2px 6px;border-radius:4px;font-size:11px">' + esc(args.path||'') + '</code>';
        } else if (a.tool_name === 'web_search') {
          actionDesc = '<span style="color:var(--text2)">Search:</span> ' + esc((args.query||'').substring(0,200));
        } else if (a.tool_name === 'web_fetch') {
          actionDesc = '<span style="color:var(--text2)">Fetch URL:</span> <code style="background:var(--bg);padding:2px 6px;border-radius:4px;font-size:11px">' + esc((args.url||'').substring(0,200)) + '</code>';
        } else if (a.tool_name === 'web_screenshot') {
          actionDesc = '<span style="color:var(--text2)">Screenshot:</span> <code style="background:var(--bg);padding:2px 6px;border-radius:4px;font-size:11px">' + esc((args.url||'').substring(0,200)) + '</code>';
        } else if (a.tool_name === 'http_request') {
          actionDesc = '<span style="color:var(--text2)">' + esc(args.method||'GET') + ':</span> <code style="background:var(--bg);padding:2px 6px;border-radius:4px;font-size:11px">' + esc((args.url||'').substring(0,200)) + '</code>';
        } else if (a.tool_name === 'mcp_call') {
          actionDesc = '<span style="color:var(--text2)">MCP:</span> ' + esc(args.mcp_id||'') + ' → <strong>' + esc(args.tool||'') + '</strong>';
          if (args.arguments) actionDesc += ' <span style="color:var(--text3);font-size:10px">' + esc(JSON.stringify(args.arguments).substring(0,150)) + '</span>';
        } else if (a.tool_name === 'send_message') {
          actionDesc = '<span style="color:var(--text2)">To:</span> ' + esc(agentName(args.to_agent||'')) + ' <span style="color:var(--text3)">— ' + esc((args.content||'').substring(0,120)) + '</span>';
        } else if (a.tool_name === 'team_create') {
          actionDesc = '<span style="color:var(--text2)">Create Agent:</span> ' + esc(args.name||'') + ' <span style="color:var(--text3)">— ' + esc((args.task||'').substring(0,120)) + '</span>';
        } else if (a.tool_name === 'task_update') {
          actionDesc = '<span style="color:var(--text2)">Task:</span> ' + esc(args.action||'') + (args.title ? ' — ' + esc(args.title.substring(0,100)) : '');
        } else if (argsStr !== '{}') {
          actionDesc = '<span style="color:var(--text3);font-size:10px;font-family:monospace">' + esc(argsStr.substring(0,250)) + '</span>';
        }
        var reasonHtml = a.reason ? '<div class="approval-detail" style="color:var(--warning);font-size:11px">' + esc(a.reason) + '</div>' : '';
        var actionHtml = actionDesc ? '<div style="margin-top:6px;font-size:12px;line-height:1.5;word-break:break-all">' + actionDesc + '</div>' : '';
        return '<div class="approval-card">' +
          '<div class="approval-header">' +
            '<div style="width:36px;height:36px;border-radius:8px;background:rgba(210,153,34,0.1);display:flex;align-items:center;justify-content:center;flex-shrink:0"><span class="material-symbols-outlined" style="font-size:18px;color:var(--warning)">lock</span></div>' +
            '<div class="approval-info">' +
              '<div class="approval-title">' + esc(a.agent_name) + ' requests to use <strong>' + esc(a.tool_name) + '</strong></div>' +
              reasonHtml +
              actionHtml +
              '<div class="approval-detail" style="margin-top:4px;font-size:10px;color:var(--text3)">' + tsText + '</div>' +
            '</div>' +
          '</div>' +
          '<div class="approval-actions">' +
            '<button class="btn btn-sm btn-success" onclick="approveRequest(\'' + a.approval_id + '\')"><span class="material-symbols-outlined" style="font-size:14px">check</span> Approve</button>' +
            '<button class="btn btn-sm" onclick="approveRequest(\'' + a.approval_id + '\',\'session\')" style="background:var(--primary);color:#0e141b"><span class="material-symbols-outlined" style="font-size:14px">verified</span> Session</button>' +
            '<button class="btn btn-sm btn-danger" onclick="denyRequest(\'' + a.approval_id + '\')"><span class="material-symbols-outlined" style="font-size:14px">close</span> Deny</button>' +
          '</div>' +
        '</div>';
      }).join('') +
    '</div>' +

    '<!-- History -->' +
    '<div>' +
      '<h3 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:15px;font-weight:700;margin-bottom:14px">Recent Decisions</h3>' +
      (history.length === 0 ? '<div style="color:var(--text3);padding:16px">No history yet.</div>' : '') +
      history.map(function(a){
        var ts = (a.decided_at || a.created_at || a.timestamp || 0) * 1000;
        var tsText = ts ? new Date(ts).toLocaleTimeString() : '—';
        var args = a.arguments || {};
        // Brief action summary for history
        var brief = '';
        if (a.tool_name === 'bash' && args.command) brief = ': ' + (args.command||'').substring(0,80);
        else if ((a.tool_name === 'write_file' || a.tool_name === 'edit_file' || a.tool_name === 'read_file') && args.path) brief = ': ' + args.path;
        else if (a.tool_name === 'web_search' && args.query) brief = ': ' + (args.query||'').substring(0,60);
        else if (a.tool_name === 'web_fetch' && args.url) brief = ': ' + (args.url||'').substring(0,60);
        else if (a.tool_name === 'mcp_call') brief = ': ' + (args.mcp_id||'') + '→' + (args.tool||'');
        else if (a.tool_name === 'http_request') brief = ': ' + (args.method||'GET') + ' ' + (args.url||'').substring(0,60);
        else if (a.tool_name === 'send_message') brief = ': → ' + agentName(args.to_agent||'');
        return '<div class="event-item"><span class="time">' + tsText + '</span><span class="kind" style="color:' + (a.status==='approved'?'var(--success)':'var(--error)') + '">' + a.status + '</span><span class="data">' + esc(a.agent_name) + ' → ' + esc(a.tool_name) + '<span style="color:var(--text3);font-size:11px">' + esc(brief) + '</span></span></div>';
      }).join('') +
    '</div>';
}

// Helper to build policy radio buttons
function _policyRadio(value, current, label, desc, color) {
  var active = current === value;
  var borderC = active ? color : 'var(--border-light)';
  var bgC = active ? color.replace('var(--', 'rgba(').replace(')', ',0.08)') : 'transparent';
  return '<label style="display:flex;align-items:center;gap:10px;padding:12px;border-radius:8px;cursor:pointer;border:1px solid ' + borderC + ';background:' + bgC + '" onclick="setAgentExecPolicy(\'' + value + '\')">' +
    '<input type="radio" name="exec-policy" value="' + value + '" ' + (active?'checked':'') + ' style="accent-color:' + color + '">' +
    '<div><div style="font-size:13px;font-weight:600;color:' + (active?color:'var(--text)') + '">' + label + '</div><div style="font-size:11px;color:var(--text3)">' + desc + '</div></div>' +
  '</label>';
}

function switchPolicyAgent(agentId) {
  _selectedPolicyAgent = agentId;
  renderApprovals();
  if (agentId) loadWorkspaceAccessPolicy(agentId);
}

async function loadWorkspaceAccessPolicy(agentId) {
  try {
    var data = await api('POST', '/api/portal/agent/workspace/list', { agent_id: agentId });
    if (!data) return;
    var allAgentsList = agents || [];
    var selectEl = document.getElementById('ws-auth-select-policy');
    if (selectEl) {
      var otherAgents = allAgentsList.filter(function(a) { return a.id !== agentId; });
      selectEl.innerHTML = '<option value="">-- Select Agent --</option>' +
        otherAgents.map(function(a) {
          return '<option value="' + esc(a.id) + '">' + esc(a.name) + '</option>';
        }).join('');
    }
    var listEl = document.getElementById('authorized-ws-list-policy');
    if (!listEl) return;
    var auth = data.authorized_workspaces || [];
    if (auth.length === 0) {
      listEl.innerHTML = '<div style="color:var(--text3);font-size:12px">No authorized workspaces</div>';
    } else {
      listEl.innerHTML = auth.map(function(otherId) {
        var otherAgent = allAgentsList.find(function(a) { return a.id === otherId; });
        var name = otherAgent ? otherAgent.name : otherId;
        return '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:var(--bg);border-radius:8px;margin-bottom:4px;border:1px solid var(--border-light)">' +
          '<span style="font-size:12px;color:var(--text)">' + esc(name) + '</span>' +
          '<button class="btn btn-sm" style="padding:4px 10px;font-size:10px;background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.3);color:#ff6b6b;border-radius:6px;cursor:pointer" onclick="revokeWorkspacePolicy(\'' + esc(otherId) + '\')">' +
            'Revoke' +
          '</button>' +
        '</div>';
      }).join('');
    }
  } catch(e) { console.error('Error loading workspace access:', e); }
}

async function authorizeWorkspacePolicy() {
  if (!_selectedPolicyAgent) return;
  var sel = document.getElementById('ws-auth-select-policy');
  var targetId = sel ? sel.value : '';
  if (!targetId) return;
  try {
    await api('POST', '/api/portal/agent/workspace/authorize', {
      agent_id: _selectedPolicyAgent,
      target_agent_id: targetId
    });
    loadWorkspaceAccessPolicy(_selectedPolicyAgent);
  } catch(e) { console.error('Error authorizing workspace:', e); }
}

async function revokeWorkspacePolicy(targetId) {
  if (!_selectedPolicyAgent) return;
  try {
    await api('POST', '/api/portal/agent/workspace/revoke', {
      agent_id: _selectedPolicyAgent,
      target_agent_id: targetId
    });
    loadWorkspaceAccessPolicy(_selectedPolicyAgent);
  } catch(e) { console.error('Error revoking workspace:', e); }
}

function setAgentExecPolicy(policy) {
  if (!_selectedPolicyAgent) return;
  var ag = agents.find(function(a){ return a.id === _selectedPolicyAgent; });
  if (!ag) return;
  if (!ag.profile) ag.profile = {};
  ag.profile.exec_policy = policy;
  api('POST', '/api/portal/agent/' + _selectedPolicyAgent + '/profile', { exec_policy: policy });
  renderApprovals();
}
function addAgentBlacklist() {
  if (!_selectedPolicyAgent) return;
  var el = document.getElementById('new-blacklist');
  var val = (el.value||'').trim();
  if (!val) return;
  var ag = agents.find(function(a){ return a.id === _selectedPolicyAgent; });
  if (!ag) return;
  if (!ag.profile) ag.profile = {};
  var bl = ag.profile.exec_blacklist || [];
  if (bl.indexOf(val) === -1) { bl.push(val); ag.profile.exec_blacklist = bl; }
  el.value = '';
  api('POST', '/api/portal/agent/' + _selectedPolicyAgent + '/profile', { exec_blacklist: bl });
  renderApprovals();
}
function removeAgentBlacklist(cmd) {
  if (!_selectedPolicyAgent) return;
  var ag = agents.find(function(a){ return a.id === _selectedPolicyAgent; });
  if (!ag || !ag.profile) return;
  ag.profile.exec_blacklist = (ag.profile.exec_blacklist||[]).filter(function(c){ return c !== cmd; });
  api('POST', '/api/portal/agent/' + _selectedPolicyAgent + '/profile', { exec_blacklist: ag.profile.exec_blacklist });
  renderApprovals();
}
function addAgentWhitelist() {
  if (!_selectedPolicyAgent) return;
  var el = document.getElementById('new-whitelist');
  var val = (el.value||'').trim();
  if (!val) return;
  var ag = agents.find(function(a){ return a.id === _selectedPolicyAgent; });
  if (!ag) return;
  if (!ag.profile) ag.profile = {};
  var wl = ag.profile.exec_whitelist || [];
  if (wl.indexOf(val) === -1) { wl.push(val); ag.profile.exec_whitelist = wl; }
  el.value = '';
  api('POST', '/api/portal/agent/' + _selectedPolicyAgent + '/profile', { exec_whitelist: wl });
  renderApprovals();
}
function removeAgentWhitelist(cmd) {
  if (!_selectedPolicyAgent) return;
  var ag = agents.find(function(a){ return a.id === _selectedPolicyAgent; });
  if (!ag || !ag.profile) return;
  ag.profile.exec_whitelist = (ag.profile.exec_whitelist||[]).filter(function(c){ return c !== cmd; });
  api('POST', '/api/portal/agent/' + _selectedPolicyAgent + '/profile', { exec_whitelist: ag.profile.exec_whitelist });
  renderApprovals();
}

async function approveRequest(approvalId, scope) {
  var payload = {approval_id: approvalId, action: 'approve'};
  if (scope === 'session') payload.scope = 'session';
  await api('POST', '/api/portal/approve', payload);
  refresh();
}

async function denyRequest(approvalId) {
  await api('POST', '/api/portal/approve', {approval_id: approvalId, action: 'deny'});
  refresh();
