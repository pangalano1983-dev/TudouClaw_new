}

// ============ Scheduler Panel ============
async function renderScheduler() {
  const content = document.getElementById('content');
  content.style.padding = '24px';
  // Inline header with title + action button (top-right) — matches other tabs
  const schedHeader = ''
    + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">'
    + '  <div><h2 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:22px;font-weight:800;margin:0">定时任务</h2>'
    + '    <p style="font-size:12px;color:var(--text3);margin-top:4px">Scheduled Jobs · 按 cron 或间隔自动触发 agent</p></div>'
    + '  <button class="btn btn-primary btn-sm" onclick="showCreateJob()"><span class="material-symbols-outlined" style="font-size:14px">add</span> New Job</button>'
    + '</div>';
  content.innerHTML = schedHeader + '<div style="color:var(--text3);padding:20px">Loading scheduled tasks...</div>';
  let jobsData, presetsData, agentsData;
  try {
    [jobsData, presetsData, agentsData] = await Promise.all([
      api('GET', '/api/portal/scheduler/jobs'),
      api('GET', '/api/portal/scheduler/presets'),
      api('GET', '/api/portal/agents'),
    ]);
  } catch(e) {
    content.innerHTML = schedHeader + '<div style="color:var(--error);padding:20px">Failed to load scheduler: '+(e && e.message || e)+'</div>';
    return;
  }
  const jobs = (jobsData && jobsData.jobs) || [];
  const presets = (presetsData && presetsData.presets) || {};
  const agents = (agentsData && agentsData.agents) || [];

  let html = schedHeader + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:16px">';

  if (jobs.length === 0) {
    html += '<div class="card" style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted)">';
    html += '<span class="material-symbols-outlined" style="font-size:48px;display:block;margin-bottom:8px">schedule</span>';
    html += '<p>No scheduled jobs yet</p>';
    html += '<p style="font-size:12px">Create one from presets or manually</p>';
    html += '<div style="margin-top:16px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap">';
    Object.entries(presets).forEach(([k,v]) => {
      html += '<button class="btn btn-sm" onclick="createFromPreset(\''+k+'\')">'+v.name+'</button>';
    });
    html += '</div></div>';
  }

  jobs.forEach(job => {
    const agentName = (agents.find(a=>a.id===job.agent_id)||{}).name||job.agent_id;
    const statusIcon = job.enabled ? (job.last_status==='success'?'check_circle':job.last_status==='failed'?'error':'pending') : 'pause_circle';
    const statusColor = job.enabled ? (job.last_status==='success'?'var(--success)':job.last_status==='failed'?'var(--danger)':'var(--muted)') : 'var(--muted)';
    const nextRun = job.next_run_at ? new Date(job.next_run_at*1000).toLocaleString() : '-';
    const lastRun = job.last_run_at ? new Date(job.last_run_at*1000).toLocaleString() : 'Never';

    html += '<div class="card" style="position:relative">';
    html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">';
    html += '<span class="material-symbols-outlined" style="color:'+statusColor+'">'+statusIcon+'</span>';
    html += '<strong style="flex:1">'+job.name+'</strong>';
    html += '<span class="badge badge-primary" style="font-size:11px">'+job.job_type+'</span>';
    html += '</div>';
    html += '<div style="font-size:12px;color:var(--muted);margin-bottom:8px">'+(job.description||'No description')+'</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:12px">';
    html += '<div><strong>Agent:</strong> '+agentName+'</div>';
    html += '<div><strong>Cron:</strong> <code>'+(job.cron_expr||'one-time')+'</code></div>';
    html += '<div><strong>Next:</strong> '+nextRun+'</div>';
    html += '<div><strong>Last:</strong> '+lastRun+'</div>';
    html += '<div><strong>Runs:</strong> '+job.run_count+(job.max_runs?' / '+job.max_runs:'')+'</div>';
    html += '<div><strong>Timeout:</strong> '+job.timeout+'s</div>';
    html += '</div>';
    if (job.tags && job.tags.length) {
      html += '<div style="margin-top:6px">';
      job.tags.forEach(t => html += '<span class="badge" style="font-size:10px;margin-right:4px">'+t+'</span>');
      html += '</div>';
    }
    html += '<div style="display:flex;gap:6px;margin-top:12px;border-top:1px solid var(--border);padding-top:10px">';
    html += '<button class="btn btn-sm btn-primary" onclick="triggerJob(\''+job.id+'\')"><span class="material-symbols-outlined" style="font-size:14px">play_arrow</span> Run Now</button>';
    html += '<button class="btn btn-sm" onclick="toggleJob(\''+job.id+'\','+(!job.enabled)+')">'+(job.enabled?'Pause':'Resume')+'</button>';
    html += '<button class="btn btn-sm" onclick="viewJobHistory(\''+job.id+'\')">History</button>';
    html += '<button class="btn btn-sm" style="margin-left:auto;color:var(--danger)" onclick="deleteJob(\''+job.id+'\')">Delete</button>';
    html += '</div></div>';
  });
  html += '</div>';
  content.innerHTML = html;
}

async function showCreateJob() {
  const [agentsData, presetsData, workflowsData] = await Promise.all([
    api('GET', '/api/portal/agents'),
    api('GET', '/api/portal/scheduler/presets'),
    api('GET', '/api/portal/workflows').catch(function(){ return {workflows:[]}; }),
  ]);
  const agents = agentsData.agents || [];
  const presets = presetsData.presets || {};
  // /api/portal/workflows returns mixed templates + instances. Templates
  // have a "steps" array but no "instance_id" / no terminal status; we
  // include anything with an id + name and let the user pick.
  const allWfs = (workflowsData && workflowsData.workflows) || [];
  const templates = allWfs.filter(function(w){
    // Heuristic: skip running/completed instances; keep entries with no
    // instance-only fields ("status" == "draft" or absent)
    var st = (w.status || '').toLowerCase();
    return !st || st === 'draft' || st === 'template';
  });

  let presetOpts = '<option value="">-- Custom --</option>';
  Object.entries(presets).forEach(([k,v]) => {
    presetOpts += '<option value="'+k+'">'+v.name+'</option>';
  });
  let agentOpts = agents.map(a => '<option value="'+a.id+'">'+a.name+' ('+a.role+')</option>').join('');
  let wfOpts = '<option value="">-- select workflow template --</option>' +
    templates.map(function(w){
      return '<option value="'+esc(w.id||w.template_id||'')+'">'+esc(w.name||'(unnamed)')+'</option>';
    }).join('');

  const html = '<div style="padding:20px;max-width:600px">' +
    '<h3 style="margin-bottom:16px">Create Scheduled Job</h3>' +
    '<label>Preset</label><select id="job-preset" onchange="applyJobPreset(this.value)" class="input" style="margin-bottom:8px">'+presetOpts+'</select>' +
    '<label>Target Type</label><select id="job-target-type" class="input" style="margin-bottom:8px" onchange="_jobTargetTypeChanged()">' +
      '<option value="chat">Agent Chat — call agent.chat with prompt</option>' +
      '<option value="workflow">Workflow — run a workflow template</option>' +
    '</select>' +
    '<div id="job-workflow-row" style="display:none;margin-bottom:8px">' +
      '<label>Workflow Template</label>' +
      '<select id="job-workflow-id" class="input" onchange="_jobWorkflowChanged()">'+wfOpts+'</select>' +
      '<div style="font-size:11px;color:var(--muted);margin-top:4px">' +
        'If step assignments are not provided below, every step will run as the selected default agent.' +
      '</div>' +
      '<div id="job-step-assignments" style="margin-top:8px"></div>' +
    '</div>' +
    '<label id="job-agent-label">Agent</label><select id="job-agent" class="input" style="margin-bottom:8px"><option value="">-- none --</option>'+agentOpts+'</select>' +
    '<label>Name</label><input id="job-name" class="input" style="margin-bottom:8px" placeholder="Daily AIGC Digest">' +
    '<label>Type</label><select id="job-type" class="input" style="margin-bottom:8px"><option value="recurring">Recurring (Cron)</option><option value="one_time">One Time</option></select>' +
    '<label>Cron Expression</label><input id="job-cron" class="input" style="margin-bottom:8px" placeholder="0 9 * * *">' +
    '<div style="font-size:11px;color:var(--muted);margin-bottom:8px">minute hour day month weekday (e.g. 0 9 * * 1-5 = weekdays 9am)</div>' +
    '<label id="job-prompt-label">Prompt Template</label><textarea id="job-prompt" class="input" rows="4" style="margin-bottom:8px" placeholder="Use {date}, {time}, {weekday} variables..."></textarea>' +
    '<label>Notify Channels (comma-separated IDs)</label><input id="job-channels" class="input" style="margin-bottom:8px">' +
    '<label>Tags (comma-separated)</label><input id="job-tags" class="input" style="margin-bottom:16px">' +
    '<div style="display:flex;gap:8px"><button class="btn btn-primary" onclick="saveNewJob()">Create</button>' +
    '<button class="btn" onclick="closeModal()">Cancel</button></div></div>';
  showModalHTML(html);
  // Store templates + agent options for step assignment rendering
  window._jobWfTemplates = templates;
  window._jobAgentOpts = agentOpts;
}

function _jobTargetTypeChanged() {
  var t = document.getElementById('job-target-type').value;
  var row = document.getElementById('job-workflow-row');
  var label = document.getElementById('job-agent-label');
  var promptLabel = document.getElementById('job-prompt-label');
  var promptEl = document.getElementById('job-prompt');
  if (t === 'workflow') {
    if (row) row.style.display = 'block';
    if (label) label.textContent = 'Default Agent (used for unassigned workflow steps)';
    if (promptLabel) promptLabel.textContent = 'Workflow Input (passed as input_data)';
    if (promptEl) promptEl.placeholder = 'Initial input passed to the workflow. Optional — leave empty to use job name.';
  } else {
    if (row) row.style.display = 'none';
    if (label) label.textContent = 'Agent';
    if (promptLabel) promptLabel.textContent = 'Prompt Template';
    if (promptEl) promptEl.placeholder = 'Use {date}, {time}, {weekday} variables...';
  }
}

function _jobWorkflowChanged() {
  var container = document.getElementById('job-step-assignments');
  if (!container) return;
  var wfId = document.getElementById('job-workflow-id').value;
  if (!wfId) { container.innerHTML = ''; return; }
  var templates = window._jobWfTemplates || [];
  var tmpl = templates.find(function(t){ return (t.id||t.template_id) === wfId; });
  if (!tmpl || !tmpl.steps || !tmpl.steps.length) {
    container.innerHTML = '<div style="font-size:11px;color:var(--muted)">该模板没有定义步骤</div>';
    return;
  }
  var agentOpts = window._jobAgentOpts || '';
  var stepRows = tmpl.steps.map(function(s, i) {
    return '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
      '<span style="font-size:11px;color:var(--text);min-width:140px;font-weight:600">Step '+(i+1)+': '+esc(s.name||s.title||'')+'</span>' +
      '<select class="job-step-agent input" data-step="'+i+'" style="flex:1;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:6px 8px;color:var(--text);font-size:12px">' +
        '<option value="">— 使用默认 Agent —</option>' + agentOpts +
      '</select>' +
      '<label title="启动前需人工批准" style="display:flex;align-items:center;gap:4px;font-size:10px;color:var(--text3);cursor:pointer;white-space:nowrap">' +
        '<input type="checkbox" class="job-step-approval" data-step="'+i+'" style="cursor:pointer">审核' +
      '</label>' +
    '</div>';
  }).join('');
  container.innerHTML =
    '<div style="font-size:12px;color:var(--text3);margin-bottom:6px;font-weight:600">步骤 → Agent 分配（未分配的步骤将使用默认 Agent）</div>' +
    stepRows;
}

function applyJobPreset(presetId) {
  if (!presetId) return;
  api('GET', '/api/portal/scheduler/presets').then(data => {
    const p = (data.presets||{})[presetId];
    if (!p) return;
    document.getElementById('job-name').value = p.name || '';
    document.getElementById('job-cron').value = p.cron_expr || '';
    document.getElementById('job-prompt').value = p.prompt_template || '';
    document.getElementById('job-type').value = p.job_type || 'recurring';
    document.getElementById('job-tags').value = (p.tags||[]).join(', ');
  });
}

async function saveNewJob() {
  const preset = document.getElementById('job-preset').value;
  const targetTypeEl = document.getElementById('job-target-type');
  const targetType = targetTypeEl ? targetTypeEl.value : 'chat';
  const body = {
    action: 'create',
    agent_id: document.getElementById('job-agent').value,
    name: document.getElementById('job-name').value,
    job_type: document.getElementById('job-type').value,
    cron_expr: document.getElementById('job-cron').value,
    prompt_template: document.getElementById('job-prompt').value,
    notify_channels: document.getElementById('job-channels').value.split(',').map(s=>s.trim()).filter(Boolean),
    tags: document.getElementById('job-tags').value.split(',').map(s=>s.trim()).filter(Boolean),
    target_type: targetType,
  };
  if (targetType === 'workflow') {
    var wfEl = document.getElementById('job-workflow-id');
    body.workflow_id = wfEl ? wfEl.value : '';
    if (!body.workflow_id) {
      alert('Please select a workflow template.');
      return;
    }
    // The prompt textarea is repurposed as workflow input in workflow mode.
    body.workflow_input = body.prompt_template;
    body.prompt_template = '';
    // Collect per-step agent assignments
    var stepAssignments = [];
    var approvalMap = {};
    document.querySelectorAll('.job-step-approval').forEach(function(chk){
      approvalMap[parseInt(chk.getAttribute('data-step'))] = chk.checked;
    });
    document.querySelectorAll('.job-step-agent').forEach(function(sel){
      var idx = parseInt(sel.getAttribute('data-step'));
      var aid = sel.value;
      if (aid) stepAssignments.push({
        step_index: idx, agent_id: aid,
        require_approval: !!approvalMap[idx],
      });
    });
    if (stepAssignments.length > 0) {
      body.workflow_step_assignments = stepAssignments;
    }
  }
  if (preset) body.preset_id = preset;
  await api('POST', '/api/portal/scheduler/jobs', body);
  closeModal();
  _refreshSchedulerView();
}

async function createFromPreset(presetId) {
  await showCreateJob();
  document.getElementById('job-preset').value = presetId;
  applyJobPreset(presetId);
}

async function triggerJob(jobId) {
  try {
    var res = await api('POST', '/api/portal/scheduler/jobs', {action:'trigger', job_id:jobId});
    if (res.ok) {
      alert('✅ Job triggered — agent正在后台执行...');
      setTimeout(function(){ _refreshSchedulerView(); }, 3000);
      setTimeout(function(){ _refreshSchedulerView(); }, 8000);
      setTimeout(function(){ _refreshSchedulerView(); }, 15000);
    } else {
      alert('❌ Trigger failed: job not found');
    }
  } catch(e) {
    alert('❌ Trigger error: '+e.message);
  }
  _refreshSchedulerView();
}

// Refresh whichever view is currently showing scheduled jobs.
// Task Center now hosts the canonical view; renderScheduler() is kept
// only for any direct deep-link callers (it falls back to Task Center).
function _refreshSchedulerView() {
  if (document.getElementById('tc-content')) {
    loadTaskCenter();
  } else if (typeof renderScheduler === 'function') {
    try { renderScheduler(); } catch(e) {}
  }
}

async function toggleJob(jobId, enabled) {
  await api('POST', '/api/portal/scheduler/jobs', {action:'toggle', job_id:jobId, enabled});
  _refreshSchedulerView();
}

async function deleteJob(jobId) {
  if (!confirm('Delete this scheduled job?')) return;
  await api('POST', '/api/portal/scheduler/jobs', {action:'delete', job_id:jobId});
  renderScheduler();
}

async function viewJobHistory(jobId) {
  const data = await api('GET', '/api/portal/scheduler/jobs/'+jobId+'/history');
  const records = data.history || [];
  let html = '<div style="padding:20px;max-width:700px"><h3>Execution History</h3>';
  if (records.length === 0) {
    html += '<p style="color:var(--muted)">No executions yet</p>';
  } else {
    html += '<table class="table" style="font-size:12px"><thead><tr><th>Time</th><th>Status</th><th>Duration</th><th>Result</th></tr></thead><tbody>';
    records.forEach(r => {
      const started = new Date(r.started_at*1000).toLocaleString();
      const dur = r.completed_at ? ((r.completed_at - r.started_at).toFixed(1)+'s') : 'running';
      const statusBadge = r.status==='success'?'badge-primary':r.status==='failed'?'badge badge-danger':'badge';
      html += '<tr><td>'+started+'</td><td><span class="badge '+statusBadge+'">'+r.status+'</span></td><td>'+dur+'</td><td style="max-width:300px;overflow:hidden;text-overflow:ellipsis">'+(r.result||r.error||'-').substring(0,200)+'</td></tr>';
    });
    html += '</tbody></table>';
  }
  html += '</div>';
  showModalHTML(html);
