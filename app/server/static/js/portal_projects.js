}

// ============ Projects ============
async function renderProjects() {
  var c = document.getElementById('content');
  c.style.padding = '24px';
  // Inline header with title + action button (top-right) — mirrors the
  // Workflow tab pattern. No button duplication in the global topbar.
  var _projHeader = ''
    + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">'
    + '  <div><h2 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:22px;font-weight:800;margin:0">Projects</h2>'
    + '    <p style="font-size:12px;color:var(--text3);margin-top:4px">' + t('project.subtitle', '组织多 agent 协作项目与任务') + '</p></div>'
    + '  <button class="btn btn-primary btn-sm" onclick="showCreateProjectModal()"><span class="material-symbols-outlined" style="font-size:14px">add</span> ' + t('project.new', 'New Project') + '</button>'
    + '</div>';
  try {
    var data = await api('GET', '/api/portal/projects');
    var projects = data.projects || [];
    var pcEl = document.getElementById('project-count');
    if (pcEl) pcEl.textContent = projects.length;
    if (!projects.length) {
      c.innerHTML = _projHeader + '<div style="text-align:center;padding:60px 20px;color:var(--text3)"><span class="material-symbols-outlined" style="font-size:48px;display:block;margin-bottom:12px">folder_special</span><div style="font-size:18px;font-weight:700;margin-bottom:8px">' + t('project.none', 'No Projects Yet') + '</div><div style="font-size:13px;margin-bottom:16px">' + t('project.noneHint', 'Create a project to organize agents into collaborative teams') + '</div><button class="btn btn-primary" onclick="showCreateProjectModal()"><span class="material-symbols-outlined" style="font-size:16px">add</span> ' + t('project.create', 'Create Project') + '</button></div>';
      return;
    }
    // Sort by created_at descending (newest first)
    projects.sort(function(a, b) {
      var da = a.created_at ? new Date(a.created_at).getTime() : 0;
      var db = b.created_at ? new Date(b.created_at).getTime() : 0;
      return db - da;
    });
    // Status metadata — label / color / bg per lifecycle state
    var STATUS_META = {
      planning:  { label: '未开始', zh: '未开始', color: '#9ca3af', bg: 'rgba(156,163,175,0.12)' },
      active:    { label: '进行中', zh: '进行中', color: 'var(--primary)', bg: 'rgba(203,201,255,0.12)' },
      suspended: { label: '挂起',   zh: '挂起',   color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
      cancelled: { label: '停止',   zh: '停止',   color: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
      completed: { label: '结束',   zh: '结束',   color: '#22c55e', bg: 'rgba(34,197,94,0.12)' },
      archived:  { label: '归档',   zh: '归档',   color: '#6b7280', bg: 'rgba(107,114,128,0.12)' },
    };
    function _statusMeta(s){
      return STATUS_META[s] || { label: s || 'unknown', color: 'var(--text3)', bg: 'rgba(255,255,255,0.05)' };
    }

    // Split into active (in-flight) vs closed (结束/停止/归档)
    var OPEN_STATES = {planning:1, active:1, suspended:1};
    var activeProjs    = projects.filter(function(p){ return OPEN_STATES[p.status] === 1; });
    var completedProjs = projects.filter(function(p){ return OPEN_STATES[p.status] !== 1; });

    function _projCard(p) {
      var ts = p.task_summary || {};
      var meta = _statusMeta(p.status);
      var isClosed = !OPEN_STATES[p.status];
      // Status transition buttons contextual to current state
      var statusBtns = '';
      function _btn(icon, label, target, color){
        var col = color || 'var(--text2)';
        return '<button class="btn btn-ghost btn-sm" style="flex:none;color:'+col+'" onclick="event.stopPropagation();changeProjectStatus(\''+p.id+'\',\''+target+'\')"><span class="material-symbols-outlined" style="font-size:14px">'+icon+'</span> '+label+'</button>';
      }
      if (p.status === 'planning') {
        statusBtns += _btn('play_arrow', '启动', 'active', 'var(--primary)');
        statusBtns += _btn('cancel', '停止', 'cancelled', '#ef4444');
      } else if (p.status === 'active') {
        statusBtns += _btn('pause', '挂起', 'suspended', '#f59e0b');
        statusBtns += _btn('check_circle', '结束', 'completed', '#22c55e');
        statusBtns += _btn('cancel', '停止', 'cancelled', '#ef4444');
      } else if (p.status === 'suspended') {
        statusBtns += _btn('play_arrow', '恢复', 'active', 'var(--primary)');
        statusBtns += _btn('cancel', '停止', 'cancelled', '#ef4444');
      } else if (p.status === 'cancelled' || p.status === 'completed') {
        statusBtns += _btn('restart_alt', '重新激活', 'active', 'var(--primary)');
        statusBtns += _btn('archive', '归档', 'archived', 'var(--text3)');
      } else if (p.status === 'archived') {
        statusBtns += _btn('unarchive', '取消归档', 'active', 'var(--primary)');
      }
      return '<div class="card" style="background:var(--surface);border-radius:14px;padding:24px;border:1px solid var(--border-light);cursor:pointer;transition:transform 0.15s,box-shadow 0.15s;opacity:'+(isClosed?'0.78':'1')+'" onmouseenter="this.style.transform=\'translateY(-2px)\';this.style.boxShadow=\'0 8px 24px rgba(0,0,0,0.2)\'" onmouseleave="this.style.transform=\'none\';this.style.boxShadow=\'none\'" onclick="openProject(\''+p.id+'\')">' +
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">' +
          '<div style="font-size:17px;font-weight:700;color:var(--text)">'+esc(p.name)+'</div>' +
          '<span style="font-size:10px;padding:3px 10px;border-radius:6px;background:'+meta.bg+';color:'+meta.color+';font-weight:700;letter-spacing:0.5px">'+esc(meta.label)+'</span>' +
        '</div>' +
        '<div style="font-size:13px;color:var(--text3);margin-bottom:16px;line-height:1.4">'+esc(p.description||'No description')+'</div>' +
        '<div style="display:flex;gap:16px;margin-bottom:14px">' +
          '<div style="font-size:12px;color:var(--text3);display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:16px">group</span> '+p.members.length+' members</div>' +
          '<div style="font-size:12px;color:var(--text3);display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:16px">chat</span> '+p.chat_count+' messages</div>' +
        '</div>' +
        '<div style="display:flex;gap:8px;font-size:11px;margin-bottom:16px">' +
          '<span style="padding:3px 8px;border-radius:4px;background:rgba(34,197,94,0.1);color:#22c55e;font-weight:600">✓ '+(ts.done||0)+' done</span>' +
          '<span style="padding:3px 8px;border-radius:4px;background:rgba(59,130,246,0.1);color:#3b82f6;font-weight:600">⏳ '+(ts.in_progress||0)+' active</span>' +
          '<span style="padding:3px 8px;border-radius:4px;background:rgba(255,255,255,0.05);color:var(--text3);font-weight:600">📋 '+(ts.todo||0)+' todo</span>' +
        '</div>' +
        '<div style="display:flex;gap:6px;border-top:1px solid rgba(255,255,255,0.06);padding-top:14px;flex-wrap:wrap">' +
          '<button class="btn btn-primary btn-sm" style="flex:none" onclick="event.stopPropagation();openProject(\''+p.id+'\')"><span class="material-symbols-outlined" style="font-size:14px">open_in_new</span> Open</button>' +
          statusBtns +
          '<button class="btn btn-ghost btn-sm" style="flex:none" onclick="event.stopPropagation();editProject(\''+p.id+'\',\''+esc(p.name).replace(/'/g,"\\'")+'\',\''+esc(p.description||'').replace(/'/g,"\\'")+'\')"><span class="material-symbols-outlined" style="font-size:14px">edit</span> Edit</button>' +
          '<button class="btn btn-ghost btn-sm" style="flex:none;color:var(--error)" onclick="event.stopPropagation();deleteProject(\''+p.id+'\')"><span class="material-symbols-outlined" style="font-size:14px">delete</span> Delete</button>' +
        '</div>' +
      '</div>';
    }

    var html = '';
    // Active section
    if (activeProjs.length) {
      html += '<div style="margin-bottom:32px">' +
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">' +
          '<span class="material-symbols-outlined" style="font-size:20px;color:var(--primary)">rocket_launch</span>' +
          '<span style="font-size:15px;font-weight:700;color:var(--text)">Active Projects</span>' +
          '<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:rgba(203,201,255,0.12);color:var(--primary);font-weight:700">'+activeProjs.length+'</span>' +
        '</div>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:18px">' +
          activeProjs.map(_projCard).join('') +
        '</div>' +
      '</div>';
    }
    // Completed section
    if (completedProjs.length) {
      html += '<div>' +
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">' +
          '<span class="material-symbols-outlined" style="font-size:20px;color:#22c55e">check_circle</span>' +
          '<span style="font-size:15px;font-weight:700;color:var(--text)">Completed Projects</span>' +
          '<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:rgba(34,197,94,0.1);color:#22c55e;font-weight:700">'+completedProjs.length+'</span>' +
        '</div>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:18px">' +
          completedProjs.map(_projCard).join('') +
        '</div>' +
      '</div>';
    }
    // If all are in one category, still show something
    if (!html) {
      html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:18px">' +
        projects.map(_projCard).join('') +
      '</div>';
    }
    c.innerHTML = _projHeader + html;
  } catch(e) { c.innerHTML = _projHeader + '<div style="color:var(--error)">Error loading projects</div>'; }
}

function openProject(projId) {
  currentView = 'project_detail';
  currentProject = projId;
  document.querySelectorAll('.nav-item').forEach(function(n){ n.classList.remove('active'); });
  renderCurrentView();
}

async function renderProjectDetail(projId) {
  var c = document.getElementById('content');
  c.style.padding = '0';
  try {
    var proj = await api('GET', '/api/portal/projects/'+projId);
    if (!proj || proj.error) { c.innerHTML = '<div style="padding:24px;color:var(--error)">Project not found</div>'; return; }
    var titleEl = document.getElementById('view-title');
    titleEl.textContent = proj.name;
    var actionsEl = document.getElementById('topbar-actions');
    var pauseBtn = proj.paused
      ? '<button class="btn btn-primary btn-sm" onclick="resumeProject(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">play_arrow</span> Resume'+(proj.paused_queue_count?' ('+proj.paused_queue_count+')':'')+'</button>'
      : '<button class="btn btn-ghost btn-sm" style="color:var(--warning,#ff9800)" onclick="pauseProject(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">pause</span> Pause</button>';
    // Lifecycle-state buttons: 结束 (close successfully) and 停止 (cancel)
    var closeBtn = '';
    if (proj.status !== 'completed' && proj.status !== 'cancelled' && proj.status !== 'archived') {
      closeBtn =
        '<button class="btn btn-ghost btn-sm" style="color:#22c55e" onclick="changeProjectStatus(\''+projId+'\',\'completed\')"><span class="material-symbols-outlined" style="font-size:16px">check_circle</span> 结束</button>' +
        '<button class="btn btn-ghost btn-sm" style="color:#ef4444" onclick="changeProjectStatus(\''+projId+'\',\'cancelled\')"><span class="material-symbols-outlined" style="font-size:16px">cancel</span> 停止</button>';
    } else {
      closeBtn =
        '<button class="btn btn-ghost btn-sm" style="color:var(--primary)" onclick="changeProjectStatus(\''+projId+'\',\'active\')"><span class="material-symbols-outlined" style="font-size:16px">restart_alt</span> 重新激活</button>';
    }
    actionsEl.innerHTML = pauseBtn + closeBtn + '<button class="btn btn-ghost btn-sm" onclick="showProjectMemberModal(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">group_add</span> Members</button><button class="btn btn-ghost btn-sm" onclick="showProjectTaskModal(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">add_task</span> Task</button><button class="btn btn-ghost btn-sm" onclick="editProject(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">edit</span> Edit</button><button class="btn btn-ghost btn-sm" style="color:var(--error)" onclick="deleteProject(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">delete</span> Delete</button><button class="btn btn-ghost btn-sm" onclick="currentView=\'projects\';renderCurrentView()"><span class="material-symbols-outlined" style="font-size:16px">arrow_back</span> Back</button>';
    if (proj.paused) {
      var pausedBanner = '<div style="background:rgba(255,152,0,0.15);border-bottom:1px solid var(--warning,#ff9800);padding:8px 16px;color:var(--warning,#ff9800);font-size:12px">⏸️ 项目已暂停 — 暂停人: '+esc(proj.paused_by||'-')+(proj.paused_reason?'，原因: '+esc(proj.paused_reason):'')+(proj.paused_queue_count?'  ·  排队消息: '+proj.paused_queue_count:'')+'</div>';
      // banner inserted via wrapper below
      c.dataset.pausedBanner = pausedBanner;
    }

    c.style.display = 'flex';
    c.style.flexDirection = 'column';
    c.style.height = '100%';
    // Tab bar: Overview (default) | Goals | Milestones | Deliverables | Issues | Team Chat
    var _activeTab = (window._projectDetailTab && window._projectDetailTab[projId]) || 'overview';
    var _tabBtn = function(key, label, icon) {
      var active = (_activeTab === key);
      return '<button onclick="switchProjectTab(\''+projId+'\',\''+key+'\')" class="btn btn-ghost btn-sm" style="border-radius:0;border-bottom:2px solid '+(active?'var(--primary)':'transparent')+';color:'+(active?'var(--primary)':'var(--text2)')+';font-weight:'+(active?'700':'500')+';padding:10px 16px"><span class="material-symbols-outlined" style="font-size:16px;margin-right:4px">'+icon+'</span>'+label+'</button>';
    };
    var tabBar = '<div style="display:flex;gap:2px;border-bottom:1px solid rgba(255,255,255,0.05);background:var(--bg);flex-shrink:0">' +
      _tabBtn('overview','Overview','dashboard') +
      _tabBtn('goals','目标','flag') +
      _tabBtn('milestones','里程碑','timeline') +
      _tabBtn('deliverables','交付件','description') +
      _tabBtn('issues','问题','bug_report') +
      _tabBtn('chat','团队协作','forum') +
    '</div>';
    // Panes: one pane per tab; only the chat pane keeps the legacy grid+sidebar.
    var paneVis = function(key){ return _activeTab === key ? '' : 'display:none;'; };
    c.innerHTML = tabBar +
      '<div id="proj-pane-overview-'+projId+'" style="flex:1;overflow:auto;padding:20px;'+paneVis('overview')+'"></div>' +
      '<div id="proj-pane-goals-'+projId+'" style="flex:1;overflow:auto;padding:20px;'+paneVis('goals')+'"></div>' +
      '<div id="proj-pane-milestones-'+projId+'" style="flex:1;overflow:auto;padding:20px;'+paneVis('milestones')+'"></div>' +
      '<div id="proj-pane-deliverables-'+projId+'" style="flex:1;overflow:auto;padding:20px;'+paneVis('deliverables')+'"></div>' +
      '<div id="proj-pane-issues-'+projId+'" style="flex:1;overflow:auto;padding:20px;'+paneVis('issues')+'"></div>' +
      '<div id="proj-pane-chat-'+projId+'" style="flex:1;min-height:0;'+paneVis('chat')+'">' +
      '<div style="display:grid;grid-template-columns:1fr 300px;height:100%;min-height:0;overflow:hidden">' +
      '<!-- Chat Area -->' +
      '<div style="display:flex;flex-direction:column;min-height:0;border-right:1px solid rgba(255,255,255,0.05)">' +
        '<div id="project-chat-msgs-'+projId+'" style="flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;min-height:0"></div>' +
        '<div style="padding:12px 16px;border-top:1px solid rgba(255,255,255,0.05);display:flex;flex-direction:column;gap:6px;position:relative">' +
          '<div id="mention-dropdown-'+projId+'" class="mention-dropdown"></div>' +
          '<div id="proj-attach-preview-'+projId+'" style="display:none;flex-wrap:wrap;gap:6px"></div>' +
          '<div style="display:flex;gap:8px;align-items:center">' +
            '<input type="file" id="proj-attach-file-'+projId+'" multiple style="display:none" onchange="handleProjAttach(\''+projId+'\',this)">' +
            '<button class="btn btn-ghost btn-sm" title="Attach files" onclick="document.getElementById(\'proj-attach-file-'+projId+'\').click()"><span class="material-symbols-outlined" style="font-size:18px">attach_file</span></button>' +
            '<input type="text" id="project-chat-input-'+projId+'" placeholder="Message the team... (@ to mention)" style="flex:1;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:10px 14px;color:var(--text);font-size:13px" onkeydown="_projInputKeydown(event,\''+projId+'\')" oninput="_projInputChange(\''+projId+'\')">' +
            '<button class="btn btn-primary btn-sm" onclick="sendProjectMsg(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:18px">send</span></button>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<!-- Sidebar: Members + Workflow Steps / Milestones + Tasks -->' +
      '<div style="overflow-y:auto;padding:16px;background:var(--bg)">' +
        '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);margin-bottom:8px">Workspace</div>' +
        '<div style="font-size:10px;color:var(--text3);margin-bottom:12px;padding:8px;background:var(--surface2);border-radius:6px;border-left:2px solid var(--primary);word-break:break-all">' + (proj.working_directory ? esc(proj.working_directory) : '(not set)') + '</div>' +
        // Team Members: 有 workflow 时只显示文字列表，无 workflow 时显示机器人头像
        (proj.workflow_binding ?
          '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);margin-bottom:8px">Team Members</div>' +
          '<div id="project-members-'+projId+'" style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:16px"></div>'
          :
          '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);margin-bottom:10px">Team Members</div>' +
          '<div id="project-members-'+projId+'" style="display:flex;flex-direction:column;gap:6px;margin-bottom:20px"></div>'
        ) +
        // Workflow Steps 或 Milestones
        (proj.workflow_binding ?
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px"><div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3)">Workflow Steps</div></div>' +
          '<div id="project-wf-steps-'+projId+'" style="display:flex;flex-direction:column;gap:6px;margin-bottom:20px"></div>'
          :
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px"><div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3)">Milestones</div><button class="btn btn-ghost btn-xs" onclick="showProjectMilestoneModal(\''+projId+'\')" title="Add milestone"><span class="material-symbols-outlined" style="font-size:14px">add</span></button></div>' +
          '<div id="project-milestones-'+projId+'" style="display:flex;flex-direction:column;gap:6px;margin-bottom:20px"></div>'
        ) +
        '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);margin-bottom:10px">Tasks</div>' +
        '<div id="project-tasks-'+projId+'" style="display:flex;flex-direction:column;gap:6px"></div>' +
      '</div>' +
      '</div>' +
    '</div>';  // /proj-pane-chat

    // Populate members — 有 workflow 时紧凑文字，无 workflow 时机器人头像
    var membersEl = document.getElementById('project-members-'+projId);
    if (membersEl) {
      if (proj.workflow_binding) {
        // 紧凑标签式 + 像素机器人头像
        membersEl.innerHTML = proj.members.map(function(m) {
          var ag = agents.find(function(a){ return a.id === m.agent_id; });
          var name = ag ? ag.name : m.agent_id;
          var role = ag ? _resolveRobotRole(ag) : 'general';
          var avatarSrc = _miniRobotDataURL(role);
          return '<span style="display:inline-flex;align-items:center;gap:5px;background:var(--surface);border-radius:12px;padding:3px 10px 3px 4px;border:1px solid rgba(255,255,255,0.08);font-size:11px;color:var(--text)">' +
            '<img src="'+avatarSrc+'" style="width:20px;height:22px;image-rendering:pixelated" />' +
            esc(name) +
          '</span>';
        }).join('');
      } else {
        // 原始机器人头像卡片
        membersEl.innerHTML = proj.members.map(function(m) {
          var ag = agents.find(function(a){ return a.id === m.agent_id; });
          var name = ag ? (ag.role+'-'+ag.name) : m.agent_id;
          var role = ag ? _resolveRobotRole(ag) : 'general';
          var avatarSrc = _miniRobotDataURL(role);
          return '<div style="display:flex;align-items:center;gap:8px;background:var(--surface);border-radius:8px;padding:8px 10px;border:1px solid rgba(255,255,255,0.05);font-size:12px">' +
            '<img src="'+avatarSrc+'" style="width:32px;height:36px;flex-shrink:0;image-rendering:pixelated" />' +
            '<div style="min-width:0">' +
              '<div style="font-weight:700;color:var(--text)">'+esc(name)+'</div>' +
              '<div style="color:var(--text3);font-size:10px;margin-top:2px">'+esc(m.responsibility||'Member')+'</div>' +
            '</div>' +
          '</div>';
        }).join('');
      }
    }

    // Populate Workflow Steps 或 Milestones
    if (proj.workflow_binding) {
      // Workflow Steps 进度显示
      var wfStepsEl = document.getElementById('project-wf-steps-'+projId);
      if (wfStepsEl) {
        // 从 tasks 中提取 [WF Step] 任务，按标题中的步骤号排序
        var wfTasks = (proj.tasks||[]).filter(function(t){ return t.title.indexOf('[WF Step') === 0; });
        wfTasks.sort(function(a,b){
          var na = parseInt((a.title.match(/\[WF Step (\d+)\]/)||[])[1])||0;
          var nb = parseInt((b.title.match(/\[WF Step (\d+)\]/)||[])[1])||0;
          return na - nb;
        });
        // 构建 step_index → agent_id 映射
        var stepAgentMap = {};
        (proj.workflow_binding.step_assignments||[]).forEach(function(sa){
          stepAgentMap[sa.step_index] = sa.agent_id;
        });
        wfStepsEl.innerHTML = wfTasks.map(function(t) {
          var isDone = t.status === 'done';
          var isInProgress = t.status === 'in_progress';
          var statusIcon = isDone ? '☑️' : isInProgress ? '⏳' : '○';
          var stepName = t.title.replace(/^\[WF Step \d+\]\s*/, '');
          var stepNum = parseInt((t.title.match(/\[WF Step (\d+)\]/)||[])[1])||0;
          var stepIdx = stepNum - 1;
          var agentId = stepAgentMap[stepIdx] || t.assigned_to || '';
          var ag = agents.find(function(a){ return a.id === agentId; });
          var agentName = ag ? ag.name : (agentId || '—');
          var barColor = isDone ? 'var(--success, #4caf50)' : isInProgress ? 'var(--warning, #ff9800)' : 'rgba(255,255,255,0.1)';
          var toggleBtn = isDone ?
            '<span class="material-symbols-outlined" style="font-size:14px;cursor:pointer;color:var(--success,#4caf50)" onclick="toggleWfStep(\''+projId+'\',\''+t.id+'\',\'todo\')" title="标记为未完成">check_circle</span>' :
            '<span class="material-symbols-outlined" style="font-size:14px;cursor:pointer;color:var(--text3);opacity:0.5" onclick="toggleWfStep(\''+projId+'\',\''+t.id+'\',\'done\')" title="标记为完成">radio_button_unchecked</span>';
          var md = t.metadata || {};
          var pendingApproval = !!md.pending_approval;
          var approvalBar = pendingApproval
            ? '<div style="display:flex;align-items:center;gap:6px;margin-top:6px;padding:6px 8px;background:rgba(59,130,246,0.10);border:1px dashed #3b82f6;border-radius:4px">' +
                '<span style="font-size:10px;color:#3b82f6;flex:1">⏸️ 等待人工批准后启动</span>' +
                '<button onclick="approveWfStep(\''+projId+'\',\''+t.id+'\')" style="font-size:10px;background:#22c55e;color:#000;border:none;border-radius:3px;padding:2px 8px;cursor:pointer;font-weight:600">✓ 批准启动</button>' +
              '</div>'
            : '';
          var borderExtra = pendingApproval ? ';border-color:rgba(59,130,246,0.4)' : '';
          return '<div style="background:var(--surface);border-radius:8px;padding:8px 10px;border:1px solid rgba(255,255,255,0.05)'+borderExtra+';font-size:11px;border-left:3px solid '+barColor+'">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;gap:6px">' +
              toggleBtn +
              '<span style="flex:1;font-weight:600;color:'+(isDone?'var(--text3)':'var(--text)')+';'+(isDone?'text-decoration:line-through':'')+'">' +esc(stepName)+'</span>' +
              '<span style="font-size:10px;color:var(--primary);white-space:nowrap">'+esc(agentName)+'</span>' +
            '</div>' +
            (t.description ? '<div style="color:var(--text3);font-size:10px;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(t.description.split('\\n')[0])+'</div>' : '') +
            approvalBar +
          '</div>';
        }).join('') || '<div style="font-size:12px;color:var(--text3)">No workflow steps</div>';

        // 进度条
        var doneCount = wfTasks.filter(function(t){ return t.status==='done'; }).length;
        var pct = wfTasks.length > 0 ? Math.round(doneCount/wfTasks.length*100) : 0;
        wfStepsEl.insertAdjacentHTML('afterbegin',
          '<div style="margin-bottom:8px">' +
            '<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text3);margin-bottom:4px"><span>Progress</span><span>'+doneCount+'/'+wfTasks.length+' ('+pct+'%)</span></div>' +
            '<div style="height:4px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden"><div style="height:100%;width:'+pct+'%;background:var(--primary);border-radius:2px;transition:width 0.3s"></div></div>' +
          '</div>'
        );
      }
    } else {
      // 原始 Milestones 显示
      var milestonesEl = document.getElementById('project-milestones-'+projId);
      if (milestonesEl) {
        milestonesEl.innerHTML = (proj.milestones||[]).map(function(m) {
          var statusIcon = m.status==='confirmed'?'✅':m.status==='completed'?'☑️':m.status==='rejected'?'❌':m.status==='in_progress'?'⏳':'○';
          var ag = agents.find(function(a){ return a.id === m.responsible_agent_id; });
          var responsible = ag ? ag.name : (m.responsible_agent_id||'—');
          var dueDate = m.due_date ? new Date(m.due_date).toLocaleDateString() : '—';
          var actions = '';
          if (m.status === 'completed') {
            // Agent 已声明完成，等待 admin 确认
            actions = '<div style="display:flex;gap:4px;margin-top:6px" onclick="event.stopPropagation()">' +
              '<button class="btn btn-primary btn-xs" onclick="confirmMilestone(\''+projId+'\',\''+m.id+'\')" style="font-size:10px;padding:2px 8px">确认</button>' +
              '<button class="btn btn-ghost btn-xs" style="color:var(--error);font-size:10px;padding:2px 8px" onclick="rejectMilestone(\''+projId+'\',\''+m.id+'\')">驳回</button>' +
              '</div>';
          }
          var reasonLine = m.status==='rejected' && m.rejected_reason
            ? '<div style="color:var(--error);font-size:10px;margin-top:2px">驳回原因: '+esc(m.rejected_reason)+'</div>' : '';
          return '<div style="background:var(--surface);border-radius:8px;padding:8px 10px;border:1px solid rgba(255,255,255,0.05);font-size:11px;cursor:pointer" onclick="showMilestoneUpdateModal(\''+projId+'\',\''+m.id+'\',\''+esc(m.name).replace(/'/g,"\\\'")+'\',\''+m.status+'\')" title="Click to update">' +
            '<div style="font-weight:600">'+statusIcon+' '+esc(m.name)+'</div>' +
            '<div style="color:var(--text3);font-size:10px;margin-top:2px">'+esc(responsible)+' · '+dueDate+'</div>' +
            reasonLine + actions +
          '</div>';
        }).join('') || '<div style="font-size:12px;color:var(--text3)">No milestones yet</div>';
      }
    }

    // Populate tasks（绑定 workflow 时过滤掉 WF Step 任务，避免重复显示）
    var tasksEl = document.getElementById('project-tasks-'+projId);
    if (tasksEl) {
      var displayTasks = (proj.tasks||[]).filter(function(t){
        return !proj.workflow_binding || t.title.indexOf('[WF Step') !== 0;
      });
      tasksEl.innerHTML = displayTasks.map(function(t) {
        var statusIcon = t.status==='done'?'✅':t.status==='in_progress'?'⏳':t.status==='blocked'?'🚫':'📋';
        var ag = agents.find(function(a){ return a.id === t.assigned_to; });
        var assignee = ag ? ag.name : (t.assigned_to||'Unassigned');
        var stepsHtml = '';
        var steps = t.steps || [];
        var hasReview = steps.some(function(s){ return s.status === 'awaiting_review'; });
        if (steps.length > 0) {
          stepsHtml = '<div style="margin-top:6px;display:flex;flex-direction:column;gap:3px">' +
            steps.map(function(s, idx) {
              var sIcon = ({
                pending:'⚪', in_progress:'⏳', awaiting_review:'🔵',
                done:'✅', failed:'❌', skipped:'⏭️'
              })[s.status] || '⚪';
              var sColor = s.status==='awaiting_review' ? '#3b82f6'
                         : s.status==='done' ? 'var(--text3)'
                         : s.status==='failed' ? '#ef4444' : 'var(--text2)';
              var reviewBadge = s.manual_review
                ? '<span title="此步骤需要人工审核" style="font-size:9px;background:rgba(59,130,246,0.15);color:#3b82f6;padding:1px 5px;border-radius:3px;margin-left:4px">👤 人工</span>'
                : '';
              var actionBtns = '';
              if (s.status === 'awaiting_review') {
                actionBtns = '<button onclick="reviewStep(\''+esc(projId)+'\',\''+esc(t.id)+'\',\''+esc(s.id)+'\',\'approve\')" style="font-size:10px;background:#22c55e;color:#000;border:none;border-radius:3px;padding:2px 6px;cursor:pointer;margin-left:4px;font-weight:600">✓ 通过</button>' +
                              '<button onclick="reviewStep(\''+esc(projId)+'\',\''+esc(t.id)+'\',\''+esc(s.id)+'\',\'reject\')" style="font-size:10px;background:rgba(239,68,68,0.2);color:#ef4444;border:1px solid #ef4444;border-radius:3px;padding:2px 6px;cursor:pointer;margin-left:2px;font-weight:600">✗ 驳回</button>';
              }
              var draftPreview = '';
              if (s.status === 'awaiting_review' && s.result) {
                draftPreview = '<div style="font-size:10px;color:var(--text3);margin-left:18px;margin-top:2px;padding:4px 6px;background:rgba(59,130,246,0.06);border-left:2px solid #3b82f6;border-radius:2px;max-height:60px;overflow:hidden">'+esc(String(s.result).slice(0,200))+(s.result.length>200?'…':'')+'</div>';
              }
              return '<div style="font-size:11px;color:'+sColor+'">' +
                '<span>'+sIcon+' '+(idx+1)+'. '+esc(s.name)+'</span>'+reviewBadge+actionBtns +
                draftPreview +
              '</div>';
            }).join('') +
          '</div>';
        }
        var editBtn = '<button onclick="editTaskSteps(\''+esc(projId)+'\',\''+esc(t.id)+'\')" title="编辑步骤" style="font-size:10px;background:transparent;color:var(--text3);border:1px solid rgba(255,255,255,0.1);border-radius:3px;padding:1px 6px;cursor:pointer;margin-left:6px">⚙️ 步骤</button>';
        var pausedBadge = hasReview ? '<span style="font-size:9px;background:rgba(59,130,246,0.18);color:#3b82f6;padding:1px 6px;border-radius:3px;margin-left:6px">⏸ 等待审核</span>' : '';
        return '<div style="background:var(--surface);border-radius:8px;padding:8px 10px;border:1px solid '+(hasReview?'rgba(59,130,246,0.4)':'rgba(255,255,255,0.05)')+';font-size:12px">' +
          '<div style="display:flex;justify-content:space-between;align-items:center">' +
            '<span style="font-weight:600">'+statusIcon+' '+esc(t.title)+pausedBadge+editBtn+'</span>' +
            '<span style="font-size:10px;color:var(--text3)">→ '+esc(assignee)+'</span>' +
          '</div>' +
          stepsHtml +
        '</div>';
      }).join('') || '<div style="font-size:12px;color:var(--text3)">No tasks yet</div>';
    }

    // Load chat history (lazy — only if chat tab active, but load anyway so tab-switch is instant)
    loadProjectChat(projId);
    // Load the active (default) tab content
    loadProjectTabContent(projId, _activeTab);
  } catch(e) { c.innerHTML = '<div style="padding:24px;color:var(--error)">Error: '+e.message+'</div>'; }
}

// ── Project detail tab switching ──
window._projectDetailTab = window._projectDetailTab || {};
function switchProjectTab(projId, tabKey) {
  window._projectDetailTab[projId] = tabKey;
  var keys = ['overview','goals','milestones','deliverables','issues','chat'];
  keys.forEach(function(k){
    var el = document.getElementById('proj-pane-'+k+'-'+projId);
    if (el) el.style.display = (k === tabKey) ? (k === 'chat' ? 'flex' : 'block') : 'none';
  });
  // Re-render tab bar highlighting (quick hack: re-run detail render)
  renderProjectDetail(projId);
}

async function loadProjectTabContent(projId, tabKey) {
  if (tabKey === 'chat') return;  // chat already bootstrapped
  var pane = document.getElementById('proj-pane-'+tabKey+'-'+projId);
  if (!pane) return;
  try {
    if (tabKey === 'overview') {
      var data = await api('GET', '/api/portal/projects/'+projId+'/overview');
      pane.innerHTML = _renderProjectOverview(projId, data);
    } else if (tabKey === 'goals') {
      var r = await api('GET', '/api/portal/projects/'+projId+'/goals');
      pane.innerHTML = _renderProjectGoals(projId, r.goals || []);
    } else if (tabKey === 'milestones') {
      var r2 = await api('GET', '/api/portal/projects/'+projId+'/milestones');
      pane.innerHTML = _renderProjectMilestonesTab(projId, r2.milestones || []);
    } else if (tabKey === 'deliverables') {
      var r3 = await api('GET', '/api/portal/projects/'+projId+'/deliverables-by-agent');
      pane.innerHTML = _renderProjectDeliverables(projId, r3);
    } else if (tabKey === 'issues') {
      var r4 = await api('GET', '/api/portal/projects/'+projId+'/issues');
      pane.innerHTML = _renderProjectIssues(projId, r4.issues || []);
    }
  } catch(e) {
    pane.innerHTML = '<div style="color:var(--error)">Error: '+esc(e.message)+'</div>';
  }
}

function _pctBar(pct) {
  pct = Math.max(0, Math.min(100, pct||0));
  var color = pct >= 100 ? '#22c55e' : pct >= 50 ? 'var(--primary)' : '#f59e0b';
  return '<div style="height:6px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden"><div style="height:100%;width:'+pct+'%;background:'+color+';transition:width 0.3s"></div></div>';
}

function _renderProjectOverview(projId, d) {
  var gs = d.goal_summary || {}; var ds = d.deliverable_summary || {}; var is = d.issue_summary || {}; var ts = d.task_summary || {};
  var goals = d.goals || []; var deliverables = d.deliverables || []; var issues = d.issues || [];
  var recentGoals = goals.slice(0,5).map(function(g){
    return '<div style="background:var(--surface);border-radius:8px;padding:10px 12px;border:1px solid rgba(255,255,255,0.05);margin-bottom:8px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><span style="font-weight:600;font-size:13px">'+esc(g.name||'(未命名目标)')+'</span><span style="font-size:11px;color:var(--text3)">'+(g.progress||0).toFixed(1)+'%</span></div>' +
      _pctBar(g.progress||0) +
    '</div>';
  }).join('') || '<div style="color:var(--text3);font-size:12px">暂无目标，点击 Goals 标签创建</div>';
  var pending = deliverables.filter(function(x){return x.status==='submitted';});
  var pendingHtml = pending.slice(0,5).map(function(x){
    return '<div style="background:var(--surface);border-radius:8px;padding:8px 12px;border:1px solid rgba(255,255,255,0.05);margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">' +
      '<div><div style="font-weight:600;font-size:13px">'+esc(x.title)+'</div><div style="font-size:10px;color:var(--text3)">v'+x.version+' · '+esc(x.kind)+'</div></div>' +
      '<div style="display:flex;gap:4px">' +
        '<button class="btn btn-primary btn-xs" onclick="reviewDeliverable(\''+projId+'\',\''+x.id+'\',true)">通过</button>' +
        '<button class="btn btn-ghost btn-xs" style="color:var(--error)" onclick="reviewDeliverable(\''+projId+'\',\''+x.id+'\',false)">驳回</button>' +
      '</div>' +
    '</div>';
  }).join('') || '<div style="color:var(--text3);font-size:12px">没有等待审阅的交付件</div>';
  var openIssues = issues.filter(function(x){return x.status==='open'||x.status==='investigating';});
  var issuesHtml = openIssues.slice(0,5).map(function(x){
    var sevColor = x.severity==='critical'?'#ef4444':x.severity==='high'?'#f59e0b':x.severity==='medium'?'var(--primary)':'var(--text3)';
    return '<div style="background:var(--surface);border-radius:8px;padding:8px 12px;border:1px solid rgba(255,255,255,0.05);margin-bottom:6px;border-left:3px solid '+sevColor+'">' +
      '<div style="font-weight:600;font-size:13px">'+esc(x.title)+'</div>' +
      '<div style="font-size:10px;color:var(--text3);margin-top:2px">'+esc(x.severity)+' · '+esc(x.status)+(x.assigned_to?' · → '+esc(x.assigned_to):'')+'</div>' +
    '</div>';
  }).join('') || '<div style="color:var(--text3);font-size:12px">目前没有未解决的问题</div>';
  var statCard = function(label, val, sub){
    return '<div style="background:var(--surface);border-radius:8px;padding:14px 16px;border:1px solid rgba(255,255,255,0.05)">' +
      '<div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:0.6px">'+label+'</div>' +
      '<div style="font-size:22px;font-weight:700;color:var(--text);margin-top:4px">'+val+'</div>' +
      (sub?'<div style="font-size:10px;color:var(--text3);margin-top:2px">'+sub+'</div>':'') +
    '</div>';
  };
  return '<div style="max-width:1100px">' +
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">' +
      statCard('目标完成', (gs.done||0)+'/'+(gs.total||0), '均值 '+(gs.avg_progress||0)+'%') +
      statCard('交付件等待审阅', (ds.submitted||0)+'', '总 '+(ds.total||0)+' · ✅'+(ds.approved||0)) +
      statCard('未解决问题', (is.open||0)+'', '总 '+(is.total||0)) +
      statCard('进行中任务', (ts.in_progress||0)+'', 'TODO '+(ts.todo||0)+' · DONE '+(ts.done||0)) +
    '</div>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">' +
      '<div><div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);margin-bottom:10px">目标概览 (Top 5)</div>'+recentGoals+'</div>' +
      '<div><div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);margin-bottom:10px">待审阅交付件</div>'+pendingHtml+'</div>' +
    '</div>' +
    '<div style="margin-top:20px"><div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);margin-bottom:10px">未解决问题</div>'+issuesHtml+'</div>' +
  '</div>';
}

function _renderProjectGoals(projId, goals) {
  var rows = (goals||[]).map(function(g){
    var pct = g.progress||0;
    var metricLabel = g.metric==='count' ? (g.current_value+' / '+g.target_value) :
                      g.metric==='percent' ? (g.current_value+' / '+g.target_value+'%') :
                      g.metric==='boolean' ? (g.done?'✅ 已达成':'⬜ 未达成') :
                      esc(g.target_text||'');
    return '<div style="background:var(--surface);border-radius:10px;padding:14px 16px;border:1px solid rgba(255,255,255,0.06);margin-bottom:10px">' +
      '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">' +
        '<div style="flex:1;min-width:0">' +
          '<div style="font-weight:700;font-size:14px;color:var(--text)">'+esc(g.name||'(未命名)')+'</div>' +
          (g.description?'<div style="color:var(--text3);font-size:12px;margin-top:3px">'+esc(g.description)+'</div>':'') +
          '<div style="font-size:11px;color:var(--text2);margin-top:6px">指标: '+esc(g.metric)+' · '+metricLabel+(g.owner_agent_id?' · 负责: '+esc(g.owner_agent_id):'')+'</div>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">' +
          '<span style="font-size:18px;font-weight:700;color:'+(pct>=100?'#22c55e':'var(--primary)')+'">'+pct.toFixed(0)+'%</span>' +
          '<button class="btn btn-ghost btn-xs" onclick="updateGoalProgressPrompt(\''+projId+'\',\''+g.id+'\',\''+g.metric+'\')">更新进度</button>' +
          '<button class="btn btn-ghost btn-xs" style="color:var(--error)" onclick="deleteGoal(\''+projId+'\',\''+g.id+'\')">删除</button>' +
        '</div>' +
      '</div>' +
      '<div style="margin-top:10px">'+_pctBar(pct)+'</div>' +
    '</div>';
  }).join('') || '<div style="color:var(--text3);font-size:13px;padding:20px;text-align:center">暂无目标。点击"新建目标"来为本项目设立可度量目标。</div>';
  return '<div style="max-width:900px">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">' +
      '<div style="font-size:16px;font-weight:700">项目目标</div>' +
      '<button class="btn btn-primary btn-sm" onclick="showAddGoalModal(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> 新建目标</button>' +
    '</div>' + rows +
  '</div>';
}

function _renderProjectMilestonesTab(projId, milestones) {
  var rows = (milestones||[]).map(function(m){
    var statusIcon = m.status==='confirmed'?'✅':m.status==='completed'?'☑️':m.status==='rejected'?'❌':m.status==='in_progress'?'⏳':'○';
    var actions = '';
    if (m.status === 'completed') {
      actions = '<div style="display:flex;gap:6px;margin-top:8px">' +
        '<button class="btn btn-primary btn-xs" onclick="confirmMilestone(\''+projId+'\',\''+m.id+'\')">确认</button>' +
        '<button class="btn btn-ghost btn-xs" style="color:var(--error)" onclick="rejectMilestone(\''+projId+'\',\''+m.id+'\')">驳回</button>' +
      '</div>';
    }
    return '<div style="background:var(--surface);border-radius:10px;padding:14px 16px;border:1px solid rgba(255,255,255,0.06);margin-bottom:10px">' +
      '<div style="font-weight:700;font-size:14px">'+statusIcon+' '+esc(m.name||'')+'</div>' +
      '<div style="font-size:11px;color:var(--text3);margin-top:4px">负责: '+esc(m.responsible_agent_id||'—')+' · 到期: '+esc(m.due_date||'—')+' · 状态: '+esc(m.status||'pending')+'</div>' +
      (m.rejected_reason?'<div style="color:var(--error);font-size:11px;margin-top:4px">驳回原因: '+esc(m.rejected_reason)+'</div>':'') +
      actions +
    '</div>';
  }).join('') || '<div style="color:var(--text3);font-size:13px;padding:20px;text-align:center">暂无里程碑</div>';
  return '<div style="max-width:900px">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">' +
      '<div style="font-size:16px;font-weight:700">里程碑</div>' +
      '<button class="btn btn-primary btn-sm" onclick="showProjectMilestoneModal(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> 新建里程碑</button>' +
    '</div>' + rows +
  '</div>';
}

function _renderProjectDeliverables(projId, data) {
  data = data || {};
  var agents = data.agents || [];
  var unassigned = data.unassigned_deliverables || [];
  var statusBadge = function(s){
    var map = {draft:['草稿','var(--text3)'], submitted:['待审阅','#f59e0b'], approved:['已通过','#22c55e'], rejected:['已驳回','#ef4444'], archived:['归档','var(--text3)']};
    var x = map[s]||[s,'var(--text3)'];
    return '<span style="font-size:10px;background:rgba(255,255,255,0.08);color:'+x[1]+';padding:2px 8px;border-radius:10px;font-weight:600">'+x[0]+'</span>';
  };
  var fmtSize = function(n){
    if (!n && n !== 0) return '';
    if (n < 1024) return n+'B';
    if (n < 1024*1024) return (n/1024).toFixed(1)+'KB';
    if (n < 1024*1024*1024) return (n/1024/1024).toFixed(1)+'MB';
    return (n/1024/1024/1024).toFixed(2)+'GB';
  };
  var fmtTime = function(ts){
    if (!ts) return '';
    try { var d = new Date(ts*1000); return d.toLocaleString(); } catch(e){ return ''; }
  };
  var renderDeliverableCard = function(dv){
    var actions = '';
    if (dv.status === 'submitted') {
      actions = '<button class="btn btn-primary btn-xs" onclick="reviewDeliverable(\''+projId+'\',\''+dv.id+'\',true)">通过</button>' +
                '<button class="btn btn-ghost btn-xs" style="color:var(--error)" onclick="reviewDeliverable(\''+projId+'\',\''+dv.id+'\',false)">驳回</button>';
    } else if (dv.status === 'draft') {
      actions = '<button class="btn btn-primary btn-xs" onclick="submitDeliverable(\''+projId+'\',\''+dv.id+'\')">提交审阅</button>';
    }
    var preview = dv.content_text ? '<div style="font-size:12px;color:var(--text2);margin-top:6px;max-height:72px;overflow:hidden;line-height:1.5">'+esc(dv.content_text.slice(0,300))+(dv.content_text.length>300?'…':'')+'</div>' : '';
    var link = dv.url ? '<a href="'+esc(dv.url)+'" target="_blank" style="font-size:11px;color:var(--primary)">'+esc(dv.url)+'</a>' : (dv.file_path?'<span style="font-size:11px;color:var(--text3)">📎 '+esc(dv.file_path)+'</span>':'');
    var reviewComment = dv.review_comment ? '<div style="margin-top:6px;font-size:11px;color:var(--text3);padding:6px 8px;background:rgba(255,255,255,0.03);border-left:2px solid '+(dv.status==='approved'?'#22c55e':'#ef4444')+';border-radius:3px">审阅意见: '+esc(dv.review_comment)+'</div>' : '';
    return '<div style="background:var(--surface);border-radius:10px;padding:12px 14px;border:1px solid rgba(255,255,255,0.06);margin-bottom:8px">' +
      '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">' +
        '<div style="flex:1;min-width:0">' +
          '<div style="display:flex;align-items:center;gap:8px"><span style="font-weight:700;font-size:13px">'+esc(dv.title)+'</span>'+statusBadge(dv.status)+'<span style="font-size:10px;color:var(--text3)">v'+dv.version+'</span></div>' +
          '<div style="font-size:11px;color:var(--text3);margin-top:3px">'+esc(dv.kind||'')+'</div>' +
          preview + (link?'<div style="margin-top:6px">'+link+'</div>':'') + reviewComment +
        '</div>' +
        '<div style="display:flex;flex-direction:column;gap:6px;align-items:flex-end">'+actions+
          '<button class="btn btn-ghost btn-xs" style="color:var(--error)" onclick="deleteDeliverable(\''+projId+'\',\''+dv.id+'\')">删除</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  };
  var renderFileRow = function(f){
    var icon = f.is_remote ? '🔗' : '📄';
    var meta = [];
    if (f.size) meta.push(fmtSize(f.size));
    if (f.mtime) meta.push(fmtTime(f.mtime));
    if (f.kind) meta.push(esc(f.kind));
    var name = f.url
      ? '<a href="'+esc(f.url)+'" target="_blank" style="color:var(--primary);text-decoration:none;font-weight:600;font-size:13px">'+esc(f.name||f.rel_path||f.path||'(unnamed)')+'</a>'
      : '<span style="font-size:13px;font-weight:600">'+esc(f.name||'(unnamed)')+'</span>';
    var rel = f.rel_path && f.rel_path !== f.name ? '<div style="font-size:10px;color:var(--text3);margin-top:2px">'+esc(f.rel_path)+'</div>' : '';
    return '<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 12px;border-bottom:1px solid rgba(255,255,255,0.04)">' +
      '<div style="font-size:14px;line-height:1">'+icon+'</div>' +
      '<div style="flex:1;min-width:0">'+name+rel+
        (meta.length?'<div style="font-size:10px;color:var(--text3);margin-top:2px">'+meta.join(' · ')+'</div>':'') +
      '</div>' +
    '</div>';
  };
  var agentSections = (agents||[]).map(function(ag){
    var explicit = (ag.explicit_deliverables||[]).map(renderDeliverableCard).join('');
    var files = (ag.files||[]).map(renderFileRow).join('');
    var emptyHint = (!explicit && !files) ? '<div style="color:var(--text3);font-size:12px;padding:14px;text-align:center">该 Agent 暂无交付物</div>' : '';
    var dirHint = ag.deliverable_dir ? '<div style="font-size:10px;color:var(--text3);margin-top:2px;font-family:monospace">📁 '+esc(ag.deliverable_dir)+'</div>' : '';
    return '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:14px;margin-bottom:14px">' +
      '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;gap:10px">' +
        '<div style="flex:1;min-width:0">' +
          '<div style="font-size:14px;font-weight:700">👤 '+esc(ag.agent_name||ag.agent_id)+(ag.role?' <span style="font-size:11px;color:var(--text3);font-weight:400">('+esc(ag.role)+')</span>':'')+'</div>' +
          dirHint +
        '</div>' +
        '<div style="font-size:10px;color:var(--text3);white-space:nowrap">📄 '+(ag.file_count||0)+' · 📋 '+(ag.explicit_count||0)+'</div>' +
      '</div>' +
      (explicit ? '<div style="margin-bottom:8px">'+explicit+'</div>' : '') +
      (files ? '<div style="background:var(--surface);border-radius:8px;overflow:hidden">'+files+'</div>' : '') +
      emptyHint +
    '</div>';
  }).join('');
  var unassignedSection = '';
  if (unassigned && unassigned.length) {
    unassignedSection = '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:14px;margin-bottom:14px">' +
      '<div style="font-size:14px;font-weight:700;margin-bottom:10px">❓ 未指派作者</div>' +
      unassigned.map(renderDeliverableCard).join('') +
    '</div>';
  }
  var body = (agentSections || unassignedSection)
    ? (agentSections + unassignedSection)
    : '<div style="color:var(--text3);font-size:13px;padding:20px;text-align:center">暂无交付件</div>';
  return '<div style="max-width:900px">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">' +
      '<div style="font-size:16px;font-weight:700">交付件 (按 Agent 分组)</div>' +
      '<button class="btn btn-primary btn-sm" onclick="showAddDeliverableModal(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> 新建交付件</button>' +
    '</div>' + body +
  '</div>';
}

function _renderProjectIssues(projId, items) {
  var sevColor = function(s){ return s==='critical'?'#ef4444':s==='high'?'#f59e0b':s==='medium'?'var(--primary)':'var(--text3)'; };
  var rows = (items||[]).map(function(iss){
    var resolved = (iss.status==='resolved'||iss.status==='wontfix');
    var actions = resolved ? '' :
      '<button class="btn btn-primary btn-xs" onclick="resolveIssuePrompt(\''+projId+'\',\''+iss.id+'\')">标记解决</button>';
    var resLine = iss.resolution ? '<div style="margin-top:6px;font-size:11px;color:#22c55e;padding:6px 8px;background:rgba(34,197,94,0.08);border-radius:3px">✓ '+esc(iss.resolution)+'</div>' : '';
    return '<div style="background:var(--surface);border-radius:10px;padding:14px 16px;border:1px solid rgba(255,255,255,0.06);margin-bottom:10px;border-left:3px solid '+sevColor(iss.severity)+'">' +
      '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">' +
        '<div style="flex:1;min-width:0">' +
          '<div style="font-weight:700;font-size:14px">'+esc(iss.title)+(resolved?' <span style="font-size:10px;color:var(--text3)">['+esc(iss.status)+']</span>':'')+'</div>' +
          (iss.description?'<div style="font-size:12px;color:var(--text2);margin-top:4px">'+esc(iss.description)+'</div>':'') +
          '<div style="font-size:11px;color:var(--text3);margin-top:6px">严重度: '+esc(iss.severity)+' · 状态: '+esc(iss.status)+(iss.assigned_to?' · → '+esc(iss.assigned_to):'')+'</div>' +
          resLine +
        '</div>' +
        '<div style="display:flex;flex-direction:column;gap:6px;align-items:flex-end">'+actions+
          '<button class="btn btn-ghost btn-xs" style="color:var(--error)" onclick="deleteIssue(\''+projId+'\',\''+iss.id+'\')">删除</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('') || '<div style="color:var(--text3);font-size:13px;padding:20px;text-align:center">暂无问题记录</div>';
  return '<div style="max-width:900px">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">' +
      '<div style="font-size:16px;font-weight:700">问题 / 风险</div>' +
      '<button class="btn btn-primary btn-sm" onclick="showAddIssueModal(\''+projId+'\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> 新建问题</button>' +
    '</div>' + rows +
  '</div>';
}

// ── Goal CRUD helpers ──
async function _fetchProjectMembers(projId) {
  try {
    var proj = await api('GET', '/api/portal/projects/'+projId);
    var members = (proj && proj.members) || [];
    // Enrich with agent name/role from agents API
    try {
      var agData = await api('GET', '/api/portal/agents');
      var agMap = {};
      ((agData && agData.agents) || []).forEach(function(a){ agMap[a.id] = a; });
      members.forEach(function(m){
        var ag = agMap[m.agent_id];
        if (ag) { m.agent_name = ag.name || m.agent_id; m.role = ag.role || ''; }
      });
    } catch(e) {}
    return members;
  } catch(e) { return []; }
}
function _memberOptions(members, selected) {
  var html = '<option value="">-- 不指派 --</option>';
  html += '<option value="__user__"'+(selected==='__user__'?' selected':'')+'>用户 (User)</option>';
  (members||[]).forEach(function(m){
    var aid = m.agent_id || '';
    var label = (m.agent_name || aid) + (m.role ? ' ('+m.role+')' : '');
    html += '<option value="'+esc(aid)+'"'+(selected===aid?' selected':'')+'>'+esc(label)+'</option>';
  });
  return html;
}
var _modalInputStyle = 'width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:13px;box-sizing:border-box';

async function showAddGoalModal(projId) {
  var members = await _fetchProjectMembers(projId);
  var modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:20px;max-width:520px;width:94%">'
    + '<h3 style="margin:0 0 14px">新建目标</h3>'
    + '<div style="display:flex;flex-direction:column;gap:10px">'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">目标名称 *</label>'
    + '<input id="goal-name" style="'+_modalInputStyle+'" placeholder="例如：完成核心功能开发"></div>'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">描述</label>'
    + '<textarea id="goal-desc" rows="2" style="'+_modalInputStyle+'" placeholder="可选描述"></textarea></div>'
    + '<div style="display:flex;gap:10px">'
    + '<div style="flex:1"><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">度量类型</label>'
    + '<select id="goal-metric" style="'+_modalInputStyle+'" onchange="_goalMetricChanged()">'
    + '<option value="count">计数 (count)</option><option value="percent">百分比 (percent)</option>'
    + '<option value="boolean">是/否 (boolean)</option><option value="text">文本 (text)</option></select></div>'
    + '<div style="flex:1" id="goal-target-wrap"><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">目标值</label>'
    + '<input id="goal-target" type="number" value="100" style="'+_modalInputStyle+'"></div>'
    + '</div>'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">负责人</label>'
    + '<select id="goal-owner" style="'+_modalInputStyle+'">'+_memberOptions(members,'__user__')+'</select></div>'
    + '</div>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">'
    + '<button class="btn btn-sm" onclick="this.closest(\'div[style*=fixed]\').remove()">取消</button>'
    + '<button class="btn btn-primary btn-sm" onclick="_submitGoal(\''+projId+'\',this)">创建</button>'
    + '</div></div>';
  document.body.appendChild(modal);
  setTimeout(function(){ var el = document.getElementById('goal-name'); if (el) el.focus(); }, 0);
}
function _goalMetricChanged() {
  var m = document.getElementById('goal-metric').value;
  var wrap = document.getElementById('goal-target-wrap');
  if (m === 'boolean') {
    wrap.innerHTML = '<label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">完成状态</label><div style="font-size:12px;color:var(--text3)">创建后通过"更新进度"标记</div>';
  } else if (m === 'text') {
    wrap.innerHTML = '<label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">目标描述</label><input id="goal-target-text" style="'+_modalInputStyle+'" placeholder="目标文本">';
  } else {
    wrap.innerHTML = '<label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">目标值</label><input id="goal-target" type="number" value="100" style="'+_modalInputStyle+'">';
  }
}
async function _submitGoal(projId, btn) {
  var name = (document.getElementById('goal-name').value||'').trim();
  if (!name) { alert('请输入目标名称'); return; }
  var metric = document.getElementById('goal-metric').value;
  var targetV = 0, targetT = '';
  if (metric === 'count' || metric === 'percent') {
    var el = document.getElementById('goal-target');
    targetV = el ? parseFloat(el.value||'0') : 0;
  } else if (metric === 'text') {
    var el2 = document.getElementById('goal-target-text');
    targetT = el2 ? el2.value : '';
  }
  var owner = document.getElementById('goal-owner').value;
  if (owner === '__user__') owner = '';
  btn.disabled = true;
  await api('POST', '/api/portal/projects/'+projId+'/goals', {
    name: name,
    description: (document.getElementById('goal-desc').value||'').trim(),
    metric: metric, target_value: targetV, target_text: targetT,
    owner_agent_id: owner,
  });
  btn.closest('div[style*=fixed]').remove();
  loadProjectTabContent(projId, 'goals');
}
function updateGoalProgressPrompt(projId, goalId, metric) {
  if (metric === 'boolean') {
    var ok = confirm('标记为已达成？');
    api('POST', '/api/portal/projects/'+projId+'/goals/'+goalId+'/progress', {done: ok})
      .then(function(){ loadProjectTabContent(projId, 'goals'); });
  } else {
    var v = parseFloat(prompt('当前进度值:', '0') || 'NaN');
    if (isNaN(v)) return;
    api('POST', '/api/portal/projects/'+projId+'/goals/'+goalId+'/progress', {current_value: v})
      .then(function(){ loadProjectTabContent(projId, 'goals'); });
  }
}
function deleteGoal(projId, goalId) {
  if (!confirm('删除此目标？')) return;
  api('POST', '/api/portal/projects/'+projId+'/goals/'+goalId+'/delete', {})
    .then(function(){ loadProjectTabContent(projId, 'goals'); });
}

// ── Deliverable CRUD helpers ──
async function showAddDeliverableModal(projId) {
  var members = await _fetchProjectMembers(projId);
  var modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:20px;max-width:520px;width:94%">'
    + '<h3 style="margin:0 0 14px">新建交付件</h3>'
    + '<div style="display:flex;flex-direction:column;gap:10px">'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">标题 *</label>'
    + '<input id="dv-title" style="'+_modalInputStyle+'" placeholder="交付件标题"></div>'
    + '<div style="display:flex;gap:10px">'
    + '<div style="flex:1"><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">类型</label>'
    + '<select id="dv-kind" style="'+_modalInputStyle+'">'
    + '<option value="document">文档 (document)</option><option value="code">代码 (code)</option>'
    + '<option value="analysis">分析 (analysis)</option><option value="url">链接 (url)</option>'
    + '<option value="media">媒体 (media)</option><option value="other">其他 (other)</option></select></div>'
    + '<div style="flex:1"><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">作者 Agent *</label>'
    + '<select id="dv-author" style="'+_modalInputStyle+'">'+_memberOptions(members,'')+'</select></div>'
    + '</div>'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">内容摘要</label>'
    + '<textarea id="dv-content" rows="3" style="'+_modalInputStyle+'" placeholder="交付件摘要或说明"></textarea></div>'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">URL / 文件路径</label>'
    + '<input id="dv-url" style="'+_modalInputStyle+'" placeholder="可选：链接地址或文件路径"></div>'
    + '</div>'
    + '<div style="font-size:11px;color:var(--text3);margin-top:8px">交付件创建后为"草稿"状态。由作者 Agent 提交后进入"待审阅"，用户审核通过/驳回。</div>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">'
    + '<button class="btn btn-sm" onclick="this.closest(\'div[style*=fixed]\').remove()">取消</button>'
    + '<button class="btn btn-primary btn-sm" onclick="_submitDeliverable(\''+projId+'\',this)">创建</button>'
    + '</div></div>';
  document.body.appendChild(modal);
  setTimeout(function(){ var el = document.getElementById('dv-title'); if (el) el.focus(); }, 0);
}
async function _submitDeliverable(projId, btn) {
  var title = (document.getElementById('dv-title').value||'').trim();
  if (!title) { alert('请输入标题'); return; }
  var author = document.getElementById('dv-author').value;
  if (author === '__user__') author = '';
  var urlVal = (document.getElementById('dv-url').value||'').trim();
  btn.disabled = true;
  await api('POST', '/api/portal/projects/'+projId+'/deliverables', {
    title: title,
    kind: document.getElementById('dv-kind').value,
    author_agent_id: author,
    content_text: (document.getElementById('dv-content').value||'').trim(),
    url: urlVal,
    file_path: urlVal.startsWith('http') ? '' : urlVal,
  });
  btn.closest('div[style*=fixed]').remove();
  loadProjectTabContent(projId, 'deliverables');
}
function submitDeliverable(projId, dvId) {
  api('POST', '/api/portal/projects/'+projId+'/deliverables/'+dvId+'/submit', {})
    .then(function(){ loadProjectTabContent(projId, 'deliverables'); });
}
function reviewDeliverable(projId, dvId, approved) {
  var label = approved ? '通过' : '驳回';
  var color = approved ? '#22c55e' : '#ef4444';
  var modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:20px;max-width:480px;width:94%">'
    + '<h3 style="margin:0 0 12px;color:'+color+'">审阅: '+label+'交付件</h3>'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">审阅意见</label>'
    + '<textarea id="review-comment" rows="3" style="'+_modalInputStyle+'" placeholder="'+(approved?'可选：通过意见':'请说明驳回原因，Agent 将收到通知并修订')+'"></textarea></div>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">'
    + '<button class="btn btn-sm" onclick="this.closest(\'div[style*=fixed]\').remove()">取消</button>'
    + '<button class="btn btn-primary btn-sm" style="background:'+color+'" onclick="_submitReview(\''+projId+'\',\''+dvId+'\','+approved+',this)">确认'+label+'</button>'
    + '</div></div>';
  document.body.appendChild(modal);
}
async function _submitReview(projId, dvId, approved, btn) {
  btn.disabled = true;
  await api('POST', '/api/portal/projects/'+projId+'/deliverables/'+dvId+'/review', {
    approved: approved,
    comment: (document.getElementById('review-comment').value||'').trim(),
  });
  btn.closest('div[style*=fixed]').remove();
  var active = (window._projectDetailTab && window._projectDetailTab[projId]) || 'deliverables';
  loadProjectTabContent(projId, active);
}
function deleteDeliverable(projId, dvId) {
  if (!confirm('删除此交付件？')) return;
  api('POST', '/api/portal/projects/'+projId+'/deliverables/'+dvId+'/delete', {})
    .then(function(){ loadProjectTabContent(projId, 'deliverables'); });
}

// ── Issue CRUD helpers ──
async function showAddIssueModal(projId) {
  var members = await _fetchProjectMembers(projId);
  var modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:20px;max-width:520px;width:94%">'
    + '<h3 style="margin:0 0 14px">新建问题</h3>'
    + '<div style="display:flex;flex-direction:column;gap:10px">'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">问题标题 *</label>'
    + '<input id="iss-title" style="'+_modalInputStyle+'" placeholder="简要描述问题"></div>'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">详细描述</label>'
    + '<textarea id="iss-desc" rows="3" style="'+_modalInputStyle+'" placeholder="问题的详细描述、复现步骤等"></textarea></div>'
    + '<div style="display:flex;gap:10px">'
    + '<div style="flex:1"><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">严重度</label>'
    + '<select id="iss-severity" style="'+_modalInputStyle+'">'
    + '<option value="low">低 (low)</option><option value="medium" selected>中 (medium)</option>'
    + '<option value="high">高 (high)</option><option value="critical">严重 (critical)</option></select></div>'
    + '<div style="flex:1"><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">报告人</label>'
    + '<select id="iss-reporter" style="'+_modalInputStyle+'">'
    + '<option value="__user__" selected>用户 (User)</option>'
    + (members||[]).map(function(m){ var aid=m.agent_id||''; var label=(m.agent_name||m.name||aid)+(m.role?' ('+m.role+')':''); return '<option value="'+esc(aid)+'">'+esc(label)+'</option>'; }).join('')
    + '</select></div>'
    + '</div>'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">指派责任人 Agent</label>'
    + '<select id="iss-assigned" style="'+_modalInputStyle+'">'+_memberOptions(members,'')+'</select>'
    + '<div style="font-size:10px;color:var(--text3);margin-top:2px">指派后该 Agent 将负责修复此问题</div></div>'
    + '</div>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">'
    + '<button class="btn btn-sm" onclick="this.closest(\'div[style*=fixed]\').remove()">取消</button>'
    + '<button class="btn btn-primary btn-sm" onclick="_submitIssue(\''+projId+'\',this)">创建</button>'
    + '</div></div>';
  document.body.appendChild(modal);
  setTimeout(function(){ var el = document.getElementById('iss-title'); if (el) el.focus(); }, 0);
}
async function _submitIssue(projId, btn) {
  var title = (document.getElementById('iss-title').value||'').trim();
  if (!title) { alert('请输入问题标题'); return; }
  var reporter = document.getElementById('iss-reporter').value;
  if (reporter === '__user__') reporter = 'user';
  var assigned = document.getElementById('iss-assigned').value;
  if (assigned === '__user__') assigned = '';
  btn.disabled = true;
  await api('POST', '/api/portal/projects/'+projId+'/issues', {
    title: title,
    description: (document.getElementById('iss-desc').value||'').trim(),
    severity: document.getElementById('iss-severity').value,
    reporter: reporter,
    assigned_to: assigned,
  });
  btn.closest('div[style*=fixed]').remove();
  loadProjectTabContent(projId, 'issues');
}
function resolveIssuePrompt(projId, issId) {
  var modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:20px;max-width:480px;width:94%">'
    + '<h3 style="margin:0 0 12px">标记问题已解决</h3>'
    + '<div><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">解决方案描述</label>'
    + '<textarea id="resolve-text" rows="3" style="'+_modalInputStyle+'" placeholder="描述解决方案"></textarea></div>'
    + '<div style="display:flex;gap:10px;margin-top:10px">'
    + '<div style="flex:1"><label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">状态</label>'
    + '<select id="resolve-status" style="'+_modalInputStyle+'">'
    + '<option value="resolved">已解决 (resolved)</option><option value="wontfix">不修复 (wontfix)</option></select></div></div>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">'
    + '<button class="btn btn-sm" onclick="this.closest(\'div[style*=fixed]\').remove()">取消</button>'
    + '<button class="btn btn-primary btn-sm" onclick="_submitResolve(\''+projId+'\',\''+issId+'\',this)">确认</button>'
    + '</div></div>';
  document.body.appendChild(modal);
}
async function _submitResolve(projId, issId, btn) {
  btn.disabled = true;
  await api('POST', '/api/portal/projects/'+projId+'/issues/'+issId+'/resolve', {
    resolution: (document.getElementById('resolve-text').value||'').trim(),
    status: document.getElementById('resolve-status').value,
  });
  btn.closest('div[style*=fixed]').remove();
  loadProjectTabContent(projId, 'issues');
}
function deleteIssue(projId, issId) {
  if (!confirm('删除此问题？')) return;
  api('POST', '/api/portal/projects/'+projId+'/issues/'+issId+'/delete', {})
    .then(function(){ loadProjectTabContent(projId, 'issues'); });
}

/* ── Rich content renderer for project chat ── */
function _renderRichContent(text) {
  var s = esc(text);
  // ── Markdown tables: | col | col | → <table>
  var lines = s.split('\n');
  var out = [], i = 0;
  while (i < lines.length) {
    // Detect table: line starts with |
    if (/^\|.+\|$/.test(lines[i].trim())) {
      var tableLines = [];
      while (i < lines.length && /^\|.+\|$/.test(lines[i].trim())) {
        tableLines.push(lines[i].trim());
        i++;
      }
      if (tableLines.length >= 2) {
        var thtml = '<div style="overflow-x:auto;margin:8px 0"><table style="border-collapse:collapse;font-size:12px;width:100%">';
        tableLines.forEach(function(row, ri) {
          // Skip separator row (|---|---|)
          if (/^\|[\s\-:]+\|$/.test(row)) return;
          var cells = row.split('|').filter(function(c,ci){ return ci > 0 && ci < row.split('|').length - 1; });
          var tag = ri === 0 ? 'th' : 'td';
          var bgStyle = ri === 0 ? 'background:rgba(203,201,255,0.1);font-weight:700' : '';
          thtml += '<tr>' + cells.map(function(c){
            return '<'+tag+' style="padding:6px 10px;border:1px solid rgba(255,255,255,0.1);text-align:left;'+bgStyle+'">'+c.trim()+'</'+tag+'>';
          }).join('') + '</tr>';
        });
        thtml += '</table></div>';
        out.push(thtml);
      } else {
        tableLines.forEach(function(l){ out.push(l); });
      }
      continue;
    }
    out.push(lines[i]);
    i++;
  }
  s = out.join('\n');
  // ── Code blocks: ```...``` → <pre><code>
  s = s.replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
    return '<pre style="background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:10px;margin:8px 0;overflow-x:auto;font-size:12px;font-family:monospace"><code>' + code + '</code></pre>';
  });
  // ── Inline code: `...`
  s = s.replace(/`([^`]+)`/g, '<code style="background:rgba(0,0,0,0.25);padding:1px 5px;border-radius:3px;font-size:12px;font-family:monospace">$1</code>');
  // ── Bold: **text** or __text__
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__(.+?)__/g, '<strong>$1</strong>');
  // ── Italic: *text* (not preceded by *)
  s = s.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');
  // ── Headings: # ## ###
  s = s.replace(/^### (.+)$/gm, '<div style="font-size:14px;font-weight:700;margin:8px 0 4px">$1</div>');
  s = s.replace(/^## (.+)$/gm, '<div style="font-size:15px;font-weight:700;margin:10px 0 4px">$1</div>');
  s = s.replace(/^# (.+)$/gm, '<div style="font-size:16px;font-weight:700;margin:12px 0 6px">$1</div>');
  // ── Bullet lists: - item or * item
  s = s.replace(/^[\-\*] (.+)$/gm, '<div style="padding-left:12px;position:relative"><span style="position:absolute;left:0">•</span> $1</div>');
  // ── Numbered lists: 1. item
  s = s.replace(/^(\d+)\. (.+)$/gm, '<div style="padding-left:16px;position:relative"><span style="position:absolute;left:0;color:var(--primary);font-weight:600">$1.</span> $2</div>');
  // ── Images: ![alt](url) → <img>, but DROP non-image extensions.
  // Matches the _renderSimpleMarkdown rule used in agent chat: a stray
  // ![foo.mp4](...) reference is silently dropped — the corresponding
  // FileCard will appear via the per-message `refs` enrichment, not as
  // a permanently broken <img> tag.
  s = s.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, function(_m, alt, src){
    var rawSrc = String(src || '').trim();
    var lower = rawSrc.toLowerCase().split('?')[0].split('#')[0];
    var imageExts = ['.png','.jpg','.jpeg','.gif','.svg','.webp','.bmp','.avif','.ico'];
    var isImage = false;
    for (var i = 0; i < imageExts.length; i++) {
      if (lower.endsWith(imageExts[i])) { isImage = true; break; }
    }
    if (!isImage && /^data:image\//i.test(rawSrc)) isImage = true;
    if (!isImage) return '';
    var safeAlt = String(alt || '').replace(/"/g, '&quot;');
    return '<div style="margin:8px 0"><img src="' + rawSrc + '" alt="' + safeAlt + '" style="max-width:100%;border-radius:8px;border:1px solid rgba(255,255,255,0.1)" onerror="this.style.display=\'none\'" /><div style="font-size:10px;color:var(--text3);margin-top:2px">' + safeAlt + '</div></div>';
  });
  // ── Links: [text](url)
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:var(--primary);text-decoration:underline">$1</a>');
  // ── Attachments: 📎filename.ext or [attachment:filename]
  s = s.replace(/📎(\S+)/g, '<span style="display:inline-flex;align-items:center;gap:4px;background:rgba(203,201,255,0.1);padding:3px 8px;border-radius:4px;font-size:11px;cursor:pointer"><span class="material-symbols-outlined" style="font-size:14px">attach_file</span>$1</span>');
  s = s.replace(/\[attachment:([^\]]+)\]/g, '<span style="display:inline-flex;align-items:center;gap:4px;background:rgba(203,201,255,0.1);padding:3px 8px;border-radius:4px;font-size:11px;cursor:pointer"><span class="material-symbols-outlined" style="font-size:14px">attach_file</span>$1</span>');
  // ── Audio: [audio:url] or 🎤 voice message
  s = s.replace(/\[audio:([^\]]+)\]/g, '<div style="margin:6px 0"><audio controls style="width:100%;max-width:300px;height:32px"><source src="$1"></audio></div>');
  // ── Horizontal rule: ---
  s = s.replace(/^---$/gm, '<hr style="border:none;border-top:1px solid rgba(255,255,255,0.1);margin:8px 0">');
  // ── Emojis: checkboxes ✅ 🔴 🟢
  // ── @mentions highlight
  s = s.replace(/@(\S+)/g, '<span style="color:var(--primary);font-weight:600;background:rgba(203,201,255,0.08);padding:0 3px;border-radius:3px">@$1</span>');
  // ── Newlines → <br> (for remaining plain text)
  s = s.replace(/\n/g, '<br>');
  return s;
}

async function loadProjectChat(projId) {
  try {
    var data = await api('GET', '/api/portal/projects/'+projId+'/chat?limit=200');
    var el = document.getElementById('project-chat-msgs-'+projId);
    if (!el) return;
    el.innerHTML = '';
    (data.messages||[]).forEach(function(m) {
      var isUser = m.sender === 'user';
      var div = document.createElement('div');
      div.style.cssText = 'max-width:85%;padding:12px 16px;border-radius:12px;font-size:13px;line-height:1.6;word-wrap:break-word;overflow-wrap:break-word;' +
        (isUser ? 'align-self:flex-end;background:linear-gradient(135deg,#1a2332,#243447);color:#e0e6ed;border:1px solid rgba(255,255,255,0.08);border-bottom-right-radius:4px' :
                  'align-self:flex-start;background:var(--surface);border:1px solid rgba(255,255,255,0.05);border-bottom-left-radius:4px');
      // 时间戳格式化
      var timeStr = '';
      if (m.timestamp) {
        var d = new Date(m.timestamp * 1000);
        timeStr = (d.getMonth()+1)+'/'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+':'+String(d.getSeconds()).padStart(2,'0');
      }
      var header = '';
      if (!isUser) {
        header = '<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">' +
          '<span style="font-size:10px;font-weight:700;color:var(--primary)">'+esc(m.sender_name||m.sender)+'</span>' +
          (timeStr ? '<span style="font-size:9px;color:var(--text3);opacity:0.6">'+timeStr+'</span>' : '') +
        '</div>';
      } else if (timeStr) {
        header = '<div style="text-align:right;margin-bottom:4px"><span style="font-size:9px;color:var(--text3);opacity:0.5">'+timeStr+'</span></div>';
      }
      var badge = m.msg_type === 'task_update' ? '<span style="font-size:9px;background:rgba(210,153,34,0.15);color:var(--warning);padding:1px 5px;border-radius:3px;margin-left:4px">TASK</span>' : '';
      div.innerHTML = header + badge + '<div class="rich-msg-body">' + _renderRichContent(m.content) + '</div>';
      // Per-message FileCards: backend has extracted local-path / URL
      // file references and attached them as `m.refs`. Reuse the same
      // _appendFileCards helper the agent chat uses, so the visual
      // shape and dedup behaviour stay consistent across surfaces.
      try {
        if (m.refs && m.refs.length) {
          // _appendFileCards expects a "msgDiv" with a child container
          // selectable as `.chat-file-cards`. Our project bubble doesn't
          // use the same selector, so create a wrapper that does.
          var cardHost = document.createElement('div');
          cardHost.className = 'chat-msg-content';
          div.appendChild(cardHost);
          _appendFileCards(cardHost, m.refs);
        }
      } catch(e) { console.log('[projectChat] file card attach failed', e); }
      el.appendChild(div);
    });
    el.scrollTop = el.scrollHeight;
  } catch(e) {}
}

// ── Chat attachments (P1 #3) ──
var _projAttachments = {};  // { [projId]: [{name, mime, size, data_base64, preview_url}] }

function _projAttachList(projId) {
  if (!_projAttachments[projId]) _projAttachments[projId] = [];
  return _projAttachments[projId];
}

function _renderProjAttachPreview(projId) {
  var box = document.getElementById('proj-attach-preview-'+projId);
  if (!box) return;
  var list = _projAttachList(projId);
  if (list.length === 0) { box.style.display = 'none'; box.innerHTML = ''; return; }
  box.style.display = 'flex';
  box.innerHTML = list.map(function(a, idx) {
    var thumb = '';
    if (a.preview_url) {
      thumb = '<img src="'+a.preview_url+'" style="width:36px;height:36px;object-fit:cover;border-radius:4px">';
    } else {
      thumb = '<span class="material-symbols-outlined" style="font-size:20px;color:var(--text3)">draft</span>';
    }
    var sizeKb = Math.max(1, Math.round((a.size||0)/1024));
    return '<div style="display:inline-flex;align-items:center;gap:6px;background:var(--surface);border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:4px 8px;font-size:11px;color:var(--text)">' +
             thumb +
             '<div style="display:flex;flex-direction:column;max-width:140px">' +
               '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(a.name)+'</span>' +
               '<span style="color:var(--text3);font-size:10px">'+sizeKb+' KB</span>' +
             '</div>' +
             '<button onclick="removeProjAttach(\''+projId+'\','+idx+')" title="Remove" style="background:none;border:none;color:var(--text3);cursor:pointer;padding:2px"><span class="material-symbols-outlined" style="font-size:14px">close</span></button>' +
           '</div>';
  }).join('');
}

function removeProjAttach(projId, idx) {
  var list = _projAttachList(projId);
  if (idx >= 0 && idx < list.length) {
    list.splice(idx, 1);
    _renderProjAttachPreview(projId);
  }
}

function handleProjAttach(projId, fileInput) {
  if (!fileInput || !fileInput.files || fileInput.files.length === 0) return;
  var list = _projAttachList(projId);
  var MAX = 10;
  var MAX_SIZE = 10 * 1024 * 1024;  // 10 MB per file
  var remaining = MAX - list.length;
  var files = Array.prototype.slice.call(fileInput.files, 0, Math.max(0, remaining));
  files.forEach(function(f) {
    if (f.size > MAX_SIZE) {
      alert('File "'+f.name+'" exceeds 10 MB and was skipped.');
      return;
    }
    var reader = new FileReader();
    reader.onload = function(e) {
      var dataUrl = e.target.result || '';
      var b64 = dataUrl.indexOf(',') >= 0 ? dataUrl.split(',')[1] : dataUrl;
      var isImage = (f.type || '').indexOf('image/') === 0;
      list.push({
        name: f.name,
        mime: f.type || 'application/octet-stream',
        size: f.size,
        data_base64: b64,
        preview_url: isImage ? dataUrl : '',
      });
      _renderProjAttachPreview(projId);
    };
    reader.readAsDataURL(f);
  });
  fileInput.value = '';  // allow re-picking the same file
}

var _projectChatPoll = null;
async function sendProjectMsg(projId) {
  var input = document.getElementById('project-chat-input-'+projId);
  if (!input) return;
  var text = input.value.trim();
  var attachments = _projAttachList(projId).slice();
  if (!text && attachments.length === 0) return;
  input.value = '';
  // Clear pending attachments immediately (we captured a snapshot above)
  _projAttachments[projId] = [];
  _renderProjAttachPreview(projId);
  // Add user bubble immediately
  var el = document.getElementById('project-chat-msgs-'+projId);
  if (el) {
    var div = document.createElement('div');
    div.style.cssText = 'max-width:80%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word;align-self:flex-end;background:linear-gradient(135deg,#1a2332,#243447);color:#e0e6ed;border:1px solid rgba(255,255,255,0.08);border-bottom-right-radius:4px';
    div.textContent = text;
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
  }
  // Send to backend
  try {
    // Parse @mentions to extract target agents
    var mentionedAgents = [];
    var mentionRegex = /@(\S+)/g;
    var match;
    while ((match = mentionRegex.exec(text)) !== null) {
      var mentioned = match[1];
      // Match against agent names or role-name patterns
      var found = agents.find(function(a) {
        return a.name === mentioned || (a.role+'-'+a.name) === mentioned || a.id === mentioned;
      });
      if (found && mentionedAgents.indexOf(found.id) < 0) mentionedAgents.push(found.id);
    }
    var chatBody = {content: text};
    if (mentionedAgents.length > 0) chatBody.target_agents = mentionedAgents;
    if (attachments.length > 0) {
      chatBody.attachments = attachments.map(function(a){
        return {name: a.name, mime: a.mime, size: a.size, data_base64: a.data_base64};
      });
    }
    await api('POST', '/api/portal/projects/'+projId+'/chat', chatBody);
    // Poll for new messages periodically while agents respond
    if (_projectChatPoll) clearInterval(_projectChatPoll);
    var pollCount = 0;
    _projectChatPoll = setInterval(function() {
      loadProjectChat(projId);
      pollCount++;
      if (pollCount > 30) clearInterval(_projectChatPoll);  // Stop after 30 polls (~1min)
    }, 2000);
  } catch(e) { alert('Send failed: '+e.message); }
}

async function editProject(projId, currentName, currentDesc) {
  // 获取项目详情和可用 workflow 模板
  var proj = await api('GET', '/api/portal/projects/'+projId);
  var tmplData = [];
  try {
    var td = await api('GET', '/api/portal/workflows');
    // 只取模板（status=template）
    tmplData = (td.workflows || []).filter(function(w){ return w.status === 'template'; });
  } catch(e) {}

  var currentWfId = (proj.workflow_binding && proj.workflow_binding.workflow_id) || '';
  var currentAssignments = (proj.workflow_binding && proj.workflow_binding.step_assignments) || [];

  // 构建模态弹窗
  var overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:9999;display:flex;align-items:center;justify-content:center';
  overlay.onclick = function(e){ if(e.target===overlay) overlay.remove(); };

  var wfOptions = '<option value="">— 不绑定 Workflow —</option>' +
    tmplData.map(function(t){ return '<option value="'+t.id+'"'+(t.id===currentWfId?' selected':'')+'>'+esc(t.name)+' ('+((t.steps||[]).length)+' steps)</option>'; }).join('');

  var box = document.createElement('div');
  box.style.cssText = 'background:var(--bg);border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:24px;width:520px;max-height:80vh;overflow-y:auto;color:var(--text)';
  box.innerHTML =
    '<div style="font-size:16px;font-weight:700;margin-bottom:16px">编辑项目</div>' +
    '<label style="font-size:12px;color:var(--text3)">项目名称</label>' +
    '<input id="ep-name" type="text" value="'+esc(proj.name).replace(/"/g,'&quot;')+'" style="width:100%;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:8px 10px;color:var(--text);font-size:13px;margin:4px 0 12px">' +
    '<label style="font-size:12px;color:var(--text3)">项目描述</label>' +
    '<textarea id="ep-desc" rows="2" style="width:100%;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:8px 10px;color:var(--text);font-size:13px;margin:4px 0 12px;resize:vertical">'+esc(proj.description||'')+'</textarea>' +
    '<label style="font-size:12px;color:var(--text3)">绑定 Workflow</label>' +
    '<select id="ep-workflow" style="width:100%;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:8px 10px;color:var(--text);font-size:13px;margin:4px 0 12px">'+wfOptions+'</select>' +
    '<div id="ep-step-assignments" style="margin-bottom:16px"></div>' +
    '<div style="display:flex;justify-content:flex-end;gap:8px">' +
      '<button class="btn btn-ghost btn-sm" onclick="this.closest(\'div[style*=fixed]\').remove()">取消</button>' +
      '<button class="btn btn-primary btn-sm" id="ep-save-btn">保存</button>' +
    '</div>';

  overlay.appendChild(box);
  document.body.appendChild(overlay);

  // 当 workflow 选择变化时渲染 step → agent 分配表
  var wfSelect = document.getElementById('ep-workflow');
  function renderStepAssignments() {
    var container = document.getElementById('ep-step-assignments');
    var selWfId = wfSelect.value;
    if (!selWfId) { container.innerHTML = ''; return; }
    var tmpl = tmplData.find(function(t){ return t.id === selWfId; });
    if (!tmpl) { container.innerHTML = ''; return; }
    var steps = tmpl.steps || [];
    var agentOpts = '<option value="">— 未分配 —</option>' +
      agents.map(function(a){ return '<option value="'+a.id+'">'+esc(a.name)+'</option>'; }).join('');
    container.innerHTML = '<div style="font-size:12px;color:var(--text3);margin-bottom:6px">步骤 → Agent 分配（☑ = 该步骤启动前需人工批准）</div>' +
      steps.map(function(s, i) {
        // 尝试回填当前分配
        var curAgent = '';
        var curApproval = false;
        if (selWfId === currentWfId) {
          var ca = currentAssignments.find(function(a){ return a.step_index === i; });
          if (ca) { curAgent = ca.agent_id; curApproval = !!ca.require_approval; }
        }
        var opts = agentOpts.replace('value="'+curAgent+'"', 'value="'+curAgent+'" selected');
        return '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
          '<span style="font-size:11px;color:var(--text);min-width:120px;font-weight:600">Step '+(i+1)+': '+esc(s.name||'')+'</span>' +
          '<select class="ep-agent-sel" data-step="'+i+'" style="flex:1;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:6px 8px;color:var(--text);font-size:12px">'+opts+'</select>' +
          '<label title="启动前需人工批准" style="display:flex;align-items:center;gap:4px;font-size:10px;color:var(--text3);cursor:pointer;white-space:nowrap">' +
            '<input type="checkbox" class="ep-approval-chk" data-step="'+i+'"'+(curApproval?' checked':'')+' style="cursor:pointer">审核' +
          '</label>' +
        '</div>';
      }).join('');
  }
  wfSelect.onchange = renderStepAssignments;
  renderStepAssignments();

  // 保存
  document.getElementById('ep-save-btn').onclick = async function() {
    var name = document.getElementById('ep-name').value.trim();
    var desc = document.getElementById('ep-desc').value.trim();
    var wfId = wfSelect.value;
    var stepAssignments = [];
    var approvalMap = {};
    document.querySelectorAll('.ep-approval-chk').forEach(function(chk){
      approvalMap[parseInt(chk.getAttribute('data-step'))] = chk.checked;
    });
    document.querySelectorAll('.ep-agent-sel').forEach(function(sel){
      var idx = parseInt(sel.getAttribute('data-step'));
      var aid = sel.value;
      if (aid) stepAssignments.push({
        step_index: idx, agent_id: aid,
        require_approval: !!approvalMap[idx],
      });
    });
    var payload = {action:'update', project_id:projId, name:name, description:desc};
    // 只有选择了 workflow 或者显式清除时才传
    if (wfId !== currentWfId || stepAssignments.length > 0) {
      payload.workflow_id = wfId;
      payload.step_assignments = stepAssignments;
    }
    await api('POST', '/api/portal/projects', payload);
    overlay.remove();
    renderCurrentView();
  };
}

async function toggleWfStep(projId, taskId, newStatus) {
  try {
    await api('POST', '/api/portal/projects/'+projId+'/task-update', {task_id: taskId, status: newStatus});
    renderProjectDetail(projId);
  } catch(e) { alert('更新失败: '+e.message); }
}

async function approveWfStep(projId, taskId) {
  if (!confirm('确认批准该步骤启动？\n批准后将立即唤醒负责 Agent 开始执行。')) return;
  try {
    await api('POST', '/api/portal/projects/'+projId+'/tasks/'+taskId+'/approve-step', {});
    renderProjectDetail(projId);
  } catch(e) { alert('批准失败: '+e.message); }
}

async function deleteProject(projId) {
  if (!confirm('确定要删除这个项目吗？所有聊天记录和任务将丢失。')) return;
  await api('POST', '/api/portal/projects', {action:'delete', project_id:projId});
  currentView = 'projects';
  renderCurrentView();
}

async function deleteProjectTask(projId, taskId) {
  if (!confirm('确定要删除这个任务吗？')) return;
  await api('POST', '/api/portal/projects/'+projId+'/task-update', {task_id:taskId, status:'deleted'});
  renderProjectDetail(projId);
}

// ── Task step editor (with manual_review checkbox) ──
async function editTaskSteps(projId, taskId) {
  // Fetch current task to load existing steps
  var proj = null;
  try {
    proj = await api('GET', '/api/portal/projects/'+projId);
  } catch(e) { alert('Load project failed: '+e.message); return; }
  var task = (proj.tasks||[]).find(function(t){ return t.id === taskId; });
  if (!task) { alert('Task not found'); return; }
  var existing = (task.steps||[]).map(function(s){
    return { name: s.name, manual_review: !!s.manual_review, _locked: s.status === 'done' || s.status === 'awaiting_review' };
  });

  // Build modal
  var overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:9999;display:flex;align-items:center;justify-content:center';
  var modal = document.createElement('div');
  modal.style.cssText = 'background:var(--surface);border:1px solid var(--border-light);border-radius:12px;padding:20px;width:min(560px,90vw);max-height:80vh;overflow-y:auto;font-family:inherit';
  function rowHtml(idx, name, mr, locked) {
    var lockNote = locked ? '<span style="font-size:10px;color:var(--text3);margin-left:6px">(已完成/审核中，不可修改)</span>' : '';
    return '<div data-row="'+idx+'" style="display:flex;align-items:center;gap:8px;margin-bottom:8px;padding:8px;background:var(--surface2);border-radius:6px">' +
      '<span style="color:var(--text3);font-size:12px;width:18px">'+(idx+1)+'.</span>' +
      '<input type="text" data-step-name value="'+esc(name).replace(/"/g,'&quot;')+'" '+(locked?'readonly':'')+' style="flex:1;background:var(--surface);color:var(--text);border:1px solid rgba(255,255,255,0.1);border-radius:4px;padding:6px 8px;font-size:13px" placeholder="步骤名称">' +
      '<label style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--text2);white-space:nowrap;cursor:pointer">' +
        '<input type="checkbox" data-step-review '+(mr?'checked':'')+' '+(locked?'disabled':'')+' style="cursor:pointer">人工审核' +
      '</label>' +
      (locked ? '' : '<button onclick="this.closest(\'[data-row]\').remove()" style="background:transparent;color:#ef4444;border:none;cursor:pointer;font-size:14px">✕</button>') +
      lockNote +
    '</div>';
  }
  var html = '<div style="font-size:16px;font-weight:700;margin-bottom:6px">编辑任务步骤</div>' +
    '<div style="font-size:11px;color:var(--text3);margin-bottom:14px">勾选「人工审核」后，agent 完成该 step 时只会产出草稿，必须由你点击「通过」才能继续后续步骤。</div>' +
    '<div id="step-rows-container">' +
      (existing.length === 0 ? '' : existing.map(function(s, i){ return rowHtml(i, s.name, s.manual_review, s._locked); }).join('')) +
    '</div>' +
    '<button id="add-step-btn" style="background:transparent;color:var(--primary);border:1px dashed var(--primary);border-radius:6px;padding:6px 12px;cursor:pointer;font-size:12px;margin-bottom:12px">+ 添加步骤</button>' +
    '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">' +
      '<button id="cancel-step-btn" class="btn btn-ghost" style="font-size:12px">取消</button>' +
      '<button id="save-step-btn" class="btn btn-primary" style="font-size:12px">保存</button>' +
    '</div>';
  modal.innerHTML = html;
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  function nextIdx() {
    return modal.querySelectorAll('[data-row]').length;
  }
  modal.querySelector('#add-step-btn').onclick = function(){
    var i = nextIdx();
    var tmp = document.createElement('div');
    tmp.innerHTML = rowHtml(i, '', false, false);
    modal.querySelector('#step-rows-container').appendChild(tmp.firstChild);
  };
  modal.querySelector('#cancel-step-btn').onclick = function(){ document.body.removeChild(overlay); };
  modal.querySelector('#save-step-btn').onclick = async function(){
    var rows = modal.querySelectorAll('[data-row]');
    var steps = [];
    for (var i = 0; i < rows.length; i++) {
      var nameEl = rows[i].querySelector('[data-step-name]');
      var mrEl = rows[i].querySelector('[data-step-review]');
      var n = (nameEl.value || '').trim();
      if (!n) continue;
      steps.push({ name: n, manual_review: !!mrEl.checked });
    }
    if (steps.length === 0) {
      if (!confirm('未填写任何步骤，将清空当前任务的所有 step（task 退化为单次执行）。继续？')) return;
    }
    try {
      await api('POST', '/api/portal/projects/'+projId+'/task-steps', {
        task_id: taskId, steps: steps,
      });
      document.body.removeChild(overlay);
      renderProjectDetail(projId);
    } catch(e) { alert('保存失败: '+e.message); }
  };
}

// ── Manual review action: approve / reject an awaiting_review step ──
async function reviewStep(projId, taskId, stepId, action) {
  var body = { task_id: taskId, step_id: stepId, action: action };
  if (action === 'reject') {
    var reason = prompt('驳回原因（可选，会作为提示传给 agent 重新执行）:', '');
    if (reason === null) return;
    body.reason = reason;
  } else {
    var override = prompt('确认通过这个 step。\n如需修改 agent 的草稿结果，请在下方编辑（留空保持原样）:', '');
    if (override === null) return;
    if (override) body.result = override;
  }
  try {
    await api('POST', '/api/portal/projects/'+projId+'/task-step-review', body);
    // Refresh whichever view we're in
    if (currentView === 'dashboard') {
      renderDashboard();
    } else {
      renderProjectDetail(projId);
    }
  } catch(e) { alert('审核失败: '+e.message); }
}

async function pauseProject(projId) {
  var reason = prompt('暂停原因（可选）:', '') || '';
  await api('POST', '/api/portal/projects/'+projId+'/pause', {reason:reason});
  renderProjectDetail(projId);
}

async function resumeProject(projId) {
  var r = await api('POST', '/api/portal/projects/'+projId+'/resume', {});
  if (r && r.replayed) {
    console.log('恢复后已回放', r.replayed, '条暂停期间消息');
  }
  renderProjectDetail(projId);
}

async function changeProjectStatus(projId, newStatus) {
  console.log('[changeProjectStatus]', projId, '->', newStatus);
  var labelMap = {
    planning: '未开始', active: '进行中', suspended: '挂起',
    cancelled: '停止', completed: '结束', archived: '归档',
  };
  var label = labelMap[newStatus] || newStatus;
  var needReason = (newStatus === 'cancelled' || newStatus === 'suspended' || newStatus === 'completed');
  var reason = '';
  if (needReason) {
    var r1 = prompt('请输入『' + label + '』的原因（可留空，回车即可）:', '');
    if (r1 === null) return;  // user cancelled
    reason = r1;
  } else {
    if (!confirm('确认将项目状态变更为『' + label + '』?')) return;
  }
  try {
    var r = await api('POST', '/api/portal/projects/'+projId+'/status', {status:newStatus, reason:reason});
    console.log('[changeProjectStatus] response', r);
    if (!r) {
      alert('变更失败: 空响应，请检查服务器日志');
      return;
    }
    if (r.error) {
      alert('变更失败: ' + r.error);
      return;
    }
    if (currentView === 'project_detail') {
      renderProjectDetail(projId);
    } else {
      renderProjects();
    }
  } catch(e) {
    console.error('[changeProjectStatus] error', e);
    alert('变更失败: ' + e);
  }
}

async function confirmMilestone(projId, msId) {
  await api('POST', '/api/portal/projects/'+projId+'/milestones/'+msId+'/confirm', {});
  renderProjectDetail(projId);
}

async function rejectMilestone(projId, msId) {
  var reason = prompt('驳回原因:', '') || '';
  await api('POST', '/api/portal/projects/'+projId+'/milestones/'+msId+'/reject', {reason:reason});
  renderProjectDetail(projId);
