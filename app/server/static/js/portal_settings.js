}

// ============ Unified Settings Page ============
// ============ New Hub Wrappers ============
// 复用已有的 sub-renderers，只在外层套一个 tab 容器，避免重复实现内容

var _hubSubTab = {};

function _renderHubTabs(hubId, tabs) {
  var current = _hubSubTab[hubId] || tabs[0].id;
  var html = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px;padding:8px;background:var(--surface);border-radius:12px;border:1px solid var(--border-light)">';
  tabs.forEach(function(t) {
    var active = current === t.id;
    html += '<button onclick="_hubSubTab[\''+hubId+'\']=\''+t.id+'\';renderCurrentView()" style="padding:8px 16px;border:none;background:'+(active?'var(--surface2)':'none')+';color:'+(active?'var(--primary)':'var(--text3)')+';font-size:12px;font-weight:'+(active?'700':'500')+';cursor:pointer;border-radius:8px;display:flex;align-items:center;gap:6px;font-family:inherit;white-space:nowrap;transition:all 0.15s">'
      + '<span class="material-symbols-outlined" style="font-size:16px">'+t.icon+'</span>'+esc(t.label)+'</button>';
  });
  html += '</div><div id="hub-'+hubId+'-content"></div>';
  return { html: html, current: current };
}

function renderProjectsHub() {
  var c = document.getElementById('content');
  var actionsEl = document.getElementById('topbar-actions');
  // All action buttons live inside each tab's own content header (top-right),
  // matching the Workflow tab pattern. The global topbar does NOT duplicate them.
  if (actionsEl) actionsEl.innerHTML = '';
  var tabs = [
    { id: 'projects', label: '项目列表', icon: 'folder_special' },
    { id: 'meetings', label: '群聊会议', icon: 'groups' },
    { id: 'task_center', label: '任务中心', icon: 'checklist' },
    { id: 'orchestration', label: '编排可视化', icon: 'hub' },
    { id: 'workflows', label: 'Workflow 模板', icon: 'account_tree' },
  ];
  var r = _renderHubTabs('projects', tabs);
  c.innerHTML = r.html;
  var sc = document.getElementById('hub-projects-content');
  var _orig = document.getElementById('content');
  sc.id = 'content'; _orig.id = 'content-outer';
  try {
    if (r.current === 'projects') {
      renderProjects();
    } else if (r.current === 'meetings') {
      renderMeetingsTab();
    } else if (r.current === 'task_center') {
      renderTaskCenterTab();
    } else if (r.current === 'orchestration') {
      renderOrchestration();
    } else if (r.current === 'workflows') {
      renderWorkflows();
    }
  } finally {
    sc.id = 'hub-projects-content'; _orig.id = 'content';
  }
