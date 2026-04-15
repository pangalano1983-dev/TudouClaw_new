}

// ============ Node Switcher (topbar global) ============
var _globalNodeFilter = '';
function onNodeSwitch(nodeId) {
  _globalNodeFilter = nodeId;
  renderCurrentView();
}
function _refreshNodeSwitcher() {
  var sel = document.getElementById('global-node-switcher');
  if (!sel || !nodes) return;
  var current = sel.value;
  var html = '<option value="">所有节点</option>';
  nodes.forEach(function(n) {
    var label = (n.name || n.node_id) + (n.is_self ? ' (Local)' : '')
      + (n.project_count ? ' · ' + n.project_count + 'p' : '');
    html += '<option value="'+esc(n.node_id||'')+'">'+esc(label)+'</option>';
  });
  sel.innerHTML = html;
  if (current) sel.value = current;
}

function renderSettingsPage() {
  var c = document.getElementById('content');
  var tabs = [
    { id: 'providers', label: 'LLM Providers', icon: 'dns' },
    { id: 'mcpconfig', label: 'MCP', icon: 'hub' },
    { id: 'config', label: 'Global Config', icon: 'settings' },
    { id: 'nodeconfig', label: 'Node Config', icon: 'tune' },
    { id: 'nodes', label: 'Nodes', icon: 'device_hub' },
    { id: 'channels', label: 'Channels', icon: 'cable' },
    { id: 'templates', label: '专业领域', icon: 'library_books' },
    { id: 'policy', label: '审批策略 Policy', icon: 'shield' },
    { id: 'tokens', label: 'API Tokens', icon: 'key' },
  ];

  var tabsHtml = tabs.map(function(t) {
    var active = _settingsSubTab === t.id;
    return '<button onclick="_settingsSubTab=\''+t.id+'\';renderSettingsPage()" style="padding:8px 16px;border:none;background:'+(active?'var(--surface2)':'none')+';color:'+(active?'var(--primary)':'var(--text3)')+';font-size:12px;font-weight:'+(active?'700':'500')+';cursor:pointer;border-radius:8px;display:flex;align-items:center;gap:6px;font-family:inherit;white-space:nowrap;transition:all 0.15s"><span class="material-symbols-outlined" style="font-size:16px">'+t.icon+'</span>'+t.label+'</button>';
  }).join('');

  c.innerHTML = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px;padding:8px;background:var(--surface);border-radius:12px;border:1px solid var(--border-light)">'+tabsHtml+'</div><div id="settings-content"></div>';

  var sc = document.getElementById('settings-content');
  var actionsEl = document.getElementById('topbar-actions');
  var _tabActions = {
    'providers':  '<button class="btn btn-primary btn-sm" onclick="showModal(\'add-provider\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> Add Provider</button>',
    'mcpconfig':  '<button class="btn btn-primary btn-sm" onclick="showAddMCP()"><span class="material-symbols-outlined" style="font-size:16px">add</span> Add MCP</button>',
    'nodes':      '<button class="btn btn-primary btn-sm" onclick="showModal(\'add-node\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> Connect Node</button>',
    'channels':   '<button class="btn btn-primary btn-sm" onclick="showModal(\'add-channel\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> Add Channel</button>',
    'tokens':     '<button class="btn btn-primary btn-sm" onclick="showModal(\'create-token\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> Create Token</button>',
    'templates':  '<button class="btn btn-primary btn-sm" onclick="showCreateTemplate()"><span class="material-symbols-outlined" style="font-size:16px">add</span> New Template</button>',
  };
  if (actionsEl) actionsEl.innerHTML = _tabActions[_settingsSubTab] || '';
  switch(_settingsSubTab) {
    case 'providers': renderProviders(sc); break;
    case 'mcpconfig': renderMCPConfig(sc); break;
    case 'config': renderConfig(sc); break;
    case 'nodeconfig': renderNodeConfig(sc); break;
    case 'nodes': renderNodes(sc); break;
    case 'channels': renderChannels(sc); break;
    case 'templates': renderTemplateLibrary(sc); break;
    case 'policy': renderPolicyConfig(sc); break;
    case 'tokens': renderTokens(sc); break;
    default: sc.innerHTML = '<div style="color:var(--text3);padding:20px">Select a settings tab</div>';
  }
