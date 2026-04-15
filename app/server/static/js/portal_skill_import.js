}

// ============ Universal Skill Import ============

function switchImportTab(agentId, tab) {
  var localDiv = document.getElementById('imp-local-' + agentId);
  var urlDiv   = document.getElementById('imp-url-' + agentId);
  var localBtn = document.getElementById('imp-tab-local-' + agentId);
  var urlBtn   = document.getElementById('imp-tab-url-' + agentId);
  if (!localDiv || !urlDiv) return;
  if (tab === 'url') {
    localDiv.style.display = 'none';
    urlDiv.style.display = 'flex';
    if (localBtn) { localBtn.style.background = ''; localBtn.style.color = ''; }
    if (urlBtn) { urlBtn.style.background = 'var(--primary)'; urlBtn.style.color = 'white'; }
  } else {
    localDiv.style.display = 'flex';
    urlDiv.style.display = 'none';
    if (localBtn) { localBtn.style.background = 'var(--primary)'; localBtn.style.color = 'white'; }
    if (urlBtn) { urlBtn.style.background = ''; urlBtn.style.color = ''; }
  }
}

async function skillStoreImportLocal(agentId) {
  var inp = document.getElementById('imp-local-path-' + agentId);
  var path = inp ? inp.value.trim() : '';
  if (!path) { _ppFlash(agentId, false, '请输入本地路径'); return; }
  try {
    // Detect if path points at a single skill (has SKILL.md) or a directory of skills
    var r = await api('POST', '/api/portal/skill-store', {action: 'import', src_path: path, auto_install: true});
    if (r && r.ok) {
      _ppFlash(agentId, true, '已导入: ' + (r.name || path) + (r.install ? ' (已安装)' : ''));
      showSkillPanel(agentId);
    } else if (r && r.error && r.error.indexOf('no SKILL.md') >= 0) {
      // Try bulk import
      var rb = await api('POST', '/api/portal/skill-store', {action: 'import_bulk', src_root: path, auto_install: true});
      if (rb && rb.ok) {
        var names = (rb.results || []).filter(function(x){return x.ok;}).map(function(x){return x.name;});
        _ppFlash(agentId, true, '批量导入: ' + names.join(', '));
        showSkillPanel(agentId);
      } else {
        _ppFlash(agentId, false, '导入失败: ' + ((rb && rb.error) || '目录中未找到 SKILL.md'));
      }
    } else {
      _ppFlash(agentId, false, '导入失败: ' + ((r && r.error) || '未知错误'));
    }
  } catch(e) { _ppFlash(agentId, false, '导入失败: ' + (e.message || e)); }
}

async function skillStoreImportURL(agentId) {
  var inp = document.getElementById('imp-url-input-' + agentId);
  var url = inp ? inp.value.trim() : '';
  if (!url) { _ppFlash(agentId, false, '请输入 URL'); return; }
  _ppFlash(agentId, true, '正在下载...');
  try {
    var r = await api('POST', '/api/portal/skill-store', {action: 'import_from_url', url: url, auto_install: true});
    if (r && r.ok) {
      _ppFlash(agentId, true, '已导入: ' + (r.name || url));
      showSkillPanel(agentId);
    } else {
      _ppFlash(agentId, false, '导入失败: ' + ((r && r.error) || '未知错误'));
    }
  } catch(e) { _ppFlash(agentId, false, '导入失败: ' + (e.message || e)); }
}

async function skillStoreRescan(agentId) {
  try {
    var r = await api('POST', '/api/portal/skill-store', {action: 'rescan'});
    _ppFlash(agentId, true, '已扫描: ' + (r && r.count || 0) + ' 个技能');
    showSkillPanel(agentId);
  } catch(e) { _ppFlash(agentId, false, '扫描失败: ' + (e.message || e)); }
}

async function skillStoreOpenCatalog(agentId) {
  var html = '<div style="padding:20px;max-width:750px;min-width:540px">' +
    '<h3 style="margin:0 0 6px"><span class="material-symbols-outlined" style="vertical-align:middle">storefront</span> 技能市场 Skill Store</h3>' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">' +
      '<div style="font-size:11px;color:var(--text3)">浏览已注册的技能。支持可执行技能 (python/shell) 和指引型技能 (markdown/SKILL.md)。</div>' +
      '<button class="btn btn-sm btn-primary" style="font-size:11px;white-space:nowrap;margin-left:12px" onclick="closeModal();skillCreatorOpen(\''+agentId+'\')">+ 新建技能</button>' +
    '</div>' +
    '<div style="display:flex;gap:8px;margin-bottom:12px">' +
      '<select id="ss-cat-source" style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);font-size:12px">' +
        '<option value="">全部来源</option><option value="official">official</option><option value="maintainer">maintainer</option><option value="community">community</option><option value="local">local</option>' +
      '</select>' +
      '<input id="ss-cat-q" placeholder="搜索技能名或描述..." style="flex:1;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);font-size:12px">' +
      '<button class="btn btn-sm" onclick="_ssCatalogReload(\''+agentId+'\')">搜索</button>' +
    '</div>' +
    '<div id="ss-cat-list" style="max-height:55vh;overflow:auto"><div style="color:var(--text3);font-size:12px;padding:20px;text-align:center">加载中...</div></div>' +
    '<div style="display:flex;justify-content:flex-end;margin-top:14px"><button class="btn" onclick="closeModal()">关闭</button></div>' +
  '</div>';
  showModalHTML(html);
  setTimeout(function(){
    var s = document.getElementById('ss-cat-q');
    if (s) s.addEventListener('keyup', function(ev){ if (ev.key === 'Enter') _ssCatalogReload(agentId); });
  }, 30);
  _ssCatalogReload(agentId);
}

async function _ssCatalogReload(agentId) {
  var list = document.getElementById('ss-cat-list');
  if (!list) return;
  var srcEl = document.getElementById('ss-cat-source');
  var qEl = document.getElementById('ss-cat-q');
  var source = srcEl ? srcEl.value : '';
  var q = qEl ? qEl.value : '';
  list.innerHTML = '<div style="color:var(--text3);font-size:12px;padding:20px;text-align:center">加载中...</div>';
  try {
    var qs = '?all=1';
    if (source) qs += '&source=' + encodeURIComponent(source);
    if (q) qs += '&q=' + encodeURIComponent(q);
    var r = await api('GET', '/api/portal/skill-store' + qs);
    var entries = (r && r.entries) || [];
    if (!entries.length) {
      list.innerHTML = '<div style="color:var(--text3);font-size:12px;padding:20px;text-align:center">目录为空。把 SKILL.md 或 manifest.yaml 放到 data/skill_catalog/ 下再点"重新扫描"。</div>';
      return;
    }
    var h = '';
    entries.forEach(function(e){
      var runtimeIcon = (e.runtime === 'markdown') ? '📖' : (e.runtime === 'python' ? '🐍' : '📦');
      var installedBadge = e.installed
        ? '<span style="font-size:10px;color:#10b981;border:1px solid #10b981;border-radius:4px;padding:1px 6px;margin-left:6px">已安装</span>'
        : '';
      h += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:6px;display:flex;align-items:flex-start;gap:10px">' +
        '<div style="font-size:20px;line-height:1">'+runtimeIcon+'</div>' +
        '<div style="flex:1;min-width:0">' +
          '<div style="font-size:13px;font-weight:600">'+esc(e.name||'')+ installedBadge +'</div>' +
          '<div style="font-size:11px;color:var(--text3);margin-top:2px;max-height:40px;overflow:hidden">'+esc((e.description||'').substring(0,160))+'</div>' +
          '<div style="display:flex;gap:8px;margin-top:4px;font-size:10px;color:var(--text3)">' +
            '<span>runtime: '+esc(e.runtime||'')+'</span>' +
            '<span>spec: '+esc(e.spec||'')+'</span>' +
            '<span>source: '+esc(e.source||'')+'</span>' +
            (e.version ? '<span>v'+esc(e.version)+'</span>':'') +
          '</div>' +
        '</div>';
      h += '<div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">';
      if (!e.installed) {
        h += '<button class="btn btn-sm btn-primary" style="font-size:10px;white-space:nowrap" onclick="_ssCatalogInstall(\''+agentId+'\',\''+esc(e.id||'')+'\',this)">安装</button>';
      } else {
        h += '<button class="btn btn-sm" style="font-size:10px;white-space:nowrap" onclick="_ssCatalogGrant(\''+agentId+'\',\''+esc(e.installed_id||'')+'\',this)">授权给 Agent</button>';
      }
      if (e.spec === 'agent-skills' || e.runtime === 'markdown') {
        h += '<button class="btn btn-sm btn-ghost" style="font-size:10px;white-space:nowrap" onclick="closeModal();skillEditorOpen(\''+agentId+'\',\''+esc(e.id||'')+'\')">编辑</button>';
      }
      h += '</div></div>';
    });
    list.innerHTML = h;
  } catch(e) {
    list.innerHTML = '<div style="color:var(--error);font-size:12px;padding:20px;text-align:center">加载失败: '+esc(e.message||String(e))+'</div>';
  }
}

async function _ssCatalogInstall(agentId, entryId, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '安装中...'; }
  try {
    var r = await api('POST', '/api/portal/skill-store', {action: 'install', entry_id: entryId});
    if (r && r.ok) {
      if (btn) { btn.textContent = '已安装'; btn.style.background = '#10b981'; }
      // Refresh list after short delay
      setTimeout(function(){ _ssCatalogReload(agentId); }, 500);
    } else {
      if (btn) { btn.disabled = false; btn.textContent = '安装'; }
      alert('安装失败: ' + ((r && r.error) || ''));
    }
  } catch(e) {
    if (btn) { btn.disabled = false; btn.textContent = '安装'; }
    alert('安装失败: ' + (e.message || e));
  }
}

async function _ssCatalogGrant(agentId, installedId, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '授权中...'; }
  try {
    await api('POST', '/api/portal/skill-store', {action: 'grant', installed_id: installedId, agent_id: agentId});
    if (btn) { btn.textContent = '已授权'; btn.style.background = '#10b981'; }
  } catch(e) {
    if (btn) { btn.disabled = false; btn.textContent = '授权给 Agent'; }
    alert('授权失败: ' + (e.message || e));
  }
}

// ── Skill Creator / Editor ──

function skillCreatorOpen(agentId) {
  var template = '---\nname: my-new-skill\ndescription: \"Describe what this skill does\"\nmetadata:\n  source: local\n  tags: []\n---\n\n# My New Skill\n\n## Overview\n\nDescribe what this skill enables the agent to do.\n\n## Instructions\n\n1. Step one...\n2. Step two...\n';
  _skillEditorModal(agentId, '', template, true);
}

async function skillEditorOpen(agentId, entryId) {
  try {
    var r = await api('POST', '/api/portal/skill-store', {action: 'preview', entry_id: entryId});
    if (!r || !r.ok) { alert('读取失败'); return; }
    _skillEditorModal(agentId, entryId, r.content || '', false, r.files || []);
  } catch(e) { alert('读取失败: ' + (e.message || e)); }
}

function _skillEditorModal(agentId, entryId, content, isNew, files) {
  var title = isNew ? '新建技能' : '编辑技能';
  var saveLabel = isNew ? '创建并安装' : '保存';
  var filesHtml = '';
  if (files && files.length) {
    filesHtml = '<div style="margin-bottom:10px;font-size:11px;color:var(--text3)">附属文件: ';
    files.forEach(function(f,i){ filesHtml += (i?', ':'') + esc(f.name) + ' ('+((f.size/1024).toFixed(1))+'KB)'; });
    filesHtml += '</div>';
  }
  var html = '<div style="padding:20px;max-width:800px;min-width:600px">' +
    '<h3 style="margin:0 0 8px">'+title+'</h3>' +
    '<div style="font-size:11px;color:var(--text3);margin-bottom:10px">SKILL.md 格式：YAML frontmatter (name, description 必填) + Markdown 正文。</div>' +
    filesHtml +
    '<div style="position:relative">' +
      '<textarea id="skill-editor-content" style="width:100%;height:45vh;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;color:var(--text);font-family:monospace;font-size:12px;resize:vertical;tab-size:2">' + esc(content) + '</textarea>' +
    '</div>' +
    '<div id="skill-editor-issues" style="margin-top:8px"></div>' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px">' +
      '<button class="btn btn-sm" style="font-size:11px" onclick="_skillEditorValidate()">检查 SKILL.md</button>' +
      '<div style="display:flex;gap:8px">' +
        '<button class="btn" onclick="closeModal()">取消</button>' +
        '<button class="btn btn-primary" onclick="_skillEditorSave(\''+agentId+'\',\''+esc(entryId||'')+'\','+(isNew?'true':'false')+')">' + saveLabel + '</button>' +
      '</div>' +
    '</div>' +
  '</div>';
  showModalHTML(html);
}

async function _skillEditorValidate() {
  var ta = document.getElementById('skill-editor-content');
  var box = document.getElementById('skill-editor-issues');
  if (!ta || !box) return;
  try {
    var r = await api('POST', '/api/portal/skill-store', {action: 'validate', content: ta.value});
    if (r && r.ok) {
      box.innerHTML = '<div style="padding:8px;background:#10b981;color:white;border-radius:6px;font-size:11px">SKILL.md 格式正确 (name: '+esc(r.parsed_meta.name||'')+', body: '+r.body_length+' chars)</div>';
    } else {
      var issues = (r && r.issues) || ['unknown error'];
      box.innerHTML = '<div style="padding:8px;background:#ef4444;color:white;border-radius:6px;font-size:11px">问题: ' + issues.map(esc).join('; ') + '</div>';
    }
  } catch(e) {
    box.innerHTML = '<div style="padding:8px;background:#ef4444;color:white;border-radius:6px;font-size:11px">检查失败: '+esc(e.message||String(e))+'</div>';
  }
}

async function _skillEditorSave(agentId, entryId, isNew) {
  var ta = document.getElementById('skill-editor-content');
  if (!ta) return;
  var content = ta.value;
  if (!content.trim()) { alert('内容不能为空'); return; }
  try {
    var action = isNew ? 'create_new' : 'save_edit';
    var payload = {action: action, content: content};
    if (!isNew) payload.entry_id = entryId;
    var r = await api('POST', '/api/portal/skill-store', payload);
    if (r && r.ok) {
      alert((isNew ? '创建' : '保存') + '成功: ' + (r.name || ''));
      closeModal();
      // Refresh catalog if open
      setTimeout(function(){ skillStoreOpenCatalog(agentId); }, 200);
    } else {
      alert('失败: ' + ((r && r.error) || '未知错误'));
    }
  } catch(e) { alert('失败: ' + (e.message || e)); }
