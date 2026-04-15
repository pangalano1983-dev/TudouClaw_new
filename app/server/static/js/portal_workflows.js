}

// ============ Workflows ============
var _wfCatalogFilter = '';

async function renderWorkflows() {
  var c = document.getElementById('content');
  c.style.padding = '24px';
  try {
    var data = await api('GET', '/api/portal/workflows');
    var wfs = data.workflows || [];
    // Also load catalog
    var catalogData = {};
    try { catalogData = await api('GET', '/api/portal/workflow-catalog'); } catch(e) {}
    var catalog = catalogData.catalog || [];
    var categories = catalogData.categories || {};

    var html = '<div style="max-width:1200px;margin:0 auto">';

    // ── Header ──
    html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">';
    html += '<div><h2 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:24px;font-weight:800;margin:0">Workflows</h2>';
    html += '<p style="font-size:12px;color:var(--text3);margin-top:4px">选择模板快速创建，或自定义工作流流程</p></div>';
    html += '<button class="btn btn-primary btn-sm" onclick="showCreateWorkflowModal()"><span class="material-symbols-outlined" style="font-size:14px">add</span> 自定义创建</button>';
    html += '</div>';

    // ── My Workflows (已创建的) ──
    if (wfs.length) {
      html += '<div style="margin-bottom:28px">';
      html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:14px"><span class="material-symbols-outlined" style="font-size:20px;color:var(--primary)">account_tree</span><span style="font-size:16px;font-weight:700">我的工作流</span><span style="font-size:11px;color:var(--text3);background:var(--surface3);padding:2px 8px;border-radius:10px">' + wfs.length + '</span></div>';
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px">';
      wfs.forEach(function(wf) {
        var stepsArr = wf.steps || [];
        var stepsPreview = stepsArr.slice(0,5).map(function(s, i) {
          return '<span style="padding:2px 8px;border-radius:4px;background:var(--surface3);font-size:10px;color:var(--text2);white-space:nowrap">' + (i+1) + '. ' + esc(s.name||'Step '+(i+1)) + '</span>';
        }).join('<span style="color:var(--text3);font-size:10px;margin:0 2px">&rarr;</span>');
        if (stepsArr.length > 5) stepsPreview += '<span style="font-size:10px;color:var(--text3);margin-left:4px">+' + (stepsArr.length - 5) + ' more</span>';

        html += '<div class="card" style="background:var(--surface);border-radius:12px;padding:18px;border:1px solid rgba(255,255,255,0.06)">' +
          '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">' +
            '<div style="display:flex;align-items:center;gap:8px"><span class="material-symbols-outlined" style="font-size:18px;color:var(--primary)">account_tree</span><span style="font-size:15px;font-weight:700">' + esc(wf.name) + '</span></div>' +
            '<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:rgba(203,201,255,0.1);color:var(--primary);font-weight:700">TEMPLATE</span>' +
          '</div>' +
          '<div style="font-size:12px;color:var(--text3);margin-bottom:10px;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">' + esc(wf.description||'No description') + '</div>' +
          '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-bottom:12px">' + (stepsPreview || '<span style="font-size:11px;color:var(--text3)">No steps</span>') + '</div>' +
          '<div style="display:flex;align-items:center;justify-content:space-between">' +
            '<span style="font-size:11px;color:var(--text3)">' + stepsArr.length + ' steps</span>' +
            '<div style="display:flex;gap:6px">' +
              '<button class="btn btn-sm" style="font-size:10px" onclick="editWorkflow(\'' + wf.id + '\')"><span class="material-symbols-outlined" style="font-size:12px">edit</span></button>' +
              '<button class="btn btn-sm" style="font-size:10px;color:var(--error)" onclick="deleteWorkflow(\'' + wf.id + '\')"><span class="material-symbols-outlined" style="font-size:12px">delete</span></button>' +
            '</div>' +
          '</div>' +
        '</div>';
      });
      html += '</div></div>';
    }

    // ── Catalog Section ──
    if (catalog.length) {
      html += '<div style="margin-bottom:20px">';
      html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">';
      html += '<div style="display:flex;align-items:center;gap:8px"><span class="material-symbols-outlined" style="font-size:20px;color:#FF9800">auto_awesome</span><span style="font-size:16px;font-weight:700">模板市场</span><span style="font-size:11px;color:var(--text3)">Template Catalog</span></div>';
      html += '</div>';

      // Category filter tabs
      var catNames = Object.keys(categories);
      html += '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">';
      html += '<button class="btn btn-sm" id="wf-cat-all" style="font-size:11px;' + (!_wfCatalogFilter ? 'background:var(--primary);color:#282572;font-weight:700' : '') + '" onclick="filterWfCatalog(\'\')">全部 (' + catalog.length + ')</button>';
      catNames.forEach(function(cat) {
        var cnt = categories[cat].length;
        var active = _wfCatalogFilter === cat;
        html += '<button class="btn btn-sm" style="font-size:11px;' + (active ? 'background:var(--primary);color:#282572;font-weight:700' : '') + '" onclick="filterWfCatalog(\'' + esc(cat) + '\')">' + esc(cat) + ' (' + cnt + ')</button>';
      });
      html += '</div>';

      // Catalog cards
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px" id="wf-catalog-grid">';
      catalog.forEach(function(t) {
        var hidden = _wfCatalogFilter && t.category !== _wfCatalogFilter;
        var tags = (t.tags || []).map(function(tag) {
          return '<span style="font-size:9px;padding:2px 6px;border-radius:4px;background:rgba(255,152,0,0.1);color:#FF9800">' + esc(tag) + '</span>';
        }).join('');
        html += '<div class="card wf-catalog-card" data-category="' + esc(t.category||'') + '" style="background:var(--surface);border-radius:12px;padding:18px;border:1px solid rgba(255,255,255,0.06);cursor:pointer;transition:border-color 0.15s,transform 0.15s;' + (hidden ? 'display:none' : '') + '" onmouseenter="this.style.borderColor=\'#FF9800\';this.style.transform=\'translateY(-2px)\'" onmouseleave="this.style.borderColor=\'rgba(255,255,255,0.06)\';this.style.transform=\'none\'" onclick="useWfCatalog(\'' + t.id + '\')">';
        html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">';
        html += '<div style="display:flex;align-items:center;gap:8px"><span style="font-size:20px">' + (t.icon||'📋') + '</span><span style="font-size:14px;font-weight:700">' + esc(t.name) + '</span></div>';
        html += '<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:rgba(255,152,0,0.1);color:#FF9800;font-weight:600">' + t.step_count + ' 步</span>';
        html += '</div>';
        html += '<div style="font-size:12px;color:var(--text3);margin-bottom:10px;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">' + esc(t.description) + '</div>';
        html += '<div style="display:flex;flex-wrap:wrap;gap:4px">' + tags + '</div>';
        html += '</div>';
      });
      html += '</div></div>';
    }

    html += '</div>';
    c.innerHTML = html;
  } catch(e) { c.innerHTML = '<div style="color:var(--error)">Error loading workflows: ' + esc(String(e)) + '</div>'; }
}

function filterWfCatalog(cat) {
  _wfCatalogFilter = cat;
  var cards = document.querySelectorAll('.wf-catalog-card');
  cards.forEach(function(card) {
    if (!cat || card.getAttribute('data-category') === cat) {
      card.style.display = '';
    } else {
      card.style.display = 'none';
    }
  });
  // Update button active state
  var btns = document.querySelectorAll('#wf-cat-all');
  // Re-render is simpler — just call renderWorkflows again
  renderWorkflows();
}

async function useWfCatalog(catalogId) {
  if (!confirm('从模板市场创建工作流？')) return;
  try {
    var data = await api('POST', '/api/portal/workflows', {
      action: 'create_from_catalog',
      catalog_id: catalogId
    });
    if (data && !data.error) {
      renderWorkflows();
    } else {
      alert((data && data.error) || 'Failed to create from catalog');
    }
  } catch(e) { alert('Error: ' + e); }
