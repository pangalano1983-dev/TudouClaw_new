}

// ============ Orchestration Visualization (force-directed SVG) ============
function renderOrchestration() {
  var c = document.getElementById('content');
  c.innerHTML =
    '<div style="padding:18px">'
    + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">'
    + '<div><h2 style="margin:0;font-family:\'Plus Jakarta Sans\',sans-serif;font-size:22px;font-weight:800">编排可视化</h2>'
    + '<p style="font-size:12px;color:var(--text3);margin-top:4px">Orchestration · 项目 / Agent / 任务关系图</p></div>'
    + '<div style="display:flex;align-items:center;gap:12px"><div id="orch-stats" style="font-size:12px;color:var(--text3)"></div>'
    + '<button class="btn btn-sm" onclick="renderOrchestration()"><span class="material-symbols-outlined" style="font-size:14px">refresh</span> 刷新</button></div></div>'
    + '<div id="orch-legend" style="font-size:11px;color:var(--text3);margin-bottom:8px">'
    + '<span style="display:inline-block;width:10px;height:10px;background:#5b8def;border-radius:2px;margin:0 4px 0 0;vertical-align:middle"></span>项目'
    + '<span style="display:inline-block;width:10px;height:10px;background:#22c55e;border-radius:50%;margin:0 4px 0 12px;vertical-align:middle"></span>Agent'
    + '<span style="display:inline-block;width:10px;height:10px;background:#a855f7;border-radius:50%;margin:0 4px 0 12px;vertical-align:middle"></span>子 Agent'
    + '<span style="display:inline-block;width:10px;height:10px;background:#f59e0b;border-radius:2px;margin:0 4px 0 12px;vertical-align:middle"></span>任务</div>'
    + '<div id="orch-svg-wrap" style="border:1px solid var(--border);border-radius:8px;background:var(--surface);overflow:auto">'
    + '<svg id="orch-svg" width="100%" height="640" style="display:block"></svg></div>'
    + '<div id="orch-detail" style="margin-top:12px;font-size:12px;color:var(--text2)"></div></div>';

  fetch('/api/portal/orchestration').then(function(r){return r.json();}).then(function(g){
    var stats = g.stats || {};
    document.getElementById('orch-stats').textContent =
      '项目 ' + (stats.projects||0) + ' · Agent ' + (stats.agents||0)
      + ' · 子 Agent ' + (stats.subagents||0) + ' · 任务 ' + (stats.tasks||0);
    _drawOrchestrationGraph(g);
  }).catch(function(e){
    document.getElementById('orch-svg-wrap').innerHTML =
      '<div style="padding:20px;color:var(--error)">加载失败: '+esc(String(e))+'</div>';
  });
}

function _drawOrchestrationGraph(g) {
  var svg = document.getElementById('orch-svg');
  if (!svg) return;
  var nodes = (g.nodes || []).slice();
  var edges = (g.edges || []).slice();
  if (!nodes.length) {
    svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="#888">暂无数据</text>';
    return;
  }
  var W = svg.clientWidth || 1000;
  var H = 640;

  // Simple layered layout: projects → agents → tasks
  var byType = { project: [], agent: [], subagent: [], task: [] };
  nodes.forEach(function(n){ (byType[n.type] || (byType[n.type]=[])).push(n); });
  var lanes = [
    { type: 'project',  y: 80,  color: '#5b8def', shape: 'rect' },
    { type: 'agent',    y: 240, color: '#22c55e', shape: 'circle' },
    { type: 'subagent', y: 380, color: '#a855f7', shape: 'circle' },
    { type: 'task',     y: 540, color: '#f59e0b', shape: 'rect' },
  ];
  var posMap = {};
  lanes.forEach(function(lane) {
    var arr = byType[lane.type] || [];
    var n = arr.length;
    if (!n) return;
    var step = W / (n + 1);
    arr.forEach(function(node, i) {
      posMap[node.id] = { x: step * (i+1), y: lane.y, color: lane.color, shape: lane.shape, node: node };
    });
  });

  // Build SVG
  var defs = '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#888"/></marker></defs>';
  var edgeSvg = edges.map(function(e) {
    var a = posMap[e.from], b = posMap[e.to];
    if (!a || !b) return '';
    var color = e.type === 'parent' ? '#a855f7' :
                e.type === 'assigned' ? '#f59e0b' :
                e.type === 'belongs_to' ? '#94a3b8' : '#5b8def';
    var dash = e.type === 'belongs_to' ? '3,3' : '0';
    return '<line x1="'+a.x+'" y1="'+a.y+'" x2="'+b.x+'" y2="'+b.y+'" stroke="'+color+'" stroke-width="1.2" stroke-dasharray="'+dash+'" marker-end="url(#arrow)" opacity="0.65"/>';
  }).join('');
  var nodeSvg = nodes.map(function(n) {
    var p = posMap[n.id]; if (!p) return '';
    var label = (n.label || n.id).replace(/[<>&]/g, '');
    var status = n.status || '';
    var sub = '';
    if (n.type === 'task' && n.step_total > 0) {
      sub = n.step_done + '/' + n.step_total + ' steps';
    } else if (n.type === 'project') {
      sub = (n.task_count||0) + ' tasks · ' + (n.member_count||0) + ' members';
    } else if (n.type === 'agent' || n.type === 'subagent') {
      sub = (n.role||'') + ' · ' + (n.task_count||0) + ' open';
    }
    var shape;
    if (p.shape === 'circle') {
      shape = '<circle cx="'+p.x+'" cy="'+p.y+'" r="22" fill="'+p.color+'" stroke="#fff" stroke-width="2"/>';
    } else {
      shape = '<rect x="'+(p.x-44)+'" y="'+(p.y-18)+'" width="88" height="36" rx="6" fill="'+p.color+'" stroke="#fff" stroke-width="2"/>';
    }
    var clickHandler = "onclick=\"_orchSelect('"+n.id+"')\"";
    return '<g style="cursor:pointer" '+clickHandler+'>'
      + shape
      + '<text x="'+p.x+'" y="'+(p.y+44)+'" text-anchor="middle" font-size="11" fill="var(--text)" font-weight="600">'+label.substring(0,18)+'</text>'
      + '<text x="'+p.x+'" y="'+(p.y+58)+'" text-anchor="middle" font-size="9" fill="var(--text3)">'+esc(sub)+'</text>'
      + (status ? '<text x="'+p.x+'" y="'+(p.y+4)+'" text-anchor="middle" font-size="9" fill="#fff" font-weight="700">'+esc(status.substring(0,5))+'</text>' : '')
      + '</g>';
  }).join('');
  svg.innerHTML = defs + edgeSvg + nodeSvg;
  window._orchData = g;
}

function _orchSelect(nid) {
  var g = window._orchData; if (!g) return;
  var n = (g.nodes||[]).find(function(x){return x.id===nid;});
  if (!n) return;
  var lines = [];
  Object.keys(n).forEach(function(k){
    if (k === 'id' || k === 'type') return;
    lines.push('<div><span style="color:var(--text3)">'+esc(k)+':</span> '+esc(String(n[k])) + '</div>');
  });
  var related = (g.edges||[]).filter(function(e){return e.from===nid || e.to===nid;});

  // Build navigation buttons based on node type
  var navBtns = '';
  var realId = '';
  if (n.type === 'project') {
    realId = nid.replace(/^proj:/, '');
    navBtns =
      '<button class="btn btn-primary btn-sm" onclick="_orchOpenProject(\''+esc(realId)+'\')">'
      + '<span class="material-symbols-outlined" style="font-size:14px">open_in_new</span> 打开项目</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="_orchOpenProjectTab(\''+esc(realId)+'\',\'goals\')">目标</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="_orchOpenProjectTab(\''+esc(realId)+'\',\'milestones\')">里程碑</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="_orchOpenProjectTab(\''+esc(realId)+'\',\'chat\')">协作</button>';
  } else if (n.type === 'agent' || n.type === 'subagent') {
    realId = nid.replace(/^agent:/, '');
    navBtns =
      '<button class="btn btn-primary btn-sm" onclick="_orchOpenAgent(\''+esc(realId)+'\')">'
      + '<span class="material-symbols-outlined" style="font-size:14px">smart_toy</span> 进入 Agent</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="showAgentMemoryView(\''+esc(realId)+'\')">'
      + '<span class="material-symbols-outlined" style="font-size:14px">psychology</span> 记忆视图</button>';
  } else if (n.type === 'task') {
    // task:projId:taskId
    var rest = nid.replace(/^task:/, '');
    var colon = rest.indexOf(':');
    var projId = colon > 0 ? rest.substring(0, colon) : rest;
    var taskId = colon > 0 ? rest.substring(colon + 1) : '';
    navBtns =
      '<button class="btn btn-primary btn-sm" onclick="_orchOpenTask(\''+esc(projId)+'\',\''+esc(taskId)+'\')">'
      + '<span class="material-symbols-outlined" style="font-size:14px">task</span> 打开任务</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="_orchOpenProject(\''+esc(projId)+'\')">所属项目</button>';
    if (n.assigned_to) {
      navBtns += '<button class="btn btn-ghost btn-sm" onclick="_orchOpenAgent(\''+esc(n.assigned_to)+'\')">执行 Agent</button>';
    }
  }

  document.getElementById('orch-detail').innerHTML =
    '<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px">'
    + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
    + '  <div style="font-weight:600">'+esc(n.label||n.id)+'</div>'
    + '  <div style="font-size:10px;padding:2px 6px;background:var(--surface2);border-radius:4px;color:var(--text3)">'+esc(n.type||'')+'</div>'
    + '</div>'
    + (navBtns ? '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">'+navBtns+'</div>' : '')
    + '<div style="font-size:11px;color:var(--text2);line-height:1.6">'+lines.join('')+'</div>'
    + '<div style="margin-top:8px;font-size:11px;color:var(--text3)">关联边: '+related.length+' 条</div></div>';
}

// Navigation helpers for orchestration click-through
function _orchOpenProject(projId) {
  if (typeof openProject === 'function') { openProject(projId); }
  else { currentView = 'project_detail'; currentProject = projId; renderCurrentView(); }
}
function _orchOpenProjectTab(projId, tab) {
  window._projectDetailTab = window._projectDetailTab || {};
  window._projectDetailTab[projId] = tab;
  _orchOpenProject(projId);
}
function _orchOpenAgent(agentId) {
  if (typeof showAgentView === 'function') { showAgentView(agentId, null); }
  else { currentView = 'agent'; currentAgent = agentId; renderCurrentView(); }
}
function _orchOpenTask(projId, taskId) {
  window._projectDetailTab = window._projectDetailTab || {};
  window._projectDetailTab[projId] = 'milestones';
  window._highlightTaskId = taskId;
  _orchOpenProject(projId);
}

// ---- Knowledge & Memory Hub (redesigned with RAG integration) ----
var _kmTab = 'shared';

function renderKnowledgeMemoryHub() {
  var c = document.getElementById('content');
  var tabs = [
    { id: 'shared',  label: '共享知识库',       icon: 'public' },
    { id: 'private', label: '专业领域知识库',   icon: 'school' },
    { id: 'rag',     label: 'RAG 提供方',       icon: 'cloud' },
    { id: 'memory',  label: 'Agent 私有记忆',   icon: 'psychology' },
  ];
  var tabsHtml = tabs.map(function(t) {
    var active = _kmTab === t.id;
    return '<button onclick="_kmTab=\''+t.id+'\';renderKnowledgeMemoryHub()" style="padding:8px 16px;border:none;background:'+(active?'var(--surface2)':'none')+';color:'+(active?'var(--primary)':'var(--text3)')+';font-size:12px;font-weight:'+(active?'700':'500')+';cursor:pointer;border-radius:8px;display:flex;align-items:center;gap:6px;font-family:inherit;transition:all 0.15s"><span class="material-symbols-outlined" style="font-size:16px">'+t.icon+'</span>'+t.label+'</button>';
  }).join('');

  c.innerHTML = '<div style="display:flex;gap:8px;margin-bottom:20px;padding:8px;background:var(--surface);border-radius:12px;border:1px solid var(--border-light);align-items:center;flex-wrap:wrap">'+tabsHtml+'</div>'
    + '<div id="km-content"></div>';

  if (_kmTab === 'shared') _renderKmShared();
  else if (_kmTab === 'private') _renderKmPrivate();
  else if (_kmTab === 'rag') _renderKmRagProviders();
  else if (_kmTab === 'memory') _renderKmMemory();
}

// ── Tab 1: Shared Knowledge ──
async function _renderKmShared() {
  var sc = document.getElementById('km-content');
  sc.innerHTML = '<div style="color:var(--text3);padding:20px;text-align:center">加载中...</div>';
  try {
    var data = await api('GET', '/api/portal/knowledge');
    var entries = data || [];
    if (Array.isArray(data)) entries = data;
    else if (data && data.entries) entries = data.entries;
    else entries = [];

    var cardsHtml = entries.map(function(e) {
      var tags = (e.tags||[]).map(function(t){return '<span style="padding:1px 6px;border-radius:4px;font-size:10px;background:rgba(203,201,255,0.1);color:var(--primary)">'+esc(t)+'</span>';}).join(' ');
      var preview = (e.content||'').substring(0,120).replace(/\n/g,' ');
      return '<div style="background:var(--surface);border-radius:10px;padding:14px;border:1px solid var(--border-light)">'
        + '<div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:6px">'
          + '<div style="font-weight:600;font-size:13px;color:var(--text)">'+esc(e.title||'')+'</div>'
          + '<div style="display:flex;gap:4px;flex-shrink:0">'
            + '<button onclick="_kmEditEntry(\''+esc(e.id)+'\')" class="btn btn-sm" style="padding:4px 8px;font-size:11px">编辑</button>'
            + '<button onclick="_kmDeleteEntry(\''+esc(e.id)+'\')" class="btn btn-sm" style="padding:4px 8px;font-size:11px;color:var(--error)">删除</button>'
          + '</div>'
        + '</div>'
        + '<div style="font-size:11px;color:var(--text3);margin-bottom:6px;line-height:1.5">'+esc(preview)+(preview.length>=120?'...':'')+'</div>'
        + (tags ? '<div style="display:flex;gap:4px;flex-wrap:wrap">'+tags+'</div>' : '')
        + '</div>';
    }).join('');

    sc.innerHTML = ''
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">'
        + '<div><div style="font-size:15px;font-weight:700;color:var(--text)">共享知识库</div>'
        + '<div style="font-size:12px;color:var(--text3);margin-top:2px">所有企业办公智能体共享的 RAG 知识，支持向量语义检索</div></div>'
        + '<div style="display:flex;gap:8px">'
          + '<button class="btn btn-sm" onclick="_kmShowImport(\'knowledge\',\'\')"><span class="material-symbols-outlined" style="font-size:14px">upload_file</span> 批量导入</button>'
          + '<button class="btn btn-primary btn-sm" onclick="_kmShowAddEntry()"><span class="material-symbols-outlined" style="font-size:14px">add</span> 新增条目</button>'
        + '</div>'
      + '</div>'
      + '<div style="display:flex;gap:10px;margin-bottom:16px">'
        + '<input id="km-search-input" placeholder="搜索知识库..." style="flex:1;font-size:13px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:8px 12px" onkeydown="if(event.key===\'Enter\')_kmSearch()">'
        + '<button class="btn btn-sm" onclick="_kmSearch()">搜索</button>'
      + '</div>'
      + (entries.length === 0 ? '<div style="color:var(--text3);padding:40px;text-align:center"><span class="material-symbols-outlined" style="font-size:40px;display:block;margin-bottom:8px">library_books</span>暂无知识条目，点击上方按钮添加</div>' : '')
      + '<div id="km-entries-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:10px">'+cardsHtml+'</div>';
  } catch(e) {
    sc.innerHTML = '<div style="color:var(--error);padding:20px">加载失败: '+e+'</div>';
  }
}

async function _kmSearch() {
  var q = (document.getElementById('km-search-input')||{}).value||'';
  if (!q.trim()) { _renderKmShared(); return; }
  try {
    var data = await api('GET', '/api/portal/knowledge/search?q='+encodeURIComponent(q));
    var grid = document.getElementById('km-entries-grid');
    if (!grid) return;
    var entries = data || [];
    if (!entries.length) { grid.innerHTML = '<div style="color:var(--text3);padding:20px;text-align:center">未找到匹配 "'+esc(q)+'" 的条目</div>'; return; }
    grid.innerHTML = entries.map(function(e) {
      return '<div style="background:var(--surface);border-radius:10px;padding:14px;border:1px solid var(--border-light)">'
        + '<div style="font-weight:600;font-size:13px;margin-bottom:4px">'+esc(e.title||'')+'</div>'
        + '<div style="font-size:11px;color:var(--text3)">'+esc((e.content||'').substring(0,120))+'</div>'
        + '</div>';
    }).join('');
  } catch(e) { console.error(e); }
}

function _kmShowAddEntry() {
  var html = '<div class="modal-overlay" id="km-add-modal" onclick="if(event.target===this)this.remove()">'
    + '<div class="modal" style="max-width:560px">'
    + '<h3>新增知识条目</h3>'
    + '<div class="form-group"><label>标题 *</label><input id="km-add-title" placeholder="e.g. 公司代码规范"></div>'
    + '<div class="form-group"><label>内容 *</label><textarea id="km-add-content" rows="8" placeholder="知识内容..."></textarea></div>'
    + '<div class="form-group"><label>标签 (逗号分隔)</label><input id="km-add-tags" placeholder="e.g. 规范,编码,Python"></div>'
    + '<div class="form-actions"><button class="btn btn-ghost" onclick="document.getElementById(\'km-add-modal\').remove()">取消</button>'
    + '<button class="btn btn-primary" onclick="_kmSaveNewEntry()">保存</button></div>'
    + '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
}

async function _kmSaveNewEntry() {
  var title = (document.getElementById('km-add-title')||{}).value||'';
  var content = (document.getElementById('km-add-content')||{}).value||'';
  var tagsRaw = (document.getElementById('km-add-tags')||{}).value||'';
  if (!title.trim() || !content.trim()) { alert('标题和内容不能为空'); return; }
  var tags = tagsRaw.split(',').map(function(t){return t.trim()}).filter(Boolean);
  try {
    await api('POST', '/api/portal/knowledge', {title:title,content:content,tags:tags});
    var m = document.getElementById('km-add-modal'); if(m)m.remove();
    _renderKmShared();
  } catch(e) { alert('保存失败: '+e); }
}

async function _kmDeleteEntry(id) {
  if (!confirm('确定删除此知识条目？')) return;
  try {
    await api('POST', '/api/portal/knowledge/'+id+'/delete');
    _renderKmShared();
  } catch(e) { alert('删除失败: '+e); }
}

async function _kmEditEntry(id) {
  try {
    var entries = await api('GET', '/api/portal/knowledge');
    var arr = Array.isArray(entries) ? entries : (entries.entries||[]);
    var entry = arr.find(function(e){return e.id===id;});
    if (!entry) { alert('未找到条目'); return; }
    var html = '<div class="modal-overlay" id="km-edit-modal" onclick="if(event.target===this)this.remove()">'
      + '<div class="modal" style="max-width:560px">'
      + '<h3>编辑知识条目</h3>'
      + '<div class="form-group"><label>标题</label><input id="km-edit-title" value="'+esc(entry.title||'')+'"></div>'
      + '<div class="form-group"><label>内容</label><textarea id="km-edit-content" rows="8">'+esc(entry.content||'')+'</textarea></div>'
      + '<div class="form-group"><label>标签</label><input id="km-edit-tags" value="'+esc((entry.tags||[]).join(', '))+'"></div>'
      + '<div class="form-actions"><button class="btn btn-ghost" onclick="document.getElementById(\'km-edit-modal\').remove()">取消</button>'
      + '<button class="btn btn-primary" onclick="_kmSaveEditEntry(\''+esc(id)+'\')">保存</button></div>'
      + '</div></div>';
    document.body.insertAdjacentHTML('beforeend', html);
  } catch(e) { alert('加载失败: '+e); }
}

async function _kmSaveEditEntry(id) {
  var title = (document.getElementById('km-edit-title')||{}).value;
  var content = (document.getElementById('km-edit-content')||{}).value;
  var tags = ((document.getElementById('km-edit-tags')||{}).value||'').split(',').map(function(t){return t.trim()}).filter(Boolean);
  try {
    await api('POST', '/api/portal/knowledge/'+id, {title:title,content:content,tags:tags});
    var m = document.getElementById('km-edit-modal'); if(m)m.remove();
    _renderKmShared();
  } catch(e) { alert('保存失败: '+e); }
}

// ── Batch import modal (shared between shared & private) ──
// Supports: file upload (PDF/DOCX/HTML/TXT/MD/CSV) + paste text
function _kmShowImport(collection, providerId) {
  var html = '<div class="modal-overlay" id="km-import-modal" onclick="if(event.target===this)this.remove()">'
    + '<div class="modal" style="max-width:640px">'
    + '<h3>导入知识</h3>'
    + '<div style="font-size:12px;color:var(--text3);margin-bottom:14px">上传文件或粘贴文本，系统自动解析并按段落分块导入向量库。目标: <b>'+esc(collection)+'</b></div>'

    // File upload area
    + '<div id="km-imp-file-zone" style="border:2px dashed var(--border);border-radius:10px;padding:24px;text-align:center;cursor:pointer;margin-bottom:14px;transition:all 0.2s;background:var(--surface)" onclick="document.getElementById(\'km-imp-file-input\').click()" ondragover="event.preventDefault();this.style.borderColor=\'var(--primary)\';this.style.background=\'rgba(203,201,255,0.06)\'" ondragleave="this.style.borderColor=\'var(--border)\';this.style.background=\'var(--surface)\'" ondrop="event.preventDefault();this.style.borderColor=\'var(--border)\';this.style.background=\'var(--surface)\';_kmHandleFileDrop(event)">'
      + '<input type="file" id="km-imp-file-input" accept=".pdf,.docx,.doc,.html,.htm,.txt,.md,.csv,.tsv,.json,.log" style="display:none" onchange="_kmHandleFileSelect(this)">'
      + '<span class="material-symbols-outlined" style="font-size:36px;color:var(--text3);display:block;margin-bottom:8px">upload_file</span>'
      + '<div style="font-size:13px;color:var(--text2);font-weight:600">点击或拖拽文件到此处</div>'
      + '<div style="font-size:11px;color:var(--text3);margin-top:4px">支持 PDF、Word (.docx)、HTML、TXT、Markdown、CSV</div>'
    + '</div>'
    + '<div id="km-imp-file-info" style="display:none;padding:10px 14px;background:rgba(63,185,80,0.08);border:1px solid rgba(63,185,80,0.2);border-radius:8px;margin-bottom:14px;font-size:12px">'
      + '<div style="display:flex;align-items:center;gap:8px">'
        + '<span class="material-symbols-outlined" style="font-size:18px;color:#3fb950">description</span>'
        + '<span id="km-imp-file-name" style="font-weight:600;color:var(--text)"></span>'
        + '<span id="km-imp-file-size" style="color:var(--text3)"></span>'
        + '<span id="km-imp-file-method" style="color:var(--text3);font-size:10px;background:var(--surface2);padding:1px 6px;border-radius:4px"></span>'
        + '<button onclick="_kmClearFile()" style="margin-left:auto;background:none;border:none;cursor:pointer;color:var(--text3);font-size:11px">✕ 清除</button>'
      + '</div>'
      + '<div id="km-imp-file-preview" style="margin-top:6px;font-size:11px;color:var(--text3);max-height:60px;overflow:hidden"></div>'
    + '</div>'

    // Divider
    + '<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px"><div style="flex:1;height:1px;background:var(--border)"></div><span style="font-size:11px;color:var(--text3)">或直接粘贴文本</span><div style="flex:1;height:1px;background:var(--border)"></div></div>'

    + '<div class="form-group"><label>文档标题</label><input id="km-imp-title" placeholder="e.g. 劳动法合集（上传文件时自动填入文件名）"></div>'
    + '<div class="form-group"><label>文本内容</label><textarea id="km-imp-content" rows="6" placeholder="粘贴文本内容...\n上传文件后此处自动填入解析后的文本"></textarea></div>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
      + '<div class="form-group"><label>标签 (逗号分隔)</label><input id="km-imp-tags" placeholder="法律,劳动法"></div>'
      + '<div class="form-group"><label>分块大小 (字符)</label><input id="km-imp-chunk" type="number" value="1000" min="200" max="5000"></div>'
    + '</div>'
    + '<div id="km-imp-status" style="display:none;padding:8px 12px;margin-bottom:10px;border-radius:6px;font-size:12px"></div>'
    + '<div class="form-actions"><button class="btn btn-ghost" onclick="document.getElementById(\'km-import-modal\').remove()">取消</button>'
    + '<button class="btn btn-primary" id="km-imp-submit-btn" onclick="_kmDoImport(\''+esc(collection)+'\',\''+esc(providerId)+'\')">导入</button></div>'
    + '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
}

// Store parsed file data globally for the modal
window._kmFileData = null;

function _kmHandleFileDrop(event) {
  var files = event.dataTransfer && event.dataTransfer.files;
  if (files && files.length > 0) _kmParseFile(files[0]);
}

function _kmHandleFileSelect(input) {
  if (input.files && input.files.length > 0) _kmParseFile(input.files[0]);
}

function _kmClearFile() {
  window._kmFileData = null;
  var info = document.getElementById('km-imp-file-info');
  var zone = document.getElementById('km-imp-file-zone');
  if (info) info.style.display = 'none';
  if (zone) zone.style.display = '';
  var ta = document.getElementById('km-imp-content');
  if (ta) ta.value = '';
  var titleEl = document.getElementById('km-imp-title');
  if (titleEl) titleEl.value = '';
}

async function _kmParseFile(file) {
  var statusEl = document.getElementById('km-imp-status');
  var infoEl = document.getElementById('km-imp-file-info');
  var zoneEl = document.getElementById('km-imp-file-zone');
  var submitBtn = document.getElementById('km-imp-submit-btn');

  // Show loading state
  if (statusEl) {
    statusEl.style.display = 'block';
    statusEl.style.background = 'rgba(203,201,255,0.08)';
    statusEl.style.color = 'var(--primary)';
    statusEl.textContent = '正在解析文件: ' + file.name + ' (' + _kmFmtSize(file.size) + ')...';
  }
  if (submitBtn) submitBtn.disabled = true;

  try {
    // Read file as base64
    var b64 = await new Promise(function(resolve, reject) {
      var reader = new FileReader();
      reader.onload = function() {
        var result = reader.result;
        resolve(result.split(',')[1]); // strip data:...;base64, prefix
      };
      reader.onerror = function() { reject(new Error('文件读取失败')); };
      reader.readAsDataURL(file);
    });

    // Send to server for parsing
    var res = await api('POST', '/api/portal/rag/parse-file', {
      file_data: b64,
      file_name: file.name
    });

    if (res.error) throw new Error(res.error);

    window._kmFileData = { name: file.name, size: file.size, text: res.text, method: res.method };

    // Fill in the form
    var titleEl = document.getElementById('km-imp-title');
    if (titleEl && !titleEl.value) {
      titleEl.value = file.name.replace(/\.[^.]+$/, '');
    }
    var contentEl = document.getElementById('km-imp-content');
    if (contentEl) contentEl.value = res.text;

    // Show file info
    if (infoEl) {
      infoEl.style.display = 'block';
      var nameEl = document.getElementById('km-imp-file-name');
      var sizeEl = document.getElementById('km-imp-file-size');
      var methodEl = document.getElementById('km-imp-file-method');
      var previewEl = document.getElementById('km-imp-file-preview');
      if (nameEl) nameEl.textContent = file.name;
      if (sizeEl) sizeEl.textContent = _kmFmtSize(file.size) + ' → ' + res.length + ' 字符';
      if (methodEl) methodEl.textContent = res.method;
      if (previewEl) previewEl.textContent = (res.text || '').substring(0, 200) + (res.length > 200 ? '...' : '');
    }
    if (zoneEl) zoneEl.style.display = 'none';

    if (statusEl) {
      statusEl.style.background = 'rgba(63,185,80,0.08)';
      statusEl.style.color = '#3fb950';
      statusEl.textContent = '解析完成: ' + res.length + ' 字符，使用 ' + res.method + ' 解析器';
      setTimeout(function(){ if(statusEl) statusEl.style.display='none'; }, 3000);
    }
  } catch(e) {
    if (statusEl) {
      statusEl.style.background = 'rgba(248,81,73,0.08)';
      statusEl.style.color = 'var(--error)';
      statusEl.textContent = '解析失败: ' + e;
    }
    window._kmFileData = null;
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function _kmFmtSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

async function _kmDoImport(collection, providerId) {
  var title = (document.getElementById('km-imp-title')||{}).value||'Imported';
  var content = (document.getElementById('km-imp-content')||{}).value||'';
  var tags = ((document.getElementById('km-imp-tags')||{}).value||'').split(',').map(function(t){return t.trim()}).filter(Boolean);
  var chunk = parseInt((document.getElementById('km-imp-chunk')||{}).value)||1000;
  if (!content.trim()) { alert('内容不能为空，请上传文件或粘贴文本'); return; }
  var statusEl = document.getElementById('km-imp-status');
  var submitBtn = document.getElementById('km-imp-submit-btn');
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '导入中...'; }
  if (statusEl) { statusEl.style.display = 'block'; statusEl.style.background = 'rgba(203,201,255,0.08)'; statusEl.style.color = 'var(--primary)'; statusEl.textContent = '正在导入并分块...'; }
  try {
    var res = await api('POST', '/api/portal/rag/import', {
      collection:collection, provider_id:providerId,
      title:title, content:content, tags:tags, chunk_size:chunk
    });
    window._kmFileData = null;
    alert('导入完成: '+((res&&res.chunks)||0)+' 个分块');
    var m = document.getElementById('km-import-modal'); if(m)m.remove();
    if (_kmTab === 'shared') _renderKmShared();
    else if (_kmTab === 'private') _renderKmPrivate();
  } catch(e) {
    alert('导入失败: '+e);
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = '导入'; }
    if (statusEl) { statusEl.style.background = 'rgba(248,81,73,0.08)'; statusEl.style.color = 'var(--error)'; statusEl.textContent = '导入失败: '+e; }
  }
}

// ── Tab 2: Domain Knowledge Bases (standalone, decoupled from agents) ──
async function _renderKmPrivate() {
  var sc = document.getElementById('km-content');
  sc.innerHTML = '<div style="color:var(--text3);padding:20px;text-align:center">加载中...</div>';
  try {
    var data = await api('POST', '/api/portal/domain-kb/list');
    var kbs = (data && data.knowledge_bases) || [];

    // Find which agents use each KB
    var agentsByKb = {};
    (agents||[]).forEach(function(a) {
      var colIds = (a.profile && a.profile.rag_collection_ids) || [];
      colIds.forEach(function(cid) { if (!agentsByKb[cid]) agentsByKb[cid] = []; agentsByKb[cid].push(a); });
    });

    var cardsHtml = kbs.map(function(kb) {
      var boundAgents = agentsByKb[kb.id] || [];
      var agentNames = boundAgents.map(function(a){ return esc(a.name); }).join(', ');
      var tagHtml = (kb.tags||[]).map(function(t){return '<span style="padding:1px 6px;border-radius:4px;font-size:10px;background:rgba(240,136,62,0.1);color:#f0883e">'+esc(t)+'</span>';}).join(' ');
      return '<div style="background:var(--surface);border-radius:12px;padding:18px;border:1px solid var(--border-light)">'
        + '<div style="display:flex;align-items:start;gap:12px;margin-bottom:10px">'
          + '<div style="width:42px;height:42px;border-radius:12px;background:rgba(240,136,62,0.12);display:flex;align-items:center;justify-content:center;flex-shrink:0"><span class="material-symbols-outlined" style="font-size:22px;color:#f0883e">menu_book</span></div>'
          + '<div style="flex:1;min-width:0">'
            + '<div style="font-weight:700;font-size:14px;color:var(--text)">'+esc(kb.name)+'</div>'
            + '<div style="font-size:11px;color:var(--text3);margin-top:2px">'+esc(kb.description||'')+'</div>'
          + '</div>'
          + '<div style="display:flex;gap:4px;flex-shrink:0">'
            + '<button onclick="_kmEditDomainKb(\''+esc(kb.id)+'\')" class="btn btn-sm" style="padding:4px 8px;font-size:11px" title="编辑"><span class="material-symbols-outlined" style="font-size:14px">edit</span></button>'
            + '<button onclick="_kmDeleteDomainKb(\''+esc(kb.id)+'\',\''+esc(kb.name)+'\')" class="btn btn-sm" style="padding:4px 8px;font-size:11px;color:var(--error)" title="删除"><span class="material-symbols-outlined" style="font-size:14px">delete</span></button>'
          + '</div>'
        + '</div>'
        + '<div style="display:flex;gap:12px;font-size:11px;color:var(--text3);margin-bottom:10px">'
          + '<span style="display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">description</span>'+kb.doc_count+' 文档块</span>'
          + '<span style="display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">smart_toy</span>'+(boundAgents.length > 0 ? boundAgents.length+' 个 Agent 使用' : '未绑定 Agent')+'</span>'
          + (kb.provider_id ? '<span style="display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">cloud</span>远程</span>' : '<span style="display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">storage</span>本地</span>')
        + '</div>'
        + (agentNames ? '<div style="font-size:11px;color:var(--text3);margin-bottom:8px">绑定: '+agentNames+'</div>' : '')
        + (tagHtml ? '<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px">'+tagHtml+'</div>' : '')
        + '<div style="display:flex;gap:8px">'
          + '<button class="btn btn-sm" onclick="_kmShowDomainImport(\''+esc(kb.id)+'\',\''+esc(kb.name)+'\')"><span class="material-symbols-outlined" style="font-size:14px">upload_file</span> 导入知识</button>'
          + '<button class="btn btn-sm" onclick="_kmSearchDomainKb(\''+esc(kb.id)+'\',\''+esc(kb.name)+'\')"><span class="material-symbols-outlined" style="font-size:14px">search</span> 检索测试</button>'
        + '</div>'
        + '</div>';
    }).join('');

    sc.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">'
      + '<div><div style="font-size:15px;font-weight:700;color:var(--text)">专业领域知识库</div>'
      + '<div style="font-size:12px;color:var(--text3);margin-top:2px">独立于智能体，可创建后绑定给多个顾问。删除智能体不影响知识库。</div></div>'
      + '<button class="btn btn-primary btn-sm" onclick="_kmShowCreateDomainKb()"><span class="material-symbols-outlined" style="font-size:14px">add</span> 新建知识库</button>'
      + '</div>'
      + (kbs.length === 0
        ? '<div style="text-align:center;padding:60px 20px;border:1px dashed var(--border);border-radius:12px">'
          + '<span class="material-symbols-outlined" style="font-size:48px;color:var(--text3);display:block;margin-bottom:12px">menu_book</span>'
          + '<div style="font-size:14px;color:var(--text2);margin-bottom:8px">暂无专业领域知识库</div>'
          + '<div style="font-size:12px;color:var(--text3);margin-bottom:16px">创建知识库后，可导入 PDF/Word/文本，然后在创建顾问智能体时选择绑定</div>'
          + '<button class="btn btn-primary btn-sm" onclick="_kmShowCreateDomainKb()"><span class="material-symbols-outlined" style="font-size:14px">add</span> 新建专业领域知识库</button>'
          + '</div>'
        : '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:12px">'+cardsHtml+'</div>');
  } catch(e) {
    sc.innerHTML = '<div style="color:var(--error);padding:20px">加载失败: '+e+'</div>';
  }
}

function _kmShowCreateDomainKb() {
  var html = '<div class="modal-overlay" id="km-dkb-modal" onclick="if(event.target===this)this.remove()">'
    + '<div class="modal" style="max-width:500px">'
    + '<h3>新建专业领域知识库</h3>'
    + '<div class="form-group"><label>知识库名称 *</label><input id="km-dkb-name" placeholder="e.g. 法律知识库、财务知识库"></div>'
    + '<div class="form-group"><label>描述</label><input id="km-dkb-desc" placeholder="e.g. 包含劳动法、合同法等法律文档"></div>'
    + '<div class="form-group"><label>标签 (逗号分隔)</label><input id="km-dkb-tags" placeholder="法律,劳动法,合同法"></div>'
    + '<div class="form-group"><label>存储提供方</label><select id="km-dkb-provider"><option value="">本地 ChromaDB (默认)</option></select></div>'
    + '<div class="form-actions"><button class="btn btn-ghost" onclick="document.getElementById(\'km-dkb-modal\').remove()">取消</button>'
    + '<button class="btn btn-primary" onclick="_kmSaveDomainKb()">创建</button></div>'
    + '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
  // Load remote providers into dropdown
  api('GET', '/api/portal/rag/providers').then(function(data) {
    var sel = document.getElementById('km-dkb-provider');
    if (!sel || !data || !data.providers) return;
    data.providers.forEach(function(p) {
      if (!p.enabled) return;
      var opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name + ' (' + p.kind + ')';
      sel.appendChild(opt);
    });
  }).catch(function(){});
}

async function _kmSaveDomainKb() {
  var name = (document.getElementById('km-dkb-name')||{}).value||'';
  var desc = (document.getElementById('km-dkb-desc')||{}).value||'';
  var tags = ((document.getElementById('km-dkb-tags')||{}).value||'').split(',').map(function(t){return t.trim()}).filter(Boolean);
  var provider = (document.getElementById('km-dkb-provider')||{}).value||'';
  if (!name.trim()) { alert('名称不能为空'); return; }
  try {
    await api('POST', '/api/portal/domain-kb/create', {name:name, description:desc, tags:tags, provider_id:provider});
    var m = document.getElementById('km-dkb-modal'); if(m) m.remove();
    _renderKmPrivate();
  } catch(e) { alert('创建失败: '+e); }
}

function _kmEditDomainKb(kbId) {
  api('POST', '/api/portal/domain-kb/list').then(function(data) {
    var kbs = (data && data.knowledge_bases) || [];
    var kb = kbs.find(function(k){ return k.id === kbId; });
    if (!kb) { alert('未找到'); return; }
    var html = '<div class="modal-overlay" id="km-dkb-edit-modal" onclick="if(event.target===this)this.remove()">'
      + '<div class="modal" style="max-width:500px">'
      + '<h3>编辑知识库</h3>'
      + '<div class="form-group"><label>名称</label><input id="km-dkb-edit-name" value="'+esc(kb.name)+'"></div>'
      + '<div class="form-group"><label>描述</label><input id="km-dkb-edit-desc" value="'+esc(kb.description||'')+'"></div>'
      + '<div class="form-group"><label>标签</label><input id="km-dkb-edit-tags" value="'+esc((kb.tags||[]).join(', '))+'"></div>'
      + '<div class="form-actions"><button class="btn btn-ghost" onclick="document.getElementById(\'km-dkb-edit-modal\').remove()">取消</button>'
      + '<button class="btn btn-primary" onclick="_kmSaveEditDomainKb(\''+esc(kbId)+'\')">保存</button></div>'
      + '</div></div>';
    document.body.insertAdjacentHTML('beforeend', html);
  }).catch(function(e){ alert('加载失败: '+e); });
}

async function _kmSaveEditDomainKb(kbId) {
  var name = (document.getElementById('km-dkb-edit-name')||{}).value;
  var desc = (document.getElementById('km-dkb-edit-desc')||{}).value;
  var tags = ((document.getElementById('km-dkb-edit-tags')||{}).value||'').split(',').map(function(t){return t.trim()}).filter(Boolean);
  try {
    await api('POST', '/api/portal/domain-kb/update', {id:kbId, name:name, description:desc, tags:tags});
    var m = document.getElementById('km-dkb-edit-modal'); if(m) m.remove();
    _renderKmPrivate();
  } catch(e) { alert('保存失败: '+e); }
}

async function _kmDeleteDomainKb(kbId, name) {
  if (!confirm('确定删除知识库 "'+name+'" 吗？\\n\\n注意：删除后知识库中的所有文档将被永久移除！')) return;
  try {
    await api('POST', '/api/portal/domain-kb/delete', {id:kbId});
    _renderKmPrivate();
  } catch(e) { alert('删除失败: '+e); }
}

function _kmShowDomainImport(kbId, kbName) {
  // Reuse the file upload import modal but target domain KB API
  var html = '<div class="modal-overlay" id="km-import-modal" onclick="if(event.target===this)this.remove()">'
    + '<div class="modal" style="max-width:640px">'
    + '<h3>导入知识到: '+esc(kbName)+'</h3>'
    + '<div style="font-size:12px;color:var(--text3);margin-bottom:14px">上传文件或粘贴文本，系统自动解析并分块导入。</div>'
    // File upload area
    + '<div id="km-imp-file-zone" style="border:2px dashed var(--border);border-radius:10px;padding:24px;text-align:center;cursor:pointer;margin-bottom:14px;transition:all 0.2s;background:var(--surface)" onclick="document.getElementById(\'km-imp-file-input\').click()" ondragover="event.preventDefault();this.style.borderColor=\'var(--primary)\';this.style.background=\'rgba(203,201,255,0.06)\'" ondragleave="this.style.borderColor=\'var(--border)\';this.style.background=\'var(--surface)\'" ondrop="event.preventDefault();this.style.borderColor=\'var(--border)\';this.style.background=\'var(--surface)\';_kmHandleFileDrop(event)">'
      + '<input type="file" id="km-imp-file-input" accept=".pdf,.docx,.doc,.html,.htm,.txt,.md,.csv,.tsv,.json,.log" style="display:none" onchange="_kmHandleFileSelect(this)">'
      + '<span class="material-symbols-outlined" style="font-size:36px;color:var(--text3);display:block;margin-bottom:8px">upload_file</span>'
      + '<div style="font-size:13px;color:var(--text2);font-weight:600">点击或拖拽文件到此处</div>'
      + '<div style="font-size:11px;color:var(--text3);margin-top:4px">支持 PDF、Word (.docx)、HTML、TXT、Markdown、CSV</div>'
    + '</div>'
    + '<div id="km-imp-file-info" style="display:none;padding:10px 14px;background:rgba(63,185,80,0.08);border:1px solid rgba(63,185,80,0.2);border-radius:8px;margin-bottom:14px;font-size:12px">'
      + '<div style="display:flex;align-items:center;gap:8px"><span class="material-symbols-outlined" style="font-size:18px;color:#3fb950">description</span>'
        + '<span id="km-imp-file-name" style="font-weight:600;color:var(--text)"></span>'
        + '<span id="km-imp-file-size" style="color:var(--text3)"></span>'
        + '<span id="km-imp-file-method" style="color:var(--text3);font-size:10px;background:var(--surface2);padding:1px 6px;border-radius:4px"></span>'
        + '<button onclick="_kmClearFile()" style="margin-left:auto;background:none;border:none;cursor:pointer;color:var(--text3);font-size:11px">✕</button>'
      + '</div>'
      + '<div id="km-imp-file-preview" style="margin-top:6px;font-size:11px;color:var(--text3);max-height:60px;overflow:hidden"></div>'
    + '</div>'
    + '<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px"><div style="flex:1;height:1px;background:var(--border)"></div><span style="font-size:11px;color:var(--text3)">或直接粘贴文本</span><div style="flex:1;height:1px;background:var(--border)"></div></div>'
    + '<div class="form-group"><label>文档标题</label><input id="km-imp-title" placeholder="e.g. 劳动法合集"></div>'
    + '<div class="form-group"><label>文本内容</label><textarea id="km-imp-content" rows="6" placeholder="上传文件后此处自动填入"></textarea></div>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
      + '<div class="form-group"><label>标签</label><input id="km-imp-tags" placeholder="法律,劳动法"></div>'
      + '<div class="form-group"><label>分块大小</label><input id="km-imp-chunk" type="number" value="1000" min="200" max="5000"></div>'
    + '</div>'
    + '<div id="km-imp-status" style="display:none;padding:8px 12px;margin-bottom:10px;border-radius:6px;font-size:12px"></div>'
    + '<div class="form-actions"><button class="btn btn-ghost" onclick="document.getElementById(\'km-import-modal\').remove()">取消</button>'
    + '<button class="btn btn-primary" id="km-imp-submit-btn" onclick="_kmDoDomainImport(\''+esc(kbId)+'\')">导入</button></div>'
    + '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
}

async function _kmDoDomainImport(kbId) {
  var title = (document.getElementById('km-imp-title')||{}).value||'Imported';
  var content = (document.getElementById('km-imp-content')||{}).value||'';
  var tags = ((document.getElementById('km-imp-tags')||{}).value||'').split(',').map(function(t){return t.trim()}).filter(Boolean);
  var chunk = parseInt((document.getElementById('km-imp-chunk')||{}).value)||1000;
  if (!content.trim()) { alert('内容不能为空'); return; }
  var submitBtn = document.getElementById('km-imp-submit-btn');
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '导入中...'; }
  try {
    var res = await api('POST', '/api/portal/domain-kb/import', {
      kb_id:kbId, title:title, content:content, tags:tags, chunk_size:chunk
    });
    window._kmFileData = null;
    alert('导入完成: '+((res&&res.chunks)||0)+' 个分块');
    var m = document.getElementById('km-import-modal'); if(m)m.remove();
    _renderKmPrivate();
  } catch(e) {
    alert('导入失败: '+e);
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = '导入'; }
  }
}

function _kmSearchDomainKb(kbId, kbName) {
  var q = prompt('在 "'+kbName+'" 中检索:');
  if (!q) return;
  api('POST', '/api/portal/domain-kb/search', {kb_id:kbId, query:q, top_k:5})
    .then(function(data) {
      var results = (data&&data.results)||[];
      if (!results.length) { alert('未找到匹配结果'); return; }
      var msg = results.map(function(r,i){return (i+1)+'. '+(r.title||'untitled')+' (distance: '+(r.distance||0).toFixed(3)+')\n  '+((r.content||'').substring(0,100));}).join('\n\n');
      alert('检索结果 ('+results.length+' 条):\n\n'+msg);
    }).catch(function(e){ alert('检索失败: '+e); });
}

// ── Tab 3: RAG Providers ──
async function _renderKmRagProviders() {
  var sc = document.getElementById('km-content');
  sc.innerHTML = '<div style="color:var(--text3);padding:20px;text-align:center">加载中...</div>';
  try {
    var data = await api('GET', '/api/portal/rag/providers');
    var providers = (data&&data.providers)||[];

    var listHtml = '<div style="background:var(--surface);border-radius:10px;padding:14px;border:1px solid var(--border-light);margin-bottom:10px">'
      + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
        + '<span class="material-symbols-outlined" style="font-size:20px;color:#3fb950">storage</span>'
        + '<div><div style="font-weight:600;font-size:13px">本地 ChromaDB (内置)</div>'
        + '<div style="font-size:11px;color:var(--text3)">默认向量数据库，零配置，数据存储在 ~/.tudou_claw/chromadb</div></div>'
      + '</div></div>';

    listHtml += providers.map(function(p) {
      return '<div style="background:var(--surface);border-radius:10px;padding:14px;border:1px solid var(--border-light);margin-bottom:10px">'
        + '<div style="display:flex;justify-content:space-between;align-items:start">'
          + '<div style="display:flex;align-items:center;gap:10px">'
            + '<span class="material-symbols-outlined" style="font-size:20px;color:var(--primary)">cloud</span>'
            + '<div><div style="font-weight:600;font-size:13px">'+esc(p.name)+'</div>'
            + '<div style="font-size:11px;color:var(--text3)">'+esc(p.kind)+' · '+esc(p.base_url||'N/A')+(p.enabled?'':' · <span style="color:var(--error)">已禁用</span>')+'</div></div>'
          + '</div>'
          + '<button onclick="_kmDeleteProvider(\''+esc(p.id)+'\')" class="btn btn-sm" style="padding:4px 8px;font-size:11px;color:var(--error)">移除</button>'
        + '</div></div>';
    }).join('');

    sc.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">'
      + '<div><div style="font-size:15px;font-weight:700;color:var(--text)">RAG 提供方管理</div>'
      + '<div style="font-size:12px;color:var(--text3);margin-top:2px">管理向量数据库后端，支持本地 ChromaDB 和远程节点 HTTP 接口</div></div>'
      + '<button class="btn btn-primary btn-sm" onclick="_kmShowAddProvider()"><span class="material-symbols-outlined" style="font-size:14px">add</span> 添加提供方</button>'
      + '</div>'
      + listHtml;
  } catch(e) {
    sc.innerHTML = '<div style="color:var(--error);padding:20px">加载失败: '+e+'</div>';
  }
}

function _kmShowAddProvider() {
  var html = '<div class="modal-overlay" id="km-prov-modal" onclick="if(event.target===this)this.remove()">'
    + '<div class="modal" style="max-width:480px">'
    + '<h3>添加 RAG 提供方</h3>'
    + '<div class="form-group"><label>名称 *</label><input id="km-prov-name" placeholder="e.g. 远程 Node-2 RAG"></div>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
      + '<div class="form-group"><label>类型</label><select id="km-prov-kind"><option value="remote">远程 HTTP</option><option value="local">本地</option></select></div>'
      + '<div class="form-group"><label>API Key (可选)</label><input id="km-prov-key" placeholder="Bearer token"></div>'
    + '</div>'
    + '<div class="form-group"><label>Base URL *</label><input id="km-prov-url" placeholder="http://192.168.1.100:8765"></div>'
    + '<div class="form-group"><label>Node Secret (可选，TudouClaw 节点间认证)</label><input id="km-prov-secret" placeholder="X-Claw-Secret"></div>'
    + '<div class="form-actions"><button class="btn btn-ghost" onclick="document.getElementById(\'km-prov-modal\').remove()">取消</button>'
    + '<button class="btn btn-primary" onclick="_kmSaveProvider()">保存</button></div>'
    + '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
}

async function _kmSaveProvider() {
  var name = (document.getElementById('km-prov-name')||{}).value||'';
  var kind = (document.getElementById('km-prov-kind')||{}).value||'remote';
  var url = (document.getElementById('km-prov-url')||{}).value||'';
  var key = (document.getElementById('km-prov-key')||{}).value||'';
  var secret = (document.getElementById('km-prov-secret')||{}).value||'';
  if (!name.trim()) { alert('名称不能为空'); return; }
  try {
    await api('POST', '/api/portal/rag/providers', {
      name:name, kind:kind, base_url:url, api_key:key,
      config: secret ? {node_secret:secret} : {}
    });
    var m = document.getElementById('km-prov-modal'); if(m)m.remove();
    _renderKmRagProviders();
  } catch(e) { alert('保存失败: '+e); }
}

async function _kmDeleteProvider(id) {
  if (!confirm('确定移除此 RAG 提供方？')) return;
  try {
    await api('POST', '/api/portal/rag/providers/'+id+'/delete');
    _renderKmRagProviders();
  } catch(e) { alert('删除失败: '+e); }
}

// ── Tab 4: Agent Private Memory ──
var _agentMemStats = {};  // {agent_id: {l1, l2, l3}}

function _renderKmMemory() {
  var sc = document.getElementById('km-content');
  var visibleAgents = (agents||[]).filter(function(a){return !a.parent_id;});
  if (!visibleAgents.length) {
    sc.innerHTML = '<div style="color:var(--text3);padding:40px;text-align:center">暂无智能体</div>';
    return;
  }
  // Render cards first, then async load memory stats
  sc.innerHTML = '<div style="margin-bottom:16px"><div style="font-size:15px;font-weight:700;color:var(--text)">Agent 私有记忆</div>'
    + '<div style="font-size:12px;color:var(--text3);margin-top:2px">点击任一 agent 查看其记忆层级（L1/L2/L3）、ExecutionPlan、Transcript</div></div>'
    + '<div id="km-agent-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px"></div>';
  _renderKmAgentCards(visibleAgents);
  // Load memory stats in background
  api('GET', '/api/portal/agents/memory-stats').then(function(data) {
    if (data) { _agentMemStats = data; _renderKmAgentCards(visibleAgents); }
  }).catch(function(){});
}

function _renderKmAgentCards(visibleAgents) {
  var grid = document.getElementById('km-agent-grid');
  if (!grid) return;
  grid.innerHTML = visibleAgents.map(function(a) {
    var cls = a.agent_class || (a.profile&&a.profile.agent_class) || 'enterprise';
    var clsMeta = _AGENT_CLASSES[cls] || _AGENT_CLASSES.enterprise;
    var memMode = a.memory_mode || (a.profile&&a.profile.memory_mode) || 'full';
    var memLabel = memMode === 'full' ? '完整记忆' : memMode === 'light' ? '轻量记忆' : '无记忆';
    var st = _agentMemStats[a.id] || {};
    var l1 = st.l1 || 0, l2 = st.l2 || 0, l3 = st.l3 || 0;
    var total = l1 + l2 + l3;
    // Color coding: green if has memories, dim if empty
    var barColor = total > 0 ? 'var(--primary, #3b82f6)' : 'var(--border-light)';
    return '<div onclick="showAgentMemoryView(\''+a.id+'\')" style="background:var(--surface);border-radius:10px;padding:14px;cursor:pointer;border:1px solid var(--border-light);transition:all 0.15s" onmouseenter="this.style.borderColor=\'var(--primary)\'" onmouseleave="this.style.borderColor=\'var(--border-light)\'">'
      + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
        + '<span class="material-symbols-outlined" style="font-size:20px;color:'+clsMeta.color+'">'+clsMeta.icon+'</span>'
        + '<div style="font-weight:600;font-size:13px;flex:1">'+esc(a.name)+'</div>'
        + '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:var(--surface2, #333);color:var(--text3)">'+memLabel+'</span>'
      + '</div>'
      // Memory layer badges
      + '<div style="display:flex;gap:6px;margin-bottom:6px">'
        + _memBadge('L1 短时', l1, '#3b82f6')
        + _memBadge('L2 工作', l2, '#8b5cf6')
        + _memBadge('L3 长期', l3, '#10b981')
      + '</div>'
      // Mini progress bar
      + '<div style="display:flex;gap:2px;height:3px;border-radius:2px;overflow:hidden;background:var(--surface2, #222)">'
        + (l1 ? '<div style="flex:'+l1+';background:#3b82f6"></div>' : '')
        + (l2 ? '<div style="flex:'+l2+';background:#8b5cf6"></div>' : '')
        + (l3 ? '<div style="flex:'+l3+';background:#10b981"></div>' : '')
        + (total === 0 ? '<div style="flex:1;background:var(--border-light)"></div>' : '')
      + '</div>'
      + '<div style="font-size:10px;color:var(--text3);margin-top:4px">共 '+total+' 条记忆</div>'
    + '</div>';
  }).join('');
}

function _memBadge(label, count, color) {
  var bg = count > 0 ? color + '20' : 'transparent';
  var fg = count > 0 ? color : 'var(--text3)';
  return '<div style="font-size:10px;padding:2px 6px;border-radius:4px;background:'+bg+';color:'+fg+';border:1px solid '+(count>0?color+'40':'var(--border-light)')+'">'
    + label + ' <b>' + count + '</b></div>';
}

function showAgentMemoryView(aid) {
  // Open a modal showing agent's L1/L2/L3 memory + execution plans — NOT chat.
  var ag = null;
  if (typeof agents !== 'undefined' && agents) {
    for (var i=0;i<agents.length;i++) { if (agents[i].id === aid) { ag = agents[i]; break; } }
  }
  var name = (ag && ag.name) || aid;

  var modal = document.createElement('div');
  modal.id = 'agent-mem-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = ''
    + '<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;width:820px;max-width:94vw;max-height:86vh;display:flex;flex-direction:column">'
    + '  <div style="padding:14px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">'
    + '    <div><div style="font-weight:700;font-size:15px">🧠 '+esc(name)+' — 记忆视图</div>'
    + '    <div style="font-size:11px;color:var(--text3);margin-top:2px">L1 短时 / L2 工作 / L3 长期 · ExecutionPlan · Transcript</div></div>'
    + '    <div style="display:flex;gap:8px">'
    + '      <button class="btn btn-sm" onclick="compactAgentMemoryFromModal(\''+esc(aid)+'\')">压缩记忆</button>'
    + '      <button class="btn btn-sm" onclick="document.getElementById(\'agent-mem-modal\').remove()">×</button>'
    + '    </div>'
    + '  </div>'
    + '  <div id="agent-mem-body" style="flex:1;overflow:auto;padding:16px 18px;font-size:12px;color:var(--text2)">加载中…</div>'
    + '</div>';
  document.body.appendChild(modal);

  // Load engine info + plans + memory stats in parallel
  Promise.all([
    api('GET', '/api/portal/agent/'+encodeURIComponent(aid)+'/engine').catch(function(){return {};}),
    api('GET', '/api/portal/agent/'+encodeURIComponent(aid)+'/plans').catch(function(){return {};}),
    api('GET', '/api/portal/agent/'+encodeURIComponent(aid)+'/transcript').catch(function(){return {};}),
    api('GET', '/api/portal/agent/'+encodeURIComponent(aid)+'/memory-stats').catch(function(){return {};}),
  ]).then(function(res){
    var eng = res[0] || {};
    var plans = res[1] || {};
    var tr = res[2] || {};
    var mem = res[3] || {};
    var body = document.getElementById('agent-mem-body');
    if (!body) return;

    var es = eng.engine_summary || {};
    var sections = [];

    // ── Memory overview card with L1/L2/L3 ──
    var l1 = mem.l1 || 0, l2 = mem.l2 || 0, l3 = mem.l3 || 0;
    var l3cat = mem.l3_by_category || {};
    sections.push(
      '<div style="background:var(--surface);border-radius:8px;padding:12px;margin-bottom:14px;border:1px solid var(--border-light)">'
      + '<div style="font-weight:600;margin-bottom:10px">记忆层级概览</div>'
      + '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:10px">'
      + _memStatCard('L1 短时记忆', l1, '#3b82f6', '当前对话窗口中的消息')
      + _memStatCard('L2 工作记忆', l2, '#8b5cf6', '历史对话压缩摘要')
      + _memStatCard('L3 长期记忆', l3, '#10b981', '结构化语义知识')
      + '</div>'
      // L3 category breakdown
      + (l3 > 0 ? '<div style="display:flex;gap:6px;flex-wrap:wrap">'
        + _catBadge('intent', '意图', l3cat.intent||0)
        + _catBadge('reasoning', '推理', l3cat.reasoning||0)
        + _catBadge('outcome', '结果', l3cat.outcome||0)
        + _catBadge('rule', '规则', l3cat.rule||0)
        + _catBadge('reflection', '反思', l3cat.reflection||0)
        + '</div>' : '')
      // Compression strategy explanation
      + '<div style="margin-top:10px;padding:8px 10px;background:var(--surface2, #222);border-radius:6px;font-size:11px;color:var(--text3)">'
      + '<b>压缩策略：</b>L1（最近对话）超出窗口后 → 自动压缩为 L2 摘要（渐进式 Level 0→1→2，信息保留递减）→ 对话中提取结构化事实写入 L3（分 5 类：意图/推理/结果/规则/反思）'
      + '</div></div>'
    );

    // ── L2 Episodic entries ──
    var l2entries = mem.l2_entries || [];
    if (l2entries.length) {
      var l2rows = l2entries.map(function(ep){
        var lvl = ep.compression_level || 0;
        var lvlLabel = lvl === 0 ? '详细' : lvl === 1 ? '中等' : '精简';
        var lvlColor = lvl === 0 ? '#3b82f6' : lvl === 1 ? '#f59e0b' : '#ef4444';
        return '<div style="padding:8px;border-bottom:1px solid var(--border-light)">'
          + '<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">'
            + '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:'+lvlColor+'20;color:'+lvlColor+'">Level '+lvl+' '+lvlLabel+'</span>'
            + '<span style="font-size:10px;color:var(--text3)">Turn '+esc(String(ep.turn_start||'?'))+'-'+esc(String(ep.turn_end||'?'))+'</span>'
            + '<span style="font-size:10px;color:var(--text3)">'+esc(String(ep.message_count||0))+' msgs</span>'
            + '<span style="font-size:10px;color:var(--text3);margin-left:auto">'+esc(String(ep.created_at||'').slice(0,19))+'</span>'
          + '</div>'
          + '<div style="font-size:11px;color:var(--text2);white-space:pre-wrap;max-height:80px;overflow:auto">'+esc(ep.summary||'')+'</div>'
          + (ep.keywords ? '<div style="margin-top:4px;font-size:10px;color:var(--text3)">关键词: '+esc(ep.keywords)+'</div>' : '')
          + '</div>';
      }).join('');
      sections.push(
        '<div style="background:var(--surface);border-radius:8px;padding:12px;margin-bottom:14px;border:1px solid var(--border-light)">'
        + '<div style="font-weight:600;margin-bottom:8px;color:#8b5cf6">L2 工作记忆 — 对话摘要 ('+l2+')</div>'
        + l2rows + '</div>'
      );
    }

    // ── L3 Semantic facts ──
    var l3entries = mem.l3_entries || [];
    if (l3entries.length) {
      var CAT_LABELS = {intent:'意图',reasoning:'推理',outcome:'结果',rule:'规则',reflection:'反思'};
      var CAT_COLORS = {intent:'#3b82f6',reasoning:'#f59e0b',outcome:'#10b981',rule:'#ef4444',reflection:'#8b5cf6'};
      var l3rows = l3entries.map(function(f){
        var cat = f.category || 'unknown';
        var catLabel = CAT_LABELS[cat] || cat;
        var catColor = CAT_COLORS[cat] || 'var(--text3)';
        var conf = f.confidence ? Math.round(f.confidence * 100) : 0;
        return '<div style="padding:8px;border-bottom:1px solid var(--border-light)">'
          + '<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">'
            + '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:'+catColor+'20;color:'+catColor+'">'+esc(catLabel)+'</span>'
            + '<span style="font-size:10px;color:var(--text3)">置信度 '+conf+'%</span>'
            + '<span style="font-size:10px;color:var(--text3);margin-left:auto">'+esc(String(f.created_at||'').slice(0,19))+'</span>'
          + '</div>'
          + '<div style="font-size:11px;color:var(--text2)">'+esc(f.content||'')+'</div>'
          + '</div>';
      }).join('');
      sections.push(
        '<div style="background:var(--surface);border-radius:8px;padding:12px;margin-bottom:14px;border:1px solid var(--border-light)">'
        + '<div style="font-weight:600;margin-bottom:8px;color:#10b981">L3 长期记忆 — 语义知识 ('+l3+')</div>'
        + l3rows + '</div>'
      );
    }

    // ── Engine overview (collapsed by default) ──
    sections.push(
      '<div style="background:var(--surface);border-radius:8px;padding:12px;margin-bottom:14px;border:1px solid var(--border-light)">'
      + '<div style="font-weight:600;margin-bottom:8px">引擎概览</div>'
      + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px">'
      + '<div><div style="color:var(--text3);font-size:10px">TURN</div><div style="font-size:18px;font-weight:600">'+esc(String(eng.turn_count||0))+'</div></div>'
      + '<div><div style="color:var(--text3);font-size:10px">TRANSCRIPT</div><div style="font-size:18px;font-weight:600">'+esc(String(eng.transcript_size||0))+'</div></div>'
      + '<div><div style="color:var(--text3);font-size:10px">MESSAGES (L1)</div><div style="font-size:18px;font-weight:600">'+esc(String(l1))+'</div></div>'
      + '<div><div style="color:var(--text3);font-size:10px">TOKENS</div><div style="font-size:18px;font-weight:600">'+esc(String(es.total_tokens || 0))+'</div></div>'
      + '</div></div>'
    );

    // Current execution plan
    if (plans.current_plan) {
      var cp = plans.current_plan;
      var steps = (cp.steps || []).map(function(s){
        var icon = s.status === 'completed' ? '✅' : (s.status === 'in_progress' ? '🔄' : (s.status === 'failed' ? '❌' : '⭕'));
        return '<div style="padding:4px 0">'+icon+' '+esc(s.title||'')+' <span style="color:var(--text3);font-size:10px">['+esc(s.status||'')+']</span></div>';
      }).join('');
      sections.push(
        '<div style="background:var(--surface);border-radius:8px;padding:12px;margin-bottom:14px;border:1px solid var(--border-light)">'
        + '<div style="font-weight:600;margin-bottom:8px">当前执行计划</div>'
        + '<div style="font-size:11px;color:var(--text3);margin-bottom:6px">'+esc(cp.task_summary||'')+'</div>'
        + (steps || '<div style="color:var(--text3)">无步骤</div>')
        + '</div>'
      );
    }

    // Recent transcript entries — filter infra noise
    var trEntriesRaw = tr.transcript || eng.transcript_preview || [];
    if (trEntriesRaw && trEntriesRaw.length) {
      var NOISE_PATTERNS = [
        /LLM provider.*(connection failed|timeout|unreachable)/i,
        /429\s*(Client Error|Too Many Requests)/i,
        /\bToo Many Requests\b/i,
        /ConnectionError|ReadTimeout|ReadTimeoutError/i,
        /ECONNREFUSED|ECONNRESET|ETIMEDOUT/i,
        /\[Delegated task from [0-9a-f]+\]\s+Error:.*(429|connection failed|timeout|Too Many Requests)/i,
      ];
      function isNoise(s){
        for (var i=0;i<NOISE_PATTERNS.length;i++){
          if (NOISE_PATTERNS[i].test(s)) return true;
        }
        return false;
      }
      var noiseFiltered = 0;
      var cleaned = [];
      for (var i=0;i<trEntriesRaw.length;i++){
        var t = trEntriesRaw[i];
        var s = (typeof t === 'string') ? t : JSON.stringify(t);
        if (isNoise(s)) { noiseFiltered++; continue; }
        var key = s.slice(0,200);
        var last = cleaned.length ? cleaned[cleaned.length-1] : null;
        if (last && last.key === key) {
          last.count += 1;
        } else {
          cleaned.push({ text: s, key: key, count: 1 });
        }
      }
      var tail = cleaned.slice(-20);
      var rows = tail.map(function(row){
        var disp = row.text.slice(0,400) + (row.text.length>400?'…':'');
        var badge = row.count > 1 ? ' <span style="color:var(--text3);font-size:10px">×'+row.count+'</span>' : '';
        return '<div style="padding:4px 6px;border-bottom:1px solid var(--border-light);font-size:11px;color:var(--text2);word-break:break-word">'+esc(disp)+badge+'</div>';
      }).join('');
      var subtitle = '最近 Transcript (显示 ' + tail.length + ' 条';
      if (noiseFiltered > 0) subtitle += '，已过滤 ' + noiseFiltered + ' 条基础设施错误';
      subtitle += ')';
      sections.push(
        '<div style="background:var(--surface);border-radius:8px;padding:12px;margin-bottom:14px;border:1px solid var(--border-light)">'
        + '<div style="font-weight:600;margin-bottom:8px">'+esc(subtitle)+'</div>'
        + (rows || '<div style="color:var(--text3);padding:6px">无可展示内容</div>')
        + '</div>'
      );
    }

    if (!sections.length) {
      body.innerHTML = '<div style="color:var(--text3);padding:20px;text-align:center">该 agent 暂无记忆数据</div>';
    } else {
      body.innerHTML = sections.join('');
    }
  }).catch(function(e){
    var body = document.getElementById('agent-mem-body');
    if (body) body.innerHTML = '<div style="color:var(--error)">加载失败: '+esc(String(e))+'</div>';
  });
}

function _memStatCard(label, count, color, desc) {
  return '<div style="text-align:center;padding:10px;border-radius:6px;background:'+color+'10;border:1px solid '+color+'30">'
    + '<div style="font-size:24px;font-weight:700;color:'+color+'">'+count+'</div>'
    + '<div style="font-size:12px;font-weight:600;color:'+color+';margin-top:2px">'+label+'</div>'
    + '<div style="font-size:10px;color:var(--text3);margin-top:2px">'+desc+'</div>'
    + '</div>';
}

function _catBadge(cat, label, count) {
  var colors = {intent:'#3b82f6',reasoning:'#f59e0b',outcome:'#10b981',rule:'#ef4444',reflection:'#8b5cf6'};
  var c = colors[cat] || 'var(--text3)';
  return '<span style="font-size:10px;padding:2px 6px;border-radius:3px;background:'+c+'15;color:'+c+'">'+label+' '+count+'</span>';
}

function compactAgentMemoryFromModal(aid) {
  if (!confirm('确定要压缩该 agent 的记忆？L1 将被折叠写入 L2。')) return;
  fetch('/api/portal/agent/'+encodeURIComponent(aid)+'/compact-memory', {method:'POST'})
    .then(function(r){return r.json();}).then(function(d){
      if (d && d.error) { alert('压缩失败: '+d.error); return; }
      alert('压缩完成');
      document.getElementById('agent-mem-modal').remove();
      showAgentMemoryView(aid);
    }).catch(function(e){ alert('压缩失败: '+e); });
}

function renderRolesSkillsHub() {
  var c = document.getElementById('content');
  var tabs = [
    { id: 'templates', label: '角色 / 专业领域', icon: 'library_books' },
    { id: 'skill-store', label: '技能商店 Store', icon: 'storefront' },
    { id: 'pending-skills', label: '技能锻造 SkillForge', icon: 'auto_fix_high' },
    { id: 'self-improvement', label: '学习闭环 / 经验沉淀', icon: 'psychology' },
  ];
  var r = _renderHubTabs('roles', tabs);
  c.innerHTML = r.html;

  var sc = document.getElementById('hub-roles-content');
  var _orig = document.getElementById('content');
  sc.id = 'content'; _orig.id = 'content-outer';
  try {
    if (r.current === 'templates') renderTemplateLibrary();
    else if (r.current === 'skill-store') renderSkillStore();
    else if (r.current === 'skill-pkgs') renderSkillStore();  // legacy redirect
    else if (r.current === 'pending-skills') renderPendingSkills();
    else if (r.current === 'self-improvement') renderSelfImprovement();
  } catch(e) { sc.innerHTML = '<div style="color:var(--error);padding:20px">'+e.message+'</div>'; }
  finally { sc.id = 'hub-roles-content'; _orig.id = 'content'; }
