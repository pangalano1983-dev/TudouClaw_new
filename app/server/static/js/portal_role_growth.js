}

// ============ Role Growth Path Panel ============
async function showGrowthPathPanel(agentId) {
  const data = await api('GET', '/api/portal/agent/' + agentId + '/growth');
  let html = '<div style="padding:20px;max-width:800px;min-width:560px">';
  html += '<h3 style="margin-bottom:4px"><span class="material-symbols-outlined" style="vertical-align:middle;color:rgb(251,146,60)">school</span> Role Growth Path</h3>';
  if (!data || !data.growth_path) {
    html += '<div style="color:var(--text3);font-size:13px;margin:16px 0">' + (data && data.message ? esc(data.message) : 'No growth path available.') + '</div>';
    html += '<button class="btn" onclick="initGrowthPath(\'' + agentId + '\')">Initialize Growth Path</button>';
  } else {
    var gp = data.growth_path;
    var summary = data.summary;
    html += '<div style="font-size:11px;color:var(--text3);margin-bottom:16px">' + esc(summary.role_name) + ' — ' + esc(summary.current_stage) + ' (' + summary.overall_progress + '% overall)</div>';
    html += '<div style="background:var(--surface2);border-radius:6px;height:8px;margin-bottom:20px;overflow:hidden">';
    html += '<div style="background:linear-gradient(90deg,rgb(251,146,60),rgb(234,88,12));height:100%;width:' + summary.overall_progress + '%;border-radius:6px;transition:width 0.3s"></div></div>';
    gp.stages.forEach(function(stage, idx) {
      var isCurrent = idx === gp.current_stage_idx;
      var borderColor = isCurrent ? 'rgba(251,146,60,0.5)' : 'var(--border)';
      var bgColor = isCurrent ? 'rgba(251,146,60,0.04)' : 'var(--surface)';
      html += '<div style="background:' + bgColor + ';border:1px solid ' + borderColor + ';border-radius:10px;padding:14px 16px;margin-bottom:12px">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">';
      html += '<div style="display:flex;align-items:center;gap:8px">';
      if (isCurrent) html += '<span style="font-size:12px;background:rgba(251,146,60,0.15);color:rgb(251,146,60);padding:2px 8px;border-radius:4px;font-weight:700">CURRENT</span>';
      html += '<span style="font-size:14px;font-weight:700">' + esc(stage.name) + '</span>';
      html += '</div>';
      html += '<span style="font-size:12px;color:var(--text3)">' + stage.completion_rate + '%</span>';
      html += '</div>';
      html += '<div style="background:var(--surface2);border-radius:4px;height:4px;margin-bottom:10px;overflow:hidden">';
      html += '<div style="background:rgb(251,146,60);height:100%;width:' + stage.completion_rate + '%;border-radius:4px"></div></div>';
      stage.objectives.forEach(function(obj) {
        var check = obj.completed ? '✅' : '⬜';
        html += '<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:4px;font-size:12px">';
        html += '<span style="flex-shrink:0">' + check + '</span>';
        html += '<span style="color:' + (obj.completed ? 'var(--text3)' : 'var(--text)') + '">' + esc(obj.title) + '</span>';
        if (!obj.completed && isCurrent) {
          html += '<button class="btn btn-sm" style="margin-left:auto;font-size:10px;padding:2px 8px" onclick="completeObjective(\'' + agentId + '\',\'' + obj.id + '\')">Complete</button>';
        }
        html += '</div>';
      });
      html += '</div>';
    });
    html += '<div style="display:flex;gap:10px;margin-top:16px">';
    html += '<button class="btn" onclick="triggerGrowthLearning(\'' + agentId + '\')"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">auto_stories</span> Trigger Learning</button>';
    html += '<button class="btn btn-ghost" onclick="closeModal()">Close</button>';
    html += '</div>';
  }
  html += '</div>';
  showModalHTML(html);
}
async function initGrowthPath(agentId) {
  await api('POST', '/api/portal/agent/' + agentId + '/growth', {action: 'init'});
  showGrowthPathPanel(agentId);
}
async function completeObjective(agentId, objectiveId) {
  const result = await api('POST', '/api/portal/agent/' + agentId + '/growth', {action: 'complete_objective', objective_id: objectiveId});
  if (result && result.advanced) { showToast('Advanced to next stage!', 'success'); }
  showGrowthPathPanel(agentId);
}
async function triggerGrowthLearning(agentId) {
  const result = await api('POST', '/api/portal/agent/' + agentId + '/growth', {action: 'trigger_learning'});
  if (result && result.ok && result.objective) {
    let html = '<div style="padding:20px;max-width:650px">';
    html += '<h3><span class="material-symbols-outlined" style="vertical-align:middle;color:rgb(251,146,60)">auto_stories</span> Learning Task</h3>';
    html += '<div style="font-size:13px;font-weight:600;margin:12px 0">' + esc(result.objective.title) + '</div>';
    html += '<div style="font-size:11px;color:var(--text2);margin-bottom:12px">' + esc(result.objective.description) + '</div>';
    html += '<pre style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;font-size:11px;white-space:pre-wrap;max-height:300px;overflow-y:auto">' + esc(result.learning_prompt) + '</pre>';
    html += '<div style="margin-top:16px"><button class="btn" onclick="closeModal()">Close</button></div>';
    html += '</div>';
    showModalHTML(html);
  } else {
    showToast(result && result.message ? result.message : 'No pending objectives', 'info');
  }
