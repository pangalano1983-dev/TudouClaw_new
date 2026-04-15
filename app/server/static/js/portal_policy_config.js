}

// ============ Policy Config Page (审批策略) ============
async function renderPolicyConfig(container) {
  var c = container || document.getElementById('content');
  c.innerHTML = '<div style="color:var(--text3);padding:20px">Loading policy config...</div>';
  try {
    var cfg = await api('GET', '/api/portal/policy');
    if (!cfg) return;

    var riskColors = { red:'#ef4444', high:'#f59e0b', moderate:'#3b82f6', low:'#22c55e' };
    var riskLabels = { red:'🚫 红线', high:'⚠️ 高风险', moderate:'🟡 中风险', low:'✅ 低风险' };
    var riskOptions = ['red','high','moderate','low'];

    // Group tools by current risk
    var toolsByRisk = { red:[], high:[], moderate:[], low:[] };
    var toolRisks = cfg.tool_risks || {};
    Object.keys(toolRisks).sort().forEach(function(t) {
      var r = toolRisks[t];
      if (toolsByRisk[r]) toolsByRisk[r].push(t);
      else toolsByRisk['moderate'].push(t);
    });

    var html = '<div style="margin-bottom:20px">' +
      '<h3 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:20px;font-weight:700;margin-bottom:4px">审批策略 Tool Policy</h3>' +
      '<p style="color:var(--text2);font-size:13px">管理员可以调整每个工具的风险级别，定义不同角色的审批权限。</p>' +
    '</div>';

    // ── Risk level legend ──
    html += '<div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap">';
    (cfg.risk_levels||[]).forEach(function(rl) {
      html += '<div style="display:flex;align-items:center;gap:6px;padding:8px 14px;background:var(--surface);border-radius:8px;border:1px solid rgba(255,255,255,0.05);font-size:12px">' +
        '<span style="width:10px;height:10px;border-radius:50%;background:'+riskColors[rl.id]+'"></span>' +
        '<span style="font-weight:700">'+rl.label+'</span>' +
        '<span style="color:var(--text3);font-size:11px">'+rl.desc+'</span>' +
      '</div>';
    });
    html += '</div>';

    // ── Tool risk table ──
    var toolDescriptions = {
      read_file:'读取文件 Read file contents', search_files:'搜索文件内容 Search file contents (grep)', glob_files:'文件名匹配 Find files by pattern',
      web_search:'网络搜索 Search the web', web_fetch:'抓取网页 Fetch web page content', write_file:'写入/创建文件 Write or create a file',
      edit_file:'编辑文件 Edit existing file', bash:'执行Shell命令 Execute shell commands', team_create:'创建子Agent Spawn sub-agent',
      send_message:'Agent间消息 Inter-agent messaging', task_update:'任务状态更新 Update task status', plan_update:'计划更新 Update plan',
      web_screenshot:'网页截图 Capture web screenshot', http_request:'HTTP请求 Outbound HTTP/API call', mcp_call:'调用MCP工具 Call external MCP tool',
      datetime_calc:'日期时间计算 Date/time calculation', json_process:'JSON处理 JSON parsing & transform', text_process:'文本处理 Text processing',
      delete_file:'删除文件 Delete a file', rm_rf:'递归删除目录 Recursive directory delete', drop_table:'删除数据库表 Drop database table', truncate:'清空数据表 Truncate database table',
    };
    var toolCategories = {
      'low': { icon:'✅', label:'查询/读取 Query & Read', sort: 4 },
      'moderate': { icon:'🟡', label:'创建/修改 Create & Modify', sort: 3 },
      'high': { icon:'⚠️', label:'危险执行 Dangerous Execution', sort: 2 },
      'red': { icon:'🚫', label:'红线操作 Red Line (Destructive)', sort: 1 },
    };

    // Group tools by current risk level
    var groupedTools = {};
    riskOptions.forEach(function(r) { groupedTools[r] = []; });
    Object.keys(toolRisks).forEach(function(t) {
      var r = toolRisks[t];
      if (!groupedTools[r]) groupedTools[r] = [];
      groupedTools[r].push(t);
    });
    // Sort each group alphabetically
    Object.keys(groupedTools).forEach(function(r) { groupedTools[r].sort(); });

    html += '<div style="margin-bottom:24px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">' +
        '<div style="font-size:14px;font-weight:700">工具风险级别 Tool Risk Levels</div>' +
        '<button class="btn btn-ghost btn-sm" onclick="showAddToolRiskPrompt()" style="font-size:11px;display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">add</span>Add Custom Tool</button>' +
      '</div>' +
      '<div style="background:var(--surface);border-radius:12px;border:1px solid var(--border-light);overflow:hidden">' +
      '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
      '<thead><tr style="background:var(--surface2)">' +
        '<th style="text-align:left;padding:10px 14px;font-weight:700;color:var(--text);width:200px">Tool</th>' +
        '<th style="text-align:left;padding:10px 14px;font-weight:700;color:var(--text);width:180px">Risk Level</th>' +
        '<th style="text-align:left;padding:10px 14px;font-weight:700;color:var(--text)">Description</th>' +
      '</tr></thead><tbody>';

    // Render grouped: red first, then high, moderate, low
    ['red','high','moderate','low'].forEach(function(riskGroup) {
      var tools = groupedTools[riskGroup] || [];
      if (tools.length === 0) return;
      var cat = toolCategories[riskGroup] || {};
      html += '<tr style="background:rgba(' + (riskGroup==='red'?'239,68,68':riskGroup==='high'?'245,158,11':riskGroup==='moderate'?'59,130,246':'34,197,94') + ',0.06)">' +
        '<td colspan="3" style="padding:8px 14px;font-size:12px;font-weight:700;color:' + riskColors[riskGroup] + '">' +
          (cat.icon||'') + ' ' + (cat.label||riskGroup) + ' (' + tools.length + ')' +
        '</td></tr>';
      tools.forEach(function(tool) {
        var risk = toolRisks[tool];
        var desc = toolDescriptions[tool] || tool;
        html += '<tr style="border-top:1px solid rgba(255,255,255,0.04)">' +
          '<td style="padding:7px 14px 7px 28px;font-family:monospace;font-size:12px;color:var(--text)">' + esc(tool) + '</td>' +
          '<td style="padding:7px 14px">' +
            '<select onchange="updateToolRisk(\'' + esc(tool) + '\',this.value)" style="background:var(--surface2);color:' + riskColors[risk] + ';border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:4px 8px;font-size:12px;cursor:pointer;font-weight:600">';
        riskOptions.forEach(function(ro) {
          html += '<option value="' + ro + '" ' + (risk===ro?'selected':'') + '>' + riskLabels[ro] + '</option>';
        });
        html += '</select></td>' +
          '<td style="padding:7px 14px;color:var(--text3);font-size:12px">' + esc(desc) + '</td>' +
        '</tr>';
      });
    });

    html += '</tbody></table></div></div>';

    // ── Role approval authority ──
    html += '<div style="margin-bottom:24px">' +
      '<div style="font-size:14px;font-weight:700;margin-bottom:10px">角色审批权限 Role Approval Authority</div>' +
      '<p style="color:var(--text3);font-size:12px;margin-bottom:10px">定义每个角色可以审批哪些风险级别的操作（勾选 = 该角色可以审批）</p>' +
      '<div style="background:var(--surface);border-radius:12px;border:1px solid var(--border-light);overflow:hidden">' +
      '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
      '<thead><tr style="background:var(--surface2)">' +
        '<th style="text-align:left;padding:10px 14px;font-weight:700">Role</th>';
    riskOptions.forEach(function(ro) {
      html += '<th style="text-align:center;padding:10px 14px;font-weight:700;color:'+riskColors[ro]+'">'+riskLabels[ro]+'</th>';
    });
    html += '</tr></thead><tbody>';

    var priLabels = cfg.priority_labels || {};
    var priAuth = cfg.priority_approval_authority || {};
    ['0','1','2','3'].forEach(function(pri) {
      var label = priLabels[pri] || 'Priority ' + pri;
      var allowed = priAuth[pri] || [];
      html += '<tr style="border-top:1px solid rgba(255,255,255,0.05)">' +
        '<td style="padding:8px 14px;font-weight:600">'+esc(label)+'</td>';
      riskOptions.forEach(function(ro) {
        var checked = allowed.indexOf(ro) >= 0;
        html += '<td style="text-align:center;padding:8px 14px">' +
          '<input type="checkbox" '+(checked?'checked':'')+' onchange="updatePriorityAuth('+pri+',\''+ro+'\',this.checked)" style="cursor:pointer;width:16px;height:16px;accent-color:'+riskColors[ro]+'">' +
        '</td>';
      });
      html += '</tr>';
    });

    html += '</tbody></table></div></div>';

    // ── Global settings ──
    html += '<div style="margin-bottom:24px">' +
      '<div style="font-size:14px;font-weight:700;margin-bottom:10px">全局设置 Global Settings</div>' +
      '<div style="display:flex;flex-direction:column;gap:12px;background:var(--surface);border-radius:12px;border:1px solid var(--border-light);padding:16px">' +
        '<label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-size:13px">' +
          '<input type="checkbox" id="policy-auto-moderate" '+(cfg.auto_approve_moderate?'checked':'')+' onchange="updatePolicyGlobal(\'auto_approve_moderate\',this.checked)" style="width:16px;height:16px;accent-color:var(--primary)">' +
          '<div><span style="font-weight:600">中风险自动通过</span><div style="font-size:11px;color:var(--text3)">开启后，中风险操作无需任何审批自动放行；关闭后，中风险需要有权限的 Agent 或管理员审批</div></div>' +
        '</label>' +
        '<label style="display:flex;align-items:center;gap:10px;font-size:13px">' +
          '<span style="font-weight:600;white-space:nowrap">审批超时</span>' +
          '<input type="number" id="policy-timeout" value="'+Math.round(cfg.approval_timeout)+'" min="30" max="3600" style="width:80px;background:var(--surface2);color:var(--text);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:6px 10px;font-size:13px" onchange="updatePolicyGlobal(\'approval_timeout\',Number(this.value))">' +
          '<span style="font-size:11px;color:var(--text3)">秒 (30-3600)</span>' +
        '</label>' +
      '</div>' +
    '</div>';

    // ── Role delegation graph (allowed_role_edges) ──
    var fp = cfg.fork_policy || {};
    var edges = fp.allowed_role_edges || {};
    var edgeRows = '';
    var roleKeys = Object.keys(edges);
    if (roleKeys.length === 0) {
      edgeRows = '<tr><td colspan="3" style="padding:14px;color:var(--text3);font-size:12px;text-align:center">未配置任何委派规则 — 当前所有角色都可以委派任意子角色（仍受 max_depth/concurrency/cost 限制）</td></tr>';
    } else {
      roleKeys.sort().forEach(function(pr) {
        var children = edges[pr] || [];
        var childStr = children.length ? children.join(', ') : '<span style="color:#ef4444">（不允许委派任何子角色）</span>';
        edgeRows += '<tr style="border-top:1px solid rgba(255,255,255,0.05)">' +
          '<td style="padding:8px 14px;font-family:monospace;font-weight:600">' + esc(pr) + '</td>' +
          '<td style="padding:8px 14px;font-size:12px;color:var(--text2)">' + childStr + '</td>' +
          '<td style="padding:8px 14px;text-align:right">' +
            '<button class="btn btn-ghost btn-sm" style="font-size:11px" onclick="editRoleEdge(\'' + esc(pr) + '\')">编辑</button>' +
            '<button class="btn btn-ghost btn-sm" style="font-size:11px;color:#ef4444" onclick="deleteRoleEdge(\'' + esc(pr) + '\')">删除</button>' +
          '</td></tr>';
      });
    }

    html += '<div style="margin-bottom:24px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">' +
        '<div>' +
          '<div style="font-size:14px;font-weight:700">编排围栏 — 角色委派图 Role Delegation Graph</div>' +
          '<div style="font-size:11px;color:var(--text3);margin-top:2px">定义"父角色 → 允许的子角色"。Agent 仍然自主决定派谁，但只能在你允许的边内活动。空表 = 不限制。</div>' +
        '</div>' +
        '<button class="btn btn-ghost btn-sm" onclick="addRoleEdge()" style="font-size:11px;display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">add</span>添加规则</button>' +
      '</div>' +
      '<div style="background:var(--surface);border-radius:12px;border:1px solid var(--border-light);overflow:hidden">' +
      '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
        '<thead><tr style="background:var(--surface2)">' +
          '<th style="text-align:left;padding:10px 14px;font-weight:700;width:200px">父角色 Parent Role</th>' +
          '<th style="text-align:left;padding:10px 14px;font-weight:700">允许委派的子角色 Allowed Children</th>' +
          '<th style="width:140px"></th>' +
        '</tr></thead>' +
        '<tbody>' + edgeRows + '</tbody>' +
      '</table></div>' +
    '</div>';

    c.innerHTML = html;
  } catch(e) {
    c.innerHTML = '<div style="color:var(--error);padding:20px">Error loading policy: '+e.message+'</div>';
  }
}

// ── Role delegation graph helpers ──
async function addRoleEdge() {
  var pr = prompt('父角色名 (parent role)，例如: manager / writer / analyst');
  if (!pr || !pr.trim()) return;
  pr = pr.trim();
  var raw = prompt('该父角色允许委派的子角色，逗号分隔，例如: analyst, writer, crawler\n（输入空字符串 = 不允许委派任何子角色）', '');
  if (raw === null) return;
  var children = raw.split(',').map(function(s){return s.trim();}).filter(function(s){return s.length>0;});
  try {
    var cfg = await api('GET', '/api/portal/policy');
    var fp = cfg.fork_policy || {};
    var edges = fp.allowed_role_edges || {};
    edges[pr] = children;
    await api('POST', '/api/portal/policy', { fork_policy: { allowed_role_edges: edges } });
    var sc = document.getElementById('settings-content');
    if (sc) renderPolicyConfig(sc);
  } catch(e) { alert('Error: '+e.message); }
}

async function editRoleEdge(pr) {
  try {
    var cfg = await api('GET', '/api/portal/policy');
    var fp = cfg.fork_policy || {};
    var edges = fp.allowed_role_edges || {};
    var current = (edges[pr] || []).join(', ');
    var raw = prompt('父角色 "'+pr+'" 允许委派的子角色（逗号分隔，留空 = 不允许委派任何子角色）', current);
    if (raw === null) return;
    var children = raw.split(',').map(function(s){return s.trim();}).filter(function(s){return s.length>0;});
    edges[pr] = children;
    await api('POST', '/api/portal/policy', { fork_policy: { allowed_role_edges: edges } });
    var sc = document.getElementById('settings-content');
    if (sc) renderPolicyConfig(sc);
  } catch(e) { alert('Error: '+e.message); }
}

async function deleteRoleEdge(pr) {
  if (!confirm('删除父角色 "'+pr+'" 的所有委派规则？删除后该角色将不再受 role-edge 限制（但仍受其他 fork_policy 限制）。')) return;
  try {
    var cfg = await api('GET', '/api/portal/policy');
    var fp = cfg.fork_policy || {};
    var edges = fp.allowed_role_edges || {};
    delete edges[pr];
    await api('POST', '/api/portal/policy', { fork_policy: { allowed_role_edges: edges } });
    var sc = document.getElementById('settings-content');
    if (sc) renderPolicyConfig(sc);
  } catch(e) { alert('Error: '+e.message); }
}

// ── Policy update helpers ──
async function updateToolRisk(tool, risk) {
  try {
    await api('POST', '/api/portal/policy', { tool_risks: { [tool]: risk } });
    // Refresh
    var sc = document.getElementById('settings-content');
    if (sc) renderPolicyConfig(sc);
  } catch(e) { alert('Error: '+e.message); }
}

async function updatePriorityAuth(priority, risk, checked) {
  try {
    var cfg = await api('GET', '/api/portal/policy');
    var priAuth = cfg.priority_approval_authority || {};
    var current = priAuth[String(priority)] || [];
    if (checked && current.indexOf(risk) < 0) {
      current.push(risk);
    } else if (!checked) {
      current = current.filter(function(r){ return r !== risk; });
    }
    var update = {};
    update[String(priority)] = current;
    await api('POST', '/api/portal/policy', { priority_approval_authority: update });
  } catch(e) { alert('Error: '+e.message); }
}

async function updatePolicyGlobal(key, value) {
  try {
    var body = {};
    body[key] = value;
    await api('POST', '/api/portal/policy', body);
  } catch(e) { alert('Error: '+e.message); }
}

function showAddToolRiskPrompt() {
  var toolName = prompt('Enter custom tool name (e.g. my_custom_tool):');
  if (!toolName || !toolName.trim()) return;
  toolName = toolName.trim().toLowerCase().replace(/[^a-z0-9_]/g, '_');
  var risk = prompt('Risk level for "' + toolName + '":\\n  red = 红线(deny)\\n  high = 高风险(admin approval)\\n  moderate = 中风险(agent/auto)\\n  low = 低风险(auto)', 'moderate');
  if (!risk || ['red','high','moderate','low'].indexOf(risk) < 0) {
    alert('Invalid risk level. Use: red, high, moderate, low');
    return;
  }
  updateToolRisk(toolName, risk);
