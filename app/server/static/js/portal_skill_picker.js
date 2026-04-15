}

// ============ Skill picker (used in Create Agent dialog) ============
window._caSelectedSkills = window._caSelectedSkills || [];
window._caSkillCatalog = null;

const CA_SKILL_CATEGORY_LABELS = {
  'builtin': '🏆 内置经典', 'marketing': '📣 市场营销', 'engineering': '💻 工程研发',
  'sales': '🤝 销售', 'design': '🎨 设计', 'product': '📋 产品', 'strategy': '🧭 战略',
  'support': '🎧 客户支持', 'testing': '🧪 测试', 'academic': '🎓 学术研究',
  'finance': '💰 财务', 'legal': '⚖️ 法务', 'hr': '👥 人力', 'paid-media': '📊 投放',
  'project-management': '📅 项目管理', 'specialized': '✨ 特殊场景',
  'spatial-computing': '🥽 空间计算', 'game-development': '🎮 游戏', 'supply-chain': '🏭 供应链',
  'community': '📦 社区'
};

async function openCreateAgentSkillPicker() {
  if (!window._caSkillCatalog) {
    const res = await api('GET', '/api/portal/enhancement-presets');
    window._caSkillCatalog = (res && res.presets) || [];
  }
  renderSkillPickerModal();
}

function renderSkillPickerModal(filter) {
  filter = (filter||'').trim().toLowerCase();
  const all = window._caSkillCatalog || [];
  // Group by category
  const groups = {};
  all.forEach(function(p) {
    const cat = p.category || (p.source ? p.source : 'builtin');
    const catKey = (cat === 'agency-agents-zh') ? 'community' : cat;
    if (!groups[catKey]) groups[catKey] = [];
    if (filter) {
      const hay = ((p.name||'') + ' ' + (p.description||'') + ' ' + (p.id||'')).toLowerCase();
      if (hay.indexOf(filter) < 0) return;
    }
    groups[catKey].push(p);
  });
  // Order categories
  const builtin_cats = ['builtin'];
  const sorted_cats = Object.keys(groups).sort(function(a,b){
    if (a==='builtin') return -1;
    if (b==='builtin') return 1;
    return (CA_SKILL_CATEGORY_LABELS[a]||a).localeCompare(CA_SKILL_CATEGORY_LABELS[b]||b);
  });
  const selected = window._caSelectedSkills || [];

  let html = '<div style="padding:18px;max-height:80vh;display:flex;flex-direction:column;min-width:680px">';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">';
  html += '<h3 style="font-family:\'Plus Jakarta Sans\',sans-serif;margin:0">选择专业领域 <span style="font-size:12px;color:var(--text3);font-weight:400">(最多 8 个，已选 <span id="sp-count">' + selected.length + '</span>/8)</span></h3>';
  html += '<input id="sp-search" type="text" placeholder="🔍 搜索专业领域..." style="padding:6px 10px;background:var(--surface3);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:12px;width:240px" oninput="renderSkillPickerModal(this.value)" value="' + esc(filter) + '">';
  html += '</div>';
  html += '<div style="overflow-y:auto;flex:1;max-height:60vh;padding-right:4px">';

  let total = 0;
  sorted_cats.forEach(function(cat) {
    const items = groups[cat] || [];
    if (!items.length) return;
    total += items.length;
    const label = CA_SKILL_CATEGORY_LABELS[cat] || cat;
    html += '<div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin:12px 0 6px">' + esc(label) + ' <span style="color:var(--text3);font-weight:400;text-transform:none">(' + items.length + ')</span></div>';
    html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">';
    items.forEach(function(p) {
      const isSelected = selected.indexOf(p.id) >= 0;
      html += '<div data-skill-id="' + esc(p.id) + '" onclick="toggleCaSkill(\'' + esc(p.id) + '\',this)" ' +
        'style="background:' + (isSelected?'rgba(203,201,255,0.12)':'var(--surface3)') + ';border-radius:8px;padding:10px;cursor:pointer;border:1px solid ' + (isSelected?'var(--primary)':'var(--border-light)') + ';transition:all 0.15s">' +
        '<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">' +
        '<span style="font-size:15px">' + (p.icon||'📦') + '</span>' +
        '<div style="font-weight:600;font-size:12px;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(p.name) + '</div>' +
        '</div>' +
        '<div style="font-size:10px;color:var(--text3);line-height:1.4;max-height:28px;overflow:hidden">' + esc(p.description||'') + '</div>' +
      '</div>';
    });
    html += '</div>';
  });
  if (total === 0) {
    html += '<div style="text-align:center;color:var(--text3);padding:40px 0">未找到匹配的技能</div>';
  }
  html += '</div>';
  html += '<div style="display:flex;justify-content:flex-end;gap:8px;padding-top:14px;border-top:1px solid var(--border-light);margin-top:12px">';
  html += '<button class="btn btn-sm" onclick="closeModal()">取消</button>';
  html += '<button class="btn btn-primary btn-sm" onclick="confirmCaSkillSelection()">确认 (<span id="sp-btn-count">' + selected.length + '</span>)</button>';
  html += '</div>';
  html += '</div>';
  showModalHTML(html);
}

function toggleCaSkill(presetId, el) {
  const list = window._caSelectedSkills || [];
  const idx = list.indexOf(presetId);
  if (idx >= 0) {
    list.splice(idx, 1);
    el.style.borderColor = 'var(--border-light)';
    el.style.background = 'var(--surface3)';
  } else {
    if (list.length >= 8) { alert('最多只能选择 8 个技能'); return; }
    list.push(presetId);
    el.style.borderColor = 'var(--primary)';
    el.style.background = 'rgba(203,201,255,0.12)';
  }
  window._caSelectedSkills = list;
  const c1 = document.getElementById('sp-count');
  const c2 = document.getElementById('sp-btn-count');
  if (c1) c1.textContent = list.length;
  if (c2) c2.textContent = list.length;
}

function confirmCaSkillSelection() {
  const list = window._caSelectedSkills || [];
  const chips = document.getElementById('ca-skills-chips');
  if (chips) {
    if (!list.length) {
      chips.innerHTML = '未选择任何专业领域';
      chips.style.color = 'var(--text3)';
    } else {
      const catalog = window._caSkillCatalog || [];
      const byId = {};
      catalog.forEach(function(p){ byId[p.id] = p; });
      chips.style.color = 'var(--text)';
      chips.innerHTML = list.map(function(id) {
        const p = byId[id] || {name:id, icon:'📦'};
        return '<span style="background:var(--primary);color:#0e141b;padding:3px 8px;border-radius:12px;font-size:11px;font-weight:600;display:inline-flex;align-items:center;gap:4px">' +
          (p.icon||'📦') + ' ' + esc(p.name) +
          '<span onclick="event.stopPropagation();removeCaSkill(\'' + esc(id) + '\')" style="cursor:pointer;margin-left:2px">✕</span></span>';
      }).join('');
    }
  }
  closeModal();
}

function removeCaSkill(id) {
  const list = window._caSelectedSkills || [];
  const idx = list.indexOf(id);
  if (idx >= 0) list.splice(idx, 1);
  window._caSelectedSkills = list;
  confirmCaSkillSelection();
}

// ── Tag (Expertise + Skills) management ──────────────────
window._caTags = [];
window._eaTags = [];

function _renderTags(tags, containerId, removeFunc) {
  var c = document.getElementById(containerId);
  if (!c) return;
  if (!tags.length) { c.innerHTML = '<span style="color:var(--text3);font-size:12px">暂无标签</span>'; return; }
  c.innerHTML = tags.map(function(t, i) {
    return '<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;background:var(--primary);color:#fff;border-radius:12px;font-size:12px;white-space:nowrap">'
      + t + ' <span onclick="'+removeFunc+'('+i+')" style="cursor:pointer;font-size:14px;line-height:1;opacity:0.8">&times;</span></span>';
  }).join('');
}

function caAddTags(input) {
  var val = input.value.trim();
  if (!val) return;
  val.split(',').forEach(function(s) {
    s = s.trim();
    if (s && window._caTags.indexOf(s) < 0) window._caTags.push(s);
  });
  input.value = '';
  _renderTags(window._caTags, 'ca-tags-display', 'caRemoveTag');
}
function caRemoveTag(i) { window._caTags.splice(i, 1); _renderTags(window._caTags, 'ca-tags-display', 'caRemoveTag'); }

function eaAddTags(input) {
  var val = input.value.trim();
  if (!val) return;
  val.split(',').forEach(function(s) {
    s = s.trim();
    if (s && window._eaTags.indexOf(s) < 0) window._eaTags.push(s);
  });
  input.value = '';
  _renderTags(window._eaTags, 'ea-tags-display', 'eaRemoveTag');
}
function eaRemoveTag(i) { window._eaTags.splice(i, 1); _renderTags(window._eaTags, 'ea-tags-display', 'eaRemoveTag'); }

// ──────────────── Multi-LLM slot helpers (Edit Agent) ────────────────
function eaToggleLlmPanel() {
  var panel = document.getElementById('ea-llm-panel');
  var icon = document.getElementById('ea-llm-toggle-label');
  if (!panel) return;
  var willShow = panel.style.display === 'none';
  panel.style.display = willShow ? 'block' : 'none';
  if (icon) icon.textContent = willShow ? 'expand_less' : 'expand_more';
}

function eaAddExtraLlmRow() {
  if (!Array.isArray(window._eaExtraLlms)) window._eaExtraLlms = [];
  window._eaExtraLlms.push({label:'', provider:'', model:'', purpose:'', note:''});
  eaRenderExtraLlms();
}

function eaRemoveExtraLlm(idx) {
  if (!Array.isArray(window._eaExtraLlms)) return;
  window._eaExtraLlms.splice(idx, 1);
  eaRenderExtraLlms();
}

// In-place mutate (so in-flight typing isn't blown away by re-render)
function eaExtraLlmSet(idx, field, value) {
  if (!Array.isArray(window._eaExtraLlms)) return;
  if (!window._eaExtraLlms[idx]) return;
  window._eaExtraLlms[idx][field] = value;
  // provider change needs model dropdown refresh
  if (field === 'provider') {
    var modelSelId = 'ea-extra-llm-model-' + idx;
    var provSelId = 'ea-extra-llm-provider-' + idx;
    // temporarily stash value so updateModelSelect can honor it
    window._eaExtraLlms[idx].model = '';
    updateModelSelect(provSelId, modelSelId, '');
  }
}

function eaRenderExtraLlms() {
  var host = document.getElementById('ea-extra-llms-rows');
  if (!host) return;
  var slots = window._eaExtraLlms || [];
  if (!slots.length) {
    host.innerHTML = '<div style="font-size:11px;color:var(--text3);padding:6px 0">（还没有 slot — 点击右上角「添加」来配置第一个）</div>';
    return;
  }
  // Build rows: [label | purpose | provider | model | note | ×]
  var providerOptions = '<option value="">（使用默认）</option>' +
    (_providerList || []).map(function(p){
      return '<option value="'+p.id+'">'+p.name+'</option>';
    }).join('');
  var html = '';
  slots.forEach(function(s, i){
    var esc = function(v){ return String(v==null?'':v).replace(/"/g,'&quot;'); };
    html += '<div style="display:grid;grid-template-columns:110px 110px 110px 140px 1fr 28px;gap:6px;margin-bottom:6px;align-items:center">' +
      '<input placeholder="label*" value="'+esc(s.label)+'" onchange="eaExtraLlmSet('+i+',\'label\',this.value)" style="font-size:12px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:6px 8px">' +
      '<input placeholder="purpose" value="'+esc(s.purpose)+'" onchange="eaExtraLlmSet('+i+',\'purpose\',this.value)" style="font-size:12px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:6px 8px">' +
      '<select id="ea-extra-llm-provider-'+i+'" onchange="eaExtraLlmSet('+i+',\'provider\',this.value)" style="font-size:12px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:6px 8px">'+providerOptions+'</select>' +
      '<select id="ea-extra-llm-model-'+i+'" onchange="eaExtraLlmSet('+i+',\'model\',this.value)" style="font-size:12px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:6px 8px"><option value="">（使用默认）</option></select>' +
      '<input placeholder="note（可选备注）" value="'+esc(s.note)+'" onchange="eaExtraLlmSet('+i+',\'note\',this.value)" style="font-size:12px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:6px 8px">' +
      '<button type="button" class="btn btn-ghost btn-sm" onclick="eaRemoveExtraLlm('+i+')" title="删除" style="padding:2px 4px"><span class="material-symbols-outlined" style="font-size:14px">close</span></button>' +
    '</div>';
  });
  host.innerHTML = html;
  // After insertion, set provider/model dropdown values + populate models
  slots.forEach(function(s, i){
    var provSel = document.getElementById('ea-extra-llm-provider-'+i);
    if (provSel) provSel.value = s.provider || '';
    updateModelSelect('ea-extra-llm-provider-'+i, 'ea-extra-llm-model-'+i, s.model || '');
  });
}

// ── Robot Avatar picker ──────────────────────────────────
var _AVATAR_ROLES = ['ceo','cto','coder','reviewer','researcher','architect','pm','designer','tester','devops','data','general'];
window._caSelectedAvatar = '';
window._eaSelectedAvatar = '';

function _renderAvatarGrid(containerId, selectedVar, clickFunc) {
  var c = document.getElementById(containerId);
  if (!c) return;
  c.innerHTML = _AVATAR_ROLES.map(function(r) {
    var id = 'robot_' + r;
    var sel = (window[selectedVar] === id) ? 'border:2px solid var(--primary);box-shadow:0 0 6px var(--primary)' : 'border:2px solid transparent';
    return '<div onclick="'+clickFunc+'(\''+id+'\')" style="cursor:pointer;border-radius:8px;padding:4px;text-align:center;'+sel+';transition:all .15s">'
      + '<img src="/static/robots/'+id+'.svg" style="width:40px;height:40px" onerror="this.outerHTML=\'<span class=material-symbols-outlined style=font-size:36px;color:var(--text3)>smart_toy</span>\'">'
      + '<div style="font-size:10px;color:var(--text2);margin-top:2px">'+r+'</div></div>';
  }).join('');
}

function caPickAvatar(id) {
  window._caSelectedAvatar = (window._caSelectedAvatar === id) ? '' : id;
  _renderAvatarGrid('ca-avatar-grid', '_caSelectedAvatar', 'caPickAvatar');
}
function eaPickAvatar(id) {
  window._eaSelectedAvatar = (window._eaSelectedAvatar === id) ? '' : id;
  _renderAvatarGrid('ea-avatar-grid', '_eaSelectedAvatar', 'eaPickAvatar');
}

// Persona template library — loaded once, reused on open
window._caPersonaCache = null;
async function loadPersonasForCreate() {
  const sel = document.getElementById('ca-persona');
  if (!sel || sel.options.length > 1) return; // already loaded
  try {
    const data = await api('GET', '/api/portal/personas');
    const list = (data && data.personas) || [];
    window._caPersonaCache = {};
    list.forEach(function(p){
      const o = document.createElement('option');
      o.value = p.id;
      o.textContent = (p.avatar_emoji||'👤') + ' ' + (p.name_cn||p.name_en||p.id) +
                      (p.role?' · '+p.role:'');
      sel.appendChild(o);
      window._caPersonaCache[p.id] = p;
    });
  } catch(e) { console.warn('load personas failed', e); }
  // Init avatar grid and clear tags
  window._caTags = [];
  _renderTags(window._caTags, 'ca-tags-display', 'caRemoveTag');
  window._caSelectedAvatar = '';
  _renderAvatarGrid('ca-avatar-grid', '_caSelectedAvatar', 'caPickAvatar');
}
async function caUpdateExpCount() {
  var role = document.getElementById('ca-role').value;
  var infoEl = document.getElementById('ca-exp-info');
  if (!infoEl) return;
  var siCheck = document.getElementById('ca-self-improve');
  var impCheck = document.getElementById('ca-import-exp');
  if (!siCheck.checked) { infoEl.textContent = 'Self-improvement disabled'; return; }
  if (!impCheck.checked) { infoEl.textContent = 'Experience import disabled'; return; }
  try {
    var data = await api('GET', '/api/portal/experience/stats');
    var roleInfo = (data && data.roles && data.roles[role]) ? data.roles[role] : null;
    if (roleInfo && roleInfo.total > 0) {
      infoEl.innerHTML = '📚 <b>'+roleInfo.total+'</b> experiences available for role <b>'+role+'</b> ('+roleInfo.core_count+' core). Will import up to 50.';
    } else {
      infoEl.textContent = 'No existing experiences for role: '+role+'. New library will be created.';
    }
  } catch(e) { infoEl.textContent = 'Experience library ready.'; }
}

function applyPersonaPreview() {
  const id = document.getElementById('ca-persona').value;
  const prev = document.getElementById('ca-persona-preview');
  if (!id) { prev.textContent = ''; return; }
  const p = (window._caPersonaCache||{})[id];
  if (!p) { prev.textContent = ''; return; }
  prev.textContent = (p.tagline||'') + (p.role?' · role='+p.role:'');
  // Auto-fill name if empty
  const nameEl = document.getElementById('ca-name');
  if (!nameEl.value.trim()) nameEl.value = p.name_cn || p.name_en || '';
}
function memoryToCount(pref) {
  return {short:20, medium:50, long:100, xlong:200}[pref] || 50;
}

async function createAgent() {
  const agentClass = document.getElementById('ca-agent-class').value;
  const memoryMode = document.getElementById('ca-memory-mode').value;
  const ragMode = document.getElementById('ca-rag-mode').value;
  const ragProviderId = document.getElementById('ca-rag-provider').value;
  const name = document.getElementById('ca-name').value.trim();
  const role = document.getElementById('ca-role').value;
  const priorityLevel = parseInt(document.getElementById('ca-priority-level').value) || 3;
  const roleTitle = document.getElementById('ca-role-title').value.trim();
  const personaId = document.getElementById('ca-persona').value;
  const personality = document.getElementById('ca-personality').value;
  const style = document.getElementById('ca-style').value;
  const allTags = (window._caTags || []).slice();
  const language = document.getElementById('ca-language').value;
  const memPref = document.getElementById('ca-memory').value;
  const temperature = parseFloat(document.getElementById('ca-temperature').value);
  const execPolicy = document.getElementById('ca-exec-policy').value;
  const model = document.getElementById('ca-model').value.trim();
  const provider = document.getElementById('ca-provider').value;
  const node_id = document.getElementById('ca-node').value;
  const workdir = document.getElementById('ca-workdir').value.trim();
  const prompt = document.getElementById('ca-prompt').value.trim();

  if(!name) { alert('Please enter agent name'); return; }

  try {
    const data = await api('POST', '/api/portal/agent/create', {
      name: name, role: role, model: model, provider: provider, node_id: node_id,
      working_dir: workdir,
      // Note: do NOT send `system_prompt` here — that would fully override
      // the persona's curated prompt. The textarea below is "Custom
      // Instructions" which gets appended via profile.custom_instructions.
      priority_level: priorityLevel, role_title: roleTitle,
      persona_id: personaId || '',
      robot_avatar: window._caSelectedAvatar || ('robot_' + role),
      profile: {
        agent_class: agentClass, memory_mode: memoryMode,
        rag_mode: ragMode, rag_provider_id: ragProviderId,
        personality: personality, communication_style: style,
        expertise: allTags,
        skills: allTags,
        language: language,
        custom_instructions: prompt,
        max_context_messages: memoryToCount(memPref),
        temperature: temperature,
        exec_policy: execPolicy
      }
    });

    if (data && data.id) {
      // Apply selected skills (enhancement presets) if any
      const selectedSkills = (window._caSelectedSkills || []).slice(0, 5);
      if (selectedSkills.length) {
        try {
          await api('POST', '/api/portal/agent/' + data.id + '/enhancement',
                    { action:'enable', domains: selectedSkills });
        } catch(err) { console.error('enable skills error:', err); }
      }
      // Enable self-improvement if checked
      const siEnabled = document.getElementById('ca-self-improve').checked;
      const siImport = document.getElementById('ca-import-exp').checked;
      if (siEnabled) {
        try {
          await api('POST', '/api/portal/agent/' + data.id + '/self-improvement/enable', {
            import_experience: siImport, import_limit: 50
          });
        } catch(err) { console.error('enable self-improvement error:', err); }
      }
      // Bind domain knowledge base if selected (for advisor/private mode)
      if (ragMode === 'private' || ragMode === 'both') {
        var domainKbId = (document.getElementById('ca-rag-domain-kb')||{}).value || '';
        if (domainKbId) {
          try {
            // Store the domain KB binding in agent's rag_collection_ids
            await api('POST', '/api/portal/agent/' + data.id + '/update', {
              profile: { rag_collection_ids: [domainKbId] }
            });
          } catch(err) { console.error('bind domain KB error:', err); }
        }
      }
      window._caSelectedSkills = [];
      hideModal('create-agent');
      document.getElementById('ca-name').value = '';
      document.getElementById('ca-priority-level').value = '3';
      document.getElementById('ca-role-title').value = '';
      document.getElementById('ca-persona').value = '';
      document.getElementById('ca-persona-preview').textContent = '';
      document.getElementById('ca-personality').value = 'helpful';
      document.getElementById('ca-style').value = 'technical';
      document.getElementById('ca-expertise').value = '';
      window._caTags = [];
      _renderTags(window._caTags, 'ca-tags-display', 'caRemoveTag');
      window._caSelectedAvatar = '';
      _renderAvatarGrid('ca-avatar-grid', '_caSelectedAvatar', 'caPickAvatar');
      document.getElementById('ca-agent-class').value = 'enterprise';
      document.getElementById('ca-memory-mode').value = 'full';
      document.getElementById('ca-rag-mode').value = 'shared';
      document.getElementById('ca-rag-provider').value = '';
      var dkbSel = document.getElementById('ca-rag-domain-kb');
      if (dkbSel) dkbSel.value = '';
      _onRagModeChange('shared');
      document.getElementById('ca-memory').value = 'medium';
      document.getElementById('ca-mem-label').textContent = '(50 条)';
      document.getElementById('ca-temperature').value = '0.7';
      document.getElementById('ca-temp-label').textContent = '(0.7 平衡)';
      document.getElementById('ca-exec-policy').value = 'ask';
      document.getElementById('ca-model').value = '';
      document.getElementById('ca-prompt').value = '';
      document.getElementById('ca-workdir').value = '';
      const chips = document.getElementById('ca-skills-chips');
      if (chips) chips.innerHTML = '未选择任何专业领域';
      await refresh();
      showAgentView(data.id, null);
    } else if (data && data.error) {
      alert('Failed to create agent: ' + data.error);
    } else {
      alert('Failed to create agent. Check console for details.');
    }
  } catch(e) {
    console.error('createAgent error:', e);
    alert('Error creating agent: ' + e.message);
  }
