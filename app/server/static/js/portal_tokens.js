}

// ============ Tokens ============
function renderTokens(container) {
  const c = container || document.getElementById('content');
  c.innerHTML = `
    <div style="margin-bottom:20px">
      <button class="btn btn-primary" onclick="showModal('create-token')">+ Create Token</button>
    </div>
    <div id="tokens-list"></div>
  `;
  loadTokens();
}

async function loadTokens() {
  try {
    const data = await api('GET', '/api/auth/tokens');
    if (!data) return;
    tokens = data.tokens || [];
    const container = document.getElementById('tokens-list');
    if (!container) return;
    container.innerHTML = tokens.map(t => {
      const adminLabel = t.admin_user_id ?
        `<span class="tag tag-blue" style="margin-left:6px" title="Bound to admin: ${esc(t.admin_user_id)}">` +
        `<span class="material-symbols-outlined" style="font-size:12px;vertical-align:middle;margin-right:2px">person</span>` +
        `${esc(t.admin_display_name || t.admin_user_id)}</span>` :
        '<span class="tag" style="margin-left:6px;opacity:0.5">Unbound</span>';
      return `
      <div class="token-item">
        <div class="token-info">
          <div style="font-weight:600;margin-bottom:4px">${esc(t.name)} ${adminLabel}</div>
          <div class="token-id">ID: ${esc(t.token_id)}</div>
          <div style="font-size:11px;color:var(--text3);margin-top:4px">
            Role: ${esc(t.role)} · Created: ${new Date(t.created_at*1000).toLocaleDateString()} ·
            Last used: ${t.last_used ? new Date(t.last_used*1000).toLocaleDateString() : 'Never'} ·
            ${t.active ? '<span class="tag tag-green">Active</span>' : '<span class="tag tag-red">Revoked</span>'}
          </div>
        </div>
        <div class="token-actions">
          ${t.active ? '<button class="btn btn-sm btn-danger" onclick="revokeToken(\''+t.token_id+'\')">Revoke</button>' : ''}
        </div>
      </div>`;
    }).join('');
  } catch(e) {}
}

async function createToken() {
  const name = document.getElementById('ct-name').value.trim();
  const role = document.getElementById('ct-role').value;
  const adminBind = document.getElementById('ct-admin-bind').value;
  if (!name) { alert('Please enter a token name'); return; }

  try {
    const body = {name, role};
    if (adminBind) body.admin_user_id = adminBind;
    const data = await api('POST', '/api/auth/tokens', body);
    if (!data) return;
    document.getElementById('ct-form').classList.add('hidden');
    document.getElementById('ct-result').classList.remove('hidden');
    document.getElementById('ct-token-display').textContent = data.raw_token || data.token;
  } catch(e) {
    alert('Error creating token: ' + e.message);
  }
}

function copyToken() {
  const text = document.getElementById('ct-token-display').textContent;
  navigator.clipboard.writeText(text).then(() => alert('Token copied to clipboard'));
}

async function revokeToken(tokenId) {
  if (!confirm('Revoke this token?')) return;
  await api('DELETE', '/api/auth/tokens/' + tokenId);
  loadTokens();
