}

// ============ Skill Panel ============
// Shows per-agent real granted skill packages (send_email, jimeng_video, ...) as
// the primary view. Prompt packs (the old markdown-based SkillSystem, now renamed
// PromptEnhancer) are shown as a collapsible secondary section.
// Catalog browsing / installation lives in the left-nav "技能商店 Store" page.
async function showSkillPanel(agentId) {
  // Primary data: real granted skill packages for this agent
  var granted = [];
  try {
    var gd = await api('GET', '/api/portal/agent/' + agentId + '/skill-pkgs');
    granted = (gd && gd.skills) || [];
  } catch(e) { granted = []; }

  // Secondary data: bound prompt packs
  var packsData = {};
  try {
    packsData = await api('GET', '/api/portal/agent/' + agentId + '/prompt-packs') || {};
  } catch(e) { packsData = {}; }
  var boundPacks = (packsData && packsData.bound_skills) || [];

  // Agent detail for MCP/tool summary
  try { window._currentAgentForSkillPanel = await api('GET', '/api/portal/agent/' + agentId); } catch(e) { window._currentAgentForSkillPanel = {}; }
  var agDetail = window._currentAgentForSkillPanel || {};
  var mcpList = agDetail.mcp_servers || [];

  var html = '<div style="padding:20px;max-width:900px;min-width:600px">';
  html += '<h3 style="margin-bottom:4px"><span class="material-symbols-outlined" style="vertical-align:middle;color:#a78bfa">build_circle</span> 能力扩展 Capabilities</h3>';
  html += '<p style="font-size:11px;color:var(--text3);margin-bottom:16px">此 Agent 可调用的真实能力：已授权的 skill 包、MCP 服务，以及提示词增强 Prompt Packs。</p>';

  // ── MCP Services overview ──
  if (mcpList.length) {
    html += '<div style="margin-bottom:16px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:8px">';
    html += '<div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px">MCP Services</div>';
    mcpList.forEach(function(m) {
      var name = (typeof m === 'string') ? m : (m.name || m.id || '');
      html += '<span style="display:inline-block;background:rgba(167,139,250,0.1);border:1px solid rgba(167,139,250,0.3);border-radius:6px;padding:3px 8px;font-size:11px;color:#a78bfa;margin:2px 4px 2px 0">' + esc(name) + '</span>';
    });
    html += '</div>';
  }

  // ── Section 1: Granted Skill Packages (primary) ──
  html += '<div style="margin-bottom:18px">';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">';
  html += '<div style="font-size:13px;font-weight:700;color:var(--text)">已授权技能 Granted Skills <span style="color:var(--text3);font-weight:400">(' + granted.length + ')</span></div>';
  html += '<button class="btn btn-sm" style="font-size:10px" onclick="showView(\'roles-skills\', document.querySelector(\'[data-view=roles-skills]\'));closeModal();">+ 从技能商店授权更多</button>';
  html += '</div>';
  if (!granted.length) {
    html += '<div style="color:var(--text3);font-size:12px;padding:20px;text-align:center;border:1px dashed var(--border);border-radius:8px">此 Agent 暂未授权任何可执行技能。<br>去 <a href="#" onclick="showView(\'roles-skills\', document.querySelector(\'[data-view=roles-skills]\'));closeModal();return false;" style="color:var(--primary)">技能商店</a> 授权可执行技能包。</div>';
  } else {
    granted.forEach(function(s) {
      var manifest = s.manifest || {};
      var name = manifest.name || s.id || '';
      var desc = manifest.description || '';
      var runtime = manifest.runtime || '';
      var mcpDeps = (manifest.depends_on && manifest.depends_on.mcp) || [];
      var status = s.status || 'installed';
      var statusColor = status === 'ready' ? '#10b981' : (status === 'needs_dependencies' ? '#f59e0b' : 'var(--text3)');
      html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin-bottom:8px">';
      html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">';
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">';
      html += '<span style="font-size:13px;font-weight:600">' + esc(name) + '</span>';
      html += '<span style="font-size:10px;color:' + statusColor + ';border:1px solid ' + statusColor + ';border-radius:4px;padding:1px 6px">' + esc(status) + '</span>';
      html += '</div>';
      html += '<div style="font-size:11px;color:var(--text3);margin-bottom:6px">' + esc(desc) + '</div>';
      html += '<div style="font-size:10px;color:var(--text3)">';
      if (runtime) html += 'runtime: <span style="color:var(--text)">' + esc(runtime) + '</span>';
      if (mcpDeps.length) {
        html += ' · 依赖 MCP: ';
        mcpDeps.forEach(function(m, i) {
          var mname = (typeof m === 'string') ? m : (m.name || m.id || '');
          html += '<span style="color:#a78bfa">' + esc(mname) + '</span>' + (i < mcpDeps.length - 1 ? ', ' : '');
        });
      }
      html += '</div>';
      html += '</div>';
      html += '<button class="btn btn-sm btn-ghost" style="font-size:10px;color:var(--error);white-space:nowrap" onclick="revokeGrantedSkill(\'' + agentId + '\',\'' + esc(s.id) + '\')">撤销授权</button>';
      html += '</div></div>';
    });
  }
  html += '</div>';

  // ── Section 2: Prompt Packs (secondary, collapsible) ──
  html += '<details style="margin-bottom:12px" open>';
  html += '<summary style="cursor:pointer;font-size:13px;font-weight:700;color:var(--text);padding:8px 0;border-top:1px solid var(--border)">提示词增强 Prompt Packs <span style="color:var(--text3);font-weight:400">(' + boundPacks.length + ')</span></summary>';
  html += '<div style="padding:8px 0 4px 0">';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">';
  html += '<div style="font-size:11px;color:var(--text3)">注入到 system prompt 的参考文档，不是可执行代码。用来给 agent 提供背景知识或行为规范。</div>';
  html += '<div style="display:flex;gap:6px;flex-shrink:0;margin-left:10px">';
  html += '<button class="btn btn-sm" style="font-size:10px" onclick="ppOpenCatalog(\''+agentId+'\')"><span class="material-symbols-outlined" style="font-size:13px;vertical-align:middle">storefront</span> 市场</button>';
  html += '<button class="btn btn-sm" style="font-size:10px" onclick="ppOpenDiscovered(\''+agentId+'\')"><span class="material-symbols-outlined" style="font-size:13px;vertical-align:middle">inventory_2</span> 已发现</button>';
  html += '</div></div>';

  // Bound packs list
  if (!boundPacks.length) {
    html += '<div style="color:var(--text3);font-size:12px;padding:16px;text-align:center">暂未绑定任何提示词增强包。</div>';
  } else {
    boundPacks.forEach(function(s) {
      html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:6px">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center">';
      html += '<div style="flex:1">';
      html += '<span style="font-size:12px;font-weight:600">' + esc(s.name||'') + '</span>';
      html += '<div style="font-size:10px;color:var(--text3);margin-top:2px">' + esc(s.description||'') + '</div>';
      html += '</div>';
      html += '<button class="btn btn-sm btn-ghost" style="font-size:10px;margin-left:10px;white-space:nowrap" onclick="unbindSkill(\'' + agentId + '\',\'' + esc(s.skill_id||'') + '\')">解除</button>';
      html += '</div></div>';
    });
  }

  // Hint
  html += '<div style="margin-top:8px;font-size:10px;color:var(--text3);text-align:center">'
    + '技能包（可执行）请前往 <a href="#" onclick="event.preventDefault();closeModal();switchTab(\'skill-store\')" style="color:var(--primary);text-decoration:underline">技能商店</a> 管理'
    + '</div>';

  html += '</div></details>';

  // Footer
  html += '<div style="margin-top:16px;display:flex;gap:8px;border-top:1px solid var(--border);padding-top:14px">';
  html += '<button class="btn btn-ghost" onclick="closeModal()">Close</button>';
  html += '</div></div>';

  showModalHTML(html);
}

// Revoke a granted skill package from an agent (uses the existing skill-pkgs
// revoke endpoint, which clears both registry grant and agent.granted_skills).
async function revokeGrantedSkill(agentId, skillInstallId) {
  if (!confirm('确认撤销对该 agent 的技能授权？')) return;
  try {
    await api('POST', '/api/portal/skill-pkgs/' + encodeURIComponent(skillInstallId) + '/revoke', {agent_id: agentId});
    showSkillPanel(agentId);
  } catch(e) {
    alert('撤销失败: ' + (e.message || e));
  }
}

async function switchSkillTab(agentId, tabName, event) {
  event.preventDefault();
  // Hide all tabs
  document.getElementById('tab-bound').style.display = 'none';
  document.getElementById('tab-all').style.display = 'none';
  document.getElementById('tab-marketplace').style.display = 'none';
  document.getElementById('tab-local').style.display = 'none';

  // Show selected tab
  document.getElementById('tab-' + tabName).style.display = 'block';

  // Update button styles
  var buttons = document.querySelectorAll('.skill-tab-btn');
  buttons.forEach(function(btn) {
    if (btn.getAttribute('data-tab') === tabName) {
      btn.style.color = 'var(--primary)';
      btn.style.borderBottom = '2px solid var(--primary)';
    } else {
      btn.style.color = 'var(--text3)';
      btn.style.borderBottom = 'none';
    }
  });
}

async function loadAllSkillsTab(agentId) {
  var tabDiv = document.getElementById('tab-all');
  try {
    const data = await api('GET', '/api/portal/prompt-packs');
    var skills = (data && data.skills) || [];
    var bound = (data && data.bound_prompt_packs) || [];

    if (!skills.length) {
      tabDiv.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text3)">No skills discovered</div>';
      return;
    }

    let html = '';
    skills.forEach(function(s) {
      var isBound = bound.includes(s.skill_id);
      html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin-bottom:8px">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center">';
      html += '<div style="flex:1">';
      html += '<span style="font-size:13px;font-weight:600">' + esc(s.name) + '</span>';
      html += '<div style="font-size:11px;color:var(--text3);margin-top:4px">' + esc(s.description||'') + '</div>';
      html += '</div>';
      if (!isBound) {
        html += '<button class="btn btn-sm" style="font-size:10px;margin-left:10px;white-space:nowrap" onclick="bindSkill(\'' + agentId + '\',\'' + s.skill_id + '\')">Bind</button>';
      } else {
        html += '<span style="font-size:10px;color:var(--text3);margin-left:10px">Bound</span>';
      }
      html += '</div></div>';
    });
    tabDiv.innerHTML = html;
  } catch (e) {
    tabDiv.innerHTML = '<div style="padding:20px;color:red">Error loading skills: ' + e.message + '</div>';
  }
}

async function loadMarketplaceTab(agentId) {
  var tabDiv = document.getElementById('tab-marketplace');
  try {
    const catalogData = await api('POST', '/api/portal/prompt-packs', {action: 'catalog'});
    var skills = (catalogData && catalogData.skills) || [];
    var categories = (catalogData && catalogData.categories) || [];

    let html = '<div style="margin-bottom:16px">';
    html += '<div style="display:flex;gap:8px;margin-bottom:12px">';
    html += '<select id="marketplace-category-filter" onchange="filterMarketplaceSkills(\'' + agentId + '\')" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text);font-size:12px">';
    html += '<option value="">All Categories</option>';
    categories.forEach(function(cat) {
      html += '<option value="' + esc(cat) + '">' + esc(cat) + '</option>';
    });
    html += '</select>';
    html += '<input type="text" id="marketplace-search" placeholder="Search skills..." onkeyup="filterMarketplaceSkills(\'' + agentId + '\')" style="flex:1;padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text);font-size:12px">';
    html += '</div></div>';

    html += '<div id="marketplace-skills">';
    if (!skills.length) {
      html += '<div style="padding:20px;text-align:center;color:var(--text3)">No skills in catalog</div>';
    } else {
      skills.forEach(function(s) {
        html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin-bottom:8px">';
        html += '<div style="display:flex;align-items:flex-start;gap:12px">';
        html += '<div style="font-size:24px">' + esc(s.icon||'') + '</div>';
        html += '<div style="flex:1">';
        html += '<div style="display:flex;justify-content:space-between;align-items:start">';
        html += '<div style="flex:1">';
        html += '<span style="font-size:13px;font-weight:600">' + esc(s.name) + '</span>';
        html += '<div style="font-size:11px;color:var(--text3);margin-top:4px;margin-bottom:6px">' + esc(s.description||'') + '</div>';
        html += '<span style="display:inline-block;font-size:10px;background:var(--primary);color:white;padding:2px 8px;border-radius:4px">' + esc(s.category||'') + '</span>';
        html += '</div>';
        html += '<button class="btn btn-sm" style="font-size:10px;white-space:nowrap" onclick="importFromCatalog(\'' + agentId + '\', [\'' + esc(s.id) + '\'])">Import</button>';
        html += '</div></div></div></div>';
      });
    }
    html += '</div>';

    tabDiv.innerHTML = html;
  } catch (e) {
    tabDiv.innerHTML = '<div style="padding:20px;color:red">Error loading catalog: ' + e.message + '</div>';
  }
}

async function filterMarketplaceSkills(agentId) {
  var category = document.getElementById('marketplace-category-filter').value;
  var search = document.getElementById('marketplace-search').value;

  try {
    const catalogData = await api('POST', '/api/portal/prompt-packs', {action: 'catalog', category: category, search: search});
    var skills = (catalogData && catalogData.skills) || [];

    let html = '';
    if (!skills.length) {
      html = '<div style="padding:20px;text-align:center;color:var(--text3)">No matching skills</div>';
    } else {
      skills.forEach(function(s) {
        html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin-bottom:8px">';
        html += '<div style="display:flex;align-items:flex-start;gap:12px">';
        html += '<div style="font-size:24px">' + esc(s.icon||'') + '</div>';
        html += '<div style="flex:1">';
        html += '<div style="display:flex;justify-content:space-between;align-items:start">';
        html += '<div style="flex:1">';
        html += '<span style="font-size:13px;font-weight:600">' + esc(s.name) + '</span>';
        html += '<div style="font-size:11px;color:var(--text3);margin-top:4px;margin-bottom:6px">' + esc(s.description||'') + '</div>';
        html += '<span style="display:inline-block;font-size:10px;background:var(--primary);color:white;padding:2px 8px;border-radius:4px">' + esc(s.category||'') + '</span>';
        html += '</div>';
        html += '<button class="btn btn-sm" style="font-size:10px;white-space:nowrap" onclick="importFromCatalog(\'' + agentId + '\', [\'' + esc(s.id) + '\'])">Import</button>';
        html += '</div></div></div></div>';
      });
    }
    document.getElementById('marketplace-skills').innerHTML = html;
  } catch (e) {
    document.getElementById('marketplace-skills').innerHTML = '<div style="padding:20px;color:red">Error: ' + e.message + '</div>';
  }
}

async function bindSkill(agentId, skillId) {
  await api('POST', '/api/portal/agent/' + agentId + '/prompt-packs', {action: 'bind', skill_id: skillId});
  showSkillPanel(agentId);
}

async function unbindSkill(agentId, skillId) {
  await api('POST', '/api/portal/agent/' + agentId + '/prompt-packs', {action: 'unbind', skill_id: skillId});
  showSkillPanel(agentId);
}

async function importFromCatalog(agentId, skillIds) {
  console.log('[importFromCatalog]', agentId, skillIds);
  try {
    var r = await api('POST', '/api/portal/agent/' + agentId + '/prompt-packs', {action: 'import_from_catalog', skill_ids: skillIds});
    console.log('[importFromCatalog] response', r);
    if (!r) {
      alert('导入失败：无响应');
      return;
    }
    if (r.error) {
      alert('导入失败: ' + r.error);
      return;
    }
    // Inline success toast inside the marketplace panel
    var mkt = document.getElementById('marketplace-skills');
    if (mkt) {
      var banner = document.createElement('div');
      banner.style.cssText = 'padding:10px;background:#10b981;color:white;border-radius:6px;font-size:12px;margin-bottom:10px';
      banner.textContent = '✅ 已导入 ' + (r.imported || 0) + ' 个技能并绑定到 Agent';
      mkt.parentNode.insertBefore(banner, mkt);
      setTimeout(function(){ banner.remove(); }, 3000);
    }
    // Refresh skill panel but stay on marketplace tab
    showSkillPanel(agentId);
    setTimeout(function(){
      try { switchSkillTab(agentId, 'marketplace', {currentTarget: document.querySelector('[data-tab="marketplace"]')}); } catch(_){}
    }, 50);
  } catch (e) {
    console.error('[importFromCatalog] error', e);
    alert('导入失败: ' + (e && e.message ? e.message : e));
  }
}

async function importLocal(agentId) {
  var path = document.getElementById('local-import-path').value;
  if (!path.trim()) {
    alert('Please enter a directory path');
    return;
  }
  try {
    const result = await api('POST', '/api/portal/agent/' + agentId + '/prompt-packs', {action: 'import_local', path: path});
    var resultDiv = document.getElementById('local-import-result');
    if (result.ok) {
      resultDiv.innerHTML = '<div style="padding:10px;background:#10b981;color:white;border-radius:6px;font-size:12px">Successfully imported ' + result.new_skills + ' new skills from ' + esc(path) + '</div>';
    } else {
      resultDiv.innerHTML = '<div style="padding:10px;background:#ef4444;color:white;border-radius:6px;font-size:12px">Error: ' + esc(result.error) + '</div>';
    }
  } catch (e) {
    var resultDiv = document.getElementById('local-import-result');
    resultDiv.innerHTML = '<div style="padding:10px;background:#ef4444;color:white;border-radius:6px;font-size:12px">Error: ' + e.message + '</div>';
  }
}

async function discoverSkills(agentId) {
  await api('POST', '/api/portal/agent/' + agentId + '/prompt-packs', {action: 'discover'});
  showSkillPanel(agentId);
}

// ── Prompt Pack import helpers (used by the inline import panel in showSkillPanel) ──

function _ppFlash(agentId, ok, msg) {
  var box = document.getElementById('pp-import-result-' + agentId);
  if (!box) { alert(msg); return; }
  var bg = ok ? '#10b981' : '#ef4444';
  box.innerHTML = '<div style="padding:8px 10px;background:'+bg+';color:white;border-radius:6px;font-size:11px">'+esc(msg)+'</div>';
  setTimeout(function(){ if (box) box.innerHTML = ''; }, 4000);
}

async function ppDiscoverNow(agentId) {
  try {
    var r = await api('POST', '/api/portal/agent/' + agentId + '/prompt-packs', {action: 'discover'});
    _ppFlash(agentId, true, '✅ 已扫描，新增 ' + (r && r.new_skills || 0) + ' 个 pack（共 ' + (r && r.total || 0) + '）');
    showSkillPanel(agentId);
  } catch(e) { _ppFlash(agentId, false, '扫描失败: ' + (e.message || e)); }
}

async function ppImportLocal(agentId) {
  var inp = document.getElementById('pp-import-path-' + agentId);
  var path = inp ? inp.value.trim() : '';
  if (!path) { _ppFlash(agentId, false, '请输入本地目录路径'); return; }
  try {
    var r = await api('POST', '/api/portal/agent/' + agentId + '/prompt-packs', {action: 'import_local', path: path});
    if (r && r.ok) {
      _ppFlash(agentId, true, '✅ 已从 ' + path + ' 导入 ' + (r.new_skills || 0) + ' 个 pack');
      showSkillPanel(agentId);
    } else {
      _ppFlash(agentId, false, '导入失败: ' + ((r && r.error) || '未知错误'));
    }
  } catch(e) { _ppFlash(agentId, false, '导入失败: ' + (e.message || e)); }
}

async function ppOpenCatalog(agentId) {
  var html = '<div style="padding:20px;max-width:720px;min-width:520px">' +
    '<h3 style="margin:0 0 6px"><span class="material-symbols-outlined" style="vertical-align:middle">storefront</span> Prompt Pack 市场</h3>' +
    '<div style="font-size:11px;color:var(--text3);margin-bottom:14px">从社区目录中选择并一键导入到当前 Agent</div>' +
    '<div style="display:flex;gap:8px;margin-bottom:12px">' +
      '<select id="pp-cat-filter" style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);font-size:12px"><option value="">全部分类</option></select>' +
      '<input id="pp-cat-search" placeholder="搜索..." style="flex:1;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);font-size:12px">' +
      '<button class="btn btn-sm" onclick="_ppCatalogReload(\''+agentId+'\')">搜索</button>' +
    '</div>' +
    '<div id="pp-cat-list" style="max-height:55vh;overflow:auto"><div style="color:var(--text3);font-size:12px;padding:20px;text-align:center">加载中...</div></div>' +
    '<div style="display:flex;justify-content:flex-end;margin-top:14px"><button class="btn" onclick="closeModal()">关闭</button></div>' +
  '</div>';
  showModalHTML(html);
  // Wire enter-key search
  setTimeout(function(){
    var s = document.getElementById('pp-cat-search');
    if (s) s.addEventListener('keyup', function(ev){ if (ev.key === 'Enter') _ppCatalogReload(agentId); });
  }, 30);
  _ppCatalogReload(agentId);
}

async function _ppCatalogReload(agentId) {
  var list = document.getElementById('pp-cat-list');
  if (!list) return;
  var catEl = document.getElementById('pp-cat-filter');
  var qEl = document.getElementById('pp-cat-search');
  var category = catEl ? catEl.value : '';
  var search = qEl ? qEl.value : '';
  list.innerHTML = '<div style="color:var(--text3);font-size:12px;padding:20px;text-align:center">加载中...</div>';
  try {
    var r = await api('POST', '/api/portal/prompt-packs', {action: 'catalog', category: category, search: search});
    var skills = (r && r.skills) || [];
    var cats = (r && r.categories) || [];
    // Populate categories on first load
    if (catEl && catEl.options.length <= 1 && cats.length) {
      cats.forEach(function(c){
        var o = document.createElement('option'); o.value = c; o.textContent = c; catEl.appendChild(o);
      });
    }
    if (!skills.length) {
      list.innerHTML = '<div style="color:var(--text3);font-size:12px;padding:20px;text-align:center">无匹配的 Prompt Pack</div>';
      return;
    }
    var html = '';
    skills.forEach(function(s){
      var sid = esc(s.id||'');
      html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:6px;display:flex;align-items:flex-start;gap:10px">' +
        '<div style="font-size:20px;line-height:1">'+esc(s.icon||'📦')+'</div>' +
        '<div style="flex:1;min-width:0">' +
          '<div style="font-size:13px;font-weight:600">'+esc(s.name||'')+'</div>' +
          '<div style="font-size:11px;color:var(--text3);margin-top:2px">'+esc(s.description||'')+'</div>' +
          (s.category?'<span style="display:inline-block;font-size:10px;background:var(--primary);color:white;padding:2px 8px;border-radius:4px;margin-top:4px">'+esc(s.category)+'</span>':'') +
        '</div>' +
        '<button class="btn btn-sm btn-primary" style="font-size:10px;white-space:nowrap" onclick="_ppCatalogImport(\''+agentId+'\',\''+sid+'\', this)">导入并绑定</button>' +
      '</div>';
    });
    list.innerHTML = html;
  } catch(e) {
    list.innerHTML = '<div style="color:var(--error);font-size:12px;padding:20px;text-align:center">加载失败: '+esc(e.message||String(e))+'</div>';
  }
}

async function _ppCatalogImport(agentId, skillId, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '导入中...'; }
  try {
    var r = await api('POST', '/api/portal/agent/' + agentId + '/prompt-packs', {action: 'import_from_catalog', skill_ids: [skillId]});
    if (r && r.ok) {
      if (btn) { btn.textContent = '✓ 已导入'; btn.style.background = '#10b981'; }
    } else {
      if (btn) { btn.disabled = false; btn.textContent = '导入并绑定'; }
      alert('导入失败: ' + ((r && r.error) || '未知错误'));
    }
  } catch(e) {
    if (btn) { btn.disabled = false; btn.textContent = '导入并绑定'; }
    alert('导入失败: ' + (e.message || e));
  }
}

async function ppOpenDiscovered(agentId) {
  var html = '<div style="padding:20px;max-width:720px;min-width:520px">' +
    '<h3 style="margin:0 0 6px"><span class="material-symbols-outlined" style="vertical-align:middle">inventory_2</span> 已发现的 Prompt Packs</h3>' +
    '<div style="font-size:11px;color:var(--text3);margin-bottom:14px">已通过本地扫描或之前导入注册的 pack。可直接绑定到当前 Agent。</div>' +
    '<div id="pp-disc-list" style="max-height:55vh;overflow:auto"><div style="color:var(--text3);font-size:12px;padding:20px;text-align:center">加载中...</div></div>' +
    '<div style="display:flex;justify-content:flex-end;margin-top:14px"><button class="btn" onclick="closeModal()">关闭</button></div>' +
  '</div>';
  showModalHTML(html);
  try {
    var pair = await Promise.all([
      api('GET', '/api/portal/prompt-packs'),
      api('GET', '/api/portal/agent/' + agentId + '/prompt-packs').catch(function(){ return {}; }),
    ]);
    var r = pair[0] || {};
    var agentR = pair[1] || {};
    var skills = r.skills || [];
    var boundList = (agentR.bound_prompt_packs || []).map(function(b){ return (b && b.skill_id) || b; });
    var bound = boundList;
    var list = document.getElementById('pp-disc-list');
    if (!list) return;
    if (!skills.length) {
      list.innerHTML = '<div style="color:var(--text3);font-size:12px;padding:20px;text-align:center">尚未发现任何 pack。试试 "重新扫描" 或 "从目录导入"。</div>';
      return;
    }
    var html2 = '';
    skills.forEach(function(s){
      var sid = esc(s.skill_id || s.id || '');
      var isBound = bound.indexOf(s.skill_id || s.id) >= 0;
      html2 += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:6px;display:flex;align-items:center;gap:10px">' +
        '<div style="flex:1;min-width:0">' +
          '<div style="font-size:13px;font-weight:600">'+esc(s.name||'')+'</div>' +
          '<div style="font-size:11px;color:var(--text3);margin-top:2px">'+esc(s.description||'')+'</div>' +
          (s.origin?'<div style="font-size:10px;color:var(--text3);margin-top:2px">来源: '+esc(s.origin)+'</div>':'') +
        '</div>' +
        (isBound
          ? '<span style="font-size:10px;color:var(--text3);white-space:nowrap">已绑定</span>'
          : '<button class="btn btn-sm btn-primary" style="font-size:10px;white-space:nowrap" onclick="_ppDiscBind(\''+agentId+'\',\''+sid+'\', this)">绑定</button>') +
      '</div>';
    });
    list.innerHTML = html2;
  } catch(e) {
    var l = document.getElementById('pp-disc-list');
    if (l) l.innerHTML = '<div style="color:var(--error);font-size:12px;padding:20px;text-align:center">加载失败: '+esc(e.message||String(e))+'</div>';
  }
}

async function _ppDiscBind(agentId, skillId, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '...'; }
  try {
    await api('POST', '/api/portal/agent/' + agentId + '/prompt-packs', {action: 'bind', skill_id: skillId});
    if (btn) { btn.textContent = '✓ 已绑定'; btn.style.background = '#10b981'; }
  } catch(e) {
    if (btn) { btn.disabled = false; btn.textContent = '绑定'; }
    alert('绑定失败: ' + (e.message || e));
  }
