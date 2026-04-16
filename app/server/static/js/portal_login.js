function switchLoginTab(tab) {
  document.getElementById('form-admin').style.display = tab==='admin' ? 'block' : 'none';
  document.getElementById('form-token').style.display = tab==='token' ? 'block' : 'none';
  document.getElementById('tab-admin').style.borderBottomColor = tab==='admin' ? 'var(--primary)' : 'transparent';
  document.getElementById('tab-admin').style.color = tab==='admin' ? 'var(--primary)' : 'var(--text3)';
  document.getElementById('tab-token').style.borderBottomColor = tab==='token' ? 'var(--primary)' : 'transparent';
  document.getElementById('tab-token').style.color = tab==='token' ? 'var(--primary)' : 'var(--text3)';
  document.getElementById('error-msg').classList.add('hidden');
}
function showTokenHelp() {
  var h = document.getElementById('token-help');
  h.style.display = 'flex';
}
async function resetToken() {
  if(!confirm('确定要重置 Admin Token 吗？旧 token 将继续有效，同时会生成一个新的。')) return;
  try {
    var resp = await fetch('/api/auth/reset-token', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    var data = await resp.json();
    if(data.token) {
      document.getElementById('api-token').value = data.token;
      document.getElementById('token-help').style.display = 'none';
      var errEl = document.getElementById('error-msg');
      errEl.classList.remove('hidden');
      errEl.style.background = 'rgba(63,185,80,0.1)';
      errEl.style.borderColor = 'rgba(63,185,80,0.3)';
      errEl.style.color = '#3fb950';
      errEl.textContent = '新 Token 已生成并填入，请点击 Sign In 登录';
    }
  } catch(e) { alert('Reset failed: ' + e.message); }
}
async function loginAdmin() {
  var username = document.getElementById('admin-username').value.trim();
  var password = document.getElementById('admin-password').value.trim();
  var errEl = document.getElementById('error-msg');
  if(!username || !password) {
    errEl.classList.remove('hidden');
    errEl.style.background = ''; errEl.style.borderColor = ''; errEl.style.color = '';
    errEl.textContent = '请输入用户名和密码';
    return;
  }
  errEl.classList.add('hidden');
  try {
    var resp = await fetch('/api/auth/login', {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: username, password: password})
    });
    var data = await resp.json();
    if(!resp.ok) {
      errEl.classList.remove('hidden');
      errEl.style.background = ''; errEl.style.borderColor = ''; errEl.style.color = '';
      errEl.textContent = data.detail || data.error || '登录失败';
    } else {
      if(data.session_id) {
        var securePart = location.protocol === 'https:' ? '; Secure' : '';
        document.cookie = 'td_sess=' + data.session_id + '; path=/; SameSite=Lax; max-age=86400' + securePart;
      }
      window.location.href = '/';
    }
  } catch(e) {
    errEl.classList.remove('hidden');
    errEl.textContent = '网络错误: ' + e.message;
  }
}
async function login() {
  var token = document.getElementById('api-token').value.trim();
  var errEl = document.getElementById('error-msg');
  var btn = document.querySelector('#form-token .btn-primary');
  if(!token) {
    errEl.classList.remove('hidden');
    errEl.textContent = 'Please enter your API token';
    return;
  }
  errEl.classList.add('hidden');
  btn.classList.add('loading');
  btn.textContent = 'Signing in...';
  try {
    var resp = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token: token})
    });
    var data = await resp.json();
    if(!resp.ok) {
      errEl.classList.remove('hidden');
      errEl.textContent = data.detail || data.error || 'Login failed (status ' + resp.status + ')';
    } else {
      if(data.session_id) {
        var securePart = location.protocol === 'https:' ? '; Secure' : '';
        document.cookie = 'td_sess=' + data.session_id + '; path=/; SameSite=Lax; max-age=86400' + securePart;
      }
      window.location.href = '/';
      return;
    }
  } catch(e) {
    errEl.classList.remove('hidden');
    errEl.textContent = 'Network error: ' + e.message;
  }
  btn.classList.remove('loading');
  btn.textContent = 'Sign In';
}
