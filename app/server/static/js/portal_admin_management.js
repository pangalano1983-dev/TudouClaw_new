}

// ============ Admin Management Page ============
async function renderAdminManage() {
  var c = document.getElementById('content');
  if (!_adminCtx.is_super) {
    c.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text3)"><span class="material-symbols-outlined" style="font-size:48px;display:block;margin-bottom:12px">lock</span>Only Super Admin can access this page</div>';
    return;
  }

  c.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text3)">Loading...</div>';

  try {
    var data = await api('POST', '/api/portal/admins/list', {});
    var admins = (data && data.admins) ? data.admins : [];

    var html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">';
    html += '<div><h3 style="font-size:16px;font-weight:700;font-family:\'Plus Jakarta Sans\',sans-serif">Admin Accounts</h3>';
    html += '<p style="font-size:12px;color:var(--text3);margin-top:4px">Manage admin users and their agent access</p></div>';
    html += '<button class="btn btn-primary btn-sm" onclick="showCreateAdminModal()"><span class="material-symbols-outlined" style="font-size:16px">person_add</span> Add Admin</button>';
    html += '</div>';

    html += '<div style="display:grid;gap:12px">';
    admins.forEach(function(a) {
      var isSuper = a.role === 'superAdmin';
      var roleBadge = isSuper
        ? '<span style="padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;background:rgba(203,201,255,0.15);color:var(--primary)">Super Admin</span>'
        : '<span style="padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;background:rgba(63,185,80,0.15);color:var(--success)">Admin</span>';
      var statusDot = a.active !== false
        ? '<span style="width:8px;height:8px;border-radius:50%;background:#3fb950;display:inline-block"></span>'
        : '<span style="width:8px;height:8px;border-radius:50%;background:var(--text3);display:inline-block"></span>';

      var agentTags = '';
      if (isSuper) {
        agentTags = '<span style="font-size:11px;color:var(--text3)">All agents</span>';
      } else if (a.agent_ids && a.agent_ids.length > 0) {
        agentTags = a.agent_ids.map(function(aid) {
          var ag = agents.find(function(x){return x.id===aid;});
          var name = ag ? ag.name : aid.substring(0,8);
          return '<span style="padding:2px 6px;background:var(--surface3);border-radius:4px;font-size:10px;color:var(--text2)">'+esc(name)+'</span>';
        }).join(' ');
      } else {
        agentTags = '<span style="font-size:11px;color:var(--text3)">No agents assigned</span>';
      }

      html += '<div style="background:var(--surface);border-radius:10px;padding:16px;border:1px solid var(--border-light);display:flex;align-items:center;gap:14px">';
      html += '<div style="width:40px;height:40px;border-radius:10px;background:var(--surface3);display:flex;align-items:center;justify-content:center;flex-shrink:0"><span class="material-symbols-outlined" style="font-size:22px;color:'+(isSuper?'var(--primary)':'var(--success)')+'">'+( isSuper ? 'admin_panel_settings' : 'person')+'</span></div>';
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'+statusDot+' <span style="font-weight:700;font-size:14px">'+esc(a.display_name || a.username)+'</span> '+roleBadge+'</div>';
      html += '<div style="font-size:11px;color:var(--text3);margin-bottom:6px">@'+esc(a.username)+'</div>';
      html += '<div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center"><span class="material-symbols-outlined" style="font-size:14px;color:var(--text3)">smart_toy</span> '+agentTags+'</div>';
      html += '</div>';
      if (!isSuper) {
        html += '<div style="display:flex;gap:6px;flex-shrink:0">';
        html += '<button class="btn btn-ghost btn-sm" onclick="showEditAdminModal(\''+a.user_id+'\')"><span class="material-symbols-outlined" style="font-size:16px">edit</span></button>';
        html += '<button class="btn btn-ghost btn-sm" style="color:var(--error)" onclick="deleteAdminUser(\''+a.user_id+'\',\''+esc(a.username)+'\')"><span class="material-symbols-outlined" style="font-size:16px">delete</span></button>';
        html += '</div>';
      }
      html += '</div>';
    });
    html += '</div>';

    c.innerHTML = html;
  } catch(e) {
    c.innerHTML = '<div style="color:var(--error);padding:20px">Failed to load admins: '+e.message+'</div>';
  }
}

function _buildAgentCheckboxes(cssClass, checkedIds) {
  // Group agents by node
  var byNode = {};
  agents.forEach(function(a) {
    var nk = a.node_name || a.node_id || 'local';
    if (!byNode[nk]) byNode[nk] = [];
    byNode[nk].push(a);
  });
  var checked = checkedIds || [];
  var html = '';
  var nodeKeys = Object.keys(byNode);
  nodeKeys.forEach(function(nk) {
    if (nodeKeys.length > 1) {
      html += '<div style="font-size:10px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;padding:6px 0 2px;border-bottom:1px solid var(--border-light);margin-bottom:4px">Node: '+esc(nk)+'</div>';
    }
    byNode[nk].forEach(function(a) {
      var isChecked = checked.indexOf(a.id) >= 0 ? 'checked' : '';
      html += '<label style="display:flex;align-items:center;gap:8px;padding:6px 4px;cursor:pointer;border-radius:4px;transition:background 0.1s" onmouseenter="this.style.background=\'var(--surface2)\'" onmouseleave="this.style.background=\'none\'">' +
        '<input type="checkbox" value="'+a.id+'" class="'+cssClass+'" '+isChecked+' style="width:16px;height:16px;flex-shrink:0;accent-color:var(--primary)">' +
        '<span style="font-size:13px;color:var(--text)">'+esc(a.name)+'</span>' +
        '<span style="font-size:10px;color:var(--text3);margin-left:auto">('+esc(a.role||'general')+')</span>' +
      '</label>';
    });
  });
  return html || '<span style="color:var(--text3);font-size:12px">No agents available</span>';
}

function showCreateAdminModal() {
  var agentOpts = _buildAgentCheckboxes('new-admin-agent', []);

  var html = '<h3 style="margin-bottom:16px">Create Admin Account</h3>';
  html += '<div class="form-group"><label>Username</label><input id="new-admin-username" placeholder="e.g. zhangsan"></div>';
  html += '<div class="form-group"><label>Password</label><input id="new-admin-password" type="password" placeholder="At least 6 characters"></div>';
  html += '<div class="form-group"><label>Display Name</label><input id="new-admin-display" placeholder="e.g. 张三"></div>';
  html += '<div class="form-group"><label>Managed Agents</label><div style="max-height:240px;overflow-y:auto;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px">'+
    agentOpts +'</div></div>';
  html += '<div class="form-actions"><button class="btn btn-ghost" onclick="closeModal()">Cancel</button>';
  html += '<button class="btn btn-primary" onclick="createAdminUser()">Create</button></div>';
  showCustomModal(html);
}

async function createAdminUser() {
  var username = document.getElementById('new-admin-username').value.trim();
  var password = document.getElementById('new-admin-password').value.trim();
  var display_name = document.getElementById('new-admin-display').value.trim();
  if (!username || !password) { alert('Username and password are required'); return; }
  if (password.length < 6) { alert('Password must be at least 6 characters'); return; }
  var checkedAgents = [];
  document.querySelectorAll('.new-admin-agent:checked').forEach(function(cb) { checkedAgents.push(cb.value); });

  var data = await api('POST', '/api/portal/admins/create', {
    username: username, password: password, display_name: display_name || username, agent_ids: checkedAgents
  });
  if (data && data.ok) {
    closeModal();
    renderAdminManage();
  } else {
    alert((data && data.error) || 'Failed to create admin');
  }
}

function showEditAdminModal(userId) {
  api('POST', '/api/portal/admins/list', {}).then(function(data) {
    var admins = (data && data.admins) || [];
    var admin = admins.find(function(a) { return a.user_id === userId; });
    if (!admin) { alert('Admin not found'); return; }

    var agentOpts = _buildAgentCheckboxes('edit-admin-agent', admin.agent_ids || []);

    var html = '<h3 style="margin-bottom:16px">Edit Admin: '+esc(admin.username)+'</h3>';
    html += '<input type="hidden" id="edit-admin-uid" value="'+admin.user_id+'">';
    html += '<div class="form-group"><label>Display Name</label><input id="edit-admin-display" value="'+esc(admin.display_name||'')+'"></div>';
    html += '<div class="form-group"><label>New Password (leave empty to keep current)</label><input id="edit-admin-password" type="password" placeholder="Leave empty to keep"></div>';
    html += '<div class="form-group"><label>Managed Agents</label><div style="max-height:240px;overflow-y:auto;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px">'+
      agentOpts +'</div></div>';
    html += '<div class="form-actions"><button class="btn btn-ghost" onclick="closeModal()">Cancel</button>';
    html += '<button class="btn btn-primary" onclick="saveAdminEdit()">Save</button></div>';
    showCustomModal(html);
  });
}

async function saveAdminEdit() {
  var uid = document.getElementById('edit-admin-uid').value;
  var display_name = document.getElementById('edit-admin-display').value.trim();
  var password = document.getElementById('edit-admin-password').value.trim();
  var checkedAgents = [];
  document.querySelectorAll('.edit-admin-agent:checked').forEach(function(cb) { checkedAgents.push(cb.value); });

  var body = { user_id: uid, display_name: display_name, agent_ids: checkedAgents };
  if (password) body.password = password;

  var data = await api('POST', '/api/portal/admins/update', body);
  if (data && data.ok) {
    closeModal();
    renderAdminManage();
  } else {
    alert((data && data.error) || 'Failed to update admin');
  }
}

async function deleteAdminUser(userId, username) {
  if (!confirm('Delete admin "'+username+'"? This cannot be undone.')) return;
  var data = await api('POST', '/api/portal/admins/delete', { user_id: userId });
  if (data && data.ok) {
    renderAdminManage();
  } else {
    alert((data && data.error) || 'Failed to delete admin');
  }
}

function showCustomModal(html) {
  // Reuse generic modal approach
  var overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.id = 'custom-modal-overlay';
  overlay.onclick = function(e) { if (e.target === overlay) closeModal(); };
  var modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML = html;
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}

function closeCustomModal() {
  var el = document.getElementById('custom-modal-overlay');
  if (el) el.remove();
}

// Override closeModal to also close custom modals
var _origCloseModal = typeof closeModal === 'function' ? closeModal : function(){};
closeModal = function(id) {
  closeCustomModal();
  try { _origCloseModal(id); } catch(e){}
};
