}

// ============ Role Presets CRUD ============
function _rpShowEdit(roleKey) {
  var preset = (window._rolePresets||{})[roleKey];
  if (!preset) { alert('Preset not found'); return; }
  var p = preset.profile || {};
  var html = '<div class="modal-overlay" id="rp-edit-modal" onclick="if(event.target===this)this.remove()">'
    + '<div class="modal" style="max-width:600px">'
    + '<h3>编辑角色预设: ' + esc(roleKey) + '</h3>'
    + '<div class="form-group"><label>角色名 Role Key</label><input id="rp-edit-key" value="'+esc(roleKey)+'" readonly style="opacity:0.6"></div>'
    + '<div class="form-group"><label>显示名 Name</label><input id="rp-edit-name" value="'+esc(preset.name||'')+'"></div>'
    + '<div class="form-group"><label>System Prompt *</label><textarea id="rp-edit-prompt" rows="5" style="font-family:monospace;font-size:12px">'+esc(preset.system_prompt||'')+'</textarea></div>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
      + '<div class="form-group"><label>性格 Personality</label><input id="rp-edit-personality" value="'+esc(p.personality||'')+'"></div>'
      + '<div class="form-group"><label>沟通风格 Communication</label><input id="rp-edit-comm" value="'+esc(p.communication_style||'')+'"></div>'
    + '</div>'
    + '<div class="form-group"><label>专长 Expertise (逗号分隔)</label><input id="rp-edit-expertise" value="'+esc((p.expertise||[]).join(', '))+'"></div>'
    + '<div class="form-group"><label>技能 Skills (逗号分隔)</label><input id="rp-edit-skills" value="'+esc((p.skills||[]).join(', '))+'"></div>'
    + '<div class="form-group"><label>允许的工具 Allowed Tools (逗号分隔，留空=全部)</label><input id="rp-edit-allowed" value="'+esc((p.allowed_tools||[]).join(', '))+'"></div>'
    + '<div class="form-group"><label>禁用的工具 Denied Tools (逗号分隔)</label><input id="rp-edit-denied" value="'+esc((p.denied_tools||[]).join(', '))+'"></div>'
    + '<div class="form-actions"><button class="btn btn-ghost" onclick="document.getElementById(\'rp-edit-modal\').remove()">取消</button>'
    + '<button class="btn btn-primary" onclick="_rpSaveEdit(\''+esc(roleKey)+'\')">保存</button></div>'
    + '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
}

function _rpShowCreate() {
  var html = '<div class="modal-overlay" id="rp-create-modal" onclick="if(event.target===this)this.remove()">'
    + '<div class="modal" style="max-width:600px">'
    + '<h3>新建角色预设</h3>'
    + '<div class="form-group"><label>角色名 Role Key * (英文，如 analyst)</label><input id="rp-new-key" placeholder="e.g. analyst, translator, tester"></div>'
    + '<div class="form-group"><label>显示名 Name</label><input id="rp-new-name" placeholder="e.g. 数据分析师"></div>'
    + '<div class="form-group"><label>System Prompt *</label><textarea id="rp-new-prompt" rows="5" style="font-family:monospace;font-size:12px" placeholder="You are a data analyst..."></textarea></div>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
      + '<div class="form-group"><label>性格 Personality</label><input id="rp-new-personality" placeholder="e.g. analytical, precise"></div>'
      + '<div class="form-group"><label>沟通风格 Communication</label><input id="rp-new-comm" placeholder="e.g. technical, brief"></div>'
    + '</div>'
    + '<div class="form-group"><label>专长 Expertise (逗号分隔)</label><input id="rp-new-expertise" placeholder="data_analysis, statistics"></div>'
    + '<div class="form-group"><label>技能 Skills (逗号分隔)</label><input id="rp-new-skills" placeholder="data_analysis, visualization"></div>'
    + '<div class="form-actions"><button class="btn btn-ghost" onclick="document.getElementById(\'rp-create-modal\').remove()">取消</button>'
    + '<button class="btn btn-primary" onclick="_rpSaveNew()">创建</button></div>'
    + '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
}

function _rpParseList(val) {
  return (val||'').split(',').map(function(s){return s.trim()}).filter(Boolean);
}

async function _rpSaveEdit(roleKey) {
  var name = (document.getElementById('rp-edit-name')||{}).value||'';
  var prompt = (document.getElementById('rp-edit-prompt')||{}).value||'';
  if (!prompt.trim()) { alert('System Prompt 不能为空'); return; }
  var profile = {
    personality: (document.getElementById('rp-edit-personality')||{}).value||'',
    communication_style: (document.getElementById('rp-edit-comm')||{}).value||'',
    expertise: _rpParseList((document.getElementById('rp-edit-expertise')||{}).value),
    skills: _rpParseList((document.getElementById('rp-edit-skills')||{}).value),
    allowed_tools: _rpParseList((document.getElementById('rp-edit-allowed')||{}).value),
    denied_tools: _rpParseList((document.getElementById('rp-edit-denied')||{}).value),
  };
  try {
    await api('POST', '/api/portal/role-presets/update', {
      key: roleKey, name: name, system_prompt: prompt, profile: profile
    });
    var m = document.getElementById('rp-edit-modal'); if(m) m.remove();
    renderConfig(document.getElementById('settings-content'));
  } catch(e) { alert('保存失败: '+e); }
}

async function _rpSaveNew() {
  var key = (document.getElementById('rp-new-key')||{}).value||'';
  var name = (document.getElementById('rp-new-name')||{}).value||'';
  var prompt = (document.getElementById('rp-new-prompt')||{}).value||'';
  if (!key.trim()) { alert('角色名不能为空'); return; }
  if (!prompt.trim()) { alert('System Prompt 不能为空'); return; }
  if (!/^[a-z][a-z0-9_]*$/.test(key)) { alert('角色名只能使用小写字母、数字和下划线'); return; }
  var profile = {
    personality: (document.getElementById('rp-new-personality')||{}).value||'',
    communication_style: (document.getElementById('rp-new-comm')||{}).value||'',
    expertise: _rpParseList((document.getElementById('rp-new-expertise')||{}).value),
    skills: _rpParseList((document.getElementById('rp-new-skills')||{}).value),
  };
  try {
    await api('POST', '/api/portal/role-presets/update', {
      key: key, name: name, system_prompt: prompt, profile: profile
    });
    var m = document.getElementById('rp-create-modal'); if(m) m.remove();
    renderConfig(document.getElementById('settings-content'));
  } catch(e) { alert('创建失败: '+e); }
}

async function _rpDelete(roleKey) {
  if (!confirm('确定删除角色预设 "'+roleKey+'" 吗？')) return;
  try {
    await api('POST', '/api/portal/role-presets/delete', { key: roleKey });
    renderConfig(document.getElementById('settings-content'));
  } catch(e) { alert('删除失败: '+e); }
