// ============ Pending Skills / SkillForge Drafts ============
var _pendingSkillsState = { status: '', drafts: [] };

// ---------- inline toast helper ----------
function _sfToast(msg, type) {
  var old = document.getElementById('sf-toast');
  if (old) old.remove();
  var bg = type === 'ok' ? '#10b981' : type === 'err' ? '#ef4444' : '#60a5fa';
  var el = document.createElement('div');
  el.id = 'sf-toast';
  el.style.cssText = 'position:fixed;top:24px;left:50%;transform:translateX(-50%);z-index:99999;'
    + 'padding:10px 24px;border-radius:8px;font-size:13px;color:#fff;background:' + bg + ';'
    + 'box-shadow:0 4px 16px rgba(0,0,0,.3);transition:opacity .4s;opacity:1';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(function(){ el.style.opacity = '0'; }, 3000);
  setTimeout(function(){ el.remove(); }, 3500);
}

async function renderPendingSkills() {
  var c = document.getElementById('content');
  c.innerHTML = ''
    + '<div style="padding:18px">'
    + '  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;gap:12px">'
    + '    <div><h2 style="margin:0">技能锻造 / SkillForge Drafts</h2>'
    + '      <div style="font-size:12px;color:var(--text3);margin-top:4px">Agent 从经验库中提炼出的技能草稿，等待管理员审核后导入技能商店。</div>'
    + '    </div>'
    + '    <button class="btn btn-sm" onclick="loadPendingSkills()"><span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle">refresh</span> 刷新</button>'
    + '  </div>'
    + '  <div style="display:flex;gap:10px;margin-bottom:12px">'
    + '    <select id="pending-status-filter" onchange="_pendingSkillsState.status=this.value;loadPendingSkills()" style="padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text)">'
    + '      <option value="">全部状态</option>'
    + '      <option value="draft">draft 草稿</option>'
    + '      <option value="exported">exported 已导出</option>'
    + '      <option value="approved">approved 已批准</option>'
    + '      <option value="rejected">rejected 已拒绝</option>'
    + '    </select>'
    + '  </div>'
    + '  <div id="pending-list" style="color:var(--text3)">加载中…</div>'
    + '</div>';
  loadPendingSkills();
}

async function loadPendingSkills() {
  var box = document.getElementById('pending-list');
  if (!box) return;
  var params = [];
  if (_pendingSkillsState.status) params.push('status=' + encodeURIComponent(_pendingSkillsState.status));
  var qs = params.length ? ('?' + params.join('&')) : '';
  try {
    var data = await api('GET', '/api/portal/pending-skills' + qs);
    _pendingSkillsState.drafts = data.drafts || [];
    if (!_pendingSkillsState.drafts.length) {
      box.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text3)">'
        + '<span class="material-symbols-outlined" style="font-size:48px;display:block;margin-bottom:8px;opacity:0.3">auto_fix_high</span>'
        + '暂无技能草稿。Agent 积累足够经验后会通过 propose_skill 工具自动生成。</div>';
      return;
    }
    box.innerHTML = _pendingSkillsState.drafts.map(_renderDraftCard).join('');
  } catch (e) {
    box.innerHTML = '<div style="color:var(--error);padding:20px">加载失败: ' + esc(e.message || String(e)) + '</div>';
  }
}

function _renderDraftCard(d) {
  var statusColors = {
    draft: '#60a5fa', exported: '#a78bfa',
    approved: '#10b981', rejected: '#ef4444'
  };
  var statusLabels = {
    draft: '草稿', exported: '待审核',
    approved: '已批准', rejected: '已拒绝'
  };
  var statusColor = statusColors[d.status] || '#94a3b8';
  var statusLabel = statusLabels[d.status] || d.status;
  var runtimeBadge = d.runtime === 'python'
    ? '<span style="padding:2px 6px;font-size:10px;background:rgba(59,130,246,0.15);color:#3b82f6;border-radius:10px">Python</span>'
    : '<span style="padding:2px 6px;font-size:10px;background:rgba(16,185,129,0.15);color:#10b981;border-radius:10px">Markdown</span>';
  var confPct = Math.round((d.confidence || 0) * 100);
  var confColor = confPct >= 80 ? '#10b981' : confPct >= 60 ? '#f59e0b' : '#ef4444';
  var codeCount = d.code_files ? Object.keys(d.code_files).length : 0;
  var dateStr = d.created_at ? new Date(d.created_at * 1000).toLocaleString() : '';

  // Actions differ by status
  var actions = '';
  if (d.status === 'draft' || d.status === 'exported') {
    actions = '<button class="btn btn-sm" style="background:var(--primary);color:#fff" onclick="approveDraft(\'' + esc(d.id) + '\',\'' + esc(d.name) + '\')">批准</button>'
      + '<button class="btn btn-sm" style="color:var(--error)" onclick="rejectDraft(\'' + esc(d.id) + '\',\'' + esc(d.name) + '\')">拒绝</button>';
  } else if (d.status === 'approved') {
    actions = '<span style="display:inline-flex;align-items:center;gap:4px;font-size:12px;color:#10b981;font-weight:600">'
      + '<span class="material-symbols-outlined" style="font-size:16px">check_circle</span> 已批准并导入商店</span>';
  } else if (d.status === 'rejected') {
    actions = '<span style="display:inline-flex;align-items:center;gap:4px;font-size:12px;color:#ef4444;font-weight:600">'
      + '<span class="material-symbols-outlined" style="font-size:16px">cancel</span> 已拒绝</span>';
  }

  return '<div style="border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:10px;background:var(--surface)">'
    + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
    + '  <div style="display:flex;align-items:center;gap:8px">'
    + '    <span style="font-weight:600;font-size:15px">' + esc(d.name) + '</span>'
    + '    <span style="padding:2px 8px;font-size:10px;border-radius:10px;background:' + statusColor + '22;color:' + statusColor + '">' + esc(statusLabel) + '</span>'
    + '    ' + runtimeBadge
    + '  </div>'
    + '  <span style="font-size:11px;color:var(--text3)">' + esc(d.id) + '</span>'
    + '</div>'
    + '<div style="font-size:13px;color:var(--text2);margin-bottom:8px">' + esc(d.description || '') + '</div>'
    + '<div style="display:flex;gap:16px;font-size:12px;color:var(--text3);margin-bottom:10px">'
    + '  <span>置信度: <span style="color:' + confColor + ';font-weight:600">' + confPct + '%</span></span>'
    + '  <span>来源: ' + (d.id && d.id.indexOf('-SUB-') > -1 ? 'Agent 提交' : d.id && d.id.indexOf('-IMP-') > -1 ? 'Agent 工作区导入' : (d.source_experiences && d.source_experiences.length ? d.source_experiences.length + ' 条经验' : '经验提炼')) + '</span>'
    + '  <span>角色: ' + esc(d.role || 'general') + '</span>'
    + (codeCount ? '  <span>代码文件: ' + codeCount + ' 个</span>' : '')
    + '  <span>' + esc(dateStr) + '</span>'
    + '</div>'
    + '<div style="display:flex;gap:8px;align-items:center">'
    + '  <button class="btn btn-sm" onclick="showDraftDetail(\'' + esc(d.id) + '\')"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">visibility</span> 查看详情</button>'
    + actions
    + '</div>'
    + '</div>';
}

async function showDraftDetail(draftId) {
  try {
    var d = await api('GET', '/api/portal/pending-skills/' + encodeURIComponent(draftId));
    var sections = [];

    // Header
    sections.push('<h3 style="margin:0 0 12px 0">' + esc(d.name) + ' <span style="font-size:12px;color:var(--text3)">' + esc(d.id) + '</span></h3>');
    sections.push('<div style="font-size:13px;color:var(--text2);margin-bottom:12px">' + esc(d.description || '') + '</div>');

    // Manifest
    sections.push('<details open style="margin-bottom:12px"><summary style="cursor:pointer;font-weight:600;font-size:13px">manifest.yaml</summary>');
    sections.push('<pre style="background:var(--bg);padding:10px;border-radius:6px;font-size:12px;overflow-x:auto;max-height:300px;border:1px solid var(--border)">' + esc(d.manifest_yaml || '') + '</pre></details>');

    // SKILL.md
    sections.push('<details style="margin-bottom:12px"><summary style="cursor:pointer;font-weight:600;font-size:13px">SKILL.md</summary>');
    sections.push('<pre style="background:var(--bg);padding:10px;border-radius:6px;font-size:12px;overflow-x:auto;max-height:400px;border:1px solid var(--border)">' + esc(d.skill_md || '') + '</pre></details>');

    // Code files
    var codeFiles = d.code_files || {};
    var fileNames = Object.keys(codeFiles);
    if (fileNames.length) {
      fileNames.forEach(function(fn) {
        sections.push('<details style="margin-bottom:12px"><summary style="cursor:pointer;font-weight:600;font-size:13px">' + esc(fn) + '</summary>');
        sections.push('<pre style="background:#1e293b;color:#e2e8f0;padding:10px;border-radius:6px;font-size:12px;overflow-x:auto;max-height:400px;border:1px solid var(--border)">' + esc(codeFiles[fn]) + '</pre></details>');
      });
    }

    // Meta info
    sections.push('<div style="font-size:11px;color:var(--text3);margin-top:8px;border-top:1px solid var(--border);padding-top:8px">'
      + '置信度: ' + Math.round((d.confidence || 0) * 100) + '% · '
      + 'Runtime: ' + esc(d.runtime || 'markdown') + ' · '
      + '来源: ' + (d.id && d.id.indexOf('-SUB-') > -1 ? 'Agent 提交' : d.id && d.id.indexOf('-IMP-') > -1 ? 'Agent 工作区导入' : (d.source_experiences && d.source_experiences.length ? d.source_experiences.length + ' 条经验' : '经验提炼')) + ' · '
      + '触发词: ' + esc((d.triggers || []).join(', '))
      + '</div>');

    // Actions — only show for draft/exported
    if (d.status === 'draft' || d.status === 'exported') {
      sections.push('<div style="display:flex;gap:8px;margin-top:14px;justify-content:flex-end">'
        + '<button class="btn btn-sm" style="background:var(--primary);color:#fff" onclick="closeModal();approveDraft(\'' + esc(d.id) + '\',\'' + esc(d.name) + '\')">批准并导入</button>'
        + '<button class="btn btn-sm" style="color:var(--error)" onclick="closeModal();rejectDraft(\'' + esc(d.id) + '\',\'' + esc(d.name) + '\')">拒绝</button>'
        + '</div>');
    } else if (d.status === 'approved') {
      sections.push('<div style="display:flex;gap:8px;margin-top:14px;justify-content:flex-end;color:#10b981;font-size:13px;font-weight:600">'
        + '<span class="material-symbols-outlined" style="font-size:18px">check_circle</span> 已批准并导入商店</div>');
    } else if (d.status === 'rejected') {
      sections.push('<div style="display:flex;gap:8px;margin-top:14px;justify-content:flex-end;color:#ef4444;font-size:13px;font-weight:600">'
        + '<span class="material-symbols-outlined" style="font-size:18px">cancel</span> 已拒绝</div>');
    }

    showModalHTML('<div style="max-width:700px;max-height:80vh;overflow-y:auto;padding:4px">' + sections.join('') + '</div>');
  } catch (e) {
    _sfToast('加载详情失败: ' + (e.message || String(e)), 'err');
  }
}

async function approveDraft(draftId, draftName) {
  try {
    var res = await api('POST', '/api/portal/pending-skills/' + encodeURIComponent(draftId) + '/approve', {});
    if (res.ok) {
      _sfToast('✓ 已批准: ' + draftName + (res.import && res.import.imported ? '，已自动导入技能商店' : ''), 'ok');
    } else {
      _sfToast('批准失败: ' + JSON.stringify(res), 'err');
    }
  } catch (e) {
    _sfToast('操作失败: ' + (e.message || String(e)), 'err');
  }
  loadPendingSkills();
}

async function rejectDraft(draftId, draftName) {
  try {
    var res = await api('POST', '/api/portal/pending-skills/' + encodeURIComponent(draftId) + '/reject', {});
    if (res.ok) {
      _sfToast('已拒绝: ' + draftName, 'ok');
    } else {
      _sfToast('操作失败: ' + JSON.stringify(res), 'err');
    }
  } catch (e) {
    _sfToast('操作失败: ' + (e.message || String(e)), 'err');
  }
  loadPendingSkills();
}
