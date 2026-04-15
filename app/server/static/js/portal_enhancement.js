}

// ============ Enhancement Panel ============
async function showEnhancementPanel(agentId) {
  const data = await api('GET', '/api/portal/agent/' + agentId + '/enhancement');
  if (!data) return;
  const enh = data.enhancement;
  const presets = data.presets || [];
  const ag = agents.find(a => a.id === agentId) || {};

  let html = '<div style="padding:20px;max-height:80vh;overflow-y:auto">';
  html += '<h3 style="margin-bottom:4px;font-family:\'Plus Jakarta Sans\',sans-serif">专业领域</h3>';
  html += '<p style="color:var(--text2);font-size:12px;margin-bottom:16px">' + esc(ag.name || agentId) + ' — 为 Agent 装载专业领域，让它在特定场景变得更专业</p>';

  if (!enh) {
    // Not enabled — show preset multi-selection (up to 8)
    window._enhSelected = window._enhSelected || {};
    window._enhSelected[agentId] = [];
    html += '<div style="margin-bottom:16px"><p style="font-size:13px;color:var(--text2);margin-bottom:8px">选择最多 8 个专业领域来装载 (点击卡片切换选中):</p>';
    html += '<div id="enh-selected-bar" style="min-height:28px;margin-bottom:10px;font-size:12px;color:var(--text3)">未选择</div>';
    html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">';
    presets.forEach(p => {
      html += '<div class="enh-preset-card" data-preset-id="' + esc(p.id) + '" ' +
        'style="background:var(--surface3);border-radius:10px;padding:14px;cursor:pointer;border:1px solid var(--border-light);transition:all 0.2s" ' +
        'onclick="toggleEnhPreset(\'' + agentId + '\',\'' + esc(p.id) + '\',this)">' +
        '<div style="font-size:20px;margin-bottom:6px">' + (p.icon||'📦') + '</div>' +
        '<div style="font-weight:700;font-size:13px">' + esc(p.name) + '</div>' +
        '<div style="font-size:11px;color:var(--text3);margin-top:4px">' + esc(p.description) + '</div>' +
      '</div>';
    });
    // Custom domain
    html += '<div style="background:var(--surface3);border-radius:10px;padding:14px;cursor:pointer;border:1px dashed var(--border-light)" ' +
      'onclick="enableCustomEnhancement(\'' + agentId + '\')">' +
      '<div style="font-size:20px;margin-bottom:6px">✏️</div>' +
      '<div style="font-weight:700;font-size:13px">自定义技能</div>' +
      '<div style="font-size:11px;color:var(--text3);margin-top:4px">创建空白技能，手动添加知识和思维模式</div>' +
    '</div>';
    html += '</div>';
    html += '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px">' +
      '<button class="btn btn-sm" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-primary btn-sm" id="enh-apply-btn" disabled onclick="applySelectedEnhancements(\'' + agentId + '\')">装载选中技能</button>' +
      '</div>';
    html += '</div>';
  } else {
    // Enabled — show stats and management
    html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">';
    html += '<div style="display:flex;align-items:center;gap:8px">';
    html += '<span style="background:var(--primary);color:#000;padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700">' + esc(enh.domain) + '</span>';
    html += '<span style="color:var(--success);font-size:12px">● Active</span>';
    html += '</div>';
    html += '<button class="btn btn-sm" style="color:var(--error);font-size:11px" onclick="disableEnhancement(\'' + agentId + '\')">Unload</button>';
    html += '</div>';

    // Stats
    html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px">';
    [{l:'Knowledge',v:enh.knowledge_entries,i:'auto_stories'},{l:'Reasoning',v:enh.reasoning_patterns,i:'psychology'},{l:'Memory',v:enh.memory_nodes,i:'neurology'},{l:'Tool Chains',v:enh.tool_chains,i:'account_tree'}].forEach(s => {
      html += '<div style="background:var(--surface3);border-radius:8px;padding:12px;text-align:center">' +
        '<span class="material-symbols-outlined" style="font-size:18px;color:var(--primary)">' + s.i + '</span>' +
        '<div style="font-size:18px;font-weight:700;margin:4px 0">' + s.v + '</div>' +
        '<div style="font-size:10px;color:var(--text3);text-transform:uppercase">' + s.l + '</div></div>';
    });
    html += '</div>';

    // Add knowledge button
    html += '<div style="display:flex;gap:8px;margin-bottom:16px">';
    html += '<button class="btn btn-primary btn-sm" onclick="showAddKnowledge(\'' + agentId + '\')"><span class="material-symbols-outlined" style="font-size:14px">add</span> Add Knowledge</button>';
    html += '<button class="btn btn-sm" onclick="showAddReasoningPattern(\'' + agentId + '\')"><span class="material-symbols-outlined" style="font-size:14px">psychology</span> Add Reasoning</button>';
    html += '<button class="btn btn-sm" onclick="showAddMemory(\'' + agentId + '\')"><span class="material-symbols-outlined" style="font-size:14px">neurology</span> Add Memory</button>';
    html += '</div>';

    // Knowledge entries list
    if (enh.knowledge_list && enh.knowledge_list.length) {
      html += '<div style="margin-bottom:12px"><div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Knowledge Entries</div>';
      enh.knowledge_list.forEach(function(k) {
        html += '<div style="display:flex;align-items:center;justify-content:space-between;background:var(--surface3);border-radius:6px;padding:8px 10px;margin-bottom:4px">' +
          '<div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600;color:var(--text)">' + esc(k.title) + '</div><div style="font-size:10px;color:var(--text3)">' + esc(k.category||'') + '</div></div>' +
          '<button class="btn btn-sm" style="color:var(--error);font-size:10px;padding:2px 6px" onclick="removeEnhItem(\'' + agentId + '\',\'remove_knowledge\',\'entry_id\',\'' + k.id + '\')">✕</button></div>';
      });
      html += '</div>';
    }

    // Reasoning patterns list
    if (enh.reasoning_list && enh.reasoning_list.length) {
      html += '<div style="margin-bottom:12px"><div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Reasoning Patterns</div>';
      enh.reasoning_list.forEach(function(r) {
        html += '<div style="display:flex;align-items:center;justify-content:space-between;background:var(--surface3);border-radius:6px;padding:8px 10px;margin-bottom:4px">' +
          '<div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600;color:var(--text)">' + esc(r.name) + '</div><div style="font-size:10px;color:var(--text3)">' + esc(r.description||'') + '</div></div>' +
          '<button class="btn btn-sm" style="color:var(--error);font-size:10px;padding:2px 6px" onclick="removeEnhItem(\'' + agentId + '\',\'remove_reasoning_pattern\',\'pattern_id\',\'' + r.id + '\')">✕</button></div>';
      });
      html += '</div>';
    }

    // Memory nodes list
    if (enh.memory_list && enh.memory_list.length) {
      html += '<div style="margin-bottom:12px"><div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Memory Nodes</div>';
      enh.memory_list.forEach(function(m) {
        html += '<div style="display:flex;align-items:center;justify-content:space-between;background:var(--surface3);border-radius:6px;padding:8px 10px;margin-bottom:4px">' +
          '<div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600;color:var(--text)">' + esc(m.title) + '</div><div style="font-size:10px;color:var(--text3)">' + esc(m.kind||'') + ' — imp: ' + (m.importance||0).toFixed(1) + '</div></div>' +
          '<button class="btn btn-sm" style="color:var(--error);font-size:10px;padding:2px 6px" onclick="removeEnhItem(\'' + agentId + '\',\'remove_memory\',\'node_id\',\'' + m.id + '\')">✕</button></div>';
      });
      html += '</div>';
    }

    // Usage stats
    html += '<div style="font-size:11px;color:var(--text3);padding:8px 0;border-top:1px solid var(--border-light)">';
    html += 'Enhance calls: ' + (enh.enhance_count||0) + ' | Recalls: ' + (enh.recall_count||0) + ' | Reflections: ' + (enh.reflection_count||0) + ' | Learned: ' + (enh.learn_count||0);
    html += '</div>';
  }
  html += '</div>';
  showModalHTML(html);
}

async function enableEnhancement(agentId, domain) {
  await api('POST', '/api/portal/agent/' + agentId + '/enhancement', {action:'enable', domain});
  closeModal();
  refresh();
}

function toggleEnhPreset(agentId, presetId, el) {
  window._enhSelected = window._enhSelected || {};
  const list = window._enhSelected[agentId] || [];
  const idx = list.indexOf(presetId);
  if (idx >= 0) {
    list.splice(idx, 1);
    el.style.borderColor = 'var(--border-light)';
    el.style.background = 'var(--surface3)';
  } else {
    if (list.length >= 8) { alert('最多只能选择 8 个技能'); return; }
    list.push(presetId);
    el.style.borderColor = 'var(--primary)';
    el.style.background = 'rgba(203,201,255,0.08)';
  }
  window._enhSelected[agentId] = list;
  const bar = document.getElementById('enh-selected-bar');
  if (bar) bar.textContent = list.length ? ('已选 ' + list.length + '/8: ' + list.join(' + ')) : '未选择';
  const btn = document.getElementById('enh-apply-btn');
  if (btn) btn.disabled = list.length === 0;
}

async function applySelectedEnhancements(agentId) {
  const list = (window._enhSelected && window._enhSelected[agentId]) || [];
  if (!list.length) return;
  await api('POST', '/api/portal/agent/' + agentId + '/enhancement', {action:'enable', domains:list});
  window._enhSelected[agentId] = [];
  closeModal();
  refresh();
}

function enableCustomEnhancement(agentId) {
  const domain = prompt('输入自定义技能名称 (如: blockchain, game_dev):');
  if (domain) enableEnhancement(agentId, domain.trim());
}

async function disableEnhancement(agentId) {
  if (!confirm('确定要卸载所有技能吗？学习记忆将丢失。')) return;
  await api('POST', '/api/portal/agent/' + agentId + '/enhancement', {action:'disable'});
  closeModal();
  refresh();
}

function showAddKnowledge(agentId) {
  const html = '<div style="padding:16px"><h3 style="margin-bottom:16px">Add Domain Knowledge</h3>' +
    '<div class="form-group"><label>Title</label><input id="enh-kb-title" placeholder="e.g. SQL注入检测模式"></div>' +
    '<div class="form-group"><label>Content</label><textarea id="enh-kb-content" rows="4" style="width:100%;background:var(--surface3);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:8px;font-size:13px" placeholder="详细知识内容..."></textarea></div>' +
    '<div class="form-group"><label>Category</label><select id="enh-kb-cat"><option value="pattern">Pattern</option><option value="best_practice">Best Practice</option><option value="constraint">Constraint</option><option value="pitfall">Pitfall</option><option value="reference">Reference</option></select></div>' +
    '<div class="form-group"><label>Tags (comma separated)</label><input id="enh-kb-tags" placeholder="security, sql, web"></div>' +
    '<div class="form-group"><label>Priority (0-10)</label><input id="enh-kb-priority" type="number" value="5" min="0" max="10"></div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">' +
    '<button class="btn btn-sm" onclick="closeModal()">Cancel</button>' +
    '<button class="btn btn-primary btn-sm" onclick="saveKnowledgeEntry(\'' + agentId + '\')">Save</button></div></div>';
  showModalHTML(html);
}

async function saveKnowledgeEntry(agentId) {
  const tags = document.getElementById('enh-kb-tags').value.split(',').map(t => t.trim()).filter(Boolean);
  await api('POST', '/api/portal/agent/' + agentId + '/enhancement', {
    action: 'add_knowledge',
    title: document.getElementById('enh-kb-title').value,
    content: document.getElementById('enh-kb-content').value,
    category: document.getElementById('enh-kb-cat').value,
    tags: tags,
    priority: parseInt(document.getElementById('enh-kb-priority').value) || 5,
  });
  closeModal();
  showEnhancementPanel(agentId);
}

function showAddReasoningPattern(agentId) {
  const html = '<div style="padding:16px"><h3 style="margin-bottom:16px">Add Reasoning Pattern</h3>' +
    '<div class="form-group"><label>Pattern Name</label><input id="enh-rp-name" placeholder="e.g. 安全审计分析"></div>' +
    '<div class="form-group"><label>Description</label><input id="enh-rp-desc" placeholder="What type of task this pattern guides"></div>' +
    '<div class="form-group"><label>Trigger Keywords (comma separated)</label><input id="enh-rp-kw" placeholder="安全, audit, 漏洞"></div>' +
    '<div class="form-group"><label>Steps (JSON array)</label><textarea id="enh-rp-steps" rows="5" style="width:100%;background:var(--surface3);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:8px;font-family:monospace;font-size:12px" placeholder=\'[{"name":"Step 1","instruction":"What to think about"}]\'></textarea></div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">' +
    '<button class="btn btn-sm" onclick="closeModal()">Cancel</button>' +
    '<button class="btn btn-primary btn-sm" onclick="saveReasoningPattern(\'' + agentId + '\')">Save</button></div></div>';
  showModalHTML(html);
}

async function saveReasoningPattern(agentId) {
  let steps = [];
  try { steps = JSON.parse(document.getElementById('enh-rp-steps').value); } catch(e) { alert('Invalid JSON for steps'); return; }
  await api('POST', '/api/portal/agent/' + agentId + '/enhancement', {
    action: 'add_reasoning_pattern',
    name: document.getElementById('enh-rp-name').value,
    description: document.getElementById('enh-rp-desc').value,
    trigger_keywords: document.getElementById('enh-rp-kw').value.split(',').map(t => t.trim()).filter(Boolean),
    steps: steps,
  });
  closeModal();
  showEnhancementPanel(agentId);
}

function showAddMemory(agentId) {
  const html = '<div style="padding:16px"><h3 style="margin-bottom:16px">Add Memory</h3>' +
    '<div class="form-group"><label>Title</label><input id="enh-mem-title" placeholder="What was learned"></div>' +
    '<div class="form-group"><label>Content</label><textarea id="enh-mem-content" rows="3" style="width:100%;background:var(--surface3);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:8px;font-size:13px" placeholder="Details..."></textarea></div>' +
    '<div class="form-group"><label>Kind</label><select id="enh-mem-kind"><option value="observation">Observation</option><option value="lesson">Lesson</option><option value="error_fix">Error Fix</option><option value="success_pattern">Success Pattern</option></select></div>' +
    '<div class="form-group"><label>Importance (0.0 - 1.0)</label><input id="enh-mem-imp" type="number" value="0.5" min="0" max="1" step="0.1"></div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">' +
    '<button class="btn btn-sm" onclick="closeModal()">Cancel</button>' +
    '<button class="btn btn-primary btn-sm" onclick="saveMemoryEntry(\'' + agentId + '\')">Save</button></div></div>';
  showModalHTML(html);
}

async function saveMemoryEntry(agentId) {
  await api('POST', '/api/portal/agent/' + agentId + '/enhancement', {
    action: 'add_memory',
    title: document.getElementById('enh-mem-title').value,
    content: document.getElementById('enh-mem-content').value,
    kind: document.getElementById('enh-mem-kind').value,
    importance: parseFloat(document.getElementById('enh-mem-imp').value) || 0.5,
  });
  closeModal();
  showEnhancementPanel(agentId);
}

async function removeEnhItem(agentId, action, idKey, idVal) {
  if (!confirm('确定要删除这个条目吗？')) return;
  var body = {action: action};
  body[idKey] = idVal;
  await api('POST', '/api/portal/agent/' + agentId + '/enhancement', body);
  showEnhancementPanel(agentId);
