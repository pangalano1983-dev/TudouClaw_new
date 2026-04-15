}

// ============ Meetings Tab (群聊会议) ============
async function renderMeetingsTab() {
  var c = document.getElementById('content');
  c.innerHTML =
    '<div style="padding:18px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">' +
        '<div><h2 style="margin:0;font-size:22px;font-weight:800">群聊 / 会议</h2>' +
        '<p style="font-size:12px;color:var(--text3);margin-top:4px">多 Agent 临时协作会议 · 任务分派 · 会议纪要</p></div>' +
        '<div style="display:flex;gap:8px">' +
          '<select id="meetings-filter-status" onchange="renderMeetingsTab()" style="background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:var(--text);font-size:12px;padding:6px 10px">' +
            '<option value="">全部状态</option>' +
            '<option value="active">进行中</option>' +
            '<option value="scheduled">已安排</option>' +
            '<option value="closed">已结束</option>' +
            '<option value="cancelled">已取消</option>' +
          '</select>' +
          '<button class="btn btn-primary btn-sm" onclick="showCreateMeetingModal()"><span class="material-symbols-outlined" style="font-size:16px">add</span> 新建会议</button>' +
        '</div>' +
      '</div>' +
      '<div id="meetings-list-area" style="min-height:100px"><div style="color:var(--text3);font-size:12px">Loading…</div></div>' +
    '</div>';
  try {
    var filter = '';
    var fEl = document.getElementById('meetings-filter-status');
    if (fEl) filter = fEl.value || '';
    var qs = filter ? ('?status='+encodeURIComponent(filter)) : '';
    var r = await api('GET', '/api/portal/meetings'+qs);
    var list = r.meetings || [];
    var listEl = document.getElementById('meetings-list-area');
    if (!list.length) {
      listEl.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text3);font-size:13px">暂无会议。点击"新建会议"拉起一场跨 Agent 协作。</div>';
      return;
    }
    listEl.innerHTML = list.map(function(m){
      var statusColor = m.status==='active'?'#22c55e':m.status==='scheduled'?'var(--primary)':m.status==='closed'?'var(--text3)':'#ef4444';
      var ts = m.created_at ? new Date(m.created_at*1000).toLocaleString() : '';
      return '<div onclick="openMeetingDetail(\''+m.id+'\')" style="background:var(--surface);border-radius:10px;padding:14px 16px;border:1px solid rgba(255,255,255,0.06);margin-bottom:10px;cursor:pointer;transition:border-color 0.2s" onmouseover="this.style.borderColor=\'var(--primary)\'" onmouseout="this.style.borderColor=\'rgba(255,255,255,0.06)\'">' +
        '<div style="display:flex;justify-content:space-between;align-items:flex-start">' +
          '<div style="flex:1;min-width:0">' +
            '<div style="display:flex;align-items:center;gap:8px"><span style="font-weight:700;font-size:14px">'+esc(m.title||'(untitled)')+'</span><span style="font-size:10px;padding:2px 8px;border-radius:10px;background:rgba(255,255,255,0.08);color:'+statusColor+';font-weight:600">'+esc(m.status||'')+'</span></div>' +
            '<div style="font-size:11px;color:var(--text3);margin-top:4px">主持: '+esc(m.host||'—')+' · 参与: '+((m.participants||[]).length)+' 人 · '+ts+'</div>' +
          '</div>' +
          '<div style="font-size:11px;color:var(--text2);text-align:right">' +
            '💬 '+m.message_count+' · 📌 '+m.open_assignments+'/'+m.assignment_count +
          '</div>' +
        '</div>' +
      '</div>';
    }).join('');
  } catch(e) {
    document.getElementById('meetings-list-area').innerHTML = '<div style="color:var(--error)">Error: '+esc(e.message)+'</div>';
  }
}

function showCreateMeetingModal() {
  var projOpts = (window._cachedProjects || []).map(function(p){
    return '<option value="'+p.id+'">'+esc(p.name)+'</option>';
  }).join('');
  var agentOpts = agents.map(function(a){
    return '<label style="display:block;padding:4px 8px;font-size:12px"><input type="checkbox" name="mtg-part" value="'+a.id+'"> '+esc((a.role||'')+'-'+a.name)+'</label>';
  }).join('');
  var html = '<div style="padding:24px;max-width:500px"><h3 style="margin:0 0 16px">新建会议</h3>' +
    '<input id="mtg-title" placeholder="会议标题" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
    '<textarea id="mtg-agenda" placeholder="议程 / 背景（可选）" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px;min-height:60px;resize:vertical"></textarea>' +
    '<select id="mtg-project" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
      '<option value="">不关联项目 (非项目型)</option>'+projOpts +
    '</select>' +
    '<div style="font-size:11px;color:var(--text3);margin:8px 0 4px">参与 Agent</div>' +
    '<div style="max-height:160px;overflow-y:auto;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:6px 10px;margin-bottom:12px">'+(agentOpts||'<div style="color:var(--text3);font-size:12px">No agents</div>')+'</div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end">' +
      '<button class="btn btn-ghost" onclick="closeModal()">取消</button>' +
      '<button class="btn btn-primary" onclick="createMeeting()">创建</button>' +
    '</div></div>';
  showModalHTML(html);
}

async function createMeeting() {
  var title = document.getElementById('mtg-title').value.trim();
  if (!title) { alert('标题不能为空'); return; }
  var agenda = document.getElementById('mtg-agenda').value.trim();
  var projId = document.getElementById('mtg-project').value;
  var parts = Array.prototype.slice.call(document.querySelectorAll('input[name="mtg-part"]:checked')).map(function(i){return i.value;});
  try {
    await api('POST', '/api/portal/meetings', {
      title: title, agenda: agenda, project_id: projId, participants: parts,
    });
    closeModal();
    renderMeetingsTab();
  } catch(e) { alert('Error: '+e.message); }
}

async function openMeetingDetail(mid) {
  try {
    var m = await api('GET', '/api/portal/meetings/'+mid);
    var c = document.getElementById('content');
    var statusBtns = '';
    if (m.status === 'scheduled') statusBtns += '<button class="btn btn-primary btn-sm" onclick="meetingAction(\''+mid+'\',\'start\')">开始</button>';
    if (m.status === 'active') statusBtns += '<button class="btn btn-ghost btn-sm" onclick="meetingCloseWithSummary(\''+mid+'\')">结束</button>';
    if (m.status !== 'cancelled' && m.status !== 'closed') statusBtns += '<button class="btn btn-ghost btn-sm" style="color:var(--error)" onclick="meetingAction(\''+mid+'\',\'cancel\')">取消</button>';

    // Each message gets a unique anchor id so we can attach FileCards
    // after the html string is rendered into the DOM (see post-render
    // pass below). Cards live in `x.refs`, populated by the backend.
    var _mtgMsgRefs = [];
    var msgHtml = (m.messages||[]).map(function(x, _i){
      var ts = x.created_at ? new Date(x.created_at*1000).toLocaleTimeString() : '';
      var anchor = 'mtg-msg-card-' + mid + '-' + _i;
      _mtgMsgRefs.push({anchor: anchor, refs: x.refs || []});
      return '<div style="padding:8px 12px;background:var(--surface);border-radius:8px;margin-bottom:6px">' +
        '<div style="font-size:10px;color:var(--primary);font-weight:600;margin-bottom:2px">'+esc(x.sender_name||x.sender||'?')+' · '+ts+'</div>' +
        '<div style="font-size:12px;color:var(--text2);white-space:pre-wrap">'+esc(x.content||'')+'</div>' +
        '<div id="'+anchor+'" class="chat-msg-content" style="margin-top:4px"></div>' +
      '</div>';
    }).join('') || '<div style="color:var(--text3);font-size:12px">暂无消息</div>';

    var asgHtml = (m.assignments||[]).map(function(a){
      var linkBadge = a.project_task_id ? '<span style="font-size:9px;background:rgba(203,201,255,0.15);color:var(--primary);padding:1px 5px;border-radius:3px;margin-left:4px">→ Project Task</span>'
                     : a.standalone_task_id ? '<span style="font-size:9px;background:rgba(34,197,94,0.15);color:#22c55e;padding:1px 5px;border-radius:3px;margin-left:4px">→ Standalone</span>' : '';
      return '<div style="padding:10px 12px;background:var(--surface);border-radius:8px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">' +
        '<div style="flex:1;min-width:0">' +
          '<div style="font-weight:600;font-size:13px">'+esc(a.title)+linkBadge+'</div>' +
          '<div style="font-size:10px;color:var(--text3);margin-top:2px">→ '+esc(a.assignee_agent_id||'—')+(a.due_hint?' · '+esc(a.due_hint):'')+' · '+esc(a.status)+'</div>' +
        '</div>' +
        '<select onchange="updateMeetingAssignment(\''+mid+'\',\''+a.id+'\',this.value)" style="background:var(--surface2);border:1px solid rgba(255,255,255,0.1);border-radius:4px;color:var(--text);font-size:11px;padding:3px 6px">' +
          '<option value="">--</option>' +
          ['open','in_progress','done','cancelled'].map(function(s){return '<option value="'+s+'"'+(a.status===s?' selected':'')+'>'+s+'</option>';}).join('') +
        '</select>' +
      '</div>';
    }).join('') || '<div style="color:var(--text3);font-size:12px">暂无任务分派</div>';

    c.innerHTML =
      '<div style="padding:18px;max-width:1000px">' +
        '<button class="btn btn-ghost btn-sm" onclick="renderMeetingsTab()"><span class="material-symbols-outlined" style="font-size:14px">arrow_back</span> 返回</button>' +
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin:16px 0">' +
          '<div><h2 style="margin:0;font-size:22px;font-weight:800">'+esc(m.title)+'</h2>' +
          '<div style="font-size:11px;color:var(--text3);margin-top:4px">主持: '+esc(m.host)+' · 状态: '+esc(m.status)+(m.project_id?' · 项目: '+esc(m.project_id):'')+'</div>' +
          (m.agenda?'<div style="font-size:12px;color:var(--text2);margin-top:8px;max-width:600px">'+esc(m.agenda)+'</div>':'') +
          '</div>' +
          '<div style="display:flex;gap:6px">'+statusBtns+'</div>' +
        '</div>' +
        (m.summary ? '<div style="background:rgba(34,197,94,0.06);border:1px solid rgba(34,197,94,0.3);border-radius:8px;padding:12px;margin-bottom:16px"><div style="font-size:11px;font-weight:700;color:#22c55e;margin-bottom:4px">会议纪要</div><div style="font-size:12px;color:var(--text2);white-space:pre-wrap">'+esc(m.summary)+'</div></div>' : '') +
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">' +
          '<div><div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text3);margin-bottom:10px">对话 ('+(m.messages||[]).length+')</div>' +
            '<div style="max-height:320px;overflow-y:auto;margin-bottom:10px">'+msgHtml+'</div>' +
            '<div id="mtg-attach-preview-'+mid+'" style="display:none;flex-wrap:wrap;gap:6px;margin-bottom:6px"></div>' +
            '<textarea id="mtg-msg-input" placeholder="发送消息..." style="width:100%;padding:8px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:12px;min-height:50px;resize:vertical"></textarea>' +
            '<div style="display:flex;gap:6px;margin-top:6px;align-items:center">' +
              '<input type="file" id="mtg-file-input-'+mid+'" multiple accept="image/*,.pdf,.doc,.docx,.txt,.csv,.json,.yaml,.yml,.md" style="display:none" onchange="handleMtgAttach(\''+mid+'\',this)">' +
              '<button class="btn btn-ghost btn-sm" onclick="document.getElementById(\'mtg-file-input-'+mid+'\').click()" title="上传图片/文件"><span class="material-symbols-outlined" style="font-size:16px">attach_file</span></button>' +
              '<button class="btn btn-primary btn-sm" onclick="meetingPostMessage(\''+mid+'\')">发送</button>' +
            '</div>' +
          '</div>' +
          '<div><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">' +
            '<div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text3)">任务分派 ('+(m.assignments||[]).length+')</div>' +
            '<button class="btn btn-ghost btn-xs" onclick="showMeetingAssignmentModal(\''+mid+'\')">+ 新增</button>' +
          '</div>'+asgHtml+'</div>' +
        '</div>' +
      '</div>';
    // Post-render pass: walk the per-message anchors emitted above and
    // attach FileCards using the shared agent-chat helper. Refs come
    // from the backend's _enrich_meeting_messages_with_refs and already
    // include url + filename + size + kind.
    try {
      for (var _ri = 0; _ri < _mtgMsgRefs.length; _ri++) {
        var rec = _mtgMsgRefs[_ri];
        if (!rec || !rec.refs || !rec.refs.length) continue;
        var host = document.getElementById(rec.anchor);
        if (host) _appendFileCards(host, rec.refs);
      }
    } catch(_e) { console.log('[meetingDetail] file card attach failed', _e); }
  } catch(e) {
    alert('Error: '+e.message);
  }
}

async function meetingAction(mid, action) {
  try { await api('POST', '/api/portal/meetings/'+mid+'/'+action, {}); openMeetingDetail(mid); }
  catch(e) { alert('Error: '+e.message); }
}
async function meetingCloseWithSummary(mid) {
  var s = prompt('会议纪要 / 结论 (可留空):') || '';
  try { await api('POST', '/api/portal/meetings/'+mid+'/close', {summary: s}); openMeetingDetail(mid); }
  catch(e) { alert('Error: '+e.message); }
}
// ============ Meeting Attachments ============
var _mtgAttachments = {};

function _mtgAttachList(mid) {
  if (!_mtgAttachments[mid]) _mtgAttachments[mid] = [];
  return _mtgAttachments[mid];
}

function _renderMtgAttachPreview(mid) {
  var box = document.getElementById('mtg-attach-preview-'+mid);
  if (!box) return;
  var list = _mtgAttachList(mid);
  if (list.length === 0) { box.style.display = 'none'; box.innerHTML = ''; return; }
  box.style.display = 'flex';
  box.innerHTML = list.map(function(a, idx) {
    var thumb = a.preview_url
      ? '<img src="'+a.preview_url+'" style="width:28px;height:28px;object-fit:cover;border-radius:3px">'
      : '<span class="material-symbols-outlined" style="font-size:16px;color:var(--text3)">draft</span>';
    return '<div style="display:inline-flex;align-items:center;gap:4px;background:var(--surface);border:1px solid rgba(255,255,255,0.08);border-radius:4px;padding:2px 6px;font-size:10px;color:var(--text)">' +
      thumb + '<span style="max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(a.name)+'</span>' +
      '<button onclick="_mtgAttachList(\''+mid+'\').splice('+idx+',1);_renderMtgAttachPreview(\''+mid+'\')" style="background:none;border:none;color:var(--text3);cursor:pointer;padding:0"><span class="material-symbols-outlined" style="font-size:12px">close</span></button>' +
    '</div>';
  }).join('');
}

function handleMtgAttach(mid, fileInput) {
  if (!fileInput || !fileInput.files || !fileInput.files.length) return;
  var list = _mtgAttachList(mid);
  var files = Array.prototype.slice.call(fileInput.files, 0, Math.max(0, 10 - list.length));
  files.forEach(function(f) {
    if (f.size > 10*1024*1024) { alert('File "'+f.name+'" exceeds 10 MB.'); return; }
    var reader = new FileReader();
    reader.onload = function(e) {
      var dataUrl = e.target.result || '';
      var b64 = dataUrl.indexOf(',') >= 0 ? dataUrl.split(',')[1] : dataUrl;
      var isImage = (f.type||'').indexOf('image/') === 0;
      list.push({ name: f.name, mime: f.type||'application/octet-stream', size: f.size, data_base64: b64, preview_url: isImage ? dataUrl : '' });
      _renderMtgAttachPreview(mid);
    };
    reader.readAsDataURL(f);
  });
  fileInput.value = '';
}

async function meetingPostMessage(mid) {
  var el = document.getElementById('mtg-msg-input');
  var v = (el && el.value || '').trim();
  var attachments = _mtgAttachList(mid).slice();
  if (!v && !attachments.length) return;
  var msgBody = {content: v || '(attached files)', role: 'user'};
  if (attachments.length) {
    msgBody.attachments = attachments.map(function(a) {
      return { name: a.name, mime: a.mime, data_base64: a.data_base64 };
    });
    _mtgAttachments[mid] = [];
    _renderMtgAttachPreview(mid);
  }
  try {
    await api('POST', '/api/portal/meetings/'+mid+'/messages', msgBody);
    openMeetingDetail(mid);
  } catch(e) { alert('Error: '+e.message); }
}
function showMeetingAssignmentModal(mid) {
  var agentOpts = '<option value="">选择负责 agent</option>' + agents.map(function(a){
    return '<option value="'+a.id+'">'+esc((a.role||'')+'-'+a.name)+'</option>';
  }).join('');
  var html = '<div style="padding:24px;max-width:480px"><h3 style="margin:0 0 16px">新建会议任务</h3>' +
    '<input id="asg-title" placeholder="任务标题" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
    '<textarea id="asg-desc" placeholder="描述 / 背景 (可选)" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px;min-height:60px;resize:vertical"></textarea>' +
    '<select id="asg-assignee" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">'+agentOpts+'</select>' +
    '<input id="asg-due" placeholder="截止提示 (e.g. \"明天 17:00\")" style="width:100%;padding:10px;margin-bottom:10px;background:var(--surface);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:var(--text);font-size:13px">' +
    '<label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text2);margin-bottom:14px"><input type="checkbox" id="asg-materialize" checked> 自动生成对应 Task (ProjectTask 或 StandaloneTask)</label>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end">' +
      '<button class="btn btn-ghost" onclick="closeModal()">取消</button>' +
      '<button class="btn btn-primary" onclick="createMeetingAssignment(\''+mid+'\')">创建</button>' +
    '</div></div>';
  showModalHTML(html);
}
async function createMeetingAssignment(mid) {
  var title = document.getElementById('asg-title').value.trim();
  if (!title) { alert('标题不能为空'); return; }
  try {
    await api('POST', '/api/portal/meetings/'+mid+'/assignments', {
      title: title,
      description: document.getElementById('asg-desc').value.trim(),
      assignee_agent_id: document.getElementById('asg-assignee').value,
      due_hint: document.getElementById('asg-due').value.trim(),
      materialize: document.getElementById('asg-materialize').checked,
    });
    closeModal();
    openMeetingDetail(mid);
  } catch(e) { alert('Error: '+e.message); }
}
async function updateMeetingAssignment(mid, aid, status) {
  if (!status) return;
  try {
    await api('POST', '/api/portal/meetings/'+mid+'/assignments/'+aid+'/update', {status: status});
    openMeetingDetail(mid);
  } catch(e) { alert('Error: '+e.message); }
