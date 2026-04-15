
// ============ Global soft toast (replaces alert) ============
(function() {
  var _origAlert = window.alert;
  window._toast = function(msg, type) {
    var old = document.getElementById('global-toast');
    if (old) old.remove();
    var isErr = type === 'err' || /失败|错误|error|fail|invalid/i.test(msg);
    var isOk = type === 'ok' || /成功|已|完成|saved|success|✓/i.test(msg);
    var bg = isErr ? '#ef4444' : isOk ? '#10b981' : '#60a5fa';
    var el = document.createElement('div');
    el.id = 'global-toast';
    el.style.cssText = 'position:fixed;top:24px;left:50%;transform:translateX(-50%);z-index:99999;'
      + 'padding:12px 28px;border-radius:8px;font-size:13px;color:#fff;background:' + bg + ';'
      + 'box-shadow:0 4px 16px rgba(0,0,0,.3);transition:opacity .4s;opacity:1;max-width:500px;text-align:center;'
      + 'white-space:pre-line;pointer-events:auto;cursor:pointer';
    el.textContent = msg;
    el.onclick = function() { el.remove(); };
    document.body.appendChild(el);
    setTimeout(function(){ el.style.opacity = '0'; }, 4000);
    setTimeout(function(){ el.remove(); }, 4500);
  };
  window.alert = function(msg) { window._toast(String(msg)); };
})();

// ============ API helper ============
async function api(method, url, body) {
  const opts = {method, credentials: 'same-origin', headers: {}};
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(url, opts);
  if (resp.status === 401) { window.location.href = '/'; return null; }
  if (resp.status === 204) return {};
  const ct = resp.headers.get('Content-Type') || '';
  const raw = await resp.text();
  let data = null;
  if (ct.indexOf('application/json') >= 0 || (raw && (raw[0] === '{' || raw[0] === '['))) {
    try { data = JSON.parse(raw); }
    catch(e) {
      const snippet = raw.slice(0, 200);
      throw new Error('HTTP '+resp.status+' — invalid JSON from '+url+': '+snippet);
    }
  } else {
    const snippet = (raw || '').slice(0, 200).replace(/\s+/g,' ');
    throw new Error('HTTP '+resp.status+' '+method+' '+url+' — non-JSON response: '+snippet);
  }
  if (!resp.ok) { console.error('API error', url, data); if (data && typeof data === 'object') return data; return {error: 'HTTP ' + resp.status}; }
  return data;
}

function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

/* Resolve agent ID → "role-name" display string; falls back to ID */
function agentName(id) {
  if (!id) return 'Unknown';
  var ag = (window._cachedAgents || agents || []).find(function(a){ return a.id === id; });
  return ag ? (ag.role + '-' + ag.name) : id;
}

function showModal(name) {
  document.getElementById('modal-'+name).classList.remove('hidden');
  if (name === 'create-agent') {
    try { loadPersonasForCreate(); } catch(e) { console.warn('loadPersonasForCreate failed', e); }
  }
}
function hideModal(name) {
  document.getElementById('modal-'+name).classList.add('hidden');
  if(name==='create-token'){
    document.getElementById('ct-form').classList.remove('hidden');
    document.getElementById('ct-result').classList.add('hidden');
    document.getElementById('ct-name').value = '';
    document.getElementById('ct-role').value = 'admin';
    document.getElementById('ct-admin-bind').disabled = false;
    // Populate admin binding dropdown
    var sel = document.getElementById('ct-admin-bind');
    sel.innerHTML = '<option value="">-- No binding (legacy) --</option>';
    if (_adminCtx.is_super) {
      api('POST', '/api/portal/admins/list', {}).then(function(data) {
        if (data && data.admins) {
          data.admins.forEach(function(a) {
            var opt = document.createElement('option');
            opt.value = a.user_id;
            opt.textContent = a.display_name + ' (' + a.role + ')';
            sel.appendChild(opt);
          });
        }
      });
    } else if (_adminCtx.user_id) {
      var opt = document.createElement('option');
      opt.value = _adminCtx.user_id;
      opt.textContent = _adminCtx.display_name + ' (' + _adminCtx.role + ')';
      opt.selected = true;
      sel.appendChild(opt);
      sel.disabled = true;
    }
  }
}

function showChangePasswordModal() {
  var html = '<h3 style="margin-bottom:16px">修改密码</h3>';
  html += '<div class="form-group"><label>当前密码</label><input id="cpw-old" type="password" placeholder="Enter current password"></div>';
  html += '<div class="form-group"><label>新密码</label><input id="cpw-new" type="password" placeholder="At least 6 characters"></div>';
  html += '<div class="form-group"><label>确认新密码</label><input id="cpw-confirm" type="password" placeholder="Repeat new password"></div>';
  html += '<div class="form-actions"><button class="btn btn-ghost" onclick="closeModal()">Cancel</button>';
  html += '<button class="btn btn-primary" onclick="submitChangePassword()">Save</button></div>';
  showCustomModal(html);
}
async function submitChangePassword() {
  var oldPw = document.getElementById('cpw-old').value;
  var newPw = document.getElementById('cpw-new').value;
  var confirmPw = document.getElementById('cpw-confirm').value;
  if (!oldPw || !newPw) { alert('请填写所有字段'); return; }
  if (newPw.length < 6) { alert('新密码至少6位'); return; }
  if (newPw !== confirmPw) { alert('两次密码不一致'); return; }
  var data = await api('POST', '/api/portal/admins/change-password', {
    user_id: _adminCtx.user_id, old_password: oldPw, new_password: newPw
  });
  if (data && data.ok) { closeModal(); alert('密码修改成功'); }
  else { alert((data && data.error) || '修改失败'); }
}

function logout() {
  // Call backend to clear HttpOnly cookie, then redirect
  fetch('/api/auth/logout', {method: 'POST', credentials: 'same-origin'})
    .finally(function() {
      // Also clear any non-HttpOnly remnants
      document.cookie = 'td_sess=; Path=/; SameSite=Lax; Expires=Thu, 01 Jan 1970 00:00:00 GMT';
      window.location.href = '/';
    });
}

function applyPortalModeRestrictions() {
  // In 'node' mode, hide admin-only sidebar items
  var isNode = portalMode === 'node';
  // Hide/disable Tokens menu (admin only)
  document.querySelectorAll('.nav-item[data-view="tokens"]').forEach(function(el) {
    el.style.display = isNode ? 'none' : '';
  });
  // Mark Settings as read-only in node mode (hide global config edit)
  var configNav = document.querySelector('.nav-item[data-view="config"]');
  if (configNav) {
    if (isNode) {
      configNav.innerHTML = configNav.innerHTML.replace('Settings', 'Settings <span style="font-size:9px;color:var(--text3)">(local)</span>');
    }
  }
  // In node mode, disable "Connect Node" button (can't manage remote nodes)
  if (isNode) {
    document.querySelectorAll('[onclick*="connectNode"]').forEach(function(el) {
      el.style.display = 'none';
    });
  }
  // Show mode indicator in header
  var header = document.querySelector('.portal-header') || document.querySelector('header');
  var modeTag = document.getElementById('portal-mode-tag');
  if (!modeTag && header) {
    modeTag = document.createElement('span');
    modeTag.id = 'portal-mode-tag';
    modeTag.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:4px;margin-left:8px;font-weight:600;';
    header.appendChild(modeTag);
  }
  if (modeTag) {
    if (isNode) {
      modeTag.textContent = 'NODE';
      modeTag.style.background = 'var(--warning)';
      modeTag.style.color = '#000';
    } else {
      modeTag.textContent = 'HUB';
      modeTag.style.background = 'var(--success)';
      modeTag.style.color = '#000';
    }
  }
