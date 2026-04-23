}

// ============ Providers ============
function renderProviders(container) {
  var c = container || document.getElementById('content');
  if (!container) c.style.padding = '24px';
  var epoch = _renderEpoch;
  // Show header immediately
  // Page header — removed the top-right "Add Provider" primary button
  // per design pass. New providers are added via the card-level action
  // / empty-state CTA further below.
  c.innerHTML = '<div style="margin-bottom:28px"><h2 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:28px;font-weight:800;letter-spacing:-0.5px">LLM Providers</h2><p style="color:var(--text2);font-size:14px;margin-top:4px">Manage external compute endpoints and local model integrations.</p></div><div id="providers-grid" style="display:grid;grid-template-columns:repeat(2,1fr);gap:20px"><div style="color:var(--text3);padding:20px">Loading...</div></div>';
  api('GET', '/api/portal/providers').then(function(data) {
    if (!data || epoch !== _renderEpoch) return;
    providers = data.providers || [];
    var grid = document.getElementById('providers-grid');
    if (!grid) return;
    var kindIcon = function(k) { return k==='ollama'?'terminal':k==='claude'?'smart_toy':'cloud'; };
    var kindLabel = function(k) { return k==='ollama'?'Local':k==='claude'?'Anthropic':'External'; };
    grid.innerHTML = providers.map(function(p) { return '<div style="background:var(--surface);border-radius:14px;padding:24px;border:1px solid var(--border-light);transition:all 0.2s" onmouseenter="this.style.background=\'var(--surface2)\'" onmouseleave="this.style.background=\'var(--surface)\'">' +
      '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px">' +
        '<div style="display:flex;align-items:center;gap:14px">' +
          '<div style="width:48px;height:48px;background:var(--surface3);border-radius:10px;display:flex;align-items:center;justify-content:center"><span class="material-symbols-outlined" style="font-size:28px;color:var(--primary)">' + kindIcon(p.kind) + '</span></div>' +
          '<div>' +
            '<div style="display:flex;align-items:center;gap:8px"><span style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:16px;font-weight:700">' + esc(p.name) + '</span><span style="font-size:10px;background:rgba(203,201,255,0.1);color:var(--primary);padding:2px 8px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px;font-weight:700">' + kindLabel(p.kind) + '</span></div>' +
            '<div style="font-size:12px;color:var(--text3);margin-top:2px">' + esc(p.base_url) + '</div>' +
          '</div>' +
        '</div>' +
        '<div style="display:flex;align-items:center;gap:6px;font-size:11px;font-weight:700;color:' + (p.enabled ? 'var(--success)' : 'var(--error)') + '"><span style="width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor;display:inline-block"></span>' + (p.enabled ? 'ENABLED' : 'DISABLED') + '</div>' +
      '</div>' +
      '<div style="margin-bottom:20px">' +
        '<div style="font-size:10px;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);font-weight:700;margin-bottom:8px">Models (' + (p.manual_models||p.models_cache||[]).length + ')</div>' +
        '<div style="display:flex;flex-wrap:wrap;gap:6px">' +
          (((p.manual_models||p.models_cache||[]).length > 0) ? (p.manual_models||p.models_cache||[]).map(function(m) { return '<span style="background:var(--surface3);padding:5px 10px;border-radius:6px;font-size:11px;color:var(--text2);display:flex;align-items:center;gap:4px">' + esc(m) + ' <span class="material-symbols-outlined" style="font-size:14px;color:var(--success)">check_circle</span></span>'; }).join('') : '<span style="font-size:12px;color:var(--text3)">No models configured — click Edit to add models</span>') +
        '</div>' +
      '</div>' +
      '<div style="margin-bottom:20px">' +
        '<div style="font-size:10px;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);font-weight:700;margin-bottom:8px">Concurrency &amp; Scheduling</div>' +
        '<div style="display:flex;flex-wrap:wrap;gap:8px">' +
          '<span style="background:var(--surface3);padding:4px 10px;border-radius:6px;font-size:11px;color:var(--text2);display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">speed</span>Max ' + (p.max_concurrent||1) + ' concurrent</span>' +
          '<span style="background:var(--surface3);padding:4px 10px;border-radius:6px;font-size:11px;color:var(--text2);display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">schedule</span>' + esc(p.schedule_strategy||'serial') + '</span>' +
          (p.rate_limit_rpm > 0 ? '<span style="background:var(--surface3);padding:4px 10px;border-radius:6px;font-size:11px;color:var(--text2);display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">timer</span>' + p.rate_limit_rpm + ' RPM</span>' : '') +
          '<span style="background:var(--surface3);padding:4px 10px;border-radius:6px;font-size:11px;color:var(--text2);display:flex;align-items:center;gap:4px"><span class="material-symbols-outlined" style="font-size:14px">' + (p.scope==='cloud'?'cloud':'computer') + '</span>' + esc(p.scope||'local') + '</span>' +
        '</div>' +
        (Object.keys(p.model_concurrency||{}).length > 0 ? '<div style="margin-top:6px;font-size:10px;color:var(--text3)">Per-model: ' + Object.entries(p.model_concurrency||{}).map(function(e) { return e[0] + '=' + e[1]; }).join(', ') + '</div>' : '') +
      '</div>' +
      (p.api_key ? '<div style="margin-bottom:20px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><span style="font-size:10px;text-transform:uppercase;letter-spacing:0.8px;color:var(--text3);font-weight:700">API Key</span><span style="font-size:10px;color:var(--text3)">Masked</span></div><div style="background:var(--bg);border:1px solid var(--border-light);border-radius:6px;padding:10px 14px;display:flex;align-items:center;gap:10px"><span class="material-symbols-outlined" style="font-size:16px;color:var(--text3)">key</span><span style="font-size:12px;color:var(--text3);font-family:monospace;letter-spacing:1px">&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;</span></div></div>' : '') +
      '<div style="display:flex;align-items:center;justify-content:space-between;padding-top:16px;border-top:1px solid var(--border-light)">' +
        '<div style="display:flex;gap:12px">' +
          '<button style="background:none;border:none;color:var(--text2);font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:4px;padding:0" onclick="editProvider(\'' + esc(p.id) + '\')"><span class="material-symbols-outlined" style="font-size:16px">edit</span> Edit</button>' +
        '</div>' +
        '<button style="background:none;border:none;color:var(--error);font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:4px;padding:0;opacity:0.7" onclick="deleteProvider(\'' + esc(p.id) + '\')"><span class="material-symbols-outlined" style="font-size:16px">delete</span> Delete</button>' +
      '</div>' +
    '</div>'; }).join('') +
    (providers.length === 0 ? '<div style="color:var(--text3);padding:20px;grid-column:1/-1">No providers configured yet. Click "+ Add Provider" to get started.</div>' : '');
  });
}

// ---- Model tag chip helpers ----
function addModelTag(prefix) {
  var input = document.getElementById(prefix + '-model-input');
  var val = (input.value || '').trim();
  if (!val) return;
  var container = document.getElementById(prefix + '-model-tags');
  // Prevent duplicates
  var existing = container.querySelectorAll('.model-tag');
  for (var i = 0; i < existing.length; i++) {
    if (existing[i].dataset.model === val) { input.value = ''; return; }
  }
  var tag = document.createElement('span');
  tag.className = 'model-tag';
  tag.dataset.model = val;
  tag.style.cssText = 'display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:var(--surface2);border:1px solid var(--border);border-radius:6px;font-size:12px;color:var(--text);font-family:monospace';
  tag.innerHTML = esc(val) + '<span onclick="this.parentElement.remove()" style="cursor:pointer;color:var(--text3);font-size:14px;line-height:1;margin-left:2px">&times;</span>';
  container.appendChild(tag);
  input.value = '';
  input.focus();
}

function getModelTags(prefix) {
  var container = document.getElementById(prefix + '-model-tags');
  var tags = container.querySelectorAll('.model-tag');
  var models = [];
  for (var i = 0; i < tags.length; i++) models.push(tags[i].dataset.model);
  return models;
}

function setModelTags(prefix, models) {
  var container = document.getElementById(prefix + '-model-tags');
  container.innerHTML = '';
  (models || []).forEach(function(m) {
    if (!m) return;
    var tag = document.createElement('span');
    tag.className = 'model-tag';
    tag.dataset.model = m;
    tag.style.cssText = 'display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:var(--surface2);border:1px solid var(--border);border-radius:6px;font-size:12px;color:var(--text);font-family:monospace';
    tag.innerHTML = esc(m) + '<span onclick="this.parentElement.remove()" style="cursor:pointer;color:var(--text3);font-size:14px;line-height:1;margin-left:2px">&times;</span>';
    container.appendChild(tag);
  });
}

async function addProvider() {
  const name = document.getElementById('ap-name').value.trim();
  const kind = document.getElementById('ap-kind').value;
  const base_url = document.getElementById('ap-url').value.trim();
  const api_key = document.getElementById('ap-key').value.trim();
  if (!name || !base_url) { alert('Name and Base URL are required'); return; }
  const manual_models = getModelTags('ap');
  const max_concurrent = parseInt(document.getElementById('ap-max-concurrent').value) || 1;
  const rate_limit_rpm = parseInt(document.getElementById('ap-rate-limit-rpm').value) || 0;
  const schedule_strategy = document.getElementById('ap-schedule-strategy').value;
  const scope = document.getElementById('ap-scope').value;
  await api('POST', '/api/portal/providers', { name, kind, base_url, api_key, manual_models, max_concurrent, rate_limit_rpm, schedule_strategy, scope });
  hideModal('add-provider');
  document.getElementById('ap-name').value = '';
  document.getElementById('ap-url').value = '';
  document.getElementById('ap-key').value = '';
  document.getElementById('ap-max-concurrent').value = '1';
  document.getElementById('ap-rate-limit-rpm').value = '0';
  document.getElementById('ap-schedule-strategy').value = 'serial';
  document.getElementById('ap-scope').value = 'local';
  setModelTags('ap', []);
  loadAvailableModels();
  renderProviders();
}

function editProvider(id) {
  const p = providers.find(x => x.id === id);
  if (!p) return;
  document.getElementById('ep-name').value = p.name;
  document.getElementById('ep-kind').value = p.kind;
  document.getElementById('ep-url').value = p.base_url;
  document.getElementById('ep-key').value = p.api_key || '';
  document.getElementById('ep-enabled').value = String(p.enabled);
  // Concurrency fields
  document.getElementById('ep-max-concurrent').value = p.max_concurrent || 1;
  document.getElementById('ep-rate-limit-rpm').value = p.rate_limit_rpm || 0;
  document.getElementById('ep-schedule-strategy').value = p.schedule_strategy || 'serial';
  document.getElementById('ep-scope').value = p.scope || 'local';
  document.getElementById('ep-context-length').value = p.context_length || 0;
  // Per-model concurrency overrides
  var mcDiv = document.getElementById('ep-model-concurrency');
  var models = p.manual_models || p.models_cache || [];
  var mc = p.model_concurrency || {};
  mcDiv.innerHTML = models.length === 0 ? '<div style="font-size:11px;color:var(--text3)">Add models first to set per-model concurrency.</div>' :
    models.map(function(m) {
      return '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">' +
        '<span style="font-size:11px;color:var(--text);font-family:monospace;min-width:120px">' + esc(m) + '</span>' +
        '<input type="number" min="0" max="100" value="' + (mc[m] || 0) + '" data-mc-model="' + esc(m) + '" style="width:60px;font-size:11px;padding:4px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--text)">' +
        '<span style="font-size:10px;color:var(--text3)">(0=use platform default)</span></div>';
    }).join('');
  // Show manual models as tag chips
  setModelTags('ep', models);
  window._editProviderId = id;
  showModal('edit-provider');
}

async function saveProvider() {
  const id = window._editProviderId;
  if (!id) return;
  const body = {
    name: document.getElementById('ep-name').value.trim(),
    kind: document.getElementById('ep-kind').value,
    base_url: document.getElementById('ep-url').value.trim(),
    api_key: document.getElementById('ep-key').value.trim(),
    enabled: document.getElementById('ep-enabled').value === 'true',
    max_concurrent: parseInt(document.getElementById('ep-max-concurrent').value) || 1,
    rate_limit_rpm: parseInt(document.getElementById('ep-rate-limit-rpm').value) || 0,
    schedule_strategy: document.getElementById('ep-schedule-strategy').value,
    scope: document.getElementById('ep-scope').value,
    context_length: parseInt(document.getElementById('ep-context-length').value) || 0,
  };
  // Collect per-model concurrency overrides
  var mcInputs = document.querySelectorAll('[data-mc-model]');
  var model_concurrency = {};
  mcInputs.forEach(function(inp) {
    var v = parseInt(inp.value) || 0;
    if (v > 0) model_concurrency[inp.dataset.mcModel] = v;
  });
  body.model_concurrency = model_concurrency;
  body.manual_models = getModelTags('ep');
  await api('POST', `/api/portal/providers/${id}/update`, body);
  hideModal('edit-provider');
  loadAvailableModels();
  renderProviders();
}

async function deleteProvider(id) {
  if (!confirm('Delete this provider?')) return;
  await api('DELETE', `/api/portal/providers/${id}`);
  loadAvailableModels();
  renderProviders();
}

async function detectModels(id) {
  const btn = event.target;
  btn.textContent = 'Detecting...';
  btn.disabled = true;
  const data = await api('POST', `/api/portal/providers/${id}/detect`);
  btn.textContent = 'Detect Models';
  btn.disabled = false;
  if (data && data.models) {
    alert(`Found ${data.models.length} model(s): ${data.models.join(', ') || '(none)'}`);
  }
  loadAvailableModels();
  renderProviders();
}

async function detectAllModels() {
  const data = await api('POST', '/api/portal/providers/detect-all');
  if (data && data.models) {
    let total = 0;
    for (const k of Object.keys(data.models)) total += data.models[k].length;
    alert(`Detected ${total} model(s) across ${Object.keys(data.models).length} provider(s)`);
  }
  loadAvailableModels();
  if (currentView === 'providers') renderProviders();
