}

// ============ Self-Improvement (自我改进) ============
function _siFormatTokens(n) {
  if (!n || n === 0) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return '' + n;
}

function renderSelfImprovement() {
  var c = document.getElementById('content');
  if (!c) { console.error('renderSelfImprovement: content element not found'); return; }
  c.style.padding = '24px';

  var siCount = agents.filter(function(a){ return a.self_improvement && a.self_improvement.enabled; }).length;

  var html = '<div style="width:100%;padding:0">';

  // Header
  html += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">';
  html += '<span class="material-symbols-outlined" style="font-size:28px;color:var(--primary)">psychology</span>';
  html += '<div><h2 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:22px;font-weight:800;margin:0;line-height:1.2">Agent Self-Improvement</h2>';
  html += '<div style="color:var(--text3);font-size:12px;margin-top:2px">复盘固化 + 主动学习 → 经验库 → 检索调用 → 迭代进化</div>';
  html += '</div></div>';

  // ── Row 1: closed-loop KPI cards ──
  // Goal → Plan → Completion → Conversion
  html += '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:18px">';
  html += '<div class="card" style="padding:14px 16px;text-align:center"><div style="font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Plans</div><div id="si-metric-plans" style="font-size:26px;font-weight:800;color:var(--primary);line-height:1">-</div><div style="font-size:10px;color:var(--text3);margin-top:4px">学习计划总数</div></div>';
  html += '<div class="card" style="padding:14px 16px;text-align:center"><div style="font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">In Progress</div><div id="si-metric-running" style="font-size:26px;font-weight:800;color:#FF9800;line-height:1">-</div><div style="font-size:10px;color:var(--text3);margin-top:4px">排队 / 进行中</div></div>';
  html += '<div class="card" style="padding:14px 16px;text-align:center"><div style="font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Completion</div><div id="si-metric-completion" style="font-size:26px;font-weight:800;color:#4CAF50;line-height:1">-</div><div style="font-size:10px;color:var(--text3);margin-top:4px">完成率</div></div>';
  html += '<div class="card" style="padding:14px 16px;text-align:center"><div style="font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Conversion</div><div id="si-metric-conversion" style="font-size:26px;font-weight:800;color:#2196F3;line-height:1">-</div><div style="font-size:10px;color:var(--text3);margin-top:4px">经验转化率</div></div>';
  html += '<div class="card" style="padding:14px 16px;text-align:center"><div style="font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Experiences</div><div id="si-metric-exp" style="font-size:26px;font-weight:800;color:var(--primary);line-height:1">-</div><div style="font-size:10px;color:var(--text3);margin-top:4px">已沉淀经验</div></div>';
  html += '</div>';
  // Secondary line: agents with SI + roles
  html += '<div style="display:flex;gap:16px;margin-bottom:18px;font-size:11px;color:var(--text3)">';
  html += '<span>自改进启用: <b style="color:var(--text1)">'+siCount+'/'+agents.length+'</b></span>';
  html += '<span>有经验的角色: <b id="si-metric-roles" style="color:var(--text1)">-</b></span>';
  html += '</div>';

  // ── Row 2: Learning Plan Board (主动学习任务看板) ──
  html += '<div class="card" style="padding:16px;margin-bottom:18px">';
  html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:12px"><span class="material-symbols-outlined" style="font-size:18px;color:#4CAF50">task_alt</span><span style="font-weight:700;font-size:14px">学习计划看板</span><span style="font-size:11px;color:var(--text3)">Learning Plan Board</span></div>';
  html += '<div id="si-plan-board" style="max-height:600px;overflow-y:auto"><div style="color:var(--text3);font-size:12px;text-align:center;padding:20px">Loading...</div></div>';
  html += '</div>';

  // ── Row 3: Retrospective Insights (复盘洞察) ──
  html += '<div class="card" style="padding:16px;margin-bottom:18px">';
  html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:12px"><span class="material-symbols-outlined" style="font-size:18px;color:#FF9800">lightbulb</span><span style="font-weight:700;font-size:14px">复盘洞察</span><span style="font-size:11px;color:var(--text3)">Retrospective Insights — 最新为准，冲突时覆盖历史</span></div>';
  html += '<div id="si-insights" style="max-height:280px;overflow-y:auto"><div style="color:var(--text3);font-size:12px;text-align:center;padding:20px">Loading...</div></div>';
  html += '</div>';

  // ── Row 4: Retrospective + Active Learning triggers (2 columns) ──
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px">';

  // Col 1: Retrospective
  html += '<div class="card" style="padding:16px;display:flex;flex-direction:column">';
  html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:10px"><span class="material-symbols-outlined" style="font-size:18px;color:#FF9800">replay</span><span style="font-weight:700;font-size:14px">自我复盘</span></div>';
  html += '<div class="form-group" style="margin-bottom:8px"><label style="font-size:11px;margin-bottom:2px">Agent</label>';
  html += '<select id="si-retro-agent" style="width:100%;padding:6px 8px;font-size:12px;border:1px solid var(--border-light);border-radius:6px;background:var(--bg);color:var(--text1)" onchange="siLoadAgentStatus(\'retro\')">';
  html += '<option value="">-- Select --</option>';
  agents.forEach(function(a) { html += '<option value="'+a.id+'">'+esc(a.name)+' ('+a.role+')</option>'; });
  html += '</select></div>';
  html += '<div class="form-group" style="margin-bottom:8px"><label style="font-size:11px;margin-bottom:2px">Task Summary (可选)</label>';
  html += '<textarea id="si-retro-summary" rows="2" style="width:100%;padding:6px 8px;font-size:12px;border:1px solid var(--border-light);border-radius:6px;background:var(--bg);color:var(--text1);resize:vertical;box-sizing:border-box" placeholder="描述要复盘的任务..."></textarea></div>';
  html += '<div id="si-retro-status" style="font-size:11px;color:var(--text3);margin-bottom:6px;min-height:16px"></div>';
  html += '<button class="btn btn-primary" id="si-retro-btn" style="width:100%;padding:8px;font-size:13px;margin-top:auto" onclick="siTriggerRetro()"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">replay</span> Run Retrospective</button>';
  html += '</div>';

  // Col 2: Active Learning
  html += '<div class="card" style="padding:16px;display:flex;flex-direction:column">';
  html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:10px"><span class="material-symbols-outlined" style="font-size:18px;color:#4CAF50">school</span><span style="font-weight:700;font-size:14px">主动学习</span></div>';
  html += '<div class="form-group" style="margin-bottom:8px"><label style="font-size:11px;margin-bottom:2px">Agent</label>';
  html += '<select id="si-learn-agent" style="width:100%;padding:6px 8px;font-size:12px;border:1px solid var(--border-light);border-radius:6px;background:var(--bg);color:var(--text1)" onchange="siLoadAgentStatus(\'learn\')">';
  html += '<option value="">-- Select --</option>';
  agents.forEach(function(a) { html += '<option value="'+a.id+'">'+esc(a.name)+' ('+a.role+')</option>'; });
  html += '</select></div>';
  html += '<div class="form-group" style="margin-bottom:8px"><label style="font-size:11px;margin-bottom:2px">Learning Goal (学习目标)</label>';
  html += '<input id="si-learn-goal" style="width:100%;padding:6px 8px;font-size:12px;border:1px solid var(--border-light);border-radius:6px;background:var(--bg);color:var(--text1);box-sizing:border-box" placeholder="e.g. 学习自动化测试最佳实践"></div>';
  html += '<div class="form-group" style="margin-bottom:8px"><label style="font-size:11px;margin-bottom:2px">Knowledge Gap (可选)</label>';
  html += '<input id="si-learn-gap" style="width:100%;padding:6px 8px;font-size:12px;border:1px solid var(--border-light);border-radius:6px;background:var(--bg);color:var(--text1);box-sizing:border-box" placeholder="e.g. 不了解pytest fixture用法"></div>';
  html += '<div id="si-learn-status" style="font-size:11px;color:var(--text3);margin-bottom:6px;min-height:16px"></div>';
  html += '<button class="btn btn-primary" id="si-learn-btn" style="width:100%;padding:8px;font-size:13px;margin-top:auto" onclick="siTriggerLearn()"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">school</span> Run Active Learning</button>';
  html += '</div>';
  html += '</div>';

  // ── Result display (hidden until triggered) ──
  html += '<div id="si-result" class="card" style="padding:16px;display:none;margin-bottom:18px">';
  html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">';
  html += '<span style="font-weight:700;font-size:14px" id="si-result-title">Result</span>';
  html += '<button class="btn btn-sm btn-ghost" style="padding:2px 6px" onclick="document.getElementById(\'si-result\').style.display=\'none\'"><span class="material-symbols-outlined" style="font-size:14px">close</span></button>';
  html += '</div>';
  html += '<div id="si-result-content"></div>';
  html += '</div>';

  // ── Row 5: Experience Library Browser ──
  html += '<div class="card" style="padding:16px;margin-bottom:18px">';
  html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px">';
  html += '<div style="display:flex;align-items:center;gap:6px"><span class="material-symbols-outlined" style="font-size:18px;color:#2196F3">library_books</span><span style="font-weight:700;font-size:14px">Global Experience Library</span><span style="font-size:11px;color:var(--text3)">全局经验库</span></div>';
  html += '<div style="display:flex;gap:6px;align-items:center">';
  html += '<select id="si-lib-role" style="padding:5px 8px;font-size:11px;border:1px solid var(--border-light);border-radius:6px;background:var(--bg);color:var(--text1)" onchange="siLoadExperiences()">';
  html += '<option value="">-- Select Role --</option>';
  var knownRoles = ["ceo","cto","coder","reviewer","researcher","architect","devops","designer","pm","tester","data","general"];
  knownRoles.forEach(function(r) { html += '<option value="'+r+'">'+r.toUpperCase()+'</option>'; });
  html += '</select>';
  html += '<button class="btn btn-sm" style="padding:4px 8px" onclick="siLoadExperiences()"><span class="material-symbols-outlined" style="font-size:14px">refresh</span></button>';
  html += '</div></div>';
  html += '<div id="si-exp-list" style="max-height:400px;overflow-y:auto">';
  html += '<div style="color:var(--text3);font-size:12px;text-align:center;padding:30px">Select a role to browse experiences</div>';
  html += '</div>';
  html += '</div>';

  html += '</div>';
  c.innerHTML = html;

  // Load initial data
  siLoadStats();
  siLoadHistory();
  siLoadPlanBoard();
  siLoadInsights();
}

async function siLoadStats() {
  try {
    var data = await api('GET', '/api/portal/experience/stats');
    var el = document.getElementById('si-stats-content');
    var metricEl = document.getElementById('si-metric-exp');
    if (!data) return;
    var roles = data.roles || {};
    var total = data.total_experiences || 0;
    if (metricEl) metricEl.textContent = '' + total;
    var rolesMetricEl = document.getElementById('si-metric-roles');
    if (rolesMetricEl) rolesMetricEl.textContent = '' + Object.keys(roles).length;
    if (!el) return;
    var html = '';
    var roleKeys = Object.keys(roles).sort();
    if (roleKeys.length > 0) {
      html += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
      roleKeys.forEach(function(r) {
        var info = roles[r];
        html += '<div style="background:var(--surface2);padding:4px 10px;border-radius:12px;font-size:11px;display:inline-flex;align-items:center;gap:4px">';
        html += '<span style="font-weight:700;text-transform:uppercase">'+r+'</span>';
        html += '<span style="color:var(--text2)">'+info.total+'</span>';
        if (info.core_count) html += '<span style="color:var(--primary);font-size:10px">'+info.core_count+' core</span>';
        html += '</div>';
      });
      html += '</div>';
    } else {
      html += '<span style="color:var(--text3)">No experiences yet. Enable self-improvement on an agent to get started.</span>';
    }
    el.innerHTML = html;
  } catch(e) { console.error('siLoadStats error:', e); }
}

function siLoadAgentStatus(type) {
  var agentId = document.getElementById('si-'+type+'-agent').value;
  var statusEl = document.getElementById('si-'+type+'-status');
  if (!agentId || !statusEl) { if(statusEl) statusEl.innerHTML = ''; return; }
  var agent = agents.find(function(a) { return a.id === agentId; });
  if (!agent) return;
  var si = agent.self_improvement;
  if (si && si.enabled) {
    statusEl.innerHTML = '<span style="color:var(--success)">✓ Self-improvement enabled</span> | ' +
      'Imported: ' + (si.imported_count||0) + ' | Retros: ' + (si.retrospective_count||0) +
      ' | Learnings: ' + (si.learning_count||0);
  } else {
    statusEl.innerHTML = '<span style="color:var(--text3)">Self-improvement not enabled for this agent</span>';
  }
}

async function siTriggerRetro() {
  var agentId = document.getElementById('si-retro-agent').value;
  if (!agentId) { alert('Please select an agent'); return; }
  var summary = document.getElementById('si-retro-summary').value.trim();

  var btn = document.getElementById('si-retro-btn');
  if (!btn) return;
  btn.disabled = true; btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px;animation:spin 1s linear infinite">sync</span> Running...';
  document.getElementById('si-retro-status').innerHTML = '<span style="color:var(--primary)">正在调用 LLM 进行复盘分析...</span>';

  try {
    var result = await api('POST', '/api/portal/experience/retrospective', {
      agent_id: agentId, task_summary: summary
    });
    if (!result) {
      document.getElementById('si-retro-status').innerHTML = '<span style="color:var(--error)">Error: 服务端返回空 — 请检查 Agent 的 LLM 配置 (provider/model)</span>';
    } else if (result.error) {
      document.getElementById('si-retro-status').innerHTML = '<span style="color:var(--error)">Error: '+esc(result.error)+'</span>';
    } else {
      document.getElementById('si-retro-status').innerHTML = '<span style="color:var(--success)">✓ 复盘完成</span>';
      siShowResult('Retrospective Result (复盘结果)', result);
      siLoadStats();
      siLoadHistory();
      siLoadPlanBoard();
      siLoadInsights();
      await refresh();
    }
  } catch(e) {
    document.getElementById('si-retro-status').innerHTML = '<span style="color:var(--error)">Error: '+esc(e.message)+'</span>';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px">replay</span> Run Retrospective';
  }
}

async function siTriggerLearn() {
  var agentId = document.getElementById('si-learn-agent').value;
  if (!agentId) { alert('Please select an agent'); return; }
  var goal = document.getElementById('si-learn-goal').value.trim();
  var gap = document.getElementById('si-learn-gap').value.trim();

  var btn = document.getElementById('si-learn-btn');
  if (!btn) return;
  btn.disabled = true; btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px;animation:spin 1s linear infinite">sync</span> Learning...';
  document.getElementById('si-learn-status').innerHTML = '<span style="color:var(--primary)">正在调用 LLM 进行主动学习...</span>';

  try {
    var result = await api('POST', '/api/portal/experience/learning', {
      agent_id: agentId, learning_goal: goal, knowledge_gap: gap
    });
    if (!result) {
      document.getElementById('si-learn-status').innerHTML = '<span style="color:var(--error)">Error: 服务端返回空 — 请检查 Agent 的 LLM 配置 (provider/model)</span>';
    } else if (result.error) {
      document.getElementById('si-learn-status').innerHTML = '<span style="color:var(--error)">Error: '+esc(result.error)+'</span>';
    } else {
      document.getElementById('si-learn-status').innerHTML = '<span style="color:var(--success)">✓ 学习完成</span>';
      siShowResult('Active Learning Result (主动学习结果)', result);
      siLoadStats();
      siLoadHistory();
      siLoadPlanBoard();
      siLoadInsights();
      await refresh();
    }
  } catch(e) {
    document.getElementById('si-learn-status').innerHTML = '<span style="color:var(--error)">Error: '+esc(e.message)+'</span>';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px">school</span> Run Active Learning';
  }
}

function siShowResult(title, result) {
  var container = document.getElementById('si-result');
  var titleEl = document.getElementById('si-result-title');
  var contentEl = document.getElementById('si-result-content');
  if (!container || !titleEl || !contentEl) return;

  titleEl.textContent = title;
  var html = '<div style="font-size:13px;line-height:1.7">';

  if (result.error) {
    html += '<div style="color:var(--error);padding:12px;background:rgba(244,67,54,0.1);border-radius:6px">'+esc(result.error)+'</div>';
  } else if (result.what_happened !== undefined) {
    // Retrospective result
    var fields = [
      {label:'发生了什么', key:'what_happened', icon:'description'},
      {label:'做得好的', key:'what_went_well', icon:'thumb_up', color:'var(--success)'},
      {label:'做得不好的', key:'what_went_wrong', icon:'thumb_down', color:'var(--error)'},
      {label:'根本原因', key:'root_cause', icon:'search'},
      {label:'改进方案', key:'improvement_plan', icon:'lightbulb', color:'var(--primary)'},
    ];
    fields.forEach(function(f) {
      if (result[f.key]) {
        html += '<div style="margin-bottom:12px"><div style="display:flex;align-items:center;gap:4px;font-weight:600;margin-bottom:4px">';
        html += '<span class="material-symbols-outlined" style="font-size:16px;color:'+(f.color||'var(--text2)')+'">'+f.icon+'</span> '+f.label+'</div>';
        html += '<div style="background:var(--surface2);padding:8px 12px;border-radius:6px;white-space:pre-wrap">'+esc(result[f.key])+'</div></div>';
      }
    });
    if (result.new_experiences && result.new_experiences.length > 0) {
      html += '<div style="margin-top:12px;padding:10px;background:rgba(76,175,80,0.1);border-radius:6px">';
      html += '<div style="font-weight:600;margin-bottom:6px;color:var(--success)">✨ New Experiences Generated ('+result.new_experiences.length+')</div>';
      result.new_experiences.forEach(function(e) {
        html += '<div style="font-size:12px;margin-bottom:4px">• <b>'+esc(e.id||'')+'</b>: '+esc(e.core_knowledge||e.scene||'')+'</div>';
      });
      html += '</div>';
    }
  } else if (result.learning_goal !== undefined) {
    // Learning result
    html += '<div style="margin-bottom:8px"><b>Learning Goal:</b> '+esc(result.learning_goal||'')+'</div>';
    html += '<div style="margin-bottom:8px"><b>Source:</b> '+esc(result.source_type||'')+' — '+esc(result.source_detail||'')+'</div>';
    if (result.key_findings) {
      html += '<div style="margin-bottom:8px"><b>Key Findings:</b></div>';
      html += '<div style="background:var(--surface2);padding:8px 12px;border-radius:6px;white-space:pre-wrap;margin-bottom:8px">'+esc(result.key_findings)+'</div>';
    }
    if (result.new_experiences && result.new_experiences.length > 0) {
      html += '<div style="padding:10px;background:rgba(76,175,80,0.1);border-radius:6px">';
      html += '<div style="font-weight:600;margin-bottom:6px;color:var(--success)">✨ New Experiences Generated ('+result.new_experiences.length+')</div>';
      result.new_experiences.forEach(function(e) {
        html += '<div style="font-size:12px;margin-bottom:4px">• <b>'+esc(e.id||'')+'</b>: '+esc(e.core_knowledge||e.scene||'')+'</div>';
      });
      html += '</div>';
    }
  } else {
    html += '<pre style="font-size:12px;max-height:300px;overflow:auto">'+esc(JSON.stringify(result,null,2))+'</pre>';
  }

  html += '</div>';
  contentEl.innerHTML = html;
  container.style.display = 'block';
  container.scrollIntoView({behavior:'smooth'});
}

var _siPlanFilter = 'all';

function siSetPlanFilter(state) {
  _siPlanFilter = state || 'all';
  siLoadPlanBoard();
}

function _siStateMeta(state) {
  if (state === 'queued')    return { label: '⏳ 待启动',  color: '#9E9E9E', bg: 'rgba(158,158,158,0.15)' };
  if (state === 'running')   return { label: '● 进行中',   color: '#FF9800', bg: 'rgba(255,152,0,0.15)' };
  if (state === 'completed') return { label: '✓ 已完成',  color: 'var(--success)', bg: 'rgba(76,175,80,0.15)' };
  return { label: state || '-', color: 'var(--text3)', bg: 'rgba(0,0,0,0)' };
}

async function siLoadPlanBoard() {
  var el = document.getElementById('si-plan-board');
  if (!el) return;
  try {
    var data = await api('GET', '/api/portal/experience/plans');
    var summary = (data && data.summary) || {};
    var plans = (data && data.plans) || [];

    // Update KPI metric cards with real closed-loop numbers
    var set = function(id, v){ var e = document.getElementById(id); if (e) e.textContent = v; };
    set('si-metric-plans', summary.total != null ? summary.total : '0');
    set('si-metric-running', (summary.queued || 0) + (summary.running || 0));
    var cr = summary.completion_rate != null ? Math.round(summary.completion_rate * 100) + '%' : '-';
    var kr = summary.conversion_rate != null ? Math.round(summary.conversion_rate * 100) + '%' : '-';
    set('si-metric-completion', cr);
    set('si-metric-conversion', kr);

    // Filter tab bar
    var tabBar = ''
      + '<div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap">'
      + _siTab('all',       '全部',    summary.total || 0)
      + _siTab('queued',    '待启动',  summary.queued || 0)
      + _siTab('running',   '进行中',  summary.running || 0)
      + _siTab('completed', '已完成',  summary.completed || 0)
      + '<div style="flex:1"></div>'
      + '<div style="font-size:11px;color:var(--text3);align-self:center">完成率 '+cr+' · 经验转化率 '+kr+' · 已沉淀 <b style="color:var(--text1)">'+(summary.experiences_produced||0)+'</b> 条</div>'
      + '</div>';

    var visible = plans.filter(function(p){
      return _siPlanFilter === 'all' || p.state === _siPlanFilter;
    });

    if (!visible.length) {
      el.innerHTML = tabBar + '<div style="color:var(--text3);font-size:12px;text-align:center;padding:30px">'
        + (plans.length === 0
            ? '暂无学习计划。使用下方「主动学习」面板设定一个学习目标开始第一个闭环。'
            : '当前过滤条件下没有计划。')
        + '</div>';
      return;
    }

    var html = tabBar;
    visible.forEach(function(p) {
      var meta = _siStateMeta(p.state);
      var expCount = (p.new_experiences || []).length;
      var tsSecs = p.completed_at || p.started_at || p.queued_at || p.created_at || 0;
      var tsStr = tsSecs ? new Date(tsSecs * 1000).toLocaleString() : '-';

      // Header row
      html += '<div class="card" style="padding:12px 16px;margin-bottom:10px;cursor:pointer;border-left:3px solid '+meta.color+'" onclick="var d=this.querySelector(\'.si-plan-detail\');if(d)d.style.display=d.style.display===\'none\'?\'block\':\'none\'">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px">';
      html += '<div style="display:flex;align-items:center;gap:8px;flex:1;min-width:0">';
      html += '<span style="background:'+meta.bg+';color:'+meta.color+';padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap">'+meta.label+'</span>';
      html += '<span style="font-weight:700;font-size:12px;color:var(--primary);white-space:nowrap">'+esc(p.agent_name || '-')+'</span>';
      html += '<span style="font-size:11px;color:var(--text3);white-space:nowrap">'+esc(p.role || '-')+'</span>';
      html += '<span style="color:var(--text2);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">'+esc(p.learning_goal || '(未设定目标)')+'</span>';
      html += '</div>';
      html += '<div style="display:flex;align-items:center;gap:10px;flex-shrink:0">';
      if (p.state === 'completed') {
        var convColor = expCount > 0 ? 'var(--success)' : 'var(--text3)';
        html += '<span style="font-size:11px;color:'+convColor+'">经验 '+expCount+' 条</span>';
      }
      html += '<span style="font-size:11px;color:var(--text3)">'+tsStr+'</span>';
      html += '<span class="material-symbols-outlined" style="font-size:16px;color:var(--text3)">expand_more</span>';
      html += '</div></div>';

      // Expandable detail
      html += '<div class="si-plan-detail" style="display:none;margin-top:12px;padding-top:12px;border-top:1px solid var(--border-light)">';

      // Goal block — always shown
      html += '<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:4px">🎯 学习目标 (Goal)</div>';
      html += '<div style="font-size:12px;background:var(--surface2);padding:8px 12px;border-radius:6px">'+esc(p.learning_goal||'(未设定)')+'</div></div>';

      if (p.knowledge_gap) {
        html += '<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:4px">❓ 知识缺口 (Gap)</div>';
        html += '<div style="font-size:12px;color:var(--text2)">'+esc(p.knowledge_gap)+'</div></div>';
      }

      if (p.state === 'queued') {
        html += '<div style="font-size:12px;color:var(--text3);padding:8px 0">等待 agent 空闲后自动启动。当前排在队列中。</div>';
      } else if (p.state === 'running') {
        html += '<div style="font-size:12px;color:#FF9800;padding:8px 0">● agent 正在执行学习任务…</div>';
      } else {
        // Completed — show closed-loop full body
        if (p.source_type || p.source_detail) {
          html += '<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:4px">📚 学习来源 (Source)</div>';
          html += '<div style="font-size:12px;color:var(--text2)">'+esc(p.source_type||'-')+(p.source_detail ? ' · '+esc(p.source_detail) : '')+'</div></div>';
        }
        if (p.key_findings) {
          html += '<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:4px">📋 关键发现 (Findings)</div>';
          html += '<div style="font-size:12px;background:var(--surface2);padding:8px 12px;border-radius:6px;white-space:pre-wrap;line-height:1.6">'+esc(p.key_findings)+'</div></div>';
        }
        if (p.applicable_scenes) {
          html += '<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:4px">🎯 适用场景 (Scenes)</div>';
          html += '<div style="font-size:12px;color:var(--text2)">'+esc(p.applicable_scenes)+'</div></div>';
        }

        // Closed-loop: new experiences + conversion outcome
        html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">';
        html += '<div style="background:rgba(76,175,80,0.05);border:1px solid rgba(76,175,80,0.2);border-radius:8px;padding:10px">';
        html += '<div style="font-size:11px;font-weight:600;color:var(--success);margin-bottom:6px">✨ 转化为经验 ('+expCount+' 条)</div>';
        if (expCount > 0) {
          (p.new_experiences || []).forEach(function(e) {
            html += '<div style="font-size:11px;margin-bottom:4px;display:flex;gap:4px">';
            html += '<span style="color:var(--primary);font-weight:600;flex-shrink:0">'+esc(e.id||'')+'</span>';
            html += '<span style="color:var(--text2);overflow:hidden;text-overflow:ellipsis">'+esc(e.core_knowledge||e.scene||'')+'</span>';
            html += '</div>';
          });
        } else {
          html += '<div style="font-size:11px;color:var(--text3)">本次学习未产出可沉淀经验（目标过宽或来源不足），建议细化目标后重试。</div>';
        }
        html += '</div>';

        html += '<div style="background:rgba(33,150,243,0.05);border:1px solid rgba(33,150,243,0.2);border-radius:8px;padding:10px">';
        html += '<div style="font-size:11px;font-weight:600;color:#2196F3;margin-bottom:6px">📦 经验固化去向</div>';
        html += '<div style="font-size:11px;color:var(--text2);line-height:1.8">';
        html += '• <b>角色经验库:</b> ~/.tudou_claw/experience/'+esc(p.role||'general')+'<br>';
        html += '• <b>System Prompt:</b> 下次对话自动注入<br>';
        html += '• <b>语义记忆 (L3):</b> 检索时命中<br>';
        html += '• <b>复用范围:</b> 同角色其他 agent 可检索';
        html += '</div></div>';
        html += '</div>';
      }

      html += '</div>'; // detail end
      html += '</div>'; // card end
    });
    el.innerHTML = html;
  } catch(e) {
    console.error('siLoadPlanBoard error:', e);
    el.innerHTML = '<div style="color:var(--error);font-size:12px;padding:20px">Load error: '+e.message+'</div>';
  }
}

function _siTab(state, label, count) {
  var active = _siPlanFilter === state;
  var bg = active ? 'var(--primary)' : 'var(--surface2)';
  var col = active ? '#282572' : 'var(--text2)';
  var fw = active ? '700' : '500';
  return '<button class="btn btn-sm" style="font-size:11px;padding:4px 10px;background:'+bg+';color:'+col+';font-weight:'+fw+'" onclick="siSetPlanFilter(\''+state+'\')">'+label+' ('+count+')</button>';
}

async function siLoadInsights() {
  var el = document.getElementById('si-insights');
  if (!el) return;
  try {
    var data = await api('GET', '/api/portal/experience/insights');
    if (!data || !data.insights || data.insights.length === 0) {
      el.innerHTML = '<div style="color:var(--text3);font-size:12px;text-align:center;padding:20px">暂无复盘洞察。使用「自我复盘」提炼经验。</div>';
      return;
    }
    var html = '';
    data.insights.forEach(function(ins, idx) {
      var ts = ins.created_at ? new Date(ins.created_at * 1000).toLocaleString() : '';
      var expCount = (ins.new_experiences && ins.new_experiences.length) || 0;
      html += '<div style="padding:10px 12px;border-radius:8px;background:var(--surface2);margin-bottom:8px'+(idx===0?';border-left:3px solid var(--primary)':'')+'">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">';
      html += '<span style="font-weight:700;font-size:12px">'+esc(ins.agent_name||'Agent')+' <span style="color:var(--text3);font-weight:400;font-size:11px">'+esc(ins.role||'')+'</span></span>';
      html += '<span style="font-size:10px;color:var(--text3)">'+ts+(idx===0?' <span style="color:var(--primary);font-weight:600">[最新]</span>':'')+'</span>';
      html += '</div>';
      if (ins.improvement_plan) {
        html += '<div style="font-size:12px;margin-bottom:4px"><span style="color:var(--primary)">改进方案:</span> '+esc(ins.improvement_plan).substring(0,150)+'</div>';
      }
      if (ins.root_cause) {
        html += '<div style="font-size:12px;margin-bottom:4px"><span style="color:#FF9800">根本原因:</span> '+esc(ins.root_cause).substring(0,120)+'</div>';
      }
      if (ins.what_went_well) {
        html += '<div style="font-size:11px;color:var(--success)">✓ '+esc(ins.what_went_well).substring(0,100)+'</div>';
      }
      if (ins.what_went_wrong) {
        html += '<div style="font-size:11px;color:var(--error)">✗ '+esc(ins.what_went_wrong).substring(0,100)+'</div>';
      }
      if (expCount > 0) {
        html += '<div style="font-size:11px;color:var(--success);margin-top:4px">+'+expCount+' 经验</div>';
      }
      html += '</div>';
    });
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div style="color:var(--error);font-size:12px;padding:10px">Error: '+esc(e.message)+'</div>';
  }
}

async function siLoadExperiences() {
  var role = document.getElementById('si-lib-role').value;
  var el = document.getElementById('si-exp-list');
  if (!el) return;
  if (!role) { el.innerHTML = '<div style="color:var(--text3);font-size:13px;text-align:center;padding:40px">Select a role to browse experiences</div>'; return; }

  el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text3)">Loading...</div>';
  try {
    var data = await api('GET', '/api/portal/experience/list?role='+encodeURIComponent(role));
    if (!data || !data.experiences || data.experiences.length === 0) {
      el.innerHTML = '<div style="color:var(--text3);font-size:13px;text-align:center;padding:40px">No experiences found for role: '+esc(role)+'</div>';
      return;
    }
    var html = '<table style="width:100%;border-collapse:collapse;font-size:12px">';
    html += '<tr style="border-bottom:1px solid var(--border);text-align:left">';
    html += '<th style="padding:8px 6px;font-weight:600">ID</th>';
    html += '<th style="padding:8px 6px;font-weight:600">Type</th>';
    html += '<th style="padding:8px 6px;font-weight:600">Scene</th>';
    html += '<th style="padding:8px 6px;font-weight:600">Knowledge</th>';
    html += '<th style="padding:8px 6px;font-weight:600">Priority</th>';
    html += '<th style="padding:8px 6px;font-weight:600">Success Rate</th>';
    html += '</tr>';
    data.experiences.forEach(function(e) {
      var rate = (e.success_count + e.fail_count) > 0 ? Math.round(e.success_count / (e.success_count + e.fail_count) * 100) : '-';
      var pColor = e.priority === 'high' ? 'var(--error)' : e.priority === 'medium' ? 'var(--primary)' : 'var(--text3)';
      var typeIcon = e.exp_type === 'retrospective' ? '🔄' : '📚';
      html += '<tr style="border-bottom:1px solid var(--border-light)">';
      html += '<td style="padding:6px;font-family:monospace;font-weight:600">'+esc(e.id)+'</td>';
      html += '<td style="padding:6px">'+typeIcon+' '+esc(e.exp_type)+'</td>';
      html += '<td style="padding:6px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+esc(e.scene)+'">'+esc(e.scene)+'</td>';
      html += '<td style="padding:6px;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+esc(e.core_knowledge)+'">'+esc(e.core_knowledge)+'</td>';
      html += '<td style="padding:6px;color:'+pColor+';font-weight:600;text-transform:uppercase">'+esc(e.priority)+'</td>';
      html += '<td style="padding:6px">'+(rate === '-' ? '<span style="color:var(--text3)">new</span>' : rate+'%')+'</td>';
      html += '</tr>';
    });
    html += '</table>';
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div style="color:var(--error);padding:20px">Error loading experiences: '+esc(e.message)+'</div>';
  }
}

async function siLoadHistory() {
  try {
    var data = await api('GET', '/api/portal/experience/history');
    var el = document.getElementById('si-history');
    if (!el || !data) return;
    var items = data.history || [];
    if (items.length === 0) {
      el.innerHTML = '<div style="color:var(--text3);font-size:13px;text-align:center;padding:20px">No activity yet. Run a retrospective or learning session to get started!</div>';
      return;
    }
    var html = '';
    items.forEach(function(item) {
      var ts = item.created_at ? new Date(item.created_at * 1000).toLocaleString() : '';
      var icon = item.type === 'retrospective' ? 'replay' : 'school';
      var color = item.type === 'retrospective' ? '#FF9800' : '#4CAF50';
      html += '<div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border-light)">';
      html += '<span class="material-symbols-outlined" style="font-size:18px;color:'+color+'">'+icon+'</span>';
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="font-size:13px;font-weight:600">'+esc(item.agent_name||'Agent')+' <span style="color:var(--text3);font-weight:400">— '+esc(item.type||'')+'</span></div>';
      html += '<div style="font-size:12px;color:var(--text3);margin-top:2px">'+esc(item.summary||'')+'</div>';
      if (item.new_count) html += '<div style="font-size:11px;color:var(--success);margin-top:2px">+'+item.new_count+' new experiences</div>';
      html += '</div>';
      html += '<div style="font-size:11px;color:var(--text3);white-space:nowrap">'+ts+'</div>';
      html += '</div>';
    });
    el.innerHTML = html;
  } catch(e) { console.error('siLoadHistory error:', e); }
}

// ---- Workflow Designer ----
var _wfSteps = [];  // [{name, agent_id, input_desc, output_desc, depends_on:[]}]

function showCreateWorkflowModal() {
  _wfSteps = [];
  var html = '<div style="max-width:700px">';
  html += '<h3 style="margin-bottom:4px">Create Workflow</h3>';
  html += '<p style="font-size:11px;color:var(--text3);margin:0 0 16px">Workflow defines abstract process steps. Agents are assigned when creating a project/task.</p>';
  html += '<div class="form-group"><label>Workflow Name</label><input id="wf-name" placeholder="e.g. Code Review Pipeline"></div>';
  html += '<div class="form-group"><label>Description</label><input id="wf-desc" placeholder="Describe the workflow..."></div>';
  html += '<div style="display:flex;align-items:center;justify-content:space-between;margin:16px 0 8px">';
  html += '<span style="font-size:13px;font-weight:700;color:var(--text)">Steps</span>';
  html += '</div>';
  html += '<div id="wf-nodes-container" style="position:relative;min-height:80px;margin-bottom:12px"></div>';
  html += '<div style="display:flex;justify-content:center;margin-bottom:16px"><div onclick="addWfStep()" style="width:48px;height:48px;border-radius:50%;background:var(--primary);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:transform 0.15s;box-shadow:0 2px 12px rgba(203,201,255,0.3)" onmouseenter="this.style.transform=\'scale(1.1)\'" onmouseleave="this.style.transform=\'scale(1)\'"><span class="material-symbols-outlined" style="font-size:28px;color:#282572">add</span></div></div>';
  html += '<div class="form-actions"><button class="btn btn-ghost" onclick="closeModal()">Cancel</button>';
  html += '<button class="btn btn-primary" onclick="createWorkflowFromDesigner()">Create</button></div>';
  html += '</div>';
  showCustomModal(html);
  renderWfNodes();
}

function addWfStep() {
  _wfSteps.push({
    name: 'Step ' + (_wfSteps.length + 1),
    description: '',
    input_desc: '',
    output_desc: '',
    depends_on: _wfSteps.length > 0 ? [_wfSteps.length - 1] : []
  });
  renderWfNodes();
}

function removeWfStep(idx) {
  _wfSteps.splice(idx, 1);
  _wfSteps.forEach(function(s) {
    s.depends_on = (s.depends_on||[]).filter(function(d){ return d < _wfSteps.length; });
  });
  renderWfNodes();
  var countEl = document.getElementById('wf-step-count');
  if (countEl) countEl.textContent = _wfSteps.length;
}

function renderWfNodes() {
  var container = document.getElementById('wf-nodes-container');
  if (!container) return;
  if (_wfSteps.length === 0) {
    container.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text3);font-size:13px;border:2px dashed var(--border);border-radius:12px">Click <strong>+</strong> to add workflow steps</div>';
    return;
  }
  var html = '';
  _wfSteps.forEach(function(step, idx) {
    if (idx > 0) {
      html += '<div style="display:flex;justify-content:center;padding:4px 0"><div style="width:2px;height:20px;background:var(--primary);opacity:0.4"></div></div>';
      html += '<div style="display:flex;justify-content:center;padding:0 0 4px"><span class="material-symbols-outlined" style="font-size:16px;color:var(--primary);opacity:0.5">arrow_downward</span></div>';
    }
    html += '<div style="background:var(--surface);border:1px solid var(--border-light);border-radius:12px;padding:14px 16px;position:relative;transition:border-color 0.15s" onmouseenter="this.style.borderColor=\'var(--primary)\'" onmouseleave="this.style.borderColor=\'var(--border-light)\'">';
    // Header: step number + editable name + remove button
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">';
    html += '<div style="display:flex;align-items:center;gap:8px"><span style="width:24px;height:24px;border-radius:50%;background:var(--primary);color:#282572;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800">'+(idx+1)+'</span>';
    html += '<input value="'+esc(step.name)+'" onchange="_wfSteps['+idx+'].name=this.value" style="background:none;border:none;color:var(--text);font-size:13px;font-weight:600;width:200px;outline:none;border-bottom:1px solid transparent" onfocus="this.style.borderBottomColor=\'var(--primary)\'" onblur="this.style.borderBottomColor=\'transparent\'">';
    html += '</div>';
    html += '<div style="display:flex;align-items:center;gap:2px">';
    if (idx > 0) html += '<button onclick="moveWfStep('+idx+',-1)" style="background:none;border:none;color:var(--text3);cursor:pointer;font-size:14px;padding:2px" title="Move up"><span class="material-symbols-outlined" style="font-size:14px">arrow_upward</span></button>';
    if (idx < _wfSteps.length-1) html += '<button onclick="moveWfStep('+idx+',1)" style="background:none;border:none;color:var(--text3);cursor:pointer;font-size:14px;padding:2px" title="Move down"><span class="material-symbols-outlined" style="font-size:14px">arrow_downward</span></button>';
    html += '<button onclick="removeWfStep('+idx+')" style="background:none;border:none;color:var(--error);cursor:pointer;opacity:0.5;font-size:16px;padding:2px" onmouseenter="this.style.opacity=1" onmouseleave="this.style.opacity=0.5">&times;</button>';
    html += '</div></div>';
    // Description
    html += '<div style="margin-bottom:8px"><div style="font-size:9px;text-transform:uppercase;color:var(--text3);letter-spacing:0.5px;margin-bottom:4px">Description</div>';
    html += '<input value="'+esc(step.description||'')+'" onchange="_wfSteps['+idx+'].description=this.value" placeholder="What this step does..." style="width:100%;padding:6px;font-size:11px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);box-sizing:border-box"></div>';
    // Input + Output (2 columns)
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
    html += '<div><div style="font-size:9px;text-transform:uppercase;color:var(--text3);letter-spacing:0.5px;margin-bottom:4px">Input</div>';
    html += '<input value="'+esc(step.input_desc)+'" onchange="_wfSteps['+idx+'].input_desc=this.value" placeholder="What goes in..." style="width:100%;padding:6px;font-size:11px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);box-sizing:border-box"></div>';
    html += '<div><div style="font-size:9px;text-transform:uppercase;color:var(--text3);letter-spacing:0.5px;margin-bottom:4px">Output</div>';
    html += '<input value="'+esc(step.output_desc)+'" onchange="_wfSteps['+idx+'].output_desc=this.value" placeholder="What comes out..." style="width:100%;padding:6px;font-size:11px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);box-sizing:border-box"></div>';
    html += '</div>';
    // Prompt template (collapsible advanced)
    html += '<details style="margin-top:8px"><summary style="font-size:9px;text-transform:uppercase;color:var(--text3);letter-spacing:0.5px;cursor:pointer;user-select:none">Prompt Template / Role</summary>';
    html += '<div style="display:grid;grid-template-columns:1fr auto;gap:8px;margin-top:6px">';
    html += '<div><textarea onchange="_wfSteps['+idx+'].prompt_template=this.value" placeholder="Agent prompt template for this step..." style="width:100%;padding:6px;font-size:11px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);box-sizing:border-box;min-height:48px;resize:vertical;font-family:monospace">'+esc(step.prompt_template||'')+'</textarea></div>';
    html += '<div><div style="font-size:9px;text-transform:uppercase;color:var(--text3);letter-spacing:0.5px;margin-bottom:4px">Role</div>';
    html += '<input value="'+esc(step.suggested_role||'')+'" onchange="_wfSteps['+idx+'].suggested_role=this.value" placeholder="coder" style="width:80px;padding:6px;font-size:11px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);box-sizing:border-box"></div>';
    html += '</div></details>';
    html += '</div>';
  });
  container.innerHTML = html;
}

async function createWorkflowFromDesigner() {
  var name = document.getElementById('wf-name').value.trim();
  if (!name) { alert('Please enter a workflow name'); return; }
  var desc = document.getElementById('wf-desc').value.trim();
  if (_wfSteps.length === 0) { alert('Please add at least one step'); return; }
  var steps = _wfSteps.map(function(s, idx) {
    return {
      name: s.name || ('Step ' + (idx+1)),
      description: s.description || '',
      input_desc: s.input_desc || '',
      output_desc: s.output_desc || '',
      task: (s.input_desc ? 'Input: '+s.input_desc+'. ' : '') + (s.output_desc ? 'Expected output: '+s.output_desc : ''),
      depends_on: s.depends_on || []
    };
  });
  var data = await api('POST', '/api/portal/workflows', {
    action: 'create', name: name, description: desc, steps: steps
  });
  if (data && !data.error) {
    closeModal();
    renderWorkflows();
  } else {
    alert((data && data.error) || 'Failed to create workflow');
  }
}

async function startWorkflow(wfId) {
  await api('POST', '/api/portal/workflows/' + wfId + '/start', {});
  renderCurrentView();
}

async function abortWorkflow(wfId) {
  if (!confirm('确定要中止这个工作流吗？')) return;
  await api('POST', '/api/portal/workflows/' + wfId + '/abort', {});
  renderCurrentView();
}

async function editWorkflow(wfId) {
  // Fetch full workflow data including steps
  var wfData = null;
  try {
    wfData = await api('GET', '/api/portal/workflows/' + wfId);
  } catch(e) {}
  if (!wfData || wfData.error) { alert('Could not load workflow'); return; }

  // Populate _wfSteps from existing steps
  _wfSteps = (wfData.steps || []).map(function(s) {
    return {
      name: s.name || '',
      description: s.description || '',
      input_desc: s.input_spec || s.input_desc || '',
      output_desc: s.output_spec || s.output_desc || '',
      prompt_template: s.prompt_template || '',
      suggested_role: s.suggested_role || '',
      depends_on: s.depends_on || []
    };
  });
  _editingWfId = wfId;

  var html = '<div style="max-width:700px">';
  html += '<h3 style="margin-bottom:4px"><span class="material-symbols-outlined" style="vertical-align:middle;color:var(--primary)">edit_note</span> Edit Workflow</h3>';
  html += '<p style="font-size:11px;color:var(--text3);margin:0 0 16px">Edit steps, add new steps, reorder, or remove steps.</p>';
  html += '<div class="form-group"><label>Workflow Name</label><input id="wf-edit-name" value="' + esc(wfData.name||'').replace(/"/g,'&quot;') + '" placeholder="e.g. Code Review Pipeline"></div>';
  html += '<div class="form-group"><label>Description</label><input id="wf-edit-desc" value="' + esc(wfData.description||'').replace(/"/g,'&quot;') + '" placeholder="Describe the workflow..."></div>';
  html += '<div style="display:flex;align-items:center;justify-content:space-between;margin:16px 0 8px">';
  html += '<span style="font-size:13px;font-weight:700;color:var(--text)">Steps (' + _wfSteps.length + ')</span>';
  html += '</div>';
  html += '<div id="wf-nodes-container" style="position:relative;min-height:80px;margin-bottom:12px;max-height:400px;overflow-y:auto"></div>';
  // Add step circle button
  html += '<div style="display:flex;justify-content:center;margin-bottom:16px">';
  html += '<div onclick="addWfStep();document.getElementById(\'wf-step-count\').textContent=_wfSteps.length" style="width:48px;height:48px;border-radius:50%;background:var(--primary);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:transform 0.15s;box-shadow:0 2px 12px rgba(203,201,255,0.3)" onmouseenter="this.style.transform=\'scale(1.1)\'" onmouseleave="this.style.transform=\'scale(1)\'">';
  html += '<span class="material-symbols-outlined" style="font-size:28px;color:#282572">add</span></div></div>';
  // Actions
  html += '<div class="form-actions" style="display:flex;justify-content:space-between;align-items:center">';
  html += '<span style="font-size:11px;color:var(--text3)"><span id="wf-step-count">' + _wfSteps.length + '</span> steps</span>';
  html += '<div style="display:flex;gap:8px">';
  html += '<button class="btn btn-ghost" onclick="_editingWfId=null;closeModal()">Cancel</button>';
  html += '<button class="btn btn-primary" onclick="saveEditedWorkflow()">Save Changes</button>';
  html += '</div></div></div>';
  showCustomModal(html);
  renderWfNodes();
}

var _editingWfId = null;

async function saveEditedWorkflow() {
  if (!_editingWfId) return;
  var name = document.getElementById('wf-edit-name').value.trim();
  if (!name) { alert('Please enter a workflow name'); return; }
  var desc = document.getElementById('wf-edit-desc').value.trim();
  var steps = _wfSteps.map(function(s, idx) {
    return {
      name: s.name || ('Step ' + (idx+1)),
      description: s.description || '',
      input_spec: s.input_desc || '',
      output_spec: s.output_desc || '',
      prompt_template: s.prompt_template || '',
      suggested_role: s.suggested_role || '',
      input_desc: s.input_desc || '',
      output_desc: s.output_desc || '',
      task: (s.input_desc ? 'Input: '+s.input_desc+'. ' : '') + (s.output_desc ? 'Expected output: '+s.output_desc : ''),
      depends_on: s.depends_on || []
    };
  });
  var data = await api('POST', '/api/portal/workflows', {
    action: 'update', workflow_id: _editingWfId,
    name: name, description: desc, steps: steps
  });
  if (data && !data.error) {
    _editingWfId = null;
    closeModal();
    renderWorkflows();
  } else {
    alert((data && data.error) || 'Failed to update workflow');
  }
}

// Move step up/down for reordering
function moveWfStep(idx, direction) {
  var newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= _wfSteps.length) return;
  var tmp = _wfSteps[idx];
  _wfSteps[idx] = _wfSteps[newIdx];
  _wfSteps[newIdx] = tmp;
  renderWfNodes();
}

async function deleteWorkflow(wfId) {
  if (!confirm('确定要删除这个工作流吗？')) return;
  await api('POST', '/api/portal/workflows', {action:'delete', workflow_id:wfId});
  renderCurrentView();
}

// --- @mention autocomplete ---
var _mentionActiveIdx = -1;
var _mentionProjId = '';

function _getProjectMembers(projId) {
  // Get current project's members matched to agent data
  var projEl = document.getElementById('project-members-'+projId);
  if (!projEl) return [];
  // Use global agents array and match to project members
  // We'll fetch from the proj data cached in DOM or use agents list
  return agents.map(function(a) {
    return { id: a.id, name: a.name, role: a.role || 'general', display: (a.role||'general')+'-'+a.name };
  });
}

function _projInputChange(projId) {
  var input = document.getElementById('project-chat-input-'+projId);
  if (!input) return;
  var val = input.value;
  var cursorPos = input.selectionStart;
  // Find @ before cursor
  var textBefore = val.slice(0, cursorPos);
  var atIdx = textBefore.lastIndexOf('@');
  if (atIdx === -1 || (atIdx > 0 && textBefore[atIdx-1] !== ' ' && textBefore[atIdx-1] !== '\n')) {
    _hideMentionDropdown(projId);
    return;
  }
  var query = textBefore.slice(atIdx + 1).toLowerCase();
  var members = _getProjectMembers(projId);
  var filtered = members.filter(function(m) {
    return m.name.toLowerCase().indexOf(query) !== -1 ||
           m.role.toLowerCase().indexOf(query) !== -1 ||
           m.display.toLowerCase().indexOf(query) !== -1;
  });
  if (filtered.length === 0) { _hideMentionDropdown(projId); return; }
  _mentionProjId = projId;
  _mentionActiveIdx = 0;
  _showMentionDropdown(projId, filtered, atIdx);
}

function _showMentionDropdown(projId, members, atIdx) {
  var dd = document.getElementById('mention-dropdown-'+projId);
  if (!dd) return;
  dd.innerHTML = members.map(function(m, i) {
    return '<div class="mention-item'+(i===0?' active':'')+'" data-name="'+esc(m.display)+'" data-at-idx="'+atIdx+'" onclick="_selectMention(\''+projId+'\',\''+esc(m.display)+'\','+atIdx+')">' +
      '<span class="material-symbols-outlined" style="font-size:18px;color:var(--primary)">smart_toy</span>' +
      '<div><span class="mention-name">'+esc(m.display)+'</span><br><span class="mention-role">'+esc(m.role)+'</span></div>' +
    '</div>';
  }).join('');
  dd.classList.add('show');
}

function _hideMentionDropdown(projId) {
  var dd = document.getElementById('mention-dropdown-'+(projId||_mentionProjId));
  if (dd) { dd.classList.remove('show'); dd.innerHTML = ''; }
  _mentionActiveIdx = -1;
}

function _selectMention(projId, name, atIdx) {
  var input = document.getElementById('project-chat-input-'+projId);
  if (!input) return;
  var val = input.value;
  var cursorPos = input.selectionStart;
  var before = val.slice(0, atIdx);
  var after = val.slice(cursorPos);
  input.value = before + '@' + name + ' ' + after;
  input.focus();
  var newPos = before.length + 1 + name.length + 1;
  input.setSelectionRange(newPos, newPos);
  _hideMentionDropdown(projId);
}

function _projInputKeydown(e, projId) {
  var dd = document.getElementById('mention-dropdown-'+projId);
  if (dd && dd.classList.contains('show')) {
    var items = dd.querySelectorAll('.mention-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _mentionActiveIdx = Math.min(_mentionActiveIdx + 1, items.length - 1);
      items.forEach(function(el,i){ el.classList.toggle('active', i===_mentionActiveIdx); });
      return;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _mentionActiveIdx = Math.max(_mentionActiveIdx - 1, 0);
      items.forEach(function(el,i){ el.classList.toggle('active', i===_mentionActiveIdx); });
      return;
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      if (_mentionActiveIdx >= 0 && _mentionActiveIdx < items.length) {
        var item = items[_mentionActiveIdx];
        _selectMention(projId, item.getAttribute('data-name'), parseInt(item.getAttribute('data-at-idx')));
      }
      return;
    } else if (e.key === 'Escape') {
      _hideMentionDropdown(projId);
      return;
    }
  }
  // Default: Enter sends message
  if (e.key === 'Enter' && !e.isComposing) {
    e.preventDefault();
    sendProjectMsg(projId);
  }
}

var _cachedWorkflows = [];

function _buildProjectMembersGroupedByNode() {
  // Group agents by node_id
  var nodeGroups = {};
  agents.forEach(function(a) {
    var nid = a.node_id || 'local';
    if (!nodeGroups[nid]) {
      nodeGroups[nid] = {
        agents: [],
        name: nid === 'local' ? '本机 (Local)' : nid
      };
    }
    nodeGroups[nid].agents.push(a);
  });

  // Render grouped HTML
  var html = '';
  Object.keys(nodeGroups).sort().forEach(function(nid) {
    var group = nodeGroups[nid];
    var statusDot = '<span style="width:6px;height:6px;border-radius:50%;background:#3fb950;display:inline-block;margin-right:4px"></span>';
    html += '<div style="margin-bottom:12px;border:1px solid var(--border-light);border-radius:8px;overflow:hidden">' +
      '<div style="background:var(--surface2);padding:8px 12px;font-size:11px;font-weight:700;display:flex;align-items:center;gap:6px;color:var(--text2)">' +
      statusDot + esc(group.name) + ' (' + group.agents.length + ')' +
      '</div>' +
      '<div style="padding:8px 12px">' +
      group.agents.map(function(a) {
        return '<label style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px;cursor:pointer"><input type="checkbox" class="proj-member-cb" value="'+a.id+'"> <span style="color:var(--text3);font-size:10px;flex-shrink:0">['+esc(a.role||'general')+']</span> '+esc(a.name)+'</label>';
      }).join('') +
      '</div></div>';
  });
  return html;
}

async function showCreateProjectModal() {
  // Load workflows for selection
  try {
    var wfData = await api('GET', '/api/portal/workflows');
    _cachedWorkflows = (wfData && wfData.workflows) ? wfData.workflows : [];
  } catch(e) { _cachedWorkflows = []; }

  var wfOpts = '<option value="">-- No Workflow (Free-form) --</option>' +
    _cachedWorkflows.map(function(wf) {
      return '<option value="'+wf.id+'">'+esc(wf.name)+' ('+((wf.steps||[]).length)+' steps)</option>';
    }).join('');

  var html = '<div style="padding:24px;max-width:600px"><h3 style="margin:0 0 16px">Create Project</h3>' +
    '<input id="new-proj-name" placeholder="Project Name" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px;box-sizing:border-box">' +
    '<textarea id="new-proj-desc" placeholder="Description" rows="3" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px;resize:vertical;box-sizing:border-box"></textarea>' +
    '<input id="new-proj-dir" placeholder="Working Directory (e.g. /home/user/project)" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px;box-sizing:border-box">' +
    '<select id="new-proj-node" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px;box-sizing:border-box">' +
      '<option value="local">Local Node</option>' +
      nodes.map(function(n){ return n.is_self ? '' : '<option value="'+n.id+'">'+esc(n.name||n.id)+'</option>'; }).join('') +
    '</select>' +

    // Workflow template selection
    '<div style="font-size:12px;font-weight:700;margin-bottom:6px"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">account_tree</span> Workflow Template</div>' +
    '<select id="new-proj-workflow" onchange="_onProjWorkflowChange()" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px;box-sizing:border-box">' + wfOpts + '</select>' +

    // Step-Agent assignment area (hidden initially)
    '<div id="proj-wf-steps" style="display:none;margin-bottom:12px"></div>' +

    // Team members (shown when no workflow is selected)
    '<div id="proj-members-section">' +
    '<div style="font-size:12px;font-weight:700;margin-bottom:8px">Add Team Members</div>' +
    '<div id="proj-members-list" style="margin-bottom:12px">' +
      _buildProjectMembersGroupedByNode() +
    '</div></div>' +

    '<div style="display:flex;gap:8px;justify-content:flex-end">' +
      '<button class="btn btn-ghost" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-primary" onclick="createProject()">Create</button>' +
    '</div></div>';
  showModalHTML(html);
}

function _onProjWorkflowChange() {
  var wfId = document.getElementById('new-proj-workflow').value;
  var stepsDiv = document.getElementById('proj-wf-steps');
  var membersSection = document.getElementById('proj-members-section');
  if (!wfId) {
    // No workflow: show team members, hide step assignment
    stepsDiv.style.display = 'none';
    membersSection.style.display = '';
    return;
  }
  // Workflow selected: hide team members, show step→agent assignment
  membersSection.style.display = 'none';
  stepsDiv.style.display = '';

  var wf = _cachedWorkflows.find(function(w){ return w.id === wfId; });
  if (!wf || !wf.steps || wf.steps.length === 0) {
    stepsDiv.innerHTML = '<div style="color:var(--text3);font-size:12px;padding:8px">This workflow has no steps.</div>';
    return;
  }

  var agentOpts = '<option value="">-- Select Agent --</option>' +
    agents.map(function(a) { return '<option value="'+a.id+'">'+esc(a.name)+' ('+esc(a.role||'general')+')</option>'; }).join('');

  var html = '<div style="font-size:12px;font-weight:700;margin-bottom:8px">Assign Agents to Workflow Steps</div>';
  html += '<div style="border:1px solid var(--border-light);border-radius:10px;overflow:hidden">';
  wf.steps.forEach(function(step, idx) {
    var borderTop = idx > 0 ? 'border-top:1px solid var(--border-light);' : '';
    html += '<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;'+borderTop+'">';
    html += '<span style="width:22px;height:22px;border-radius:50%;background:var(--primary);color:#282572;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;flex-shrink:0">'+(idx+1)+'</span>';
    html += '<div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600;color:var(--text)">'+esc(step.name||'Step '+(idx+1))+'</div>';
    if (step.description) html += '<div style="font-size:10px;color:var(--text3);margin-top:1px">'+esc(step.description)+'</div>';
    html += '</div>';
    html += '<select class="wf-step-agent" data-step-idx="'+idx+'" style="padding:6px 8px;font-size:11px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);min-width:140px">' + agentOpts + '</select>';
    html += '<label title="启动前需人工批准" style="display:flex;align-items:center;gap:4px;font-size:10px;color:var(--text3);cursor:pointer;white-space:nowrap"><input type="checkbox" class="wf-step-approval" data-step-idx="'+idx+'" style="cursor:pointer">审核</label>';
    html += '</div>';
  });
  html += '</div>';
  stepsDiv.innerHTML = html;
}

function closeModal() {
  // Remove ALL overlays with this id (there may be duplicates from prior renders)
  var overlays = document.querySelectorAll('#modal-overlay');
  overlays.forEach(function(o){ o.remove(); });
}

async function createProject() {
  var name = document.getElementById('new-proj-name').value.trim();
  var desc = document.getElementById('new-proj-desc').value.trim();
  var workingDir = document.getElementById('new-proj-dir').value.trim();
  var nodeId = document.getElementById('new-proj-node').value;
  if (!name) { alert('Name required'); return; }

  var wfId = document.getElementById('new-proj-workflow').value;
  var members = [];
  var stepAssignments = [];

  if (wfId) {
    // Workflow mode: collect step→agent assignments as members
    var selects = document.querySelectorAll('.wf-step-agent');
    var approvalMap = {};
    document.querySelectorAll('.wf-step-approval').forEach(function(chk){
      approvalMap[parseInt(chk.getAttribute('data-step-idx'))] = chk.checked;
    });
    var assignedAgentIds = {};
    selects.forEach(function(sel) {
      var agentId = sel.value;
      var stepIdx = parseInt(sel.getAttribute('data-step-idx'));
      if (agentId) {
        stepAssignments.push({
          step_index: stepIdx,
          agent_id: agentId,
          require_approval: !!approvalMap[stepIdx],
        });
        if (!assignedAgentIds[agentId]) {
          assignedAgentIds[agentId] = true;
          members.push({agent_id: agentId, responsibility: ''});
        }
      }
    });
  } else {
    // Free-form mode: collect checked members
    document.querySelectorAll('.proj-member-cb:checked').forEach(function(cb) {
      members.push({agent_id: cb.value, responsibility: ''});
    });
  }

  try {
    var payload = {name: name, description: desc, members: members, working_directory: workingDir, node_id: nodeId};
    if (wfId) {
      payload.workflow_id = wfId;
      payload.step_assignments = stepAssignments;
    }
    await api('POST', '/api/portal/projects', payload);
    closeModal();
    renderProjects();
  } catch(e) { alert('Error: '+e.message); }
}

function showProjectMemberModal(projId) {
  var html = '<div style="padding:24px"><h3 style="margin:0 0 16px">Manage Members</h3>' +
    '<div id="proj-add-members">' +
      agents.map(function(a) {
        return '<label style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px;cursor:pointer"><input type="checkbox" class="proj-add-member-cb" value="'+a.id+'"> '+esc(a.role+'-'+a.name)+' <input type="text" class="proj-resp-input" data-aid="'+a.id+'" placeholder="Responsibility" style="flex:1;padding:4px 8px;background:var(--bg);border:1px solid rgba(255,255,255,0.1);border-radius:4px;color:var(--text);font-size:11px"></label>';
      }).join('') +
    '</div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">' +
      '<button class="btn btn-ghost" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-primary" onclick="updateProjectMembers(\''+projId+'\')">Save</button>' +
    '</div></div>';
  showModalHTML(html);
}

async function updateProjectMembers(projId) {
  var cbs = document.querySelectorAll('.proj-add-member-cb:checked');
  for (var i = 0; i < cbs.length; i++) {
    var aid = cbs[i].value;
    var respInput = document.querySelector('.proj-resp-input[data-aid="'+aid+'"]');
    var resp = respInput ? respInput.value : '';
    await api('POST', '/api/portal/projects/'+projId+'/members', {agent_id: aid, responsibility: resp});
  }
  closeModal();
  renderProjectDetail(projId);
}

function showProjectTaskModal(projId) {
  var html = '<div style="padding:24px"><h3 style="margin:0 0 16px">Assign Task</h3>' +
    '<input id="new-task-title" placeholder="Task Title" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
    '<textarea id="new-task-desc" placeholder="Description" rows="3" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px;resize:vertical"></textarea>' +
    '<select id="new-task-assignee" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
      '<option value="">Unassigned</option>' +
      agents.map(function(a){ return '<option value="'+a.id+'">'+esc(a.role+'-'+a.name)+'</option>'; }).join('') +
    '</select>' +
    '<select id="new-task-priority" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
      '<option value="0">Normal Priority</option><option value="1">High Priority</option><option value="2">Urgent</option>' +
    '</select>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end">' +
      '<button class="btn btn-ghost" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-primary" onclick="createProjectTask(\''+projId+'\')">Assign</button>' +
    '</div></div>';
  showModalHTML(html);
}

async function createProjectTask(projId) {
  var title = document.getElementById('new-task-title').value.trim();
  if (!title) { alert('Title required'); return; }
  var desc = document.getElementById('new-task-desc').value.trim();
  var assignee = document.getElementById('new-task-assignee').value;
  var priority = parseInt(document.getElementById('new-task-priority').value)||0;
  try {
    await api('POST', '/api/portal/projects/'+projId+'/tasks', {
      title: title, description: desc, assigned_to: assignee, priority: priority
    });
    closeModal();
    renderProjectDetail(projId);
    // Poll for agent responses if assigned
    if (assignee) {
      if (_projectChatPoll) clearInterval(_projectChatPoll);
      var pollCount = 0;
      _projectChatPoll = setInterval(function() {
        loadProjectChat(projId);
        pollCount++;
        if (pollCount > 30) clearInterval(_projectChatPoll);
      }, 2000);
    }
  } catch(e) { alert('Error: '+e.message); }
}


function showProjectMilestoneModal(projId) {
  var html = '<div style="padding:24px"><h3 style="margin:0 0 16px">Create Milestone</h3>' +
    '<input id="new-milestone-name" placeholder="Milestone Name" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
    '<select id="new-milestone-agent" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
      '<option value="">Select Responsible Agent</option>' +
      agents.map(function(a){ return '<option value="'+a.id+'">'+esc(a.role+'-'+a.name)+'</option>'; }).join('') +
    '</select>' +
    '<input id="new-milestone-duedate" type="date" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
    '<div style="display:flex;gap:8px;justify-content:flex-end">' +
      '<button class="btn btn-ghost" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-primary" onclick="createProjectMilestone(\''+projId+'\')">Create</button>' +
    '</div></div>';
  showModalHTML(html);
}

async function createProjectMilestone(projId) {
  var name = document.getElementById('new-milestone-name').value.trim();
  if (!name) { alert('Name required'); return; }
  var agentId = document.getElementById('new-milestone-agent').value;
  var dueDate = document.getElementById('new-milestone-duedate').value;
  try {
    await api('POST', '/api/portal/projects/'+projId+'/milestones', {
      name: name, responsible_agent_id: agentId, due_date: dueDate
    });
    closeModal();
    renderProjectDetail(projId);
  } catch(e) { alert('Error: '+e.message); }
}

function showMilestoneUpdateModal(projId, milestoneId, milestoneName, currentStatus) {
  var newStatus = currentStatus === 'completed' ? 'in_progress' : currentStatus === 'in_progress' ? 'pending' : 'in_progress';
  var html = '<div style="padding:24px"><h3 style="margin:0 0 16px">Update Milestone</h3>' +
    '<div style="margin-bottom:16px"><div style="font-size:13px;font-weight:600;margin-bottom:8px">Current Status: '+currentStatus.toUpperCase()+'</div>' +
    '<select id="milestone-status-select" style="width:100%;padding:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
      '<option value="pending" '+(currentStatus==='pending'?'selected':'')+'>Pending</option>' +
      '<option value="in_progress" '+(currentStatus==='in_progress'?'selected':'')+'>In Progress</option>' +
      '<option value="completed" '+(currentStatus==='completed'?'selected':'')+'>Completed</option>' +
    '</select></div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end">' +
      '<button class="btn btn-ghost" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-primary" onclick="updateProjectMilestone(\''+projId+'\',\''+milestoneId+'\')">Save</button>' +
    '</div></div>';
  showModalHTML(html);
}

async function updateProjectMilestone(projId, milestoneId) {
  var newStatus = document.getElementById('milestone-status-select').value;
  try {
    await api('POST', '/api/portal/projects/'+projId+'/milestones/'+milestoneId+'/update', {
      milestone_id: milestoneId, status: newStatus
    });
    closeModal();
    renderProjectDetail(projId);
  } catch(e) { alert('Error: '+e.message); }
