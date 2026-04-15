}

// ============ Audit Log ============
function renderAudit() {
  const c = document.getElementById('content');
  c.innerHTML = `
    <div style="margin-bottom:12px">
      <select id="audit-filter" onchange="renderAudit()" style="padding:6px 10px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);color:var(--text)">
        <option value="">All Actions</option>
        <option value="login">Login</option>
        <option value="create_agent">Create Agent</option>
        <option value="chat">Chat</option>
        <option value="tool_call">Tool Call</option>
        <option value="approval">Approval</option>
      </select>
    </div>
    <table class="audit-table">
      <thead>
        <tr>
          <th>Timestamp</th>
          <th>Action</th>
          <th>Actor</th>
          <th>Role</th>
          <th>Target</th>
          <th>Details</th>
          <th>IP</th>
          <th>Result</th>
        </tr>
      </thead>
      <tbody>
        ${(auditLog||[]).slice().reverse().map(row => `
          <tr>
            <td>${new Date(row.timestamp*1000).toLocaleString()}</td>
            <td>${esc(row.action)}</td>
            <td>${esc(row.actor)}</td>
            <td>${esc(row.role)}</td>
            <td>${esc(row.target || '-')}</td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc((row.detail||'').slice(0,100))}</td>
            <td style="font-size:11px;color:var(--text3)">${esc(row.ip)}</td>
            <td><span class="tag ${row.success?'tag-green':'tag-red'}">${row.success?'OK':'Failed'}</span></td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
  loadAuditLog();
}

async function loadAuditLog() {
  try {
    const filterEl = document.getElementById('audit-filter');
    const filter = filterEl ? filterEl.value : '';
    const data = await api('GET', '/api/portal/audit' + (filter ? '?action=' + filter : ''));
    if (!data) return;
    auditLog = (data.entries || []).reverse();
    const tbody = document.querySelector('.audit-table tbody');
    if (!tbody) return;
    tbody.innerHTML = (auditLog||[]).map(row => `
      <tr>
        <td>${new Date(row.timestamp*1000).toLocaleString()}</td>
        <td>${esc(row.action)}</td>
        <td>${esc(row.actor)}</td>
        <td>${esc(row.role)}</td>
        <td>${esc(row.target || '-')}</td>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc((row.detail||'').slice(0,100))}</td>
        <td style="font-size:11px;color:var(--text3)">${esc(row.ip)}</td>
        <td><span class="tag ${row.success?'tag-green':'tag-red'}">${row.success?'OK':'Failed'}</span></td>
      </tr>
    `).join('');
  } catch(e) {}
