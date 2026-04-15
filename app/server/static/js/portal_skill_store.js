}

// ============ Skill Store (Hub-level marketplace) ============
var _skillStoreState = { q: '', source: '', entries: [], stats: null };

function _fmtSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1048576).toFixed(1) + ' MB';
}

async function renderSkillStore() {
  var c = document.getElementById('content');
  c.innerHTML = ''
    + '<div style="padding:18px">'
    + '  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;gap:12px">'
    + '    <div><h2 style="margin:0">技能商店 / Skill Store</h2>'
    + '      <div style="font-size:12px;color:var(--text3);margin-top:4px">兼容 Anthropic Agent Skills 规范 (SKILL.md) 与 TudouClaw manifest.yaml。按信任分级浏览、安装、授权给 agent。</div>'
    + '    </div>'
    + '    <div style="display:flex;gap:8px">'
    + '    <button class="btn btn-sm" onclick="_showLocalImportModal()"><span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle">folder_open</span> 从本地导入</button>'
    + '    <button class="btn btn-sm" onclick="_showRemoteScanModal()"><span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle">cloud_download</span> 从 URL 导入</button>'
    + '    <button class="btn btn-sm" onclick="rescanSkillStore()"><span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle">refresh</span> 重新扫描</button>'
    + '    </div>'
    + '  </div>'
    + '  <div style="display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap">'
    + '    <input id="store-q" placeholder="搜索名称/描述/标签…" style="flex:1;min-width:260px;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text)" oninput="_skillStoreState.q=this.value;_debouncedLoadStore()">'
    + '    <select id="store-source" onchange="_skillStoreState.source=this.value;loadSkillStore()" style="padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text)">'
    + '      <option value="">所有来源</option>'
    + '      <option value="official">official 官方</option>'
    + '      <option value="maintainer">maintainer 维护</option>'
    + '      <option value="community">community 社区</option>'
    + '      <option value="agent">agent Agent创建</option>'
    + '      <option value="local">local 本地</option>'
    + '    </select>'
    + '  </div>'
    + '  <div id="store-stats" style="font-size:11px;color:var(--text3);margin-bottom:10px"></div>'
    + '  <div id="store-list" style="color:var(--text3)">加载中…</div>'
    + '</div>';
  loadSkillStore();
}

var _storeLoadTimer = null;
function _debouncedLoadStore() {
  if (_storeLoadTimer) clearTimeout(_storeLoadTimer);
  _storeLoadTimer = setTimeout(loadSkillStore, 250);
}

async function loadSkillStore() {
  var box = document.getElementById('store-list');
  if (!box) return;
  var params = [];
  if (_skillStoreState.q) params.push('q=' + encodeURIComponent(_skillStoreState.q));
  if (_skillStoreState.source) params.push('source=' + encodeURIComponent(_skillStoreState.source));
  var qs = params.length ? ('?' + params.join('&')) : '';
  try {
    var data = await api('GET', '/api/portal/skill-store' + qs);
    _skillStoreState.entries = data.entries || [];
    _skillStoreState.stats = data.stats || null;
    var annMap = {};
    (data.annotations || []).forEach(function(a){ annMap[a.skill_id] = a; });
    var installedMap = data.installed || {};
    var s = data.stats || {};
    var stats = document.getElementById('store-stats');
    if (stats) {
      var by = s.by_source || {};
      var pill = function(k,v){ return '<span style="padding:2px 8px;border:1px solid var(--border);border-radius:10px;margin-right:6px">'+esc(k)+': '+v+'</span>'; };
      stats.innerHTML = '共 ' + (s.total||0) + ' 个 · 已安装 ' + (s.installed||0) + ' · '
        + Object.keys(by).map(function(k){ return pill(k, by[k]); }).join('');
    }
    if (!_skillStoreState.entries.length) {
      box.innerHTML = '<div style="padding:20px;text-align:center">目录为空。把 SKILL.md 或 manifest.yaml 放到 data/skill_catalog/ 下再点"重新扫描"。</div>';
      return;
    }
    box.innerHTML = _skillStoreState.entries.map(function(e){
      var srcColor = e.source === 'official' ? '#10b981'
                   : e.source === 'maintainer' ? '#a78bfa'
                   : e.source === 'community' ? '#60a5fa'
                   : e.source === 'agent' ? '#f59e0b' : '#94a3b8';
      var ann = annMap[e.id] || annMap[e.installed_id];
      var annBadge = (ann && ann.notes && ann.notes.length)
        ? '<span title="本地笔记 " style="padding:2px 6px;font-size:10px;background:rgba(251,191,36,0.15);color:#f59e0b;border-radius:10px;margin-left:6px">💡 '+ann.notes.length+'</span>'
        : '';
      var actions = '';
      if (e.installed) {
        actions = '<button class="btn btn-sm" onclick="openGrantModal(\''+esc(e.installed_id)+'\',\''+esc(e.name)+'\')">授权给 Agent</button>'
                + '<button class="btn btn-sm" onclick="openAnnotateModal(\''+esc(e.installed_id)+'\',\''+esc(e.name)+'\')">📝 笔记</button>'
                + '<button class="btn btn-sm" style="color:var(--error)" onclick="uninstallStoreEntry(\''+esc(e.id)+'\')">卸载</button>';
      } else {
        actions = '<button class="btn btn-primary btn-sm" onclick="installStoreEntry(\''+esc(e.id)+'\')">安装到 Hub</button>';
      }
      var sensitive = e.sensitive ? '<span style="padding:2px 6px;font-size:10px;background:rgba(239,68,68,0.15);color:#ef4444;border-radius:10px;margin-left:6px">敏感</span>' : '';
      var tagList = (e.tags||[]).slice(0,6).map(function(t){ return '<span style="font-size:10px;padding:1px 6px;border:1px solid var(--border);border-radius:8px;margin-right:4px">'+esc(t)+'</span>'; }).join('');
      return '<div style="border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:10px;background:var(--surface)">'
        + '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">'
        + '  <div style="flex:1;min-width:0">'
        + '    <div style="font-weight:600;font-size:14px">'+esc(e.name)
        + '      <span style="font-size:11px;color:var(--text3);font-weight:400;margin-left:6px">'+esc(e.id)+' v'+esc(e.version)+'</span>'
        + '      <span style="padding:2px 8px;font-size:10px;background:'+srcColor+'20;color:'+srcColor+';border:1px solid '+srcColor+';border-radius:10px;margin-left:8px">'+esc(e.source)+'</span>'
        + annBadge + sensitive
        + '    </div>'
        + '    <div style="font-size:12px;color:var(--text2);margin-top:4px">'+esc(e.description||'')+'</div>'
        + '    <div style="font-size:11px;color:var(--text3);margin-top:6px">'
        + 'spec: '+esc(e.spec)+' · runtime: '+esc(e.runtime)+' · entry: '+esc(e.entry||'')
        + ' · author: '+esc(e.author)
        + (e.size_bytes ? ' · '+_fmtSize(e.size_bytes) : '')
        + (e.last_updated ? ' · '+new Date(e.last_updated*1000).toLocaleDateString() : '')
        + '</div>'
        + (e.languages && e.languages.length ? '<div style="font-size:10px;color:var(--text3);margin-top:3px">languages: '+esc(e.languages.join(', '))+'</div>' : '')
        + (tagList ? '<div style="margin-top:6px">'+tagList+'</div>' : '')
        + '  </div>'
        + '  <div style="display:flex;gap:6px;flex-shrink:0">'+actions+'</div>'
        + '</div></div>';
    }).join('');
  } catch(err) {
    box.innerHTML = '<div style="color:var(--error);padding:20px">加载失败: '+esc(String(err))+'</div>';
  }
}

async function rescanSkillStore() {
  try {
    await api('POST', '/api/portal/skill-store', {action: 'rescan'});
    loadSkillStore();
  } catch(e) { alert('扫描失败: '+e); }
}

async function installStoreEntry(entryId) {
  try {
    var r = await api('POST', '/api/portal/skill-store', {action:'install', entry_id: entryId});
    if (r && r.ok) loadSkillStore();
    else alert('安装失败: ' + JSON.stringify(r));
  } catch(e) { alert('安装失败: '+e); }
}

async function uninstallStoreEntry(entryId) {
  if (!confirm('卸载这个技能？对 agent 的授权会同时撤销。')) return;
  try {
    var r = await api('POST', '/api/portal/skill-store', {action:'uninstall', entry_id: entryId});
    if (r && r.ok) loadSkillStore();
    else alert('卸载失败');
  } catch(e) { alert('卸载失败: '+e); }
}

// ── Local Path Import Modal ──
function _showLocalImportModal() {
  var modal = document.createElement('div');
  modal.id = 'local-import-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:20px;max-width:600px;width:94%;max-height:85vh;overflow:auto">'
    + '<h3 style="margin:0 0 6px">从本地路径导入技能</h3>'
    + '<div style="font-size:11px;color:var(--text3);margin-bottom:12px">'
    + '输入包含 SKILL.md 或 manifest.yaml 的本地目录绝对路径。系统会将技能包复制到 skill catalog 并自动安装。'
    + '</div>'
    + '<div style="margin-bottom:10px">'
    + '<input id="local-import-path" placeholder="/path/to/skill-folder  (包含 SKILL.md 的目录)" '
    + 'style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:13px;box-sizing:border-box">'
    + '</div>'
    + '<div style="margin-bottom:12px">'
    + '<label style="font-size:12px;color:var(--text2);margin-right:8px">来源分级:</label>'
    + '<select id="local-import-tier" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:12px">'
    + '<option value="community">community 社区</option>'
    + '<option value="local">local 本地</option>'
    + '</select>'
    + '</div>'
    + '<div id="local-import-status" style="font-size:12px;margin-bottom:8px;display:none"></div>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px">'
    + '<button class="btn btn-sm" onclick="document.getElementById(\'local-import-modal\').remove()">取消</button>'
    + '<button class="btn btn-primary btn-sm" id="local-import-btn" onclick="_doLocalImport()">导入</button>'
    + '</div></div>';
  document.body.appendChild(modal);
  setTimeout(function(){ var inp = document.getElementById('local-import-path'); if (inp) inp.focus(); }, 0);
}

async function _doLocalImport() {
  var pathInput = document.getElementById('local-import-path');
  var srcPath = (pathInput && pathInput.value || '').trim();
  if (!srcPath) { alert('请输入本地路径'); return; }
  var tierSel = document.getElementById('local-import-tier');
  var tier = tierSel ? tierSel.value : 'community';
  var btn = document.getElementById('local-import-btn');
  var status = document.getElementById('local-import-status');
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle;animation:spin 1s linear infinite">progress_activity</span> 导入中…';
  status.style.display = 'block';
  status.style.color = 'var(--text3)';
  status.innerHTML = '正在导入 ' + esc(srcPath) + ' …';
  try {
    var data = await api('POST', '/api/portal/skill-store', {
      action: 'import', src_path: srcPath, tier: tier, auto_install: true
    });
    if (data.ok) {
      status.style.color = '#10b981';
      status.innerHTML = '✓ 技能 <b>' + esc(data.name || '') + '</b> 已导入'
        + (data.install ? ' 并安装' : '') + '。';
      loadSkillStore();
      setTimeout(function(){
        var m = document.getElementById('local-import-modal');
        if (m) m.remove();
      }, 1500);
    } else {
      status.style.color = 'var(--error)';
      status.innerHTML = '导入失败: ' + esc(data.error || JSON.stringify(data));
    }
  } catch(err) {
    status.style.color = 'var(--error)';
    status.innerHTML = '请求失败: ' + esc(String(err));
  }
  btn.disabled = false;
  btn.innerHTML = '导入';
}

// ── Remote URL Scan Modal ──
var _remoteScanState = { temp_dir: '', skills: [] };

function _showRemoteScanModal() {
  var modal = document.createElement('div');
  modal.id = 'remote-scan-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:20px;max-width:680px;width:94%;max-height:85vh;overflow:auto">'
    + '<h3 style="margin:0 0 6px">从 URL 导入技能</h3>'
    + '<div style="font-size:11px;color:var(--text3);margin-bottom:12px">'
    + '支持 GitHub 仓库地址、.zip、.tar.gz 文件链接。系统会扫描其中的 SKILL.md / manifest.yaml 技能包。'
    + '</div>'
    + '<div style="display:flex;gap:8px;margin-bottom:12px">'
    + '<input id="remote-scan-url" placeholder="https://github.com/user/repo  或  https://example.com/skill.zip" '
    + 'style="flex:1;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:13px">'
    + '<button id="remote-scan-btn" class="btn btn-primary btn-sm" onclick="_doRemoteScan()" style="white-space:nowrap">'
    + '<span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">search</span> 扫描</button>'
    + '</div>'
    + '<div id="remote-scan-status" style="font-size:12px;color:var(--text3);margin-bottom:8px;display:none"></div>'
    + '<div id="remote-scan-results"></div>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">'
    + '<button class="btn btn-sm" onclick="_closeRemoteScan()">关闭</button>'
    + '</div>'
    + '</div>';
  document.body.appendChild(modal);
  setTimeout(function(){ var inp = document.getElementById('remote-scan-url'); if (inp) inp.focus(); }, 0);
}

function _closeRemoteScan() {
  // cleanup temp_dir if scan was done but not imported
  if (_remoteScanState.temp_dir) {
    try { api('POST', '/api/portal/skill-store', {action: 'cleanup_scan', temp_dir: _remoteScanState.temp_dir}); } catch(e) {}
    _remoteScanState.temp_dir = '';
    _remoteScanState.skills = [];
  }
  var m = document.getElementById('remote-scan-modal');
  if (m) m.remove();
}

async function _doRemoteScan() {
  var urlInput = document.getElementById('remote-scan-url');
  var url = (urlInput && urlInput.value || '').trim();
  if (!url) { alert('请输入 URL'); return; }
  var btn = document.getElementById('remote-scan-btn');
  var status = document.getElementById('remote-scan-status');
  var results = document.getElementById('remote-scan-results');
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle;animation:spin 1s linear infinite">progress_activity</span> 扫描中…';
  status.style.display = 'block';
  status.innerHTML = '正在下载并扫描 ' + esc(url) + ' …';
  results.innerHTML = '';
  // cleanup previous scan
  if (_remoteScanState.temp_dir) {
    try { await api('POST', '/api/portal/skill-store', {action: 'cleanup_scan', temp_dir: _remoteScanState.temp_dir}); } catch(e) {}
    _remoteScanState.temp_dir = '';
    _remoteScanState.skills = [];
  }
  try {
    var data = await api('POST', '/api/portal/skill-store', {action: 'scan_url', url: url});
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">search</span> 扫描';
    if (!data.ok) {
      status.innerHTML = '<span style="color:var(--error)">扫描失败: ' + esc(data.error || 'unknown') + '</span>';
      results.innerHTML = '';
      if (data.scanned_dirs) {
        results.innerHTML = '<div style="font-size:11px;color:var(--text3);margin-top:6px">目录结构: ' + esc(JSON.stringify(data.scanned_dirs).substring(0, 400)) + '</div>';
      }
      return;
    }
    _remoteScanState.temp_dir = data.temp_dir || '';
    _remoteScanState.skills = data.skills || [];
    status.innerHTML = '找到 <b>' + data.skill_count + '</b> 个技能包：';
    _renderScanResults(data.skills || []);
  } catch(err) {
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">search</span> 扫描';
    status.innerHTML = '<span style="color:var(--error)">请求失败: ' + esc(String(err)) + '</span>';
  }
}

function _renderScanResults(skills) {
  var box = document.getElementById('remote-scan-results');
  if (!box) return;
  if (!skills.length) { box.innerHTML = ''; return; }
  var html = skills.map(function(s, idx) {
    var specColor = s.spec === 'agent-skills' ? '#10b981' : '#60a5fa';
    var filesInfo = (s.files || []).slice(0, 8).map(function(f) {
      var sz = f.size > 1024 ? ((f.size / 1024).toFixed(1) + ' KB') : (f.size + ' B');
      return esc(f.name) + ' (' + sz + ')';
    }).join(', ');
    return '<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px;background:var(--surface)">'
      + '<div style="display:flex;align-items:flex-start;gap:10px">'
      + '<input type="checkbox" id="scan-skill-' + idx + '" data-skill-name="' + esc(s.name) + '" checked style="margin-top:4px">'
      + '<div style="flex:1;min-width:0">'
      + '<div style="font-weight:600;font-size:14px">' + esc(s.name)
      + '  <span style="padding:2px 8px;font-size:10px;background:' + specColor + '20;color:' + specColor + ';border:1px solid ' + specColor + ';border-radius:10px;margin-left:6px">' + esc(s.spec) + '</span>'
      + (s.version ? '<span style="font-size:11px;color:var(--text3);margin-left:6px">v' + esc(s.version) + '</span>' : '')
      + '</div>'
      + '<div style="font-size:12px;color:var(--text2);margin-top:4px">' + esc(s.description || '') + '</div>'
      + '<div style="font-size:11px;color:var(--text3);margin-top:4px">author: ' + esc(s.author || '-') + ' · runtime: ' + esc(s.runtime || '-') + ' · files: ' + (s.file_count || 0) + '</div>'
      + (filesInfo ? '<div style="font-size:10px;color:var(--text3);margin-top:2px">' + filesInfo + '</div>' : '')
      + '</div></div></div>';
  }).join('');
  html += '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px">'
    + '<select id="scan-import-tier" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:12px">'
    + '<option value="community">community 社区</option>'
    + '<option value="local">local 本地</option>'
    + '</select>'
    + '<button class="btn btn-primary btn-sm" id="scan-import-btn" onclick="_doImportScanned()">导入选中的技能</button>'
    + '</div>';
  box.innerHTML = html;
}

async function _doImportScanned() {
  if (!_remoteScanState.temp_dir) { alert('没有扫描数据'); return; }
  var checks = document.querySelectorAll('[id^="scan-skill-"]');
  var names = [];
  for (var i = 0; i < checks.length; i++) {
    if (checks[i].checked) names.push(checks[i].getAttribute('data-skill-name'));
  }
  if (!names.length) { alert('请至少选择一个技能'); return; }
  var tierSel = document.getElementById('scan-import-tier');
  var tier = tierSel ? tierSel.value : 'community';
  var btn = document.getElementById('scan-import-btn');
  var status = document.getElementById('remote-scan-status');
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle;animation:spin 1s linear infinite">progress_activity</span> 导入中…';
  status.innerHTML = '正在导入 ' + names.length + ' 个技能…';
  try {
    var data = await api('POST', '/api/portal/skill-store', {
      action: 'import_scanned',
      temp_dir: _remoteScanState.temp_dir,
      skill_names: names,
      tier: tier,
      auto_install: true,
    });
    _remoteScanState.temp_dir = '';  // temp dir cleaned by backend
    _remoteScanState.skills = [];
    if (data.ok) {
      var imported = (data.results || []).filter(function(r){ return r.ok; });
      var failed = (data.results || []).filter(function(r){ return !r.ok; });
      var msg = '成功导入 ' + imported.length + ' 个技能';
      if (failed.length) msg += '，' + failed.length + ' 个失败';
      status.innerHTML = '<span style="color:#10b981">' + msg + '</span>';
      var results = document.getElementById('remote-scan-results');
      if (results) {
        var detailHtml = (data.results || []).map(function(r) {
          if (r.ok) return '<div style="font-size:12px;color:#10b981;padding:4px 0">✓ ' + esc(r.name) + ' 已导入' + (r.install ? ' 并安装' : '') + '</div>';
          return '<div style="font-size:12px;color:var(--error);padding:4px 0">✗ ' + esc(r.name || '?') + ': ' + esc(r.error || 'unknown') + '</div>';
        }).join('');
        results.innerHTML = detailHtml;
      }
      // Refresh skill store list
      loadSkillStore();
    } else {
      status.innerHTML = '<span style="color:var(--error)">导入失败: ' + esc(data.error || 'unknown') + '</span>';
    }
  } catch(err) {
    status.innerHTML = '<span style="color:var(--error)">请求失败: ' + esc(String(err)) + '</span>';
  }
  btn.disabled = false;
  btn.innerHTML = '导入选中的技能';
}

async function openGrantModal(installedId, skillName) {
  var ags = [];
  try {
    var d = await api('GET', '/api/portal/agents');
    ags = (d && d.agents) || [];
  } catch(e) { alert('无法获取 agent 列表: '+e); return; }
  if (!ags.length) { alert('还没有 agent'); return; }
  var opts = ags.map(function(a){
    var granted = (a.granted_skills||[]).indexOf(installedId) >= 0;
    return '<label style="display:flex;align-items:center;gap:8px;padding:6px;border-bottom:1px solid var(--border)"><input type="checkbox" data-agent-id="'+esc(a.id)+'" '+(granted?'checked':'')+'><span>'+esc(a.name||a.id)+' <span style="color:var(--text3);font-size:11px">('+esc(a.role||'-')+')</span></span></label>';
  }).join('');
  var modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:18px;max-width:500px;width:90%;max-height:80vh;overflow:auto">'
    + '<h3 style="margin:0 0 10px">授权 '+esc(skillName)+' 给 Agent</h3>'
    + '<div style="font-size:11px;color:var(--text3);margin-bottom:10px">勾选后点击保存。会同时向 agent working_dir/.claw/granted_skills/ 写入 pointer 文件，支持独立进程 agent 发现。</div>'
    + '<div id="grant-ag-list" style="max-height:320px;overflow:auto">'+opts+'</div>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">'
    + '<button class="btn btn-sm" onclick="this.closest(\'div[style*=fixed]\').remove()">取消</button>'
    + '<button class="btn btn-primary btn-sm" onclick="submitGrant(\''+esc(installedId)+'\', this)">保存</button>'
    + '</div></div>';
  document.body.appendChild(modal);
}

async function submitGrant(installedId, btn) {
  var modal = btn.closest('div[style*=fixed]');
  var checks = modal.querySelectorAll('#grant-ag-list input[type=checkbox]');
  btn.disabled = true;
  for (var i=0;i<checks.length;i++) {
    var cb = checks[i];
    var aid = cb.getAttribute('data-agent-id');
    var action = cb.checked ? 'grant' : 'revoke';
    try {
      await api('POST', '/api/portal/skill-store', {action: action, installed_id: installedId, agent_id: aid});
    } catch(e) { /* swallow */ }
  }
  modal.remove();
  loadSkillStore();
}

function openAnnotateModal(installedId, skillName) {
  var modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:18px;max-width:560px;width:90%">'
    + '<h3 style="margin:0 0 6px">📝 为 '+esc(skillName)+' 添加笔记</h3>'
    + '<div style="font-size:11px;color:var(--text3);margin-bottom:10px">本地笔记会在 agent 加载这个 skill 时自动附加到 prompt 里，下次 session 无需手动回忆。建议写：踩过的坑 / workaround / 版本差异。</div>'
    + '<textarea id="ann-text" rows="5" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:13px" placeholder="例如：调用时如果 traceId 为空会 500，必须先生成 UUID 再传入"></textarea>'
    + '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">'
    + '<button class="btn btn-sm" onclick="this.closest(\'div[style*=fixed]\').remove()">取消</button>'
    + '<button class="btn btn-primary btn-sm" onclick="submitAnnotate(\''+esc(installedId)+'\', this)">保存</button>'
    + '</div></div>';
  document.body.appendChild(modal);
  setTimeout(function(){ var ta = document.getElementById('ann-text'); if (ta) ta.focus(); }, 0);
}

async function submitAnnotate(installedId, btn) {
  var modal = btn.closest('div[style*=fixed]');
  var ta = modal.querySelector('#ann-text');
  var text = (ta && ta.value || '').trim();
  if (!text) { alert('笔记不能为空'); return; }
  try {
    await api('POST', '/api/portal/skill-store', {action:'annotate', skill_id: installedId, text: text});
    modal.remove();
    loadSkillStore();
  } catch(e) { alert('保存失败: '+e); }
