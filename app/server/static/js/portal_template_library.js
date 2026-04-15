}

// ============ Template Library ============
function renderTemplateLibrary(container) {
  const c = container || document.getElementById('content');
  if (!container) c.style.padding = '24px';
  const epoch = _renderEpoch;
  c.innerHTML = '<div style="color:var(--text3);padding:20px">Loading templates...</div>';
  api('GET', '/api/portal/templates').then(data => {
    if (!data || epoch !== _renderEpoch) return;
    const templates = data.templates || [];

    // Group by category
    const cats = {};
    templates.forEach(t => {
      const cat = t.category || 'General';
      if (!cats[cat]) cats[cat] = [];
      cats[cat].push(t);
    });

    let html = '<div style="margin-bottom:20px">' +
      '<h3 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:20px;font-weight:700;margin-bottom:4px">专业领域</h3>' +
      '<p style="color:var(--text2);font-size:13px">Agent 执行任务时自动匹配对应专业领域，注入领域方法论和检查清单。共 ' + templates.length + ' 个领域。</p>' +
      '<button class="btn btn-primary btn-sm" style="margin-top:10px" onclick="showCreateTemplate()">' +
        '<span class="material-symbols-outlined" style="font-size:14px">add</span> 新建专业领域</button>' +
    '</div>';

    Object.keys(cats).sort().forEach(cat => {
      html += '<div style="margin-bottom:24px">';
      html += '<div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:var(--text3);margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border-light)">' + esc(cat) + ' (' + cats[cat].length + ')</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">';
      cats[cat].forEach(t => {
        html += '<div class="card" style="padding:16px;cursor:pointer;transition:all 0.2s;border:1px solid var(--border-light)" ' +
          'onmouseenter="this.style.borderColor=\'var(--primary)\'" onmouseleave="this.style.borderColor=\'var(--border-light)\'" ' +
          'onclick="viewTemplate(\'' + esc(t.id) + '\')">' +
          '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">' +
            '<span style="font-weight:700;font-size:14px;line-height:1.3">' + esc(t.name) + '</span>' +
            '<span style="font-size:18px;flex-shrink:0;margin-left:8px">' + getCategoryIcon(cat) + '</span>' +
          '</div>' +
          '<div style="font-size:12px;color:var(--text2);line-height:1.4;margin-bottom:8px">' + esc(t.description||'').slice(0,100) + '</div>' +
          '<div style="display:flex;flex-wrap:wrap;gap:4px">' +
            (t.tags||[]).slice(0,4).map(tag => '<span style="font-size:10px;background:var(--surface3);padding:2px 6px;border-radius:4px;color:var(--text3)">' + esc(tag) + '</span>').join('') +
          '</div>' +
          '<div style="font-size:10px;color:var(--text3);margin-top:8px">' +
            'Roles: ' + (t.roles||[]).slice(0,3).map(r => esc(r)).join(', ') +
          '</div>' +
        '</div>';
      });
      html += '</div></div>';
    });
    c.innerHTML = html;
  });
}

function getCategoryIcon(cat) {
  const map = {
    'Product Management': '📋', 'Business': '📊', 'Development': '💻',
    'Quality Assurance': '✅', 'Security': '🛡️', 'Operations': '🚀',
    'Documentation': '📝', 'Data': '📈', 'Design': '🎨',
    'Project Management': '📅', 'General': '📦',
  };
  for (const [k,v] of Object.entries(map)) {
    if (cat.toLowerCase().includes(k.toLowerCase().split(' ')[0])) return v;
  }
  return '📄';
}

async function viewTemplate(templateId) {
  const data = await api('GET', '/api/portal/templates/' + templateId);
  if (!data) return;
  const t = data;
  // Render content as HTML (basic markdown conversion)
  const contentHtml = (t.content||'')
    .replace(/^### (.*$)/gm, '<h4 style="color:var(--primary);margin:12px 0 6px;font-size:14px">$1</h4>')
    .replace(/^## (.*$)/gm, '<h3 style="color:var(--text);margin:16px 0 8px;font-size:16px;font-weight:700">$1</h3>')
    .replace(/^# (.*$)/gm, '<h2 style="color:var(--text);margin:20px 0 10px;font-size:18px;font-weight:800">$1</h2>')
    .replace(/^- \[x\] (.*$)/gm, '<div style="display:flex;align-items:flex-start;gap:6px;margin:3px 0"><span style="color:var(--success);font-size:14px">☑</span><span style="font-size:13px;color:var(--text2)">$1</span></div>')
    .replace(/^- \[ \] (.*$)/gm, '<div style="display:flex;align-items:flex-start;gap:6px;margin:3px 0"><span style="color:var(--text3);font-size:14px">☐</span><span style="font-size:13px;color:var(--text2)">$1</span></div>')
    .replace(/^- (.*$)/gm, '<div style="margin:2px 0 2px 12px;font-size:13px;color:var(--text2)">• $1</div>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.*?)`/g, '<code style="background:var(--surface3);padding:1px 4px;border-radius:3px;font-size:12px">$1</code>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');

  const html = '<div style="padding:20px;max-height:80vh;overflow-y:auto;max-width:700px">' +
    '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">' +
      '<div>' +
        '<h3 style="font-family:\'Plus Jakarta Sans\',sans-serif;margin-bottom:4px">' + esc(t.name) + '</h3>' +
        '<p style="font-size:12px;color:var(--text2)">' + esc(t.description||'') + '</p>' +
      '</div>' +
      '<div style="display:flex;gap:6px">' +
        '<button class="btn btn-sm" style="font-size:11px" onclick="editTemplateContent(\'' + esc(t.id) + '\')"><span class="material-symbols-outlined" style="font-size:14px">edit</span> Edit</button>' +
        '<button class="btn btn-sm" style="font-size:11px;color:var(--error)" onclick="deleteTemplate(\'' + esc(t.id) + '\')"><span class="material-symbols-outlined" style="font-size:14px">delete</span></button>' +
      '</div>' +
    '</div>' +
    '<div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap">' +
      (t.roles||[]).map(r => '<span style="font-size:10px;background:rgba(203,201,255,0.15);color:var(--primary);padding:2px 8px;border-radius:4px;font-weight:600">' + esc(r) + '</span>').join('') +
      (t.tags||[]).map(tg => '<span style="font-size:10px;background:var(--surface3);padding:2px 6px;border-radius:4px;color:var(--text3)">' + esc(tg) + '</span>').join('') +
    '</div>' +
    '<div style="border:1px solid var(--border-light);border-radius:8px;padding:16px;background:var(--bg);font-size:13px;line-height:1.6;max-height:50vh;overflow-y:auto">' + contentHtml + '</div>' +
    '<div style="text-align:right;margin-top:12px"><button class="btn btn-sm" onclick="closeModal()">Close</button></div>' +
  '</div>';
  showModalHTML(html);
}

function showCreateTemplate() {
  const html = '<div style="padding:16px">' +
    '<h3 style="margin-bottom:16px">Create Template</h3>' +
    '<div class="form-group"><label>Name</label><input id="tpl-name" placeholder="e.g. 性能优化技能"></div>' +
    '<div class="form-group"><label>Description</label><input id="tpl-desc" placeholder="Brief description"></div>' +
    '<div class="form-group"><label>Category</label><input id="tpl-cat" value="General" placeholder="e.g. Development, Security"></div>' +
    '<div class="form-group"><label>Roles (comma separated)</label><input id="tpl-roles" placeholder="e.g. Developer, Architect"></div>' +
    '<div class="form-group"><label>Tags (comma separated)</label><input id="tpl-tags" placeholder="e.g. performance, optimization"></div>' +
    '<div class="form-group"><label>Content (Markdown)</label>' +
      '<textarea id="tpl-content" rows="12" style="width:100%;background:var(--surface3);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:10px;font-family:monospace;font-size:12px;line-height:1.5" placeholder="# Template Title\n\ntags: tag1, tag2\n\n## Section 1\n\n- [ ] Checklist item..."></textarea>' +
    '</div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">' +
      '<button class="btn btn-sm" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-primary btn-sm" onclick="saveNewTemplate()">Create</button>' +
    '</div></div>';
  showModalHTML(html);
}

async function saveNewTemplate() {
  const name = document.getElementById('tpl-name').value.trim();
  const content = document.getElementById('tpl-content').value;
  if (!name || !content) { alert('Name and content required'); return; }
  await api('POST', '/api/portal/templates', {
    action: 'create',
    name: name,
    description: document.getElementById('tpl-desc').value,
    category: document.getElementById('tpl-cat').value || 'General',
    roles: document.getElementById('tpl-roles').value.split(',').map(s=>s.trim()).filter(Boolean),
    tags: document.getElementById('tpl-tags').value.split(',').map(s=>s.trim()).filter(Boolean),
    content: content,
  });
  closeModal();
  renderTemplateLibrary();
}

function editTemplateContent(templateId) {
  api('GET', '/api/portal/templates/' + templateId).then(t => {
    if (!t) return;
    const html = '<div style="padding:16px">' +
      '<h3 style="margin-bottom:16px">Edit: ' + esc(t.name) + '</h3>' +
      '<div class="form-group"><label>Name</label><input id="tpl-edit-name" value="' + esc(t.name) + '"></div>' +
      '<div class="form-group"><label>Description</label><input id="tpl-edit-desc" value="' + esc(t.description||'') + '"></div>' +
      '<div class="form-group"><label>Content (Markdown)</label>' +
        '<textarea id="tpl-edit-content" rows="15" style="width:100%;background:var(--surface3);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:10px;font-family:monospace;font-size:12px;line-height:1.5">' + esc(t.content||'') + '</textarea>' +
      '</div>' +
      '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">' +
        '<button class="btn btn-sm" onclick="closeModal()">Cancel</button>' +
        '<button class="btn btn-primary btn-sm" onclick="saveEditTemplate(\'' + esc(templateId) + '\')">Save</button>' +
      '</div></div>';
    showModalHTML(html);
  });
}

async function saveEditTemplate(templateId) {
  await api('POST', '/api/portal/templates', {
    action: 'update',
    template_id: templateId,
    name: document.getElementById('tpl-edit-name').value,
    description: document.getElementById('tpl-edit-desc').value,
    content: document.getElementById('tpl-edit-content').value,
  });
  closeModal();
  renderTemplateLibrary();
}

async function deleteTemplate(templateId) {
  if (!confirm('确定要删除这个技能吗?')) return;
  await api('POST', '/api/portal/templates', { action: 'delete', template_id: templateId });
  closeModal();
  renderTemplateLibrary();
