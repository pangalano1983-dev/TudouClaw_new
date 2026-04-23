}

// ============ Dashboard ============
function _dashFmtTokens(n) {
  if (!n || n === 0) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return '' + n;
}

function renderDashboard() {
  var c = document.getElementById('content');
  var epoch = _renderEpoch;
  var idle = agents.filter(function(a){return a.status==='idle'}).length;
  var busy = agents.filter(function(a){return a.status==='busy'}).length;
  var errorA = agents.filter(function(a){return a.status==='error'}).length;
  var safeApprovals = Array.isArray(approvals) ? approvals : [].concat((approvals||{}).pending||[]).concat((approvals||{}).history||[]);
  var pending = safeApprovals.filter(function(a){return a.status==='pending'}).length;

  // Token totals: separate In (sent to model) and Out (returned by model)
  var tokensIn = 0, tokensOut = 0;
  agents.forEach(function(a) {
    var tu = a.cost_summary || {};
    tokensIn += (tu.input_tokens || 0);
    tokensOut += (tu.output_tokens || 0);
  });
  var tokensTotal = tokensIn + tokensOut;

  var statusOrb = function(s) {
    if(s==='idle') return 'background:#3fb950;box-shadow:0 0 8px rgba(63,185,80,0.5)';
    if(s==='busy') return 'background:#d29922;box-shadow:0 0 8px rgba(210,153,34,0.5);animation:pulse 1.5s infinite';
    if(s==='error') return 'background:#f85149;box-shadow:0 0 8px rgba(248,81,73,0.5)';
    return 'background:var(--text3)';
  };
  var statusLabel = function(s, a) {
    if (s === 'busy') return 'Working';
    if (a && a.self_improvement && a.self_improvement.is_learning) return 'Learning';
    if (s === 'idle') return 'Online';
    if (s === 'error') return 'Error';
    return 'Offline';
  };

  // Build robot avatar helper
  var robotSrc = function(a) {
    var rid = a.robot_avatar || ('robot_' + (a.role || 'general'));
    return '/static/robots/' + rid + '.svg';
  };

  c.innerHTML = `
    <!-- Header -->
    <div style="margin-bottom:24px">
      <h2 style="font-family:'Plus Jakarta Sans',sans-serif;font-size:26px;font-weight:800;letter-spacing:-0.5px;line-height:1.2">System Overview</h2>
      <p style="color:var(--text3);font-size:13px;margin-top:4px">Tudou Claw — Multi-Agent Coordination Hub</p>
    </div>

    <!-- Row 1: 6 metric cards (clickable) -->
    <section style="display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:24px">
      <div style="background:var(--surface);border-radius:12px;padding:16px;border:1px solid var(--border-light);text-align:center;cursor:pointer;transition:all 0.15s"
           onclick="_settingsSubTab='nodes';showView('settings',null)"
           onmouseenter="this.style.borderColor='rgba(203,201,255,0.3)';this.style.transform='translateY(-2px)'"
           onmouseleave="this.style.borderColor='var(--border-light)';this.style.transform='none'">
        <div style="font-size:9px;color:var(--text3);text-transform:uppercase;font-weight:700;letter-spacing:1px;margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Agents</div>
        <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:28px;font-weight:800;color:var(--primary);line-height:1">${agents.length}</div>
        <div style="display:flex;justify-content:center;gap:8px;margin-top:8px">
          <span style="font-size:10px;color:#3fb950;font-weight:600">${idle}<span style="color:var(--text3);font-weight:400"> on</span></span>
          <span style="font-size:10px;color:#d29922;font-weight:600">${busy}<span style="color:var(--text3);font-weight:400"> busy</span></span>
          <span style="font-size:10px;color:#f85149;font-weight:600">${errorA}<span style="color:var(--text3);font-weight:400"> err</span></span>
        </div>
      </div>
      <div style="background:var(--surface);border-radius:12px;padding:16px;border:1px solid var(--border-light);text-align:center;cursor:pointer;transition:all 0.15s"
           onclick="showView('projects',null)"
           onmouseenter="this.style.borderColor='rgba(63,185,80,0.3)';this.style.transform='translateY(-2px)'"
           onmouseleave="this.style.borderColor='var(--border-light)';this.style.transform='none'">
        <div style="font-size:9px;color:var(--text3);text-transform:uppercase;font-weight:700;letter-spacing:1px;margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Projects</div>
        <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:28px;font-weight:800;color:var(--success);line-height:1" id="dash-project-count">-</div>
        <div style="font-size:10px;color:var(--text3);margin-top:8px">active</div>
      </div>
      <div style="background:var(--surface);border-radius:12px;padding:16px;border:1px solid var(--border-light);text-align:center;cursor:pointer;transition:all 0.15s"
           onclick="_settingsSubTab='providers';showView('settings',null)"
           onmouseenter="this.style.borderColor='rgba(33,150,243,0.3)';this.style.transform='translateY(-2px)'"
           onmouseleave="this.style.borderColor='var(--border-light)';this.style.transform='none'">
        <div style="font-size:9px;color:var(--text3);text-transform:uppercase;font-weight:700;letter-spacing:1px;margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Tokens In</div>
        <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:28px;font-weight:800;color:#2196F3;line-height:1">${_dashFmtTokens(tokensIn)}</div>
        <div style="font-size:10px;color:var(--text3);margin-top:8px">sent to model</div>
      </div>
      <div style="background:var(--surface);border-radius:12px;padding:16px;border:1px solid var(--border-light);text-align:center;cursor:pointer;transition:all 0.15s"
           onclick="_settingsSubTab='providers';showView('settings',null)"
           onmouseenter="this.style.borderColor='rgba(76,175,80,0.3)';this.style.transform='translateY(-2px)'"
           onmouseleave="this.style.borderColor='var(--border-light)';this.style.transform='none'">
        <div style="font-size:9px;color:var(--text3);text-transform:uppercase;font-weight:700;letter-spacing:1px;margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Tokens Out</div>
        <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:28px;font-weight:800;color:#4CAF50;line-height:1">${_dashFmtTokens(tokensOut)}</div>
        <div style="font-size:10px;color:var(--text3);margin-top:8px">from model</div>
      </div>
      <div style="background:var(--surface);border-radius:12px;padding:16px;border:1px solid var(--border-light);text-align:center;cursor:pointer;transition:all 0.15s"
           onclick="_settingsSubTab='providers';showView('settings',null)"
           onmouseenter="this.style.borderColor='rgba(255,255,255,0.1)';this.style.transform='translateY(-2px)'"
           onmouseleave="this.style.borderColor='var(--border-light)';this.style.transform='none'">
        <div style="font-size:9px;color:var(--text3);text-transform:uppercase;font-weight:700;letter-spacing:1px;margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Tokens Total</div>
        <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:28px;font-weight:800;color:var(--text);line-height:1">${_dashFmtTokens(tokensTotal)}</div>
        <div style="font-size:10px;color:var(--text3);margin-top:8px">all agents</div>
      </div>
      <div style="background:var(--surface);border-radius:12px;padding:16px;border:1px solid var(--border-light);text-align:center;cursor:pointer;transition:all 0.15s"
           onclick="showView('approvals',null)"
           onmouseenter="this.style.borderColor='${pending>0?'rgba(210,153,34,0.3)':'rgba(255,255,255,0.1)'}';this.style.transform='translateY(-2px)'"
           onmouseleave="this.style.borderColor='var(--border-light)';this.style.transform='none'">
        <div style="font-size:9px;color:var(--text3);text-transform:uppercase;font-weight:700;letter-spacing:1px;margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Approvals</div>
        <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:28px;font-weight:800;color:${pending>0?'var(--warning)':'var(--text)'};line-height:1">${pending}</div>
        <div style="font-size:10px;color:var(--text3);margin-top:8px">pending</div>
      </div>
    </section>

    <!-- Row 2: Agent Cards (full width, responsive grid) -->
    <section style="margin-bottom:24px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text);font-family:'Plus Jakarta Sans',sans-serif">Active Agents</h3>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px">
        ${agents.map(a => {
          var tu = a.cost_summary || {};
          var aIn = tu.input_tokens || 0;
          var aOut = tu.output_tokens || 0;
          // Unified model label — same helper used by chat header, info cards,
          // agent list, so the same raw ID always shortens to the same label.
          var _pp = window._prettyModelLabel || function(x){
            return (x||'default').split('/').pop().split(':')[0];
          };
          var modelShort = _pp(a.model) || 'default';
          if (modelShort.length > 16) modelShort = modelShort.substring(0,14) + '..';
          return `
          <div style="background:var(--surface);padding:12px 14px;border-radius:10px;border:1px solid var(--border-light);cursor:pointer;transition:all 0.15s;display:flex;align-items:center;gap:10px;overflow:hidden"
               onclick="showAgentView('${a.id}',null)"
               onmouseenter="this.style.borderColor='rgba(203,201,255,0.2)';this.style.transform='translateY(-1px)'"
               onmouseleave="this.style.borderColor='var(--border-light)';this.style.transform='none'">
            <img src="${robotSrc(a)}" style="width:32px;height:32px;border-radius:8px;flex-shrink:0;background:var(--surface3)" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" alt="">
            <div style="width:32px;height:32px;border-radius:8px;background:var(--surface3);display:none;align-items:center;justify-content:center;flex-shrink:0">
              <span class="material-symbols-outlined" style="font-size:18px;color:var(--primary)">smart_toy</span>
            </div>
            <div style="flex:1;min-width:0">
              <div style="font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%">${esc(a.name)}</div>
              <div style="display:flex;align-items:center;gap:5px;margin-top:2px">
                <span style="width:5px;height:5px;border-radius:50%;display:inline-block;flex-shrink:0;${statusOrb(a.status)}"></span>
                <span style="font-size:9px;color:var(--text3);text-transform:uppercase;font-weight:600">${statusLabel(a.status, a)}</span>
                <span style="font-size:9px;color:var(--text3);margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:80px" title="${esc(a.model||'default')}">${esc(modelShort)}</span>
              </div>
            </div>
            <div style="text-align:right;flex-shrink:0;border-left:1px solid var(--border-light);padding-left:10px;min-width:52px">
              <div style="font-size:9px;color:#2196F3;font-family:monospace;white-space:nowrap">${_dashFmtTokens(aIn)} in</div>
              <div style="font-size:9px;color:#4CAF50;font-family:monospace;white-space:nowrap;margin-top:1px">${_dashFmtTokens(aOut)} out</div>
            </div>
          </div>`;
        }).join('')}
        ${agents.length === 0 ? '<div style="color:var(--text3);padding:20px;grid-column:1/-1;font-size:13px">No agents deployed. Click "Deploy Agent" to create one.</div>' : ''}
      </div>
    </section>

    <!-- Row 3: Projects Status -->
    <section style="margin-bottom:24px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text);font-family:'Plus Jakarta Sans',sans-serif">Projects</h3>
        <span style="color:var(--primary);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;cursor:pointer" onclick="showView('projects',null)">View All</span>
      </div>
      <div id="dash-projects-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px">
        <div style="color:var(--text3);font-size:13px;padding:16px">Loading projects...</div>
      </div>
    </section>

    <!-- Row 3.5: Pending Manual Review (only renders when there are items) -->
    <section id="dash-review-section" style="margin-bottom:24px;display:none">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text);font-family:'Plus Jakarta Sans',sans-serif">
          <span style="color:#3b82f6">⏸ Pending Manual Review</span>
          <span id="dash-review-count" style="background:#3b82f6;color:#000;padding:1px 8px;border-radius:10px;font-size:10px;margin-left:8px;font-weight:800">0</span>
        </h3>
      </div>
      <div id="dash-review-list" style="display:flex;flex-direction:column;gap:8px"></div>
    </section>

    <!-- Row 4: System Modules (4 cards in a row) -->
    <section style="margin-bottom:24px">
      <h3 style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;font-family:'Plus Jakarta Sans',sans-serif">System Modules</h3>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px" id="dashboard-modules">
        <div style="background:var(--surface);border-radius:10px;padding:18px;border:1px solid var(--border-light);cursor:pointer;transition:all 0.15s"
             onclick="showView('nodes',null)"
             onmouseenter="this.style.borderColor='rgba(203,201,255,0.2)'" onmouseleave="this.style.borderColor='var(--border-light)'">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <span class="material-symbols-outlined" style="font-size:18px;color:var(--primary);flex-shrink:0">hub</span>
            <span style="font-size:12px;font-weight:600">Nodes</span>
          </div>
          <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:24px;font-weight:800;color:var(--text);line-height:1">${nodes.length}</div>
          <div style="font-size:10px;color:var(--text3);margin-top:6px">${nodes.filter(n=>n.status==='online').length} online</div>
        </div>
        <div style="background:var(--surface);border-radius:10px;padding:18px;border:1px solid var(--border-light);cursor:pointer;transition:all 0.15s"
             onclick="showView('channels',null)"
             onmouseenter="this.style.borderColor='rgba(203,201,255,0.2)'" onmouseleave="this.style.borderColor='var(--border-light)'">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <span class="material-symbols-outlined" style="font-size:18px;color:var(--primary);flex-shrink:0">cable</span>
            <span style="font-size:12px;font-weight:600">Channels</span>
          </div>
          <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:24px;font-weight:800;color:var(--text);line-height:1" id="dash-channel-count">-</div>
          <div style="font-size:10px;color:var(--text3);margin-top:6px">IM integrations</div>
        </div>
        <div style="background:var(--surface);border-radius:10px;padding:18px;border:1px solid var(--border-light);cursor:pointer;transition:all 0.15s"
             onclick="showView('providers',null)"
             onmouseenter="this.style.borderColor='rgba(203,201,255,0.2)'" onmouseleave="this.style.borderColor='var(--border-light)'">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <span class="material-symbols-outlined" style="font-size:18px;color:var(--primary);flex-shrink:0">dns</span>
            <span style="font-size:12px;font-weight:600">Providers</span>
          </div>
          <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:24px;font-weight:800;color:var(--text);line-height:1" id="dash-provider-count">-</div>
          <div style="font-size:10px;color:var(--text3);margin-top:6px">model backends</div>
        </div>
        <div style="background:var(--surface);border-radius:10px;padding:18px;border:1px solid var(--border-light);cursor:pointer;transition:all 0.15s"
             onclick="showView('approvals',null)"
             onmouseenter="this.style.borderColor='rgba(203,201,255,0.2)'" onmouseleave="this.style.borderColor='var(--border-light)'">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <span class="material-symbols-outlined" style="font-size:18px;color:${pending>0?'var(--warning)':'var(--primary)'};flex-shrink:0">shield</span>
            <span style="font-size:12px;font-weight:600">Approvals</span>
          </div>
          <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:24px;font-weight:800;color:${pending>0?'var(--warning)':'var(--text)'};line-height:1">${pending}</div>
          <div style="font-size:10px;color:var(--text3);margin-top:6px">pending</div>
        </div>
      </div>
    </section>
  `;

  // Async: load counts
  api('GET', '/api/portal/channels').then(data => {
    if (epoch !== _renderEpoch) return;
    const el = document.getElementById('dash-channel-count');
    if (el && data) el.textContent = (data.channels||[]).length;
  });
  api('GET', '/api/portal/providers').then(data => {
    if (epoch !== _renderEpoch) return;
    const el = document.getElementById('dash-provider-count');
    if (el && data) el.textContent = (data.providers||[]).length;
  });
  // Async: load projects for dashboard
  api('GET', '/api/portal/projects').then(async function(data) {
    if (epoch !== _renderEpoch) return;
    var grid = document.getElementById('dash-projects-grid');
    if (!grid || !data) return;
    var projects = data.projects || [];
    var countEl = document.getElementById('dash-project-count');
    if (countEl) countEl.textContent = projects.length;

    // ── Build pending-manual-review list ──
    // Prefer the dedicated endpoint (always fresh, always includes steps).
    // Fall back to walking the projects list when the endpoint hasn't run yet.
    var reviewItems = [];
    try {
      var prResp = await api('GET', '/api/portal/pending-reviews');
      if (prResp && prResp.items) {
        reviewItems = prResp.items.map(function(it) {
          return {
            proj_id: it.proj_id, proj_name: it.proj_name,
            task_id: it.task_id, task_title: it.task_title,
            assignee: it.assignee, step: it.step,
          };
        });
      }
    } catch(_e) {
      projects.forEach(function(p) {
        (p.tasks || []).forEach(function(t) {
          (t.steps || []).forEach(function(s) {
            if (s.status === 'awaiting_review') {
              reviewItems.push({
                proj_id: p.id, proj_name: p.name,
                task_id: t.id, task_title: t.title,
                assignee: t.assigned_to,
                step: s,
              });
            }
          });
        });
      });
    }
    var revSection = document.getElementById('dash-review-section');
    var revList = document.getElementById('dash-review-list');
    var revCount = document.getElementById('dash-review-count');
    if (revSection && revList) {
      if (reviewItems.length === 0) {
        revSection.style.display = 'none';
      } else {
        revSection.style.display = '';
        if (revCount) revCount.textContent = reviewItems.length;
        // Sort: oldest first (so the longest-waiting bubble to top)
        reviewItems.sort(function(a, b){
          return (a.step.completed_at || 0) - (b.step.completed_at || 0);
        });
        revList.innerHTML = reviewItems.map(function(it) {
          var ag = agents.find(function(a){ return a.id === it.assignee; });
          var assigneeName = ag ? (ag.role + '-' + ag.name) : (it.assignee || '?');
          var waitMin = '';
          if (it.step.completed_at) {
            var secs = Math.floor(Date.now()/1000 - it.step.completed_at);
            if (secs < 60) waitMin = secs + 's';
            else if (secs < 3600) waitMin = Math.floor(secs/60) + 'm';
            else if (secs < 86400) waitMin = Math.floor(secs/3600) + 'h';
            else waitMin = Math.floor(secs/86400) + 'd';
          }
          var draft = String(it.step.result || '').slice(0, 240);
          if ((it.step.result || '').length > 240) draft += '…';
          return '<div style="background:var(--surface);border-left:3px solid #3b82f6;border-radius:8px;padding:12px 14px;border:1px solid rgba(59,130,246,0.25)">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;gap:8px;flex-wrap:wrap">' +
              '<div style="font-size:12px;font-weight:700;display:flex;align-items:center;gap:6px;flex-wrap:wrap">' +
                '<span style="color:var(--primary);cursor:pointer" onclick="openProject(\''+it.proj_id+'\')">📁 '+esc(it.proj_name)+'</span>' +
                '<span style="color:var(--text3)">›</span>' +
                '<span>'+esc(it.task_title)+'</span>' +
                '<span style="color:var(--text3)">›</span>' +
                '<span style="color:#3b82f6">'+esc(it.step.name)+'</span>' +
                '<span style="font-size:9px;background:rgba(59,130,246,0.15);color:#3b82f6;padding:1px 5px;border-radius:3px;margin-left:2px">👤 人工</span>' +
              '</div>' +
              '<div style="font-size:10px;color:var(--text3);display:flex;gap:8px;align-items:center">' +
                '<span>by '+esc(assigneeName)+'</span>' +
                (waitMin ? '<span title="等待时长">⏱ '+waitMin+'</span>' : '') +
              '</div>' +
            '</div>' +
            (draft ? '<div style="font-size:11px;color:var(--text2);background:rgba(59,130,246,0.06);border-radius:4px;padding:8px 10px;margin:6px 0;line-height:1.5;max-height:80px;overflow:hidden">'+esc(draft)+'</div>' : '') +
            '<div style="display:flex;gap:6px;justify-content:flex-end;margin-top:8px">' +
              '<button onclick="reviewStep(\''+esc(it.proj_id)+'\',\''+esc(it.task_id)+'\',\''+esc(it.step.id)+'\',\'reject\')" style="font-size:11px;background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.4);border-radius:4px;padding:4px 12px;cursor:pointer;font-weight:600">✗ 驳回</button>' +
              '<button onclick="reviewStep(\''+esc(it.proj_id)+'\',\''+esc(it.task_id)+'\',\''+esc(it.step.id)+'\',\'approve\')" style="font-size:11px;background:#22c55e;color:#000;border:none;border-radius:4px;padding:4px 14px;cursor:pointer;font-weight:700">✓ 通过</button>' +
              '<button onclick="openProject(\''+esc(it.proj_id)+'\')" style="font-size:11px;background:transparent;color:var(--text3);border:1px solid rgba(255,255,255,0.1);border-radius:4px;padding:4px 10px;cursor:pointer">查看</button>' +
            '</div>' +
          '</div>';
        }).join('');
      }
    }
    if (projects.length === 0) {
      grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:24px;color:var(--text3);font-size:13px">No projects yet. <span style="color:var(--primary);cursor:pointer;font-weight:600" onclick="showView(\'projects\',null)">Create one</span></div>';
      return;
    }
    grid.innerHTML = projects.map(function(p) {
      var memberCount = (p.members||[]).length;
      var taskCount = (p.tasks||[]).length;
      var doneTasks = (p.tasks||[]).filter(function(t){return t.status==='done'}).length;
      var inProgress = (p.tasks||[]).filter(function(t){return t.status==='in_progress'}).length;
      var progress = taskCount > 0 ? Math.round(doneTasks / taskCount * 100) : 0;
      var progressColor = progress >= 100 ? 'var(--success)' : progress > 0 ? 'var(--primary)' : 'var(--text3)';
      // Build member avatars
      var memberAvatars = (p.members||[]).slice(0,5).map(function(m) {
        var ag = agents.find(function(a){ return a.id === m.agent_id; });
        var initial = ag ? (ag.name||'?')[0] : '?';
        return '<div style="width:26px;height:26px;border-radius:50%;background:var(--surface3);border:2px solid var(--bg);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:var(--primary);margin-left:-6px" title="'+esc(ag?(ag.role+'-'+ag.name):m.agent_id)+'">'+esc(initial)+'</div>';
      }).join('');
      var extraMembers = memberCount > 5 ? '<div style="width:26px;height:26px;border-radius:50%;background:var(--surface3);border:2px solid var(--bg);display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;color:var(--text3);margin-left:-6px">+' + (memberCount-5) + '</div>' : '';
      return '<div style="background:var(--surface);border-radius:14px;padding:20px;border:1px solid var(--border-light);cursor:pointer;transition:all 0.15s" onclick="openProject(\''+p.id+'\')" onmouseenter="this.style.borderColor=\'rgba(203,201,255,0.2)\';this.style.transform=\'translateY(-2px)\'" onmouseleave="this.style.borderColor=\'var(--border-light)\';this.style.transform=\'none\'">' +
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">' +
          '<div>' +
            '<div style="font-size:15px;font-weight:700;letter-spacing:0.1px">' + esc(p.name) + '</div>' +
            '<div style="font-size:11px;color:var(--text3);margin-top:2px;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(p.description||'No description') + '</div>' +
          '</div>' +
          '<div style="display:flex;align-items:center;gap:4px;flex-shrink:0">' +
            '<span class="material-symbols-outlined" style="font-size:16px;color:var(--primary)">folder</span>' +
          '</div>' +
        '</div>' +
        '<!-- Progress -->' +
        '<div style="margin-bottom:12px">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">' +
            '<span style="font-size:10px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px">Progress</span>' +
            '<span style="font-size:11px;font-weight:700;color:' + progressColor + '">' + progress + '%</span>' +
          '</div>' +
          '<div style="width:100%;height:5px;background:var(--surface3);border-radius:4px;overflow:hidden">' +
            '<div style="height:100%;background:' + progressColor + ';border-radius:4px;transition:width 0.3s;width:' + progress + '%"></div>' +
          '</div>' +
        '</div>' +
        '<!-- Members + Tasks Row -->' +
        '<div style="display:flex;justify-content:space-between;align-items:center">' +
          '<div style="display:flex;align-items:center;padding-left:6px">' + memberAvatars + extraMembers + '</div>' +
          '<div style="display:flex;gap:12px;font-size:10px;color:var(--text3)">' +
            '<span title="In Progress"><span class="material-symbols-outlined" style="font-size:13px;vertical-align:middle;color:var(--warning)">pending</span> ' + inProgress + '</span>' +
            '<span title="Done"><span class="material-symbols-outlined" style="font-size:13px;vertical-align:middle;color:var(--success)">check_circle</span> ' + doneTasks + '/' + taskCount + '</span>' +
          '</div>' +
        '</div>' +
      '</div>';
    }).join('');
  });
