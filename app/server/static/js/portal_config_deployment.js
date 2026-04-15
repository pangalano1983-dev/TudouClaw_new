}

// ============ Config Deployment ============

function showPushConfig(nodeId) {
  // Build agent selector from node's agents
  var node = nodes.find(function(n) { return n.node_id === nodeId; });
  if (!node) return;
  var agentOpts = '<option value="">-- Select Agent --</option>';
  var agentList = node.is_self
    ? Object.values(window._localAgentsForRender || {})
    : (node.agents || []);
  agentList.forEach(function(a) {
    agentOpts += '<option value="' + esc(a.id) + '">' + esc(a.name || a.id) + '</option>';
  });

  var html = '<div style="position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:1000;display:flex;align-items:center;justify-content:center" id="config-modal" onclick="if(event.target===this)this.remove()">' +
    '<div style="background:var(--surface);border-radius:16px;padding:32px;width:520px;max-height:80vh;overflow:auto;border:1px solid var(--border-light)">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px">' +
        '<h3 style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:20px;font-weight:800;margin:0">Push Config to Node</h3>' +
        '<button onclick="document.getElementById(\'config-modal\').remove()" style="background:none;border:none;cursor:pointer;color:var(--text3)"><span class="material-symbols-outlined">close</span></button>' +
      '</div>' +
      '<div style="font-size:12px;color:var(--text3);margin-bottom:16px">Node: <b>' + esc(node.name) + '</b> (' + esc(nodeId) + ')</div>' +
      '<div style="display:flex;flex-direction:column;gap:14px">' +
        '<div><label style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px">Target Agent</label>' +
          '<select id="pc-agent" style="width:100%;padding:10px 12px;border:1px solid var(--border-light);border-radius:8px;background:var(--bg);color:var(--text1);font-size:14px;margin-top:4px">' + agentOpts + '</select></div>' +
        '<div><label style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px">Model</label>' +
          '<input id="pc-model" style="width:100%;padding:10px 12px;border:1px solid var(--border-light);border-radius:8px;background:var(--bg);color:var(--text1);font-size:14px;margin-top:4px;box-sizing:border-box" placeholder="e.g. qwen3-235b-a22b"></div>' +
        '<div><label style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px">Provider</label>' +
          '<input id="pc-provider" style="width:100%;padding:10px 12px;border:1px solid var(--border-light);border-radius:8px;background:var(--bg);color:var(--text1);font-size:14px;margin-top:4px;box-sizing:border-box" placeholder="e.g. ollama, openai"></div>' +
        '<div><label style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px">Role</label>' +
          '<input id="pc-role" style="width:100%;padding:10px 12px;border:1px solid var(--border-light);border-radius:8px;background:var(--bg);color:var(--text1);font-size:14px;margin-top:4px;box-sizing:border-box" placeholder="e.g. coder, reviewer"></div>' +
        '<div><label style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px">System Prompt</label>' +
          '<textarea id="pc-sysprompt" rows="3" style="width:100%;padding:10px 12px;border:1px solid var(--border-light);border-radius:8px;background:var(--bg);color:var(--text1);font-size:13px;margin-top:4px;box-sizing:border-box;resize:vertical" placeholder="Optional system prompt override"></textarea></div>' +
        '<div><label style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px">Working Directory</label>' +
          '<input id="pc-workdir" style="width:100%;padding:10px 12px;border:1px solid var(--border-light);border-radius:8px;background:var(--bg);color:var(--text1);font-size:14px;margin-top:4px;box-sizing:border-box" placeholder="/path/to/project"></div>' +
        '<div><label style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px">Temperature</label>' +
          '<input id="pc-temp" type="number" step="0.1" min="0" max="2" style="width:100%;padding:10px 12px;border:1px solid var(--border-light);border-radius:8px;background:var(--bg);color:var(--text1);font-size:14px;margin-top:4px;box-sizing:border-box" placeholder="0.7"></div>' +
      '</div>' +
      '<div style="display:flex;gap:12px;justify-content:flex-end;margin-top:24px">' +
        '<button onclick="document.getElementById(\'config-modal\').remove()" style="padding:10px 20px;border:1px solid var(--border-light);border-radius:8px;background:none;color:var(--text2);font-size:13px;cursor:pointer">Cancel</button>' +
        '<button onclick="doPushConfig(\'' + esc(nodeId) + '\')" style="padding:10px 24px;border:none;border-radius:8px;background:var(--primary);color:#fff;font-size:13px;font-weight:700;cursor:pointer">Deploy Config</button>' +
      '</div>' +
      '<div id="pc-result" style="margin-top:16px;display:none"></div>' +
    '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
}

async function doPushConfig(nodeId) {
  var agentId = document.getElementById('pc-agent').value;
  if (!agentId) { alert('Please select an agent'); return; }
  var config = {};
  var model = document.getElementById('pc-model').value.trim();
  var provider = document.getElementById('pc-provider').value.trim();
  var role = document.getElementById('pc-role').value.trim();
  var sysprompt = document.getElementById('pc-sysprompt').value.trim();
  var workdir = document.getElementById('pc-workdir').value.trim();
  var temp = document.getElementById('pc-temp').value.trim();
  if (model) config.model = model;
  if (provider) config.provider = provider;
  if (role) config.role = role;
  if (sysprompt) config.system_prompt = sysprompt;
  if (workdir) config.working_dir = workdir;
  if (temp) config.profile = {temperature: parseFloat(temp)};
  config.partial = true;

  var resultDiv = document.getElementById('pc-result');
  resultDiv.style.display = 'block';
  resultDiv.innerHTML = '<div style="color:var(--text3);font-size:12px"><span class="material-symbols-outlined" style="font-size:14px;animation:spin 1s linear infinite">sync</span> Deploying...</div>';

  try {
    var res = await api('POST', '/api/hub/dispatch-config', {
      node_id: nodeId, agent_id: agentId, config: config
    });
    var statusColor = res.status === 'applied' ? 'var(--success)' : res.status === 'failed' ? 'var(--error)' : 'var(--warning)';
    var statusIcon = res.status === 'applied' ? 'check_circle' : res.status === 'failed' ? 'error' : 'schedule';
    resultDiv.innerHTML = '<div style="background:var(--bg);border-radius:8px;padding:12px;border:1px solid ' + statusColor + '">' +
      '<div style="display:flex;align-items:center;gap:8px;color:' + statusColor + ';font-weight:700;font-size:13px"><span class="material-symbols-outlined" style="font-size:18px">' + statusIcon + '</span>' + res.status.toUpperCase() + '</div>' +
      '<div style="font-size:11px;color:var(--text3);margin-top:4px">Deploy ID: ' + (res.deploy_id || '-') + (res.error ? ' · Error: ' + res.error : '') + '</div>' +
      (res.duration ? '<div style="font-size:11px;color:var(--text3)">Duration: ' + res.duration.toFixed(2) + 's</div>' : '') +
    '</div>';
    // Auto-refresh after successful apply
    if (res.status === 'applied') {
      setTimeout(function() { refresh(); }, 1000);
    }
  } catch(e) {
    resultDiv.innerHTML = '<div style="color:var(--error);font-size:12px">Error: ' + e.message + '</div>';
  }
}

async function loadNodeConfigStatus(nodeId) {
  var el = document.getElementById('node-config-' + nodeId);
  if (!el) return;
  // Toggle visibility
  if (el.style.display === 'block') { el.style.display = 'none'; return; }
  el.style.display = 'block';
  el.innerHTML = '<div style="color:var(--text3);font-size:12px">Loading config status...</div>';
  try {
    var data = await api('GET', '/api/portal/node/' + nodeId + '/config-status');
    if (data.total === 0) {
      el.innerHTML = '<div style="background:var(--bg);border-radius:8px;padding:10px 12px;font-size:12px;color:var(--text3)">No config deployments for this node.</div>';
      return;
    }
    var html = '<div style="background:var(--bg);border-radius:8px;padding:12px">' +
      '<div style="display:flex;gap:16px;margin-bottom:10px;font-size:11px">' +
        '<span style="color:var(--success);font-weight:700">' + data.applied + ' Applied</span>' +
        '<span style="color:var(--warning);font-weight:700">' + data.pending + ' Pending</span>' +
        '<span style="color:var(--error);font-weight:700">' + data.failed + ' Failed</span>' +
      '</div>' +
      '<div style="display:flex;flex-direction:column;gap:6px;max-height:200px;overflow:auto">';
    (data.deployments || []).slice(0, 10).forEach(function(d) {
      var sc = d.status === 'applied' ? 'var(--success)' : d.status === 'failed' ? 'var(--error)' : 'var(--warning)';
      var si = d.status === 'applied' ? 'check_circle' : d.status === 'failed' ? 'error' : 'schedule';
      html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:6px;background:var(--surface);font-size:11px">' +
        '<span class="material-symbols-outlined" style="font-size:14px;color:' + sc + '">' + si + '</span>' +
        '<span style="color:var(--text2);font-weight:600">' + esc(d.agent_id || '-').substr(0, 8) + '</span>' +
        '<span style="color:' + sc + ';font-weight:700">' + d.status + '</span>' +
        '<span style="color:var(--text3);margin-left:auto">' + new Date(d.created_at * 1000).toLocaleTimeString() + '</span>' +
        (d.error ? '<span style="color:var(--error)" title="' + esc(d.error) + '">⚠</span>' : '') +
      '</div>';
    });
    html += '</div></div>';
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div style="color:var(--error);font-size:12px">Error loading config status</div>';
  }
