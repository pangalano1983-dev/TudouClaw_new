}

// ============ Execution Analysis Panel ============
async function showAnalysisPanel(agentId) {
  const data = await api('GET', '/api/portal/agent/' + agentId + '/analyses');
  let html = '<div style="padding:20px;max-width:750px;min-width:520px">';
  html += '<h3 style="margin-bottom:4px"><span class="material-symbols-outlined" style="vertical-align:middle;color:#34d399">analytics</span> Execution Analysis</h3>';
  html += '<div style="font-size:11px;color:var(--text3);margin-bottom:16px">Auto-analysis of recent task executions</div>';
  var analyses = (data && data.analyses) || [];
  if (!analyses.length) {
    html += '<div style="color:var(--text3);font-size:13px">No analyses yet. Analyses are generated automatically after each chat interaction.</div>';
  } else {
    analyses.forEach(function(a) {
      var ratingColor = a.auto_rating >= 4 ? '#10b981' : a.auto_rating >= 3 ? '#f59e0b' : '#ef4444';
      var statusIcon = a.task_completed ? '✅' : '❌';
      html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin-bottom:10px">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">';
      html += '<div style="font-size:13px;font-weight:600">' + statusIcon + ' ' + esc(a.task_id) + '</div>';
      html += '<div style="display:flex;align-items:center;gap:8px">';
      html += '<span style="font-size:12px;color:' + ratingColor + ';font-weight:700">' + '★'.repeat(a.auto_rating) + '<span style="color:var(--text3)">' + '★'.repeat(5-a.auto_rating) + '</span></span>';
      html += '<span style="font-size:10px;color:var(--text3)">' + new Date(a.analyzed_at*1000).toLocaleString() + '</span>';
      html += '</div></div>';
      html += '<div style="font-size:11px;color:var(--text2);margin-bottom:6px">' + esc(a.execution_note) + '</div>';
      html += '<div style="display:flex;gap:12px;font-size:10px;color:var(--text3)">';
      html += '<span>Tools: ' + a.tool_call_count + '</span>';
      html += '<span>Errors: ' + a.error_count + '</span>';
      html += '<span>Duration: ' + a.total_duration.toFixed(1) + 's</span>';
      if (a.inferred_skill_tags && a.inferred_skill_tags.length) {
        html += '<span>Skills: ' + a.inferred_skill_tags.join(', ') + '</span>';
      }
      html += '</div>';
      if (a.tool_issues && a.tool_issues.length) {
        html += '<div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.04)">';
        a.tool_issues.forEach(function(ti) {
          var sevColor = ti.severity==='high'?'#ef4444':ti.severity==='medium'?'#f59e0b':'var(--text3)';
          html += '<div style="font-size:10px;color:' + sevColor + '">⚠ ' + esc(ti.tool_name) + ': ' + esc(ti.issue_type) + ' — ' + esc(ti.description) + '</div>';
        });
        html += '</div>';
      }
      html += '</div>';
    });
  }
  html += '<div style="margin-top:16px"><button class="btn" onclick="closeModal()">Close</button></div>';
  html += '</div>';
  showModalHTML(html);
