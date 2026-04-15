}

// ============ Node Configuration ============
function renderNodeConfig(container) {
  const c = container || document.getElementById('content');
  if (!container) c.style.padding = '24px';
  const epoch = _renderEpoch;
  c.innerHTML = '<div style="color:var(--text3);padding:20px">Loading node configurations...</div>';
  api('GET', '/api/portal/node-configs').then(data => {
    if (!data || epoch !== _renderEpoch) return;
    const configs = data.configs || [];
    const isHub = portalMode === 'hub';
    c.innerHTML = `
      <div style="margin-bottom:20px">
        <h3 style="font-family:'Plus Jakarta Sans',sans-serif;font-size:20px;font-weight:700;margin-bottom:4px">Node Configuration</h3>
        <p style="color:var(--text2);font-size:13px">Per-node secrets, tokens, and environment variables. ${isHub ? 'Admin can manage all nodes.' : 'You can only edit local node config.'}</p>
      </div>
      <div id="node-config-list"></div>
    `;
    const listEl = document.getElementById('node-config-list');
    if (configs.length === 0) {
      listEl.innerHTML = '<div style="color:var(--text3);padding:16px">No nodes found.</div>';
      return;
    }
    listEl.innerHTML = configs.map(nc => {
      const nid = nc.node_id;
      const nname = nc.node_name || nid;
      const items = Object.values(nc.items || {});
      const canEdit = isHub || nid === 'local';
      const unsyncedCount = items.filter(i => !i.synced).length;
      return `
        <div class="card" style="margin-bottom:16px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <div>
              <span style="font-weight:700;font-size:15px">${esc(nname)}</span>
              <span style="font-size:11px;color:var(--text3);margin-left:8px">${esc(nid)}</span>
              ${nid === 'local' ? '<span style="font-size:10px;background:var(--primary);color:white;padding:1px 6px;border-radius:4px;margin-left:6px">LOCAL</span>' : '<span style="font-size:10px;background:var(--warning);color:#333;padding:1px 6px;border-radius:4px;margin-left:6px">REMOTE</span>'}
            </div>
            <div style="display:flex;gap:8px">
              ${isHub && nid !== 'local' ? `<button class="btn btn-sm" style="font-size:11px" onclick="syncNodeConfig('${esc(nid)}')" title="Push config to node">
                <span class="material-symbols-outlined" style="font-size:14px">sync</span> Sync ${unsyncedCount > 0 ? '('+unsyncedCount+' pending)' : ''}
              </button>` : ''}
              ${canEdit ? `<button class="btn btn-primary btn-sm" style="font-size:11px" onclick="showAddNodeConfigItem('${esc(nid)}')">
                <span class="material-symbols-outlined" style="font-size:14px">add</span> Add
              </button>` : ''}
            </div>
          </div>
          <div id="ncfg-items-${esc(nid)}">
            ${items.length === 0 ? '<div style="color:var(--text3);font-size:13px;padding:8px 0">No config items yet.</div>' :
              `<table style="width:100%;border-collapse:collapse;font-size:13px">
                <tr style="border-bottom:1px solid var(--border-light);color:var(--text3);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">
                  <th style="text-align:left;padding:6px 8px">Key</th>
                  <th style="text-align:left;padding:6px 8px">Value</th>
                  <th style="text-align:left;padding:6px 8px">Category</th>
                  <th style="text-align:left;padding:6px 8px">Synced</th>
                  ${canEdit ? '<th style="text-align:right;padding:6px 8px">Actions</th>' : ''}
                </tr>
                ${items.map(item => `
                  <tr style="border-bottom:1px solid var(--border-light)">
                    <td style="padding:8px;font-family:monospace;font-weight:600">${esc(item.key)}</td>
                    <td style="padding:8px;font-family:monospace;color:var(--text2)">${item.is_secret ? '<span style="color:var(--text3)">••••••••</span>' : esc(item.value)}</td>
                    <td style="padding:8px"><span style="font-size:11px;background:var(--surface3);padding:2px 8px;border-radius:4px">${esc(item.category)}</span></td>
                    <td style="padding:8px">${item.synced ? '<span style="color:var(--success);font-size:12px">&#10003; synced</span>' : '<span style="color:var(--warning);font-size:12px">pending</span>'}</td>
                    ${canEdit ? `<td style="padding:8px;text-align:right">
                      <button style="background:none;border:none;color:var(--primary);cursor:pointer;font-size:11px;font-weight:700" onclick="editNodeConfigItem('${esc(nid)}','${esc(item.key)}')">Edit</button>
                      <button style="background:none;border:none;color:var(--error);cursor:pointer;font-size:11px;font-weight:700;margin-left:8px" onclick="deleteNodeConfigItem('${esc(nid)}','${esc(item.key)}')">Delete</button>
                    </td>` : ''}
                  </tr>
                `).join('')}
              </table>`
            }
          </div>
        </div>
      `;
    }).join('');
  });
}

function showAddNodeConfigItem(nodeId) {
  const html = `
    <div style="padding:16px">
      <h3 style="margin-bottom:16px">Add Config Item — ${esc(nodeId)}</h3>
      <div class="form-group"><label>Key</label><input id="ncfg-key" placeholder="e.g. market_api_token"></div>
      <div class="form-group"><label>Value</label><input id="ncfg-value" placeholder="Enter value"></div>
      <div class="form-group"><label>Description</label><input id="ncfg-desc" placeholder="What is this for?"></div>
      <div class="form-group"><label>Category</label>
        <select id="ncfg-category">
          <option value="general">General</option>
          <option value="credentials">Credentials</option>
          <option value="integration">Integration</option>
          <option value="custom">Custom</option>
        </select>
      </div>
      <div class="form-group" style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" id="ncfg-secret"> <label for="ncfg-secret" style="margin:0">Secret (masked in UI)</label>
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
        <button class="btn btn-sm" onclick="closeModal()">Cancel</button>
        <button class="btn btn-primary btn-sm" onclick="saveNodeConfigItem('${esc(nodeId)}')">Save</button>
      </div>
    </div>
  `;
  showModalHTML(html);
}

function editNodeConfigItem(nodeId, key) {
  // Fetch current value
  api('GET', '/api/portal/node/' + nodeId + '/config?mask=0').then(data => {
    const item = (data.items || {})[key];
    if (!item) return;
    const html = `
      <div style="padding:16px">
        <h3 style="margin-bottom:16px">Edit Config — ${esc(key)}</h3>
        <div class="form-group"><label>Key</label><input id="ncfg-key" value="${esc(key)}" readonly style="opacity:0.6"></div>
        <div class="form-group"><label>Value</label><input id="ncfg-value" value="${esc(item.value)}"></div>
        <div class="form-group"><label>Description</label><input id="ncfg-desc" value="${esc(item.description)}"></div>
        <div class="form-group"><label>Category</label>
          <select id="ncfg-category">
            <option value="general" ${item.category==='general'?'selected':''}>General</option>
            <option value="credentials" ${item.category==='credentials'?'selected':''}>Credentials</option>
            <option value="integration" ${item.category==='integration'?'selected':''}>Integration</option>
            <option value="custom" ${item.category==='custom'?'selected':''}>Custom</option>
          </select>
        </div>
        <div class="form-group" style="display:flex;align-items:center;gap:8px">
          <input type="checkbox" id="ncfg-secret" ${item.is_secret?'checked':''}> <label for="ncfg-secret" style="margin:0">Secret</label>
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
          <button class="btn btn-sm" onclick="closeModal()">Cancel</button>
          <button class="btn btn-primary btn-sm" onclick="saveNodeConfigItem('${esc(nodeId)}')">Save</button>
        </div>
      </div>
    `;
    showModalHTML(html);
  });
}

async function saveNodeConfigItem(nodeId) {
  const key = document.getElementById('ncfg-key').value.trim();
  const value = document.getElementById('ncfg-value').value;
  const desc = document.getElementById('ncfg-desc').value;
  const cat = document.getElementById('ncfg-category').value;
  const secret = document.getElementById('ncfg-secret').checked;
  if (!key) return alert('Key is required');
  await api('POST', '/api/portal/node/' + nodeId + '/config', {
    key, value, description: desc, category: cat, is_secret: secret
  });
  closeModal();
  renderNodeConfig();
}

async function deleteNodeConfigItem(nodeId, key) {
  if (!confirm('Delete config "' + key + '" from node ' + nodeId + '?')) return;
  await api('POST', '/api/portal/node/' + nodeId + '/config', {
    action: 'delete', key: key
  });
  renderNodeConfig();
}

async function syncNodeConfig(nodeId) {
  const result = await api('POST', '/api/portal/node/' + nodeId + '/config/sync', {});
  if (result && result.ok) {
    alert('Synced ' + (result.synced||0) + ' config items to node ' + nodeId);
  } else {
    alert('Sync failed: ' + (result && result.error || 'Unknown error'));
  }
  renderNodeConfig();
}

function showModalHTML(html) {
  // Remove any existing overlays first to prevent duplicate stacking
  document.querySelectorAll('#modal-overlay').forEach(function(o){ o.remove(); });
  var overlay = document.createElement('div');
  overlay.id = 'modal-overlay';
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;z-index:1000';
  document.body.appendChild(overlay);
  overlay.innerHTML = '<div style="background:var(--surface);border-radius:16px;min-width:400px;max-width:550px;max-height:85vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.3);border:1px solid var(--border-light)">' + html + '</div>';
  overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };
