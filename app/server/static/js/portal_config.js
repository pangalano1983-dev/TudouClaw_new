}

// ============ System Prompts ============
var _scenePrompts = [];
var _availableRoles = []; // populated from role_presets keys

function _spScopeLabel(sp) {
  var scope = sp.scope || 'all';
  if (scope === 'all') return '<span style="background:var(--primary);color:#fff;padding:1px 6px;border-radius:4px;font-size:10px">All Agents</span>';
  var roles = sp.roles || [];
  if (roles.length === 0) return '<span style="background:var(--warning,#f0ad4e);color:#fff;padding:1px 6px;border-radius:4px;font-size:10px">No roles</span>';
  return roles.map(function(r) {
    return '<span style="background:var(--surface3);padding:1px 6px;border-radius:4px;font-size:10px;color:var(--text2)">' + esc(r) + '</span>';
  }).join(' ');
}

function _spRender(prompts) {
  _scenePrompts = prompts || [];
  var el = document.getElementById('scene-prompts-list');
  if (!el) return;
  if (_scenePrompts.length === 0) {
    el.innerHTML = '<div style="color:var(--text3);text-align:center;padding:16px 0;font-size:13px">No system prompts yet. Click "Add Prompt" to create one.</div>';
    return;
  }
  var html = '';
  _scenePrompts.forEach(function(sp, i) {
    var enabled = sp.enabled !== false;
    var preview = (sp.prompt || '').slice(0, 100) + ((sp.prompt || '').length > 100 ? '...' : '');
    html += '<div style="background:var(--surface);border-radius:8px;padding:12px;margin-bottom:8px;border:1px solid ' + (enabled ? 'var(--border-light)' : 'var(--border)') + ';opacity:' + (enabled ? '1' : '0.6') + '">'
      + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">'
        + '<div style="display:flex;align-items:center;gap:8px">'
          + '<label style="cursor:pointer;display:flex;align-items:center"><input type="checkbox" ' + (enabled ? 'checked' : '') + ' onchange="_spToggle(' + i + ',this.checked)" style="margin:0"></label>'
          + '<span style="font-weight:600;font-size:13px;color:var(--text)">' + esc(sp.name || 'Unnamed') + '</span>'
          + _spScopeLabel(sp)
        + '</div>'
        + '<div style="display:flex;gap:4px">'
          + '<button class="btn btn-sm" onclick="_spEdit(' + i + ')" style="padding:3px 8px;font-size:11px"><span class="material-symbols-outlined" style="font-size:14px">edit</span></button>'
          + '<button class="btn btn-sm" onclick="_spDelete(' + i + ')" style="padding:3px 8px;font-size:11px;color:var(--error)"><span class="material-symbols-outlined" style="font-size:14px">delete</span></button>'
        + '</div>'
      + '</div>'
      + '<div style="font-size:12px;color:var(--text3);line-height:1.4;white-space:pre-wrap">' + esc(preview) + '</div>'
    + '</div>';
  });
  el.innerHTML = html;
}

function _spAdd() {
  _spShowEditor(-1, {name: '', prompt: '', enabled: true, scope: 'all', roles: []});
}

function _spEdit(idx) {
  var sp = _scenePrompts[idx];
  if (!sp) return;
  _spShowEditor(idx, sp);
}

function _spShowEditor(idx, sp) {
  var existing = document.getElementById('sp-edit-modal');
  if (existing) existing.remove();

  var scope = sp.scope || 'all';
  var roles = sp.roles || [];

  // Build role checkboxes
  var roleChecks = _availableRoles.map(function(r) {
    var checked = roles.indexOf(r) >= 0 ? ' checked' : '';
    return '<label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:12px;padding:2px 0">'
      + '<input type="checkbox" class="sp-role-cb" value="' + esc(r) + '"' + checked + ' style="margin:0">'
      + esc(r) + '</label>';
  }).join('');

  var modal = document.createElement('div');
  modal.id = 'sp-edit-modal';
  modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:9999';
  modal.innerHTML = '<div style="background:var(--surface);border-radius:12px;padding:24px;width:90%;max-width:600px;max-height:80vh;overflow-y:auto">'
    + '<div style="font-size:16px;font-weight:700;margin-bottom:16px">' + (idx >= 0 ? 'Edit System Prompt' : 'New System Prompt') + '</div>'
    + '<div class="form-group" style="margin-bottom:12px"><label style="font-size:12px">Name · 名称</label>'
    + '<input id="sp-edit-name" value="' + esc(sp.name || '').replace(/"/g,'&quot;') + '" style="width:100%;padding:8px 10px;background:var(--surface2);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px" placeholder="e.g. 全局规则 / 编码规范 / 运维操作"></div>'
    // Scope selector
    + '<div class="form-group" style="margin-bottom:12px"><label style="font-size:12px">Scope · 作用范围</label>'
    + '<div style="display:flex;gap:12px;margin-top:4px">'
      + '<label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:13px"><input type="radio" name="sp-scope" value="all"' + (scope === 'all' ? ' checked' : '') + ' onchange="_spScopeChanged()"> All Agents · 所有智能体</label>'
      + '<label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:13px"><input type="radio" name="sp-scope" value="roles"' + (scope === 'roles' ? ' checked' : '') + ' onchange="_spScopeChanged()"> Specific Roles · 指定角色</label>'
    + '</div></div>'
    // Role checkboxes (shown when scope=roles)
    + '<div id="sp-roles-panel" style="margin-bottom:12px;padding:10px;background:var(--surface2);border-radius:6px;display:' + (scope === 'roles' ? 'block' : 'none') + '">'
      + '<div style="font-size:11px;color:var(--text3);margin-bottom:6px">选择需要遵从此提示词的角色：</div>'
      + '<div style="display:flex;flex-wrap:wrap;gap:8px 16px">' + roleChecks + '</div>'
    + '</div>'
    // Prompt content
    + '<div class="form-group" style="margin-bottom:12px"><label style="font-size:12px">Prompt Content · 提示词内容</label>'
    + '<textarea id="sp-edit-prompt" rows="10" style="width:100%;padding:10px 12px;background:var(--surface2);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;font-family:\'Fira Code\',\'Cascadia Code\',monospace;resize:vertical;line-height:1.6" placeholder="e.g. 编写代码时遵循以下规范...">' + esc(sp.prompt || '') + '</textarea></div>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px">'
    + '<button class="btn btn-sm" onclick="document.getElementById(\'sp-edit-modal\').remove()" style="padding:6px 16px">Cancel</button>'
    + '<button class="btn btn-sm btn-primary" onclick="_spSaveEditor(' + idx + ')" style="padding:6px 16px">Save</button>'
    + '</div></div>';
  document.body.appendChild(modal);
  modal.addEventListener('click', function(e) { if (e.target === modal) modal.remove(); });
}

function _spScopeChanged() {
  var panel = document.getElementById('sp-roles-panel');
  if (!panel) return;
  var radios = document.querySelectorAll('input[name="sp-scope"]');
  var scope = 'all';
  radios.forEach(function(r) { if (r.checked) scope = r.value; });
  panel.style.display = scope === 'roles' ? 'block' : 'none';
}

function _spSaveEditor(idx) {
  var nameEl = document.getElementById('sp-edit-name');
  var promptEl = document.getElementById('sp-edit-prompt');
  if (!nameEl || !promptEl) return;
  var name = nameEl.value.trim();
  var promptText = promptEl.value.trim();
  if (!name) { alert('Name is required'); return; }
  if (!promptText) { alert('Prompt content is required'); return; }

  // Read scope
  var radios = document.querySelectorAll('input[name="sp-scope"]');
  var scope = 'all';
  radios.forEach(function(r) { if (r.checked) scope = r.value; });

  // Read selected roles
  var roles = [];
  if (scope === 'roles') {
    document.querySelectorAll('.sp-role-cb').forEach(function(cb) {
      if (cb.checked) roles.push(cb.value);
    });
  }

  if (idx >= 0) {
    _scenePrompts[idx].name = name;
    _scenePrompts[idx].prompt = promptText;
    _scenePrompts[idx].scope = scope;
    _scenePrompts[idx].roles = roles;
  } else {
    _scenePrompts.push({
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      name: name,
      prompt: promptText,
      enabled: true,
      scope: scope,
      roles: roles
    });
  }

  document.getElementById('sp-edit-modal').remove();
  _spRender(_scenePrompts);
  _spSave();
}

function _spToggle(idx, checked) {
  if (_scenePrompts[idx]) {
    _scenePrompts[idx].enabled = checked;
    _spRender(_scenePrompts);
    _spSave();
  }
}

function _spDelete(idx) {
  var sp = _scenePrompts[idx];
  if (!sp) return;
  var el = document.getElementById('scene-prompts-list');
  if (!el) return;
  var cards = el.children;
  if (!cards[idx]) return;
  var card = cards[idx];
  var orig = card.innerHTML;
  card.innerHTML = '<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0">'
    + '<span style="color:var(--error);font-size:13px">Delete "' + esc(sp.name || 'Unnamed') + '"?</span>'
    + '<div style="display:flex;gap:6px">'
    + '<button class="btn btn-sm" onclick="this.closest(\'div[style]\').parentElement.innerHTML=window._spDeleteOrig;window._spDeleteOrig=null" style="padding:4px 12px;font-size:12px">Cancel</button>'
    + '<button class="btn btn-sm" style="padding:4px 12px;font-size:12px;background:var(--error);color:#fff" onclick="_spConfirmDelete(' + idx + ')">Delete</button>'
    + '</div></div>';
  window._spDeleteOrig = orig;
}

function _spConfirmDelete(idx) {
  _scenePrompts.splice(idx, 1);
  _spRender(_scenePrompts);
  _spSave();
}

async function _spSave() {
  try {
    await api('POST', '/api/portal/config', { scene_prompts: _scenePrompts, global_system_prompt: '' });
  } catch(e) {
    alert('Save failed: ' + e.message);
  }
}

// ============ Config ============
function renderConfig(container) {
  const c = container || document.getElementById('content');
  if (!container) c.style.padding = '24px';
  const epoch = _renderEpoch;
  api('GET', '/api/portal/config').then(cfg => {
    if (!cfg || epoch !== _renderEpoch) return;
    // Store presets for editing
    window._rolePresets = cfg.role_presets || {};
    _availableRoles = Object.keys(cfg.role_presets || {}).sort();

    // Auto-migrate legacy global_system_prompt into scene_prompts
    var _mergedPrompts = cfg.scene_prompts || [];
    if (cfg.global_system_prompt && cfg.global_system_prompt.trim()) {
      var hasLegacy = _mergedPrompts.some(function(p) { return p._is_global; });
      if (!hasLegacy) {
        _mergedPrompts.unshift({
          id: 'global_default',
          name: 'Global Rules · 全局规则',
          prompt: cfg.global_system_prompt.trim(),
          enabled: true,
          _is_global: true
        });
      }
    }

    c.innerHTML = `
      <!-- System Prompts (unified) -->
      <div class="card" style="margin-bottom:16px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <div>
            <div class="card-title" style="margin:0">
              <span class="material-symbols-outlined" style="font-size:18px;vertical-align:middle;margin-right:4px;color:var(--primary)">tune</span>
              System Prompts · 系统提示词
            </div>
            <div style="font-size:12px;color:var(--text3);margin-top:4px">
              为所有 Agent 定义系统提示词。可按场景分条管理（如「全局规则」「复杂工程任务」「编码规范」等），启用的条目会注入到每个 Agent 的系统提示中。
            </div>
          </div>
          <button class="btn btn-sm btn-primary" onclick="_spAdd()" style="padding:6px 14px">
            <span class="material-symbols-outlined" style="font-size:15px;vertical-align:middle;margin-right:2px">add</span> Add Prompt
          </button>
        </div>
        <div id="scene-prompts-list"></div>
      </div>

      <!-- Row 2: Role Presets (editable) -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
          <div>
            <div class="card-title" style="margin:0">
              <span class="material-symbols-outlined" style="font-size:18px;vertical-align:middle;margin-right:4px;color:var(--primary)">person</span>
              Role Presets · 角色预设
            </div>
            <div style="font-size:12px;color:var(--text3);margin-top:4px">
              创建智能体时可选角色预设。编辑 system_prompt 和 profile 属性，点击保存后立即生效。
            </div>
          </div>
          <button class="btn btn-sm btn-primary" onclick="_rpShowCreate()" style="padding:6px 14px">
            <span class="material-symbols-outlined" style="font-size:15px;vertical-align:middle;margin-right:2px">add</span> 新建角色
          </button>
        </div>
        <div id="role-presets-list" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:10px"></div>
      </div>
    `;
    // Populate role presets grid after innerHTML is set
    _rpRenderCards(cfg.role_presets || {});
    _spRender(_mergedPrompts);
  });
}

function _rpRenderCards(presets) {
  var grid = document.getElementById('role-presets-list');
  if (!grid) return;
  var html = '';
  Object.keys(presets).forEach(function(k) {
    var v = presets[k];
    var p = v.profile || {};
    var expertiseStr = (p.expertise||[]).slice(0,4).join(', ');
    var skillsStr = (p.skills||[]).slice(0,4).join(', ');
    html += '<div style="background:var(--surface);border-radius:10px;padding:14px;border:1px solid var(--border-light);transition:all 0.15s" onmouseenter="this.style.borderColor=\'var(--primary)\'" onmouseleave="this.style.borderColor=\'var(--border-light)\'">'
      + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
        + '<div style="font-weight:700;font-size:14px;color:var(--primary)">' + esc(k) + '</div>'
        + '<div style="display:flex;gap:4px">'
          + '<button class="btn btn-sm" onclick="_rpShowEdit(\'' + esc(k) + '\')" style="padding:3px 8px;font-size:11px" title="编辑"><span class="material-symbols-outlined" style="font-size:14px">edit</span></button>'
          + '<button class="btn btn-sm" onclick="_rpDelete(\'' + esc(k) + '\')" style="padding:3px 8px;font-size:11px;color:var(--error)" title="删除"><span class="material-symbols-outlined" style="font-size:14px">delete</span></button>'
        + '</div>'
      + '</div>'
      + '<div style="font-size:12px;color:var(--text2);margin-bottom:6px;line-height:1.5;max-height:48px;overflow:hidden">' + esc((v.system_prompt||'').slice(0,120)) + (v.system_prompt && v.system_prompt.length > 120 ? '...' : '') + '</div>'
      + (p.personality ? '<div style="font-size:11px;color:var(--text3)"><b>性格:</b> ' + esc(p.personality) + '</div>' : '')
      + (expertiseStr ? '<div style="font-size:11px;color:var(--text3)"><b>专长:</b> ' + esc(expertiseStr) + '</div>' : '')
      + (skillsStr ? '<div style="font-size:11px;color:var(--text3)"><b>技能:</b> ' + esc(skillsStr) + '</div>' : '')
    + '</div>';
  });
  grid.innerHTML = html;
}

// ── Knowledge Wiki Management ──
var _kbAllEntries = [];   // full list from server
var _kbActiveTag = '';     // currently selected tag filter

function _kbRenderCard(e) {
  var tags = (e.tags||[]).map(function(t){ return '<span style="background:var(--surface3);padding:1px 6px;border-radius:4px;font-size:11px;color:var(--text2)">'+esc(t)+'</span>'; }).join(' ');
  var preview = esc((e.content||'').slice(0, 120)) + (e.content && e.content.length > 120 ? '...' : '');
  return '<div class="kb-card" style="border:1px solid var(--border-light);border-radius:8px;padding:12px">' +
    '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">' +
      '<div style="font-weight:600;font-size:14px;color:var(--text)">' + esc(e.title) + '</div>' +
      '<div style="display:flex;gap:4px">' +
        '<button class="btn btn-sm" onclick="_kbShowEdit(\''+e.id+'\')" style="padding:3px 8px;font-size:11px"><span class="material-symbols-outlined" style="font-size:13px">edit</span></button>' +
        '<button class="btn btn-sm" onclick="_kbDelete(\''+e.id+'\',\''+esc(e.title).replace(/'/g,"\\'")+'\')" style="padding:3px 8px;font-size:11px;color:var(--error)"><span class="material-symbols-outlined" style="font-size:13px">delete</span></button>' +
      '</div>' +
    '</div>' +
    (tags ? '<div style="margin-bottom:6px">'+tags+'</div>' : '') +
    '<div style="color:var(--text3);font-size:12px;line-height:1.4;white-space:pre-wrap">'+preview+'</div>' +
  '</div>';
}

function _kbRenderTagBar(entries) {
  var bar = document.getElementById('kb-tag-bar');
  if (!bar) return;
  var tagSet = {};
  entries.forEach(function(e) { (e.tags||[]).forEach(function(t){ tagSet[t] = (tagSet[t]||0) + 1; }); });
  var allTags = Object.keys(tagSet).sort();
  if (allTags.length === 0) { bar.innerHTML = ''; return; }
  var html = '<button class="btn btn-sm" style="padding:2px 10px;font-size:11px;border-radius:12px;' +
    (!_kbActiveTag ? 'background:var(--accent);color:#fff' : '') +
    '" onclick="_kbSetTag(&quot;&quot;)">All</button>';
  allTags.forEach(function(t) {
    var active = (_kbActiveTag === t);
    var safe = esc(t).replace(/"/g, '&quot;');
    html += ' <button class="btn btn-sm" style="padding:2px 10px;font-size:11px;border-radius:12px;' +
      (active ? 'background:var(--accent);color:#fff' : '') +
      '" onclick="_kbSetTag(&quot;'+safe+'&quot;)">' + esc(t) + ' <span style="opacity:0.6">(' + tagSet[t] + ')</span></button>';
  });
  bar.innerHTML = html;
}

function _kbSetTag(tag) {
  _kbActiveTag = tag;
  _kbFilter();
}

function _kbFilter() {
  var searchEl = document.getElementById('kb-search');
  var q = (searchEl ? searchEl.value : '').toLowerCase().trim();
  var filtered = _kbAllEntries.filter(function(e) {
    // tag filter
    if (_kbActiveTag && (e.tags||[]).indexOf(_kbActiveTag) === -1) return false;
    // text search
    if (!q) return true;
    var title = (e.title||'').toLowerCase();
    var content = (e.content||'').toLowerCase();
    var tags = (e.tags||[]).join(' ').toLowerCase();
    return title.indexOf(q) !== -1 || content.indexOf(q) !== -1 || tags.indexOf(q) !== -1;
  });
  var el = document.getElementById('kb-entries-list');
  if (!el) return;
  if (filtered.length === 0) {
    el.innerHTML = '<div style="color:var(--text3);text-align:center;padding:20px 0;grid-column:1/-1">' +
      (q || _kbActiveTag ? 'No matching entries.' : 'No entries yet. Click "Add Entry" to create your first knowledge entry.') + '</div>';
  } else {
    el.innerHTML = filtered.map(_kbRenderCard).join('');
  }
  _kbRenderTagBar(_kbAllEntries);
}

async function _kbLoadEntries() {
  var el = document.getElementById('kb-entries-list');
  if (!el) return;
  try {
    var data = await api('GET', '/api/portal/knowledge');
    _kbAllEntries = (data && data.entries) || [];
    _kbFilter();
  } catch(e) {
    el.innerHTML = '<div style="color:var(--error)">Failed to load: '+esc(e.message)+'</div>';
  }
}

var _kbCache = {};  // id → entry for edit

function _kbShowAdd() {
  document.getElementById('kb-edit-id').value = '';
  document.getElementById('kb-edit-title').value = '';
  document.getElementById('kb-edit-tags').value = '';
  document.getElementById('kb-edit-content').value = '';
  document.getElementById('kb-modal-title').textContent = 'Add Knowledge Entry';
  document.getElementById('kb-modal').style.display = 'flex';
}

async function _kbShowEdit(id) {
  try {
    var data = await api('GET', '/api/portal/knowledge');
    var entry = ((data && data.entries) || []).find(function(e){ return e.id === id; });
    if (!entry) { alert('Entry not found'); return; }
    document.getElementById('kb-edit-id').value = entry.id;
    document.getElementById('kb-edit-title').value = entry.title || '';
    document.getElementById('kb-edit-tags').value = (entry.tags || []).join(', ');
    document.getElementById('kb-edit-content').value = entry.content || '';
    document.getElementById('kb-modal-title').textContent = 'Edit: ' + entry.title;
    document.getElementById('kb-modal').style.display = 'flex';
  } catch(e) { alert('Error: ' + e.message); }
}

function _kbCloseModal() {
  document.getElementById('kb-modal').style.display = 'none';
}

async function _kbSave() {
  var id = document.getElementById('kb-edit-id').value;
  var title = document.getElementById('kb-edit-title').value.trim();
  var content = document.getElementById('kb-edit-content').value.trim();
  var tagsRaw = document.getElementById('kb-edit-tags').value.trim();
  var tags = tagsRaw ? tagsRaw.split(',').map(function(t){ return t.trim(); }).filter(Boolean) : [];
  if (!title) { alert('Title is required'); return; }
  if (!content) { alert('Content is required'); return; }
  try {
    if (id) {
      await api('POST', '/api/portal/knowledge/' + id, { title: title, content: content, tags: tags });
    } else {
      await api('POST', '/api/portal/knowledge', { title: title, content: content, tags: tags });
    }
    _kbCloseModal();
    _kbLoadEntries();
  } catch(e) { alert('Save failed: ' + e.message); }
}

async function _kbDelete(id, title) {
  if (!confirm('Delete "' + title + '"?')) return;
  try {
    await api('POST', '/api/portal/knowledge/' + id + '/delete');
    _kbLoadEntries();
  } catch(e) { alert('Delete failed: ' + e.message); }
}

function _cfgProviderChanged() {
  var provEl = document.getElementById('cfg-provider');
  var modelEl = document.getElementById('cfg-model');
  if (!provEl || !modelEl) return;
  var pid = provEl.value;
  var models = _availableModels[pid] || [];
  modelEl.innerHTML = models.length
    ? models.map(m => '<option value="'+esc(m)+'">'+esc(m)+'</option>').join('')
    : '<option value="">-- no models detected --</option>';
  saveConfig();
}

async function _cfgDetectModels() {
  var provEl = document.getElementById('cfg-provider');
  if (!provEl) return;
  var pid = provEl.value;
  var btn = event.currentTarget;
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:16px;animation:spin 1s linear infinite">refresh</span> Detecting...';
  try {
    var data = await api('POST', '/api/portal/providers/'+pid+'/detect');
    if (data && data.models) {
      _availableModels[pid] = data.models;
      var modelEl = document.getElementById('cfg-model');
      if (modelEl) {
        modelEl.innerHTML = data.models.map(m =>
          '<option value="'+esc(m)+'">'+esc(m)+'</option>'
        ).join('');
      }
    }
  } catch(e) {
    alert('Detection failed: ' + e.message);
  }
  btn.disabled = false;
  btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:16px">refresh</span> Detect';
}

async function saveConfig() {
  var provEl = document.getElementById('cfg-provider');
  var modelEl = document.getElementById('cfg-model');
  if (!provEl || !modelEl) return;
  const body = {
    provider: provEl.value,
    model: modelEl.value,
  };
  await api('POST', '/api/portal/config', body);
  loadAvailableModels();
}

// _cfgSaveGlobalPrompt removed — merged into unified System Prompts (scene_prompts)
