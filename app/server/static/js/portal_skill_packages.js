}

// ============ Skill Packages (new SkillRegistry-backed UI) ============
function renderSkillPkgs() {
  var c = document.getElementById('content');
  c.innerHTML = '<div style="padding:18px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><h2 style="margin:0">技能库 / Skill Packages</h2><button class="btn btn-primary btn-sm" onclick="showInstallSkillPkg()"><span class="material-symbols-outlined" style="font-size:16px">add</span> 安装技能</button></div><div id="skill-pkgs-list" style="color:var(--text3)">加载中…</div></div>';
  fetch('/api/portal/skill-pkgs').then(function(r){return r.json();}).then(function(d){
    var box = document.getElementById('skill-pkgs-list');
    var items = (d && d.skills) || [];
    if (!items.length) { box.innerHTML = '<div style="padding:20px;text-align:center">暂无已安装的技能。点击右上角"安装技能"添加。</div>'; return; }
    var rows = items.map(function(s){
      var m = s.manifest || {};
      var grants = (s.granted_to || []).length;
      var statusColor = s.status === 'ready' ? 'var(--success)' : (s.status === 'error' ? 'var(--error)' : 'var(--warning)');
      return '<div style="border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:10px;background:var(--surface)">'
        + '<div style="display:flex;justify-content:space-between;align-items:center"><div><div style="font-weight:600;font-size:14px">'+esc(m.name||s.id)+' <span style="font-size:11px;color:var(--text3);font-weight:400">v'+esc(m.version||'?')+'</span></div>'
        + '<div style="font-size:12px;color:var(--text2);margin-top:4px">'+esc(m.description||'')+'</div>'
        + '<div style="font-size:11px;color:var(--text3);margin-top:6px">runtime: '+esc(m.runtime||'?')+' · 触发词: '+esc((m.triggers||[]).join(', ')||'-')+' · 已授权 '+grants+' 个 agent</div></div>'
        + '<div style="display:flex;gap:6px;align-items:center"><span style="font-size:11px;color:'+statusColor+';padding:2px 8px;border:1px solid '+statusColor+';border-radius:4px">'+esc(s.status||'?')+'</span>'
        + '<button class="btn btn-sm" onclick="grantSkillPkg(\''+esc(s.id)+'\')">授权</button>'
        + '<button class="btn btn-sm" style="color:var(--error)" onclick="uninstallSkillPkg(\''+esc(s.id)+'\')">卸载</button></div></div></div>';
    }).join('');
    box.innerHTML = rows;
  }).catch(function(e){
    document.getElementById('skill-pkgs-list').innerHTML = '<div style="color:var(--error)">加载失败: '+esc(String(e))+'</div>';
  });
}

function showInstallSkillPkg() {
  var c = document.getElementById('content');
  c.innerHTML = ''
    + '<div style="padding:18px;max-width:760px">'
    + '  <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">'
    + '    <button class="btn btn-sm" onclick="renderSkillPkgs()"><span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle">arrow_back</span> 返回</button>'
    + '    <h2 style="margin:0">安装技能包</h2>'
    + '  </div>'
    + '  <div style="border:1px solid var(--border);border-radius:10px;padding:18px;background:var(--surface)">'
    + '    <div style="font-size:13px;color:var(--text2);margin-bottom:10px">从服务器本地目录安装一个技能包。技能包目录需包含 <code>SKILL.md</code> 和可执行脚本。</div>'
    + '    <label style="display:block;font-size:12px;color:var(--text3);margin-bottom:6px">技能包目录绝对路径 (服务器侧)</label>'
    + '    <input id="install-skill-path" type="text" placeholder="例如：/Users/you/skills/my_skill" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-family:ui-monospace,Menlo,monospace;font-size:13px">'
    + '    <div style="margin-top:6px;font-size:11px;color:var(--text3)">支持 <code>~</code> 开头的用户目录；相对路径会基于服务器工作目录解析。</div>'
    + '    <div id="install-skill-msg" style="margin-top:12px;font-size:12px;min-height:16px"></div>'
    + '    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">'
    + '      <button class="btn btn-sm" onclick="renderSkillPkgs()">取消</button>'
    + '      <button id="install-skill-submit" class="btn btn-primary btn-sm" onclick="submitInstallSkillPkg()">安装</button>'
    + '    </div>'
    + '  </div>'
    + '</div>';
  setTimeout(function(){
    var inp = document.getElementById('install-skill-path');
    if (inp) {
      inp.focus();
      inp.addEventListener('keydown', function(e){
        if (e.key === 'Enter') { e.preventDefault(); submitInstallSkillPkg(); }
      });
    }
  }, 0);
}

function submitInstallSkillPkg() {
  var inp = document.getElementById('install-skill-path');
  var msg = document.getElementById('install-skill-msg');
  var btn = document.getElementById('install-skill-submit');
  if (!inp || !msg || !btn) return;
  var path = (inp.value || '').trim();
  if (!path) {
    msg.innerHTML = '<span style="color:var(--error)">请输入技能包目录路径</span>';
    inp.focus();
    return;
  }
  btn.disabled = true;
  msg.innerHTML = '<span style="color:var(--text3)">安装中…</span>';
  fetch('/api/portal/skill-pkgs/install', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path: path})
  }).then(function(r){return r.json();}).then(function(d){
    btn.disabled = false;
    if (d && d.error) {
      msg.innerHTML = '<span style="color:var(--error)">安装失败：'+esc(String(d.error))+'</span>';
      return;
    }
    var sid = (d && d.skill && d.skill.id) || '';
    msg.innerHTML = '<span style="color:var(--success)">✓ 已安装：'+esc(sid)+'，正在返回列表…</span>';
    setTimeout(function(){ renderSkillPkgs(); }, 600);
  }).catch(function(e){
    btn.disabled = false;
    msg.innerHTML = '<span style="color:var(--error)">请求失败：'+esc(String(e))+'</span>';
  });
}

function grantSkillPkg(sid) {
  // Look up the skill so we can show which agents already have it.
  fetch('/api/portal/skill-pkgs').then(function(r){return r.json();}).then(function(d){
    var items = (d && d.skills) || [];
    var sk = null;
    for (var i=0;i<items.length;i++) { if (items[i].id === sid) { sk = items[i]; break; } }
    var granted = (sk && sk.granted_to) || [];
    var grantedSet = {};
    granted.forEach(function(a){ grantedSet[a] = true; });
    var skName = (sk && sk.manifest && sk.manifest.name) || sid;

    var list = (typeof agents !== 'undefined' && agents) ? agents : [];
    if (!list.length) { alert('当前没有可授权的 agent，请先创建 agent。'); return; }

    // Filter: only include top-level agents (hide sub-agents)
    var visible = list.filter(function(a){ return !a.parent_id; });
    if (!visible.length) visible = list;

    var rows = visible.map(function(a){
      var checked = grantedSet[a.id] ? 'checked' : '';
      var roleLabel = esc(a.role || '');
      var nodeLabel = a.node_id && a.node_id !== 'local' ? ' · '+esc(a.node_id) : '';
      return '<label style="display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid var(--border);border-radius:6px;margin-bottom:6px;cursor:pointer;background:var(--surface)">'
        + '<input type="checkbox" data-aid="'+esc(a.id)+'" '+checked+' style="margin:0">'
        + '<div style="flex:1;min-width:0">'
        + '<div style="font-weight:600;font-size:13px">'+esc(a.name||a.id)+'</div>'
        + '<div style="font-size:11px;color:var(--text3)">'+roleLabel+nodeLabel+' · '+esc(a.id.slice(0,8))+'</div>'
        + '</div></label>';
    }).join('');

    var modal = document.createElement('div');
    modal.id = 'grant-skill-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
    modal.innerHTML = ''
      + '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;width:480px;max-width:92vw;max-height:80vh;display:flex;flex-direction:column">'
      + '  <div style="padding:14px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">'
      + '    <div><div style="font-weight:600">授权技能：'+esc(skName)+'</div>'
      + '    <div style="font-size:11px;color:var(--text3);margin-top:2px">勾选要授权的 agent · 取消勾选已授权项以撤销</div></div>'
      + '    <button class="btn btn-sm" onclick="document.getElementById(\'grant-skill-modal\').remove()">×</button>'
      + '  </div>'
      + '  <div style="padding:8px 10px"><input id="grant-skill-search" placeholder="搜索 agent…" style="width:100%;padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text)"></div>'
      + '  <div id="grant-skill-list" style="flex:1;overflow:auto;padding:6px 12px 0">'+rows+'</div>'
      + '  <div style="padding:12px 16px;border-top:1px solid var(--border);display:flex;justify-content:flex-end;gap:8px">'
      + '    <button class="btn btn-sm" onclick="document.getElementById(\'grant-skill-modal\').remove()">取消</button>'
      + '    <button class="btn btn-primary btn-sm" onclick="submitGrantSkill(\''+esc(sid)+'\')">保存</button>'
      + '  </div>'
      + '</div>';
    document.body.appendChild(modal);

    // Search filter
    document.getElementById('grant-skill-search').addEventListener('input', function(e){
      var q = (e.target.value || '').toLowerCase();
      var labels = document.querySelectorAll('#grant-skill-list label');
      labels.forEach(function(lb){
        lb.style.display = lb.textContent.toLowerCase().indexOf(q) >= 0 ? 'flex' : 'none';
      });
    });
    // Stash original grants for diff
    modal._originalGrants = grantedSet;
  }).catch(function(e){ alert('加载技能信息失败: '+e); });
}

function submitGrantSkill(sid) {
  var modal = document.getElementById('grant-skill-modal');
  if (!modal) return;
  var orig = modal._originalGrants || {};
  var checks = modal.querySelectorAll('#grant-skill-list input[type=checkbox]');
  var toGrant = [], toRevoke = [];
  checks.forEach(function(cb){
    var aid = cb.getAttribute('data-aid');
    var was = !!orig[aid];
    if (cb.checked && !was) toGrant.push(aid);
    if (!cb.checked && was) toRevoke.push(aid);
  });
  if (!toGrant.length && !toRevoke.length) { modal.remove(); return; }
  var calls = [];
  toGrant.forEach(function(aid){
    calls.push(fetch('/api/portal/skill-pkgs/'+encodeURIComponent(sid)+'/grant', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({agent_id: aid})
    }).then(function(r){return r.json();}));
  });
  toRevoke.forEach(function(aid){
    calls.push(fetch('/api/portal/skill-pkgs/'+encodeURIComponent(sid)+'/revoke', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({agent_id: aid})
    }).then(function(r){return r.json();}));
  });
  Promise.all(calls).then(function(results){
    var errs = results.filter(function(d){return d && d.error;});
    if (errs.length) { alert('部分操作失败：'+errs.map(function(e){return e.error;}).join('; ')); }
    modal.remove();
    renderSkillPkgs();
  }).catch(function(e){ alert('授权失败: '+e); });
}

function uninstallSkillPkg(sid) {
  if (!confirm('确定卸载技能 '+sid+'？')) return;
  fetch('/api/portal/skill-pkgs/'+encodeURIComponent(sid)+'/uninstall', {method:'POST'})
    .then(function(r){return r.json();}).then(function(d){
      if (d.error) { alert('卸载失败: '+d.error); return; }
      renderSkillPkgs();
    });
}

function renderToolsApprovalsHub() {
  var c = document.getElementById('content');
  var actionsEl = document.getElementById('topbar-actions');
  var tabs = [
    { id: 'approvals', label: '待审批 / 历史', icon: 'shield' },
    { id: 'mcpconfig', label: 'MCP 服务器', icon: 'hub' },
  ];
  var r = _renderHubTabs('tools', tabs);
  c.innerHTML = r.html;
  if (r.current === 'mcpconfig') {
    actionsEl.innerHTML = '<button class="btn btn-primary btn-sm" onclick="showAddMCP()"><span class="material-symbols-outlined" style="font-size:16px">add</span> Add MCP</button>';
  }
  var sc = document.getElementById('hub-tools-content');
  var _orig = document.getElementById('content');
  sc.id = 'content'; _orig.id = 'content-outer';
  try {
    if (r.current === 'approvals') renderApprovals();
    else if (r.current === 'mcpconfig') renderMCPConfig();
  } catch(e) { sc.innerHTML = '<div style="color:var(--error);padding:20px">'+e.message+'</div>'; }
  finally { sc.id = 'hub-tools-content'; _orig.id = 'content'; }
}

function renderIntegrationsHub() {
  var c = document.getElementById('content');
  var sc;
  c.innerHTML = '<div id="integrations-channels-wrap"></div>';
  sc = document.getElementById('integrations-channels-wrap');
  var _orig = document.getElementById('content');
  sc.id = 'content'; _orig.id = 'content-outer';
  try { renderChannels(); }
  catch(e) { sc.innerHTML = '<div style="color:var(--error);padding:20px">'+e.message+'</div>'; }
  finally { sc.id = 'integrations-channels-wrap'; _orig.id = 'content'; }
}

function renderSettingsHub() {
  var c = document.getElementById('content');
  var tabs = [
    { id: 'config', label: '全局配置', icon: 'settings' },
    { id: 'providers', label: 'LLM 提供商', icon: 'dns' },
    { id: 'nodeconfig', label: '节点配置', icon: 'tune' },
    { id: 'nodes', label: '节点列表', icon: 'device_hub' },
    { id: 'tokens', label: 'API Tokens', icon: 'key' },
    { id: 'audit', label: '审计日志', icon: 'assignment' },
  ];
  var r = _renderHubTabs('settings', tabs);
  c.innerHTML = r.html;
  var actionsEl = document.getElementById('topbar-actions');
  var sc = document.getElementById('hub-settings-content');
  var _orig = document.getElementById('content');
  sc.id = 'content'; _orig.id = 'content-outer';
  try {
    if (r.current === 'config') renderConfig();
    else if (r.current === 'providers') {
      actionsEl.innerHTML = '<button class="btn btn-primary btn-sm" onclick="showModal(\'add-provider\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> Add Provider</button>';
      renderProviders();
    } else if (r.current === 'nodeconfig') renderNodeConfig();
    else if (r.current === 'nodes') {
      actionsEl.innerHTML = '<button class="btn btn-primary btn-sm" onclick="showModal(\'add-node\')"><span class="material-symbols-outlined" style="font-size:16px">add</span> Connect Node</button>';
      renderNodes();
    } else if (r.current === 'tokens') renderTokens();
    else if (r.current === 'audit') renderAudit();
  } catch(e) { sc.innerHTML = '<div style="color:var(--error);padding:20px">'+e.message+'</div>'; }
  finally { sc.id = 'hub-settings-content'; _orig.id = 'content'; }
