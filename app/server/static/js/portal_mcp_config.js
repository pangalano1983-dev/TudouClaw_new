}

// ============ MCP Config Panel ============
async function renderMCPConfig(container) {
  const content = container || document.getElementById('content');
  if (!container) content.style.padding = '24px';
  const epoch = _renderEpoch;
  content.innerHTML = '<div style="color:var(--text3);padding:20px">Loading MCP configuration...</div>';
  let nodesData, catalogData, agentsData;
  try {
    [nodesData, catalogData, agentsData] = await Promise.all([
      api('GET', '/api/portal/mcp/nodes'),
      api('GET', '/api/portal/mcp/catalog'),
      api('GET', '/api/portal/agents'),
    ]);
  } catch(e) {
    if (epoch !== _renderEpoch) return;
    content.innerHTML = '<div style="color:var(--error);padding:20px">Failed to load MCP config: '+(e && e.message || e)+'</div>';
    return;
  }
  if (epoch !== _renderEpoch) return;
  const nodes = (nodesData && nodesData.nodes) || {};
  const catalog = (catalogData && catalogData.catalog) || {};
  const agents = (agentsData && agentsData.agents) || [];

  let html = '';

  // Page header with Add button
  html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:28px">';
  html += '<div><h2 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:28px;font-weight:800;letter-spacing:-0.5px">MCP Configuration</h2>';
  html += '<p style="color:var(--text2);font-size:14px;margin-top:4px">Manage Model Context Protocol server bindings and catalog.</p></div>';
  html += '<button class="btn btn-primary" onclick="showAddMCP()" style="flex-shrink:0"><span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle;margin-right:4px">add</span>Add MCP</button>';
  html += '</div>';

  // MCP Catalog — 分 Global / Node 两组
  var globalCaps = Object.entries(catalog).filter(([_,c]) => c.scope === 'global');
  var nodeCaps = Object.entries(catalog).filter(([_,c]) => c.scope !== 'global');

  function _renderCapCards(caps) {
    var h = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px">';
    caps.forEach(([id, cap]) => {
      var typeIcon = {filesystem:'folder',database:'storage',api:'api',search:'search',communication:'chat',custom:'extension'}[cap.server_type]||'extension';
      var scopeBadge = cap.scope==='global'
        ? '<span style="font-size:9px;background:#dbeafe;color:#1d4ed8;padding:1px 5px;border-radius:4px;margin-left:6px">Global</span>'
        : '<span style="font-size:9px;background:#fef3c7;color:#92400e;padding:1px 5px;border-radius:4px;margin-left:6px">Node</span>';
      h += '<div style="border:1px solid var(--border-light);border-radius:12px;padding:14px;cursor:pointer;background:var(--surface);transition:all 0.2s" onmouseover="this.style.borderColor=\'var(--border)\';this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.2)\'" onmouseout="this.style.borderColor=\'var(--border-light)\';this.style.boxShadow=\'none\'" onclick="showCatalogDetail(\''+id+'\')">';
      h += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">';
      h += '<div style="width:32px;height:32px;border-radius:8px;background:var(--bg);display:flex;align-items:center;justify-content:center;flex-shrink:0"><span class="material-symbols-outlined" style="font-size:18px;color:var(--primary)">'+typeIcon+'</span></div>';
      h += '<strong style="font-size:13px">'+cap.name+'</strong>'+scopeBadge+'</div>';
      h += '<div style="font-size:11px;color:var(--text3);line-height:1.4;margin-bottom:8px">'+cap.description.substring(0,80)+'</div>';
      h += '<div style="font-size:10px;display:flex;flex-wrap:wrap;gap:4px">';
      (cap.tools_provided||[]).slice(0,3).forEach(t => h += '<span class="badge" style="font-size:9px;padding:2px 6px;border-radius:5px">'+t+'</span>');
      if ((cap.tools_provided||[]).length > 3) h += '<span style="color:var(--text3);font-size:9px">+'+((cap.tools_provided||[]).length-3)+'</span>';
      h += '</div></div>';
    });
    h += '</div>';
    return h;
  }

  html += '<div class="card" style="margin-bottom:16px">';
  html += '<h3 style="margin-bottom:12px"><span class="material-symbols-outlined" style="vertical-align:middle">inventory_2</span> MCP Catalog</h3>';
  // scope tabs
  html += '<div style="display:flex;gap:0;margin-bottom:14px;border-bottom:1px solid var(--border-light)">';
  html += '<button class="btn btn-sm" id="mcp-tab-global" onclick="_switchMCPCatalogTab(\'global\')" style="border-radius:8px 8px 0 0;border-bottom:2px solid var(--primary);font-weight:700;color:var(--primary)"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">public</span> Global ('+globalCaps.length+')</button>';
  html += '<button class="btn btn-sm" id="mcp-tab-node" onclick="_switchMCPCatalogTab(\'node\')" style="border-radius:8px 8px 0 0;border-bottom:2px solid transparent;color:var(--text3)"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">dns</span> Node ('+nodeCaps.length+')</button>';
  html += '</div>';
  html += '<div style="font-size:11px;color:var(--text3);margin-bottom:10px" id="mcp-catalog-hint">Global MCP: 调用外部 API / 云服务，配置一次可同步到所有 Node</div>';
  html += '<div id="mcp-catalog-global">' + _renderCapCards(globalCaps) + '</div>';
  html += '<div id="mcp-catalog-node" style="display:none">' + _renderCapCards(nodeCaps) + '</div>';
  html += '</div>';

  // Per-Node MCP configs
  Object.entries(nodes).forEach(([nodeId, nodeCfg]) => {
    const mcps = nodeCfg.available_mcps || {};
    const bindings = nodeCfg.agent_bindings || {};

    html += '<div class="card" style="margin-bottom:16px">';
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">';
    html += '<h3 style="margin:0"><span class="material-symbols-outlined" style="vertical-align:middle">dns</span> Node: '+nodeId+'</h3>';
    html += '<button class="btn btn-sm" onclick="syncGlobalToNode(\''+nodeId+'\')"><span class="material-symbols-outlined" style="font-size:14px">sync</span> 同步 Global MCP</button>';
    html += '</div>';

    if (Object.keys(mcps).length === 0) {
      html += '<p style="color:var(--muted);font-size:13px">No MCP servers configured on this node</p>';
    } else {
      html += '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:12px">';
      Object.entries(mcps).forEach(([mcpId, mcp]) => {
        const boundAgents = Object.entries(bindings).filter(([aid,mids])=>mids.includes(mcpId)).map(([aid])=>{
          const a = agents.find(x=>x.id===aid);
          return a ? a.name : aid;
        });
        const typeIcon = {filesystem:'folder',database:'storage',api:'api',search:'search',communication:'chat',custom:'extension'}[mcp.server_type]||'extension';
        const tools = mcp.tools_provided || [];
        html += '<div style="border:1px solid var(--border-light);border-radius:14px;padding:20px;background:var(--surface);transition:all 0.2s">';
        // Header
        html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">';
        html += '<div style="display:flex;align-items:center;gap:10px;min-width:0;flex:1">';
        html += '<div style="width:40px;height:40px;border-radius:10px;background:var(--bg);display:flex;align-items:center;justify-content:center;flex-shrink:0;border:1px solid var(--border-light)"><span class="material-symbols-outlined" style="font-size:20px;color:var(--primary)">'+typeIcon+'</span></div>';
        html += '<div style="min-width:0;flex:1">';
        html += '<div style="font-weight:700;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+esc(mcp.name)+'</div>';
        html += '<div style="font-size:11px;color:var(--text3);font-family:monospace;margin-top:2px">'+esc(mcpId)+'</div>';
        html += '</div></div>';
        html += '<span style="font-size:12px;font-weight:600;color:'+(mcp.enabled?'var(--success)':'var(--text3)')+'"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:'+(mcp.enabled?'var(--success)':'var(--text3)')+';margin-right:5px;vertical-align:middle"></span>'+(mcp.enabled?'Active':'Disabled')+'</span>';
        html += '</div>';
        // ── Install status badge ──
        var ist = mcp.install_status || 'unknown';
        if (ist === 'installing') {
          html += '<div style="background:#fff3cd;color:#856404;font-size:11px;padding:4px 10px;border-radius:6px;margin-bottom:10px;display:flex;align-items:center;gap:6px"><span class="material-symbols-outlined" style="font-size:14px;animation:spin 1s linear infinite">progress_activity</span> 正在安装...</div>';
        } else if (ist === 'failed') {
          html += '<div style="background:#f8d7da;color:#721c24;font-size:11px;padding:4px 10px;border-radius:6px;margin-bottom:10px">';
          html += '<span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">error</span> 安装失败';
          if (mcp.install_error) html += ': ' + esc(String(mcp.install_error).substring(0,80));
          html += ' <a href="#" onclick="retryMCPInstall(\''+nodeId+'\',\''+mcpId+'\');return false" style="color:#721c24;font-weight:700;text-decoration:underline;margin-left:6px">重试</a>';
          html += '</div>';
        } else if (ist === 'installed') {
          html += '<div style="background:#d4edda;color:#155724;font-size:11px;padding:4px 10px;border-radius:6px;margin-bottom:10px"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">check_circle</span> 已安装</div>';
        }
        // Description
        if (mcp.description) {
          html += '<div style="font-size:12px;color:var(--text3);margin-bottom:10px;line-height:1.5">'+esc(String(mcp.description).substring(0,100))+'</div>';
        }
        // Meta row
        html += '<div style="display:flex;gap:6px;font-size:10px;margin-bottom:10px;flex-wrap:wrap">';
        if (mcp.scope === 'global') {
          html += '<span style="font-size:9px;background:#dbeafe;color:#1d4ed8;padding:2px 6px;border-radius:5px;font-weight:600">Global</span>';
        } else {
          html += '<span style="font-size:9px;background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:5px;font-weight:600">Node</span>';
        }
        html += '<span class="badge" style="font-size:10px;padding:3px 8px;border-radius:6px">'+esc(mcp.transport)+'</span>';
        tools.slice(0,3).forEach(t => html += '<span class="badge" style="font-size:10px;padding:3px 8px;border-radius:6px">'+esc(t)+'</span>');
        if (tools.length > 3) html += '<span style="color:var(--text3);font-size:10px">+'+(tools.length-3)+'</span>';
        html += '</div>';
        // Config details (command / URL / env)
        html += '<div style="background:var(--bg);border-radius:8px;padding:10px 12px;margin-bottom:10px;font-size:11px;font-family:monospace;line-height:1.6">';
        if (mcp.command) {
          html += '<div style="margin-bottom:4px"><span style="color:var(--text3);font-family:sans-serif;font-size:10px">Command:</span><br><span style="color:var(--text2);word-break:break-all">'+esc(mcp.command)+'</span></div>';
        }
        if (mcp.url) {
          html += '<div style="margin-bottom:4px"><span style="color:var(--text3);font-family:sans-serif;font-size:10px">URL:</span><br><span style="color:var(--text2);word-break:break-all">'+esc(mcp.url)+'</span></div>';
        }
        var envOverridesForCard = (nodeCfg.env_overrides || {})[mcpId] || {};
        var mergedEnv = Object.assign({}, mcp.env || {}, envOverridesForCard);
        var envKeys = Object.keys(mergedEnv);
        if (envKeys.length) {
          html += '<div><span style="color:var(--text3);font-family:sans-serif;font-size:10px">Env (' + envKeys.length + '):</span><br>';
          envKeys.forEach(function(k) {
            var v = mergedEnv[k];
            var masked = v ? (v.length > 6 ? v.substring(0,3) + '***' + v.substring(v.length-2) : '***') : '<empty>';
            html += '<span style="color:var(--primary)">'+esc(k)+'</span>=<span style="color:var(--text3)">'+esc(masked)+'</span><br>';
          });
          html += '</div>';
        } else {
          html += '<div style="color:var(--text3);font-family:sans-serif;font-size:10px">⚠️ No env vars configured</div>';
        }
        html += '</div>';
        // Bound agents
        html += '<div style="font-size:12px;margin-bottom:14px"><span style="color:var(--text3)">Bound:</span> ';
        html += boundAgents.length?('<span style="font-weight:600;color:var(--text)">'+boundAgents.map(esc).join(', ')+'</span>'):'<span style="color:var(--text3)">None</span>';
        html += '</div>';
        // Separator + Actions
        html += '<div style="border-top:1px solid var(--border-light);padding-top:12px;display:flex;gap:8px">';
        html += '<button class="btn btn-sm" style="flex:1" onclick="showBindMCP(\''+nodeId+'\',\''+mcpId+'\')"><span class="material-symbols-outlined" style="font-size:14px">link</span> Bind</button>';
        html += '<button class="btn btn-sm" style="flex:1" onclick="showEditMCPEnv(\''+nodeId+'\',\''+mcpId+'\')"><span class="material-symbols-outlined" style="font-size:14px">settings</span> Env</button>';
        html += '<button class="btn btn-sm" title="Change scope" onclick="showChangeMCPScope(\''+mcpId+'\',\''+(mcp.scope||'node')+'\',\''+nodeId+'\')"><span class="material-symbols-outlined" style="font-size:14px">swap_horiz</span> Scope</button>';
        html += '<button class="btn btn-sm btn-danger" onclick="removeMCPFromNode(\''+nodeId+'\',\''+mcpId+'\')"><span class="material-symbols-outlined" style="font-size:14px">delete</span></button>';
        html += '</div>';
        html += '</div>';
      });
      html += '</div>';
    }
    html += '</div>';
  });

  // If no nodes at all, show empty state
  if (Object.keys(nodes).length === 0) {
    html += '<div class="card" style="text-align:center;padding:40px;color:var(--muted)">';
    html += '<span class="material-symbols-outlined" style="font-size:48px;display:block;margin-bottom:8px">hub</span>';
    html += '<p>No MCP configurations yet</p><p style="font-size:12px">Add an MCP server from the catalog above</p></div>';
  }

  content.innerHTML = html;
}

async function showAddMCP(preSelectCapId) {
  const catalogData = await api('GET', '/api/portal/mcp/catalog');
  const catalog = catalogData.catalog || {};

  let opts = '<option value="">-- Select from Catalog --</option>';
  opts += Object.entries(catalog).map(([id,cap]) => '<option value="'+id+'"'+(id===preSelectCapId?' selected':'')+'>'+cap.name+' ('+cap.server_type+')</option>').join('');

  const html = '<div style="padding:20px;max-width:550px">' +
    '<h3 style="margin-bottom:16px">Add MCP Server</h3>' +
    '<label>Select from Catalog</label><select id="mcp-catalog" class="input" style="margin-bottom:8px" onchange="onMCPCatalogSelect(this.value)">'+opts+'</select>' +
    '<div id="mcp-env-fields" style="margin-bottom:8px"></div>' +
    '<label>Or Custom: Name</label><input id="mcp-name" class="input" style="margin-bottom:8px">' +
    '<label>Transport</label><select id="mcp-transport" class="input" style="margin-bottom:8px"><option value="stdio">stdio</option><option value="sse">sse</option><option value="streamable-http">streamable-http</option></select>' +
    '<label>Command (stdio)</label><input id="mcp-command" class="input" style="margin-bottom:8px">' +
    '<label>URL (sse/http)</label><input id="mcp-url" class="input" style="margin-bottom:12px">' +
    // ── Scope selector (Invariant D: Node / Global / multi-Node) ──
    // Global MCPs are eagerly copied into every node at save time, so
    // every agent on every node can see them. Node-scope restricts the
    // MCP to one node. multi_node restricts it to an explicit list.
    '<label>Scope</label>' +
    '<select id="mcp-scope" class="input" style="margin-bottom:8px" onchange="onMCPScopeChange()">' +
      '<option value="node">Node — only this node (' + esc(window._currentNodeId || 'local') + ')</option>' +
      '<option value="global">Global — visible to every node</option>' +
      '<option value="multi_node">Multi-Node — pick specific nodes</option>' +
    '</select>' +
    '<div id="mcp-scope-nodes" style="display:none;margin-bottom:8px">' +
      '<label style="font-size:11px;color:var(--text3)">Target nodes (comma-separated)</label>' +
      '<input id="mcp-scope-nodes-input" class="input" placeholder="nodeA,nodeB" style="font-size:12px">' +
    '</div>' +
    '<div style="font-size:11px;color:var(--text3);margin-bottom:12px;line-height:1.5">' +
      'Scope 决定 MCP 的可见范围。<b>Global</b> 会在每个 Node 的列表里都出现；' +
      '<b>Node</b> 只绑定到当前 Node；<b>Multi-Node</b> 指定一组 Node 白名单。' +
    '</div>' +
    '<div id="mcp-test-result" style="margin-bottom:12px;font-size:12px"></div>' +
    '<div style="display:flex;gap:8px"><button class="btn btn-primary" onclick="saveMCP()">Add</button>' +
    '<button class="btn" onclick="testMCP()">Test</button>' +
    '<button class="btn" onclick="closeModal()">Cancel</button></div></div>';
  showModalHTML(html);
  // If pre-selected, auto-populate the form
  if (preSelectCapId && catalog[preSelectCapId]) {
    onMCPCatalogSelect(preSelectCapId);
  }
}

function onMCPScopeChange() {
  var sel = document.getElementById('mcp-scope');
  var nodesBox = document.getElementById('mcp-scope-nodes');
  if (!sel || !nodesBox) return;
  nodesBox.style.display = (sel.value === 'multi_node') ? 'block' : 'none';
}

// ── Rescope existing MCP (Invariant D: admin-driven scope change) ──
// Calls POST /api/portal/mcp/manage { action: 'change_scope', ... }. The
// backend handles eager propagation (global → all nodes) and whitelist
// enforcement (multi_node → target_nodes list) in manager.change_mcp_scope.
function showChangeMCPScope(mcpId, currentScope, currentNodeId) {
  var cs = currentScope || 'node';
  var html = '<div style="padding:20px;max-width:520px">' +
    '<h3 style="margin-bottom:6px">Change MCP Scope</h3>' +
    '<div style="font-size:12px;color:var(--text3);margin-bottom:14px">' +
      'MCP: <code style="background:var(--bg);padding:2px 6px;border-radius:4px">'+esc(mcpId)+'</code>' +
      ' &nbsp; Current: <b>'+esc(cs)+'</b>' +
    '</div>' +
    '<label>New Scope</label>' +
    '<select id="rescope-scope" class="input" style="margin-bottom:10px" onchange="onRescopeChange()">' +
      '<option value="node"'+(cs==='node'?' selected':'')+'>Node — exactly one node</option>' +
      '<option value="global"'+(cs==='global'?' selected':'')+'>Global — every node (eager copy)</option>' +
      '<option value="multi_node"'+(cs==='multi_node'?' selected':'')+'>Multi-Node — whitelist</option>' +
    '</select>' +
    '<div id="rescope-node-box" style="display:none;margin-bottom:10px">' +
      '<label style="font-size:11px;color:var(--text3)">Target node id</label>' +
      '<input id="rescope-node-input" class="input" value="'+esc(currentNodeId||'')+'" style="font-size:12px">' +
    '</div>' +
    '<div id="rescope-multi-box" style="display:none;margin-bottom:10px">' +
      '<label style="font-size:11px;color:var(--text3)">Target nodes (comma-separated)</label>' +
      '<input id="rescope-multi-input" class="input" placeholder="nodeA,nodeB" style="font-size:12px">' +
    '</div>' +
    '<div style="font-size:11px;color:var(--text3);margin-bottom:14px;line-height:1.5">' +
      '切换到 <b>Global</b> 会把这个 MCP 物理复制到所有 Node；切换到 <b>Node</b> 只保留指定一个 Node；<b>Multi-Node</b> 按白名单保留。' +
    '</div>' +
    '<div style="display:flex;gap:8px">' +
      '<button class="btn btn-primary" onclick="submitChangeMCPScope(\''+mcpId+'\')">Apply</button>' +
      '<button class="btn" onclick="closeModal()">Cancel</button>' +
    '</div></div>';
  showModalHTML(html);
  onRescopeChange();
}

function onRescopeChange() {
  var sel = document.getElementById('rescope-scope');
  if (!sel) return;
  var nb = document.getElementById('rescope-node-box');
  var mb = document.getElementById('rescope-multi-box');
  if (nb) nb.style.display = (sel.value === 'node') ? 'block' : 'none';
  if (mb) mb.style.display = (sel.value === 'multi_node') ? 'block' : 'none';
}

async function submitChangeMCPScope(mcpId) {
  var scope = document.getElementById('rescope-scope').value;
  var payload = { action: 'change_scope', mcp_id: mcpId, scope: scope };
  if (scope === 'node') {
    var one = (document.getElementById('rescope-node-input').value || '').trim();
    if (!one) { alert('Node scope 需要指定 target node id'); return; }
    payload.target_nodes = [one];
  } else if (scope === 'multi_node') {
    var raw = (document.getElementById('rescope-multi-input').value || '').trim();
    var list = raw.split(',').map(function(s){return s.trim();}).filter(Boolean);
    if (!list.length) { alert('Multi-Node scope 需要至少一个 target node id'); return; }
    payload.target_nodes = list;
  }
  try {
    var r = await api('POST', '/api/portal/mcp/manage', payload);
    if (!r || r.ok === false) {
      alert('Change scope failed: ' + ((r && r.error) || 'unknown'));
      return;
    }
    closeModal();
    renderMCPConfig();
  } catch (e) {
    alert('Change scope failed: ' + (e && e.message || e));
  }
}

function onMCPCatalogSelect(capId) {
  api('GET', '/api/portal/mcp/catalog').then(data => {
    const cap = (data.catalog||{})[capId];
    if (!cap) return;
    document.getElementById('mcp-name').value = cap.name;
    document.getElementById('mcp-transport').value = cap.transport;
    document.getElementById('mcp-command').value = cap.command_template || '';
    document.getElementById('mcp-url').value = cap.url_template || '';
    // Catalog entries carry a preferred scope (e.g. jimeng_video is
    // scope="global"). Pre-select it so the user doesn't have to guess,
    // but leave the selector enabled so admins can override.
    var scopeSel = document.getElementById('mcp-scope');
    if (scopeSel && cap.scope) {
      scopeSel.value = cap.scope;
      onMCPScopeChange();
    }
    let envHtml = '';
    if (cap.notes) {
      envHtml += '<div style="background:var(--surface3);border-left:3px solid var(--warning,#d29922);padding:8px 10px;margin:4px 0 10px;font-size:11px;color:var(--text2);border-radius:4px">'
                 + esc(cap.notes) + '</div>';
    }
    if (cap.install_command) {
      envHtml += '<div style="font-size:11px;color:var(--muted);margin-bottom:8px">安装: <code style="background:var(--surface3);padding:2px 6px;border-radius:3px;font-size:10px">'
                 + esc(cap.install_command) + '</code></div>';
    }
    (cap.required_env||[]).forEach(e => {
      envHtml += '<label style="font-size:12px">'+e+' (required)</label><input id="mcp-env-'+e+'" class="input" style="margin-bottom:4px" placeholder="'+e+'">';
    });
    (cap.optional_env||[]).forEach(e => {
      envHtml += '<label style="font-size:12px">'+e+' (optional)</label><input id="mcp-env-'+e+'" class="input" style="margin-bottom:4px" placeholder="'+e+'">';
    });
    document.getElementById('mcp-env-fields').innerHTML = envHtml;
  });
}

async function testMCP() {
  const box = document.getElementById('mcp-test-result');
  if (box) box.innerHTML = '<span style="color:var(--muted)">⏳ 正在测试连接... (最多 15s)</span>';
  try {
    const capIdEl = document.getElementById('mcp-catalog');
    const capId = capIdEl ? capIdEl.value : '';
    const envFields = document.getElementById('mcp-env-fields').querySelectorAll('input');
    const envValues = {};
    envFields.forEach(inp => {
      const key = inp.id.replace('mcp-env-','');
      if (inp.value.trim()) envValues[key] = inp.value.trim();
    });
    let payload;
    if (capId) {
      payload = {action:'test_connection', capability_id: capId, env_values: envValues};
    } else {
      payload = {action:'test_connection', config:{
        name: document.getElementById('mcp-name').value,
        transport: document.getElementById('mcp-transport').value,
        command: document.getElementById('mcp-command').value,
        url: document.getElementById('mcp-url').value,
        env: envValues,
      }};
    }
    const r = await api('POST', '/api/portal/mcp/manage', payload);
    if (!box) return;
    if (!r) { box.innerHTML = '<span style="color:var(--danger)">✗ 请求失败</span>'; return; }
    const color = r.ok ? 'var(--success, #3fb950)' : 'var(--danger, #f85149)';
    const icon = r.ok ? '✓' : '✗';
    let html = '<div style="color:'+color+';font-weight:600">'+icon+' '+esc(r.message||'')+'</div>';
    if (r.server_info && r.server_info.serverInfo && r.server_info.serverInfo.name) {
      html += '<div style="color:var(--muted);margin-top:4px">Server: '+esc(r.server_info.serverInfo.name)+' v'+esc(r.server_info.serverInfo.version||'?')+'</div>';
    }
    if (r.stderr && !r.ok) {
      html += '<details style="margin-top:4px"><summary style="cursor:pointer;color:var(--muted)">stderr</summary><pre style="font-size:10px;max-height:120px;overflow:auto;background:var(--surface3);padding:6px;border-radius:4px;white-space:pre-wrap">'+esc(r.stderr)+'</pre></details>';
    }
    box.innerHTML = html;
  } catch (e) {
    if (box) box.innerHTML = '<span style="color:var(--danger)">✗ '+esc(e.message||String(e))+'</span>';
  }
}

async function saveMCP() {
  try {
    const capIdEl = document.getElementById('mcp-catalog');
    const capId = capIdEl ? capIdEl.value : '';
    // Collect env values
    const envFields = document.getElementById('mcp-env-fields').querySelectorAll('input');
    const envValues = {};
    envFields.forEach(inp => {
      const key = inp.id.replace('mcp-env-','');
      if (inp.value.trim()) envValues[key] = inp.value.trim();
    });

    // Scope decides where the MCP lives and whether it propagates.
    // Invariant D: a Global MCP is eagerly copied into every node's
    // available_mcps server-side, so we only need to call one endpoint
    // per scope — the backend owns the propagation semantics.
    var scopeSel = document.getElementById('mcp-scope');
    var scope = scopeSel ? scopeSel.value : 'node';
    var targetNodes = null;
    if (scope === 'multi_node') {
      var raw = (document.getElementById('mcp-scope-nodes-input').value || '').trim();
      targetNodes = raw.split(',').map(function(s){return s.trim();}).filter(Boolean);
      if (!targetNodes.length) {
        alert('Multi-Node scope 需要至少一个目标 node id');
        return;
      }
    }

    let result;
    if (scope === 'global') {
      // ── Global: single authoritative source, eager-copied into all nodes ──
      if (capId) {
        result = await api('POST', '/api/portal/mcp/manage', {
          action: 'add_global_mcp',
          capability_id: capId,
          env_values: envValues,
        });
      } else {
        const name = (document.getElementById('mcp-name').value||'').trim();
        if (!name) { alert('请填写 MCP Name'); return; }
        result = await api('POST', '/api/portal/mcp/manage', {
          action: 'add_global_mcp',
          config: {
            name: name,
            transport: document.getElementById('mcp-transport').value,
            command: document.getElementById('mcp-command').value,
            url: document.getElementById('mcp-url').value,
            env: envValues,
          }
        });
      }
    } else if (capId) {
      // ── Node-scope from catalog: use the existing one-click install ──
      result = await api('POST', '/api/portal/mcp/manage', {
        action: 'install',
        capability_id: capId,
        env_values: envValues,
      });
    } else {
      // ── Node-scope custom config ──
      const name = (document.getElementById('mcp-name').value||'').trim();
      if (!name) { alert('请填写 MCP Name'); return; }
      result = await api('POST', '/api/portal/mcp/manage', {
        action: 'add_mcp',
        config: {
          name: name,
          transport: document.getElementById('mcp-transport').value,
          command: document.getElementById('mcp-command').value,
          url: document.getElementById('mcp-url').value,
          env: envValues,
        }
      });
    }
    // Post-save: if user asked for multi_node, re-scope immediately.
    // We first create the MCP (as Global or Node, whichever branch
    // ran) and then call change_scope to narrow/broaden it. This
    // keeps all creation paths going through the standard create
    // endpoints and change_scope as the single re-scoping authority.
    if (scope === 'multi_node' && result && (result.ok || result.mcp || result.id)) {
      var createdId = (result.mcp && result.mcp.id) || result.id
                    || (capId ? capId : (document.getElementById('mcp-name').value||'').trim());
      if (createdId) {
        await api('POST', '/api/portal/mcp/manage', {
          action: 'change_scope',
          mcp_id: createdId,
          scope: 'multi_node',
          target_nodes: targetNodes,
        });
      }
    }
    if (result === null) {
      alert('添加 MCP 失败，请查看浏览器控制台或服务器日志');
      return;
    }
    if (result && !result.ok && result.message) {
      alert(result.message);
      return;
    }
    if (result && result.error) {
      alert('添加 MCP 失败: ' + result.error);
      return;
    }

    // 如果正在安装，显示进度并轮询
    if (result && result.status === 'installing' && result.task_id) {
      document.querySelectorAll('#modal-overlay').forEach(function(o){ o.remove(); });
      _showInstallProgress(result.task_id, result.message || '安装中...');
      return;
    }

    // Remove all modal overlays
    document.querySelectorAll('#modal-overlay').forEach(function(o){ o.remove(); });
    renderMCPConfig();
  } catch (e) {
    console.error('saveMCP failed', e);
    alert('添加 MCP 出错: ' + (e && e.message ? e.message : e));
  }
}

function _showInstallProgress(taskId, initialMsg) {
  // 创建安装进度提示条
  var bar = document.createElement('div');
  bar.id = 'mcp-install-bar';
  bar.style.cssText = 'position:fixed;bottom:20px;right:20px;background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px 20px;box-shadow:0 4px 16px rgba(0,0,0,0.15);z-index:9999;min-width:300px;font-size:13px;';
  bar.innerHTML = '<div style="display:flex;align-items:center;gap:8px">'
    + '<span class="material-symbols-outlined" style="font-size:18px;animation:spin 1s linear infinite">progress_activity</span>'
    + '<span id="install-msg">' + esc(initialMsg) + '</span></div>'
    + '<div id="install-output" style="margin-top:8px;font-size:11px;color:var(--text3);max-height:80px;overflow:auto;display:none"></div>';
  document.body.appendChild(bar);

  // 轮询安装状态
  var pollTimer = setInterval(async function() {
    try {
      var task = await api('POST', '/api/portal/mcp/manage', {action:'install_status', task_id: taskId});
      if (!task || task.error) return;
      var msgEl = document.getElementById('install-msg');
      var outEl = document.getElementById('install-output');
      if (task.status === 'completed') {
        clearInterval(pollTimer);
        if (msgEl) msgEl.innerHTML = '<span style="color:var(--success)">✓ 安装成功</span>';
        if (outEl && task.output) { outEl.style.display='block'; outEl.textContent = task.output.slice(-300); }
        setTimeout(function(){ var b = document.getElementById('mcp-install-bar'); if(b) b.remove(); renderMCPConfig(); }, 2500);
      } else if (task.status === 'failed') {
        clearInterval(pollTimer);
        if (msgEl) msgEl.innerHTML = '<span style="color:var(--danger)">✗ 安装失败</span>';
        if (outEl) { outEl.style.display='block'; outEl.textContent = (task.error || task.output || '').slice(-300); }
        setTimeout(function(){ var b = document.getElementById('mcp-install-bar'); if(b) b.remove(); renderMCPConfig(); }, 5000);
      }
    } catch(e) { /* ignore poll errors */ }
  }, 2000);
}

async function retryMCPInstall(nodeId, mcpId) {
  var result = await api('POST', '/api/portal/mcp/manage', {action:'retry_install', node_id: nodeId, mcp_id: mcpId});
  if (result && result.task_id) {
    _showInstallProgress(result.task_id, result.message || '重新安装中...');
  } else {
    alert(result && result.message ? result.message : '重试失败');
  }
}

async function showEditMCPEnv(nodeId, mcpId) {
  try {
    const nodeData = await api('GET', '/api/portal/mcp/node/' + nodeId);
    const mcp = (nodeData.available_mcps || {})[mcpId];
    if (!mcp) { alert('MCP not found'); return; }
    const envOverrides = (nodeData.env_overrides || {})[mcpId] || {};
    // Merge base env + overrides
    const merged = Object.assign({}, mcp.env || {}, envOverrides);
    let html = '<div style="padding:20px;max-width:500px">';
    html += '<h3 style="margin-bottom:4px">Edit Env: ' + esc(mcp.name) + '</h3>';
    html += '<div style="font-size:11px;color:var(--text3);margin-bottom:14px;font-family:monospace">' + esc(mcpId) + '</div>';
    // Existing env vars. Each row has a delete (×) button that removes
    // the row from the DOM; saveMCPEnv() diffs _originalKeys against the
    // surviving inputs to build the delete_keys list sent to the backend.
    var keys = Object.keys(merged);
    window._mcpEnvOriginalKeys = keys.slice();
    if (keys.length) {
      keys.forEach(function(k) {
        var safeId = 'mcp-env-row-' + encodeURIComponent(k).replace(/%/g,'_');
        html += '<div id="'+safeId+'" style="margin-bottom:8px">';
        html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:2px">';
        html += '<label style="font-size:12px;font-weight:600">'+esc(k)+'</label>';
        html += '<button type="button" title="Delete this variable" onclick="deleteMCPEnvRow(\''+esc(k).replace(/\\/g,'\\\\').replace(/\'/g,"\\'")+'\')" style="background:transparent;border:none;color:var(--text3);cursor:pointer;padding:2px 6px;font-size:16px;line-height:1">×</button>';
        html += '</div>';
        html += '<input data-env-key="'+esc(k)+'" id="mcp-env-edit-'+esc(k)+'" class="input" value="'+esc(merged[k] || '')+'" style="font-size:12px">';
        html += '</div>';
      });
    }
    // Add new env var
    html += '<div style="border-top:1px solid var(--border-light);padding-top:10px;margin-top:10px">';
    html += '<div style="font-size:11px;color:var(--text3);margin-bottom:6px">Add New Variable</div>';
    html += '<div style="display:flex;gap:6px"><input id="mcp-env-new-key" class="input" placeholder="KEY" style="flex:1;font-size:12px"><input id="mcp-env-new-val" class="input" placeholder="VALUE" style="flex:2;font-size:12px"></div>';
    html += '</div>';
    html += '<div style="display:flex;gap:8px;margin-top:16px">';
    html += '<button class="btn btn-primary" onclick="saveMCPEnv(\''+nodeId+'\',\''+mcpId+'\')">Save</button>';
    html += '<button class="btn" onclick="closeModal()">Cancel</button></div></div>';
    showModalHTML(html);
  } catch(e) { alert('Failed: ' + (e.message||e)); }
}

// Soft-delete an env row from the dialog. Actual deletion is applied
// at save time via the delete_keys diff — until Save, the user can
// cancel to abort.
function deleteMCPEnvRow(key) {
  var safeId = 'mcp-env-row-' + encodeURIComponent(key).replace(/%/g,'_');
  var row = document.getElementById(safeId);
  if (row && row.parentNode) row.parentNode.removeChild(row);
}

async function saveMCPEnv(nodeId, mcpId) {
  const envObj = {};
  // Use data-env-key attribute (safer than parsing the DOM id, which
  // may contain characters that were escaped).
  document.querySelectorAll('input[data-env-key]').forEach(function(inp) {
    const key = inp.getAttribute('data-env-key');
    if (key) envObj[key] = inp.value;
  });
  // New key
  const newKey = (document.getElementById('mcp-env-new-key') || {}).value || '';
  const newVal = (document.getElementById('mcp-env-new-val') || {}).value || '';
  if (newKey.trim()) envObj[newKey.trim()] = newVal;
  // Diff: whatever was in the original set but is no longer in envObj
  // has been removed by the user and must be deleted on the backend.
  var originals = window._mcpEnvOriginalKeys || [];
  var deleteKeys = originals.filter(function(k) { return !(k in envObj); });
  try {
    await api('POST', '/api/portal/mcp/manage', {
      action: 'set_env',
      node_id: nodeId,
      mcp_id: mcpId,
      env: envObj,
      delete_keys: deleteKeys,
    });
    closeModal();
    renderMCPConfig();
  } catch(e) { alert('Save failed: ' + (e.message||e)); }
}

async function showEditAgentMCPEnv(nodeId, agentId, mcpId) {
  try {
    // Get base MCP env + node overrides + agent overrides
    const nodeData = await api('GET', '/api/portal/mcp/node/' + nodeId);
    const mcp = (nodeData.available_mcps || {})[mcpId];
    if (!mcp) { alert('MCP not found'); return; }
    const nodeEnvOverrides = (nodeData.env_overrides || {})[mcpId] || {};
    const agentEnvOverrides = ((nodeData.agent_env_overrides || {})[agentId] || {})[mcpId] || {};
    // Show base env (read-only) and agent-specific overrides (editable)
    const baseEnv = Object.assign({}, mcp.env || {}, nodeEnvOverrides);
    const allAgents = (await api('GET', '/api/portal/agents')).agents || [];
    const agentName = (allAgents.find(a => a.id === agentId) || {}).name || agentId;
    let html = '<div style="padding:20px;max-width:500px">';
    html += '<h3 style="margin-bottom:4px">Agent 专属 Env</h3>';
    html += '<div style="font-size:12px;color:var(--text2);margin-bottom:4px">Agent: <b>' + esc(agentName) + '</b></div>';
    html += '<div style="font-size:11px;color:var(--text3);margin-bottom:14px;font-family:monospace">' + esc(mcpId) + '</div>';
    html += '<div style="font-size:11px;color:var(--text3);margin-bottom:10px;background:var(--surface3);padding:8px;border-radius:6px">';
    html += '此处设置的变量仅对此 Agent 生效，优先级高于节点级配置。留空则使用节点级默认值。';
    html += '</div>';
    // Show each env key with agent override value
    var keys = Object.keys(baseEnv);
    if (keys.length) {
      keys.forEach(function(k) {
        var agentVal = agentEnvOverrides[k] || '';
        var baseVal = baseEnv[k] || '';
        html += '<div style="margin-bottom:8px">';
        html += '<label style="font-size:12px;font-weight:600">' + esc(k) + '</label>';
        html += '<div style="font-size:10px;color:var(--text3);margin-bottom:2px">节点默认: ' + esc(baseVal ? baseVal.substring(0, 30) + (baseVal.length > 30 ? '...' : '') : '(空)') + '</div>';
        html += '<input id="agent-env-edit-' + esc(k) + '" class="input" value="' + esc(agentVal) + '" placeholder="留空使用默认值" style="font-size:12px">';
        html += '</div>';
      });
    }
    // Add new env var
    html += '<div style="border-top:1px solid var(--border-light);padding-top:10px;margin-top:10px">';
    html += '<div style="font-size:11px;color:var(--text3);margin-bottom:6px">添加新变量 (Agent专属)</div>';
    html += '<div style="display:flex;gap:6px"><input id="agent-env-new-key" class="input" placeholder="KEY" style="flex:1;font-size:12px"><input id="agent-env-new-val" class="input" placeholder="VALUE" style="flex:2;font-size:12px"></div>';
    html += '</div>';
    html += '<div style="display:flex;gap:8px;margin-top:16px">';
    html += '<button class="btn btn-primary" onclick="saveAgentMCPEnv(\''+nodeId+'\',\''+agentId+'\',\''+mcpId+'\')">Save</button>';
    html += '<button class="btn" onclick="showBindMCP(\''+nodeId+'\',\''+mcpId+'\')">Back</button></div></div>';
    showModalHTML(html);
  } catch(e) { alert('Failed: ' + (e.message||e)); }
}

async function saveAgentMCPEnv(nodeId, agentId, mcpId) {
  const envObj = {};
  document.querySelectorAll('[id^="agent-env-edit-"]').forEach(function(inp) {
    const key = inp.id.replace('agent-env-edit-','');
    if (inp.value.trim()) envObj[key] = inp.value;  // Only save non-empty overrides
  });
  const newKey = (document.getElementById('agent-env-new-key') || {}).value || '';
  const newVal = (document.getElementById('agent-env-new-val') || {}).value || '';
  if (newKey.trim()) envObj[newKey.trim()] = newVal;
  try {
    await api('POST', '/api/portal/mcp/manage', {action:'set_env', node_id: nodeId, agent_id: agentId, mcp_id: mcpId, env: envObj});
    showBindMCP(nodeId, mcpId);  // Go back to bind modal
  } catch(e) { alert('Save failed: ' + (e.message||e)); }
}

async function syncGlobalToNode(nodeId) {
  try {
    var result = await api('POST', '/api/portal/mcp/manage', {action:'sync_global_to_node', node_id: nodeId});
    if (result && result.synced) {
      var msg = '已同步 ' + result.synced.length + ' 个 Global MCP 到 ' + nodeId;
      if (result.errors && result.errors.length) msg += '\n部分错误: ' + result.errors.join(', ');
      alert(msg);
    } else {
      alert('同步完成');
    }
    renderMCPConfig();
  } catch(e) {
    alert('同步失败: ' + (e.message||e));
  }
}

function _switchMCPCatalogTab(tab) {
  var globalDiv = document.getElementById('mcp-catalog-global');
  var nodeDiv = document.getElementById('mcp-catalog-node');
  var globalTab = document.getElementById('mcp-tab-global');
  var nodeTab = document.getElementById('mcp-tab-node');
  var hint = document.getElementById('mcp-catalog-hint');
  if (tab === 'global') {
    if (globalDiv) globalDiv.style.display = '';
    if (nodeDiv) nodeDiv.style.display = 'none';
    if (globalTab) { globalTab.style.borderBottom = '2px solid var(--primary)'; globalTab.style.color = 'var(--primary)'; globalTab.style.fontWeight = '700'; }
    if (nodeTab) { nodeTab.style.borderBottom = '2px solid transparent'; nodeTab.style.color = 'var(--text3)'; nodeTab.style.fontWeight = '400'; }
    if (hint) hint.textContent = 'Global MCP: 调用外部 API / 云服务，配置一次可同步到所有 Node';
  } else {
    if (globalDiv) globalDiv.style.display = 'none';
    if (nodeDiv) nodeDiv.style.display = '';
    if (nodeTab) { nodeTab.style.borderBottom = '2px solid var(--primary)'; nodeTab.style.color = 'var(--primary)'; nodeTab.style.fontWeight = '700'; }
    if (globalTab) { globalTab.style.borderBottom = '2px solid transparent'; globalTab.style.color = 'var(--text3)'; globalTab.style.fontWeight = '400'; }
    if (hint) hint.textContent = 'Node MCP: 需要本地安装，依赖本机进程/资源，每个 Node 独立管理';
  }
}

function showCatalogDetail(capId) {
  api('GET', '/api/portal/mcp/catalog').then(data => {
    const cap = (data.catalog||{})[capId];
    if (!cap) return;
    let html = '<div style="padding:20px;max-width:550px">';
    html += '<h3>'+cap.name+'</h3>';
    html += '<p style="margin:8px 0;color:var(--muted)">'+cap.description+'</p>';
    // Scope badge
    var scopeLabel = cap.scope==='global'
      ? '<span style="display:inline-block;font-size:11px;background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:5px;font-weight:600;margin-bottom:8px">Global — 配置一次，同步所有 Node</span>'
      : '<span style="display:inline-block;font-size:11px;background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:5px;font-weight:600;margin-bottom:8px">Node — 每个节点独立安装</span>';
    html += '<div style="margin:4px 0">'+scopeLabel+'</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;margin:12px 0">';
    html += '<div><strong>Type:</strong> '+cap.server_type+'</div>';
    html += '<div><strong>Transport:</strong> '+cap.transport+'</div>';
    html += '</div>';
    if (cap.tools_provided && cap.tools_provided.length) {
      html += '<div style="margin:8px 0"><strong style="font-size:12px">Tools:</strong><br>';
      cap.tools_provided.forEach(t => html += '<span class="badge" style="font-size:10px;margin:2px">'+t+'</span>');
      html += '</div>';
    }
    if (cap.compatible_roles && cap.compatible_roles.length) {
      html += '<div style="margin:8px 0"><strong style="font-size:12px">Best for roles:</strong> '+cap.compatible_roles.join(', ')+'</div>';
    }
    if (cap.install_command) {
      html += '<div style="margin:8px 0"><strong style="font-size:12px">Install:</strong><br><code style="font-size:11px;background:var(--bg-secondary);padding:4px 8px;border-radius:4px">'+cap.install_command+'</code></div>';
    }
    html += '<div style="margin-top:16px;display:flex;gap:8px">';
    html += '<button class="btn btn-primary" onclick="closeModal();showAddMCP(\''+capId+'\')">'+(cap.scope==='global'?'配置并安装':'安装到 Node')+'</button>';
    html += '</div>';
    html += '</div>';
    showModalHTML(html);
  });
}

async function showBindMCP(nodeId, mcpId) {
  try {
    const agentsData = await api('GET', '/api/portal/agents');
    const allAgents = (agentsData && agentsData.agents) || [];
    const nodeData = await api('GET', '/api/portal/mcp/node/'+nodeId);
    const bindings = (nodeData && nodeData.agent_bindings) || {};

    // Only agents on THIS node can bind to the node's MCP
    const agents = allAgents.filter(a => (a.node_id || '') === nodeId);

    let html = '<div style="padding:20px;max-width:420px">';
    html += '<h3 style="margin-bottom:6px">Bind MCP to Agents</h3>';
    html += '<p style="font-size:11px;color:var(--muted);margin-bottom:12px">Node: <code>'+esc(nodeId)+'</code> — 只能绑定此节点上的 agents</p>';
    if (agents.length === 0) {
      html += '<div style="background:var(--surface3);padding:12px;border-radius:6px;font-size:12px;color:var(--text2)">';
      html += '此节点没有 agent。请先在 Agents 页面创建一个属于该节点的 agent，再来绑定 MCP。';
      html += '</div>';
    } else {
      const agentEnvOverrides = (nodeData && nodeData.agent_env_overrides) || {};
      agents.forEach(a => {
        const bound = (bindings[a.id]||[]).includes(mcpId);
        const hasAgentEnv = agentEnvOverrides[a.id] && agentEnvOverrides[a.id][mcpId] && Object.keys(agentEnvOverrides[a.id][mcpId]).length > 0;
        html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0">';
        html += '<label style="display:flex;align-items:center;gap:8px;flex:1;cursor:pointer">';
        html += '<input type="checkbox" '+(bound?'checked':'')+' onchange="toggleMCPBind(\''+nodeId+'\',\''+a.id+'\',\''+mcpId+'\',this.checked)">';
        html += '<span>'+esc(a.name)+' <span style="color:var(--muted);font-size:11px">('+esc(a.role||'')+')</span></span></label>';
        if (bound) {
          html += '<button class="btn btn-sm" style="font-size:10px;padding:2px 8px" title="Agent专属Env配置" onclick="showEditAgentMCPEnv(\''+nodeId+'\',\''+a.id+'\',\''+mcpId+'\')">';
          html += '<span class="material-symbols-outlined" style="font-size:14px">tune</span>';
          if (hasAgentEnv) html += ' <span style="color:var(--primary);font-size:10px">●</span>';
          html += '</button>';
        }
        html += '</div>';
      });
      html += '<div style="margin-top:8px;padding:8px;background:var(--surface3);border-radius:6px;font-size:11px;color:var(--text3)">';
      html += '<span class="material-symbols-outlined" style="font-size:13px;vertical-align:middle">info</span> ';
      html += '点击 <span class="material-symbols-outlined" style="font-size:13px;vertical-align:middle">tune</span> 可为每个Agent设置独立的MCP环境变量（如不同邮箱账号）。● 表示已有专属配置。';
      html += '</div>';
    }
    html += '<div style="margin-top:16px;display:flex;justify-content:flex-end"><button class="btn btn-sm" onclick="closeModal();renderMCPConfig()">Done</button></div></div>';
    showModalHTML(html);
  } catch (e) {
    alert('打开 Bind 失败: '+(e && e.message || e));
  }
}

async function toggleMCPBind(nodeId, agentId, mcpId, bind) {
  await api('POST', '/api/portal/mcp/manage', {
    action: bind ? 'bind_agent' : 'unbind_agent',
    node_id: nodeId, agent_id: agentId, mcp_id: mcpId,
  });
}

async function removeMCPFromNode(nodeId, mcpId) {
  if (!confirm('Remove this MCP server from the node?')) return;
  await api('POST', '/api/portal/mcp/manage', {action:'remove_mcp', node_id:nodeId, mcp_id:mcpId});
  renderMCPConfig();
