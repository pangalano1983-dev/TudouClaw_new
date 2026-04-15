}

// ============ Nodes ============
function renderNodes(container) {
  var c = container || document.getElementById('content');
  if (!container) c.style.padding = '24px';
  var epoch = _renderEpoch;

  // Cache local agents for the node card render (before rendering)
  window._localAgentsForRender = {};
  agents.forEach(function(a) { window._localAgentsForRender[a.id] = a; });

  // Header
  var onlineCount = nodes.filter(function(n){ return n.status === 'online'; }).length;
  var remoteCount = nodes.filter(function(n){ return !n.is_self; }).length;
  c.innerHTML = '' +
    '<div style="margin-bottom:28px;display:flex;justify-content:space-between;align-items:flex-start">' +
      '<div>' +
        '<h2 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:28px;font-weight:800;letter-spacing:-0.5px">Network Nodes</h2>' +
        '<p style="color:var(--text2);font-size:14px;margin-top:4px">Manage connected machines and multi-node agent orchestration.</p>' +
      '</div>' +
      '<button class="btn btn-primary btn-sm" onclick="showModal(\'add-node\')" style="flex-shrink:0"><span class="material-symbols-outlined" style="font-size:16px">add</span> Connect Node</button>' +
    '</div>' +
    '<div id="nodes-grid" style="display:grid;grid-template-columns:repeat(2,1fr);gap:20px"></div>';

  var grid = document.getElementById('nodes-grid');
  if (!grid) return;

  grid.innerHTML = nodes.map(function(n) {
    var isOnline = n.status === 'online';
    var isSelf = n.is_self;
    var nodeIcon = isSelf ? 'dns' : 'computer';
    var nodeLabel = isSelf ? 'LOCAL' : 'REMOTE';
    var agentCount = n.agent_count || 0;
    var agentList = (n.agents || []);

    return '<div style="background:var(--surface);border-radius:14px;padding:24px;border:1px solid var(--border-light);transition:all 0.2s" onmouseenter="this.style.background=\'var(--surface2)\'" onmouseleave="this.style.background=\'var(--surface)\'">' +
      // Top: icon + name + status
      '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px">' +
        '<div style="display:flex;align-items:center;gap:14px">' +
          '<div style="width:48px;height:48px;background:var(--surface3);border-radius:10px;display:flex;align-items:center;justify-content:center"><span class="material-symbols-outlined" style="font-size:28px;color:var(--primary)">' + nodeIcon + '</span></div>' +
          '<div>' +
            '<div style="display:flex;align-items:center;gap:8px">' +
              '<span style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:16px;font-weight:700">' + esc(n.name) + '</span>' +
              '<span style="font-size:10px;background:' + (isSelf ? 'rgba(76,175,80,0.1)' : 'rgba(203,201,255,0.1)') + ';color:' + (isSelf ? 'var(--success)' : 'var(--primary)') + ';padding:2px 8px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px;font-weight:700">' + nodeLabel + '</span>' +
            '</div>' +
            '<div style="font-size:12px;color:var(--text3);margin-top:2px">' + esc(n.url === 'local' ? 'localhost' : n.url) + ' · Node ID: ' + esc(n.node_id) + '</div>' +
          '</div>' +
        '</div>' +
        '<div style="display:flex;align-items:center;gap:6px;font-size:11px;font-weight:700;color:' + (isOnline ? 'var(--success)' : 'var(--error)') + '"><span style="width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor;display:inline-block"></span>' + (isOnline ? 'ONLINE' : 'OFFLINE') + '</div>' +
      '</div>' +
      // Agents section
      '<div style="margin-bottom:20px">' +
        '<div style="font-size:10px;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);font-weight:700;margin-bottom:8px">Agents (' + agentCount + ')</div>' +
        '<div style="display:flex;flex-wrap:wrap;gap:6px">' +
          (agentCount > 0 ?
            (isSelf ? Object.values(window._localAgentsForRender || {}).map(function(a) { return '<span style="background:var(--surface3);padding:5px 10px;border-radius:6px;font-size:11px;color:var(--text2);display:flex;align-items:center;gap:4px">' + esc(a.name || 'Agent') + ' <span class="material-symbols-outlined" style="font-size:14px;color:' + (a.status === 'idle' ? 'var(--success)' : a.status === 'busy' ? 'var(--warning)' : 'var(--text3)') + '">' + (a.status === 'idle' ? 'check_circle' : a.status === 'busy' ? 'sync' : 'radio_button_unchecked') + '</span></span>'; }).join('') :
             agentList.map(function(a) { return '<span style="background:var(--surface3);padding:5px 10px;border-radius:6px;font-size:11px;color:var(--text2);display:flex;align-items:center;gap:4px">' + esc(a.name || 'Remote Agent') + ' <span class="material-symbols-outlined" style="font-size:14px;color:var(--primary)">cloud</span></span>'; }).join('')) :
            '<span style="font-size:12px;color:var(--text3)">No agents on this node</span>') +
        '</div>' +
      '</div>' +
      // Stats row
      '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px">' +
        '<div style="background:var(--bg);border-radius:8px;padding:10px 12px;text-align:center"><div style="font-size:18px;font-weight:800;font-family:\'Plus Jakarta Sans\',sans-serif">' + agentCount + '</div><div style="font-size:9px;text-transform:uppercase;letter-spacing:0.6px;color:var(--text3);margin-top:2px">Agents</div></div>' +
        '<div style="background:var(--bg);border-radius:8px;padding:10px 12px;text-align:center"><div style="font-size:18px;font-weight:800;font-family:\'Plus Jakarta Sans\',sans-serif;color:' + (isOnline ? 'var(--success)' : 'var(--error)') + '">' + (isOnline ? '●' : '○') + '</div><div style="font-size:9px;text-transform:uppercase;letter-spacing:0.6px;color:var(--text3);margin-top:2px">Status</div></div>' +
        '<div style="background:var(--bg);border-radius:8px;padding:10px 12px;text-align:center"><div style="font-size:18px;font-weight:800;font-family:\'Plus Jakarta Sans\',sans-serif">' + (n.last_seen ? new Date(n.last_seen * 1000).toLocaleTimeString() : '-') + '</div><div style="font-size:9px;text-transform:uppercase;letter-spacing:0.6px;color:var(--text3);margin-top:2px">Last Seen</div></div>' +
      '</div>' +
      // Config deploy status bar
      '<div id="node-config-' + esc(n.node_id) + '" style="margin-bottom:16px;display:none"></div>' +
      // Actions row
      '<div style="display:flex;align-items:center;justify-content:space-between;padding-top:16px;border-top:1px solid var(--border-light)">' +
        '<div style="display:flex;gap:12px">' +
          (!isSelf ? '<button style="background:none;border:none;color:var(--primary);font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:4px;padding:0" onclick="refreshNode(\'' + esc(n.node_id) + '\')"><span class="material-symbols-outlined" style="font-size:16px">refresh</span> Refresh</button>' : '<button style="background:none;border:none;color:var(--primary);font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:4px;padding:0" onclick="showView(\'dashboard\',null)"><span class="material-symbols-outlined" style="font-size:16px">dashboard</span> Dashboard</button>') +
          '<button style="background:none;border:none;color:var(--warning);font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:4px;padding:0" onclick="showPushConfig(\'' + esc(n.node_id) + '\')"><span class="material-symbols-outlined" style="font-size:16px">settings_suggest</span> Push Config</button>' +
          '<button style="background:none;border:none;color:var(--text3);font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:4px;padding:0" onclick="loadNodeConfigStatus(\'' + esc(n.node_id) + '\')"><span class="material-symbols-outlined" style="font-size:16px">verified</span> Config Status</button>' +
        '</div>' +
        (!isSelf ? '<button style="background:none;border:none;color:var(--error);font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:4px;padding:0;opacity:0.7" onclick="removeNode(\'' + esc(n.node_id) + '\')"><span class="material-symbols-outlined" style="font-size:16px">link_off</span> Disconnect</button>' : '') +
      '</div>' +
    '</div>';
  }).join('') +
  (nodes.length === 0 ? '<div style="color:var(--text3);padding:20px;grid-column:1/-1">No nodes connected. Click "+ Connect Node" to add a remote machine.</div>' : '');
}

async function refreshNode(nodeId) { await api('POST','/api/hub/refresh',{node_id:nodeId}); refresh(); }
async function removeNode(nodeId) {
  if (!confirm('Disconnect this node?')) return;
  await api('DELETE','/api/hub/node/'+nodeId);
  refresh();
}
async function addNode() {
  var name = document.getElementById('an-name').value.trim();
  var url = document.getElementById('an-url').value.trim();
  if(!name||!url) { alert('Please fill in all fields'); return; }
  await api('POST', '/api/hub/register', {name: name, url: url, node_id: 'remote-' + Date.now()});
  hideModal('add-node');
  refresh();
