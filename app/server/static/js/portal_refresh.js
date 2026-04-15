}

// ============ Refresh ============
var portalMode = 'hub';  // 'hub' or 'node'
async function refresh() {
  try {
    var data = await api('GET', '/api/portal/state');
    if (!data) return;
    agents = data.agents || [];
    window._cachedAgents = agents;  // Cache for robot avatar lookups
    nodes = data.nodes || [];
    try { _refreshNodeSwitcher(); } catch(e) {}
    messages = data.messages || [];
    portalMode = data.portal_mode || 'hub';
    var rawApprovals = data.approvals || {};
    approvals = [].concat(rawApprovals.pending || []).concat(rawApprovals.history || []);

    // Load projects list
    try {
      var pData = await api('GET', '/api/portal/projects');
      if (pData) projects = pData.projects || [];
    } catch(e){}

    // Load admin context
    try {
      var meData = await api('GET', '/api/portal/admin/me');
      if (meData && meData.admin) {
        _adminCtx = {
          user_id: meData.admin.user_id || '',
          username: meData.admin.username || '',
          role: meData.admin.role || '',
          display_name: meData.admin.display_name || '',
          agent_ids: meData.admin.agent_ids || [],
          is_super: meData.admin.role === 'superAdmin',
        };
      } else {
        // Token-based login — treat as superAdmin
        _adminCtx = { user_id: '', username: 'admin', role: 'superAdmin', display_name: 'Admin', agent_ids: [], is_super: true };
      }
    } catch(e) {
      _adminCtx = { user_id: '', username: 'admin', role: 'superAdmin', display_name: 'Admin', agent_ids: [], is_super: true };
    }
    // Update sidebar footer with admin info
    var footerUser = document.getElementById('footer-username');
    var footerRole = document.getElementById('footer-role');
    if (footerUser) footerUser.textContent = _adminCtx.display_name || _adminCtx.username || 'admin';
    if (footerRole) { footerRole.textContent = _adminCtx.role || 'admin'; footerRole.style.background = _adminCtx.is_super ? 'rgba(203,201,255,0.15)' : 'rgba(63,185,80,0.15)'; footerRole.style.color = _adminCtx.is_super ? 'var(--primary)' : 'var(--success)'; }
    // Show/hide admin management nav
    var adminNav = document.getElementById('nav-admin-manage');
    if (adminNav) adminNav.style.display = _adminCtx.is_super ? '' : 'none';
    // Show change password button for logged-in admin users
    var changePwBtn = document.getElementById('btn-change-pw');
    if (changePwBtn) changePwBtn.style.display = _adminCtx.user_id ? '' : 'none';

    // Apply portal mode UI restrictions
    applyPortalModeRestrictions();

    // Update agent count badge in sidebar
    var agentBadge = document.getElementById('agent-count-badge');
    if (agentBadge) agentBadge.textContent = agents.length;

    var nodeCountEl = document.getElementById('node-count');
    if (nodeCountEl) nodeCountEl.textContent = nodes.length;
    var pendingApprovals = approvals.filter(function(a){ return a.status === 'pending'; }).length;
    var approvalBadge = document.getElementById('approval-badge');
    var globalNotif = document.getElementById('global-notif-badge');
    if (globalNotif) {
      if (pendingApprovals > 0) { globalNotif.textContent = pendingApprovals; globalNotif.classList.remove('hidden'); }
      else { globalNotif.classList.add('hidden'); }
    }
    if (approvalBadge) {
      if (pendingApprovals > 0) {
        approvalBadge.textContent = pendingApprovals;
        approvalBadge.classList.remove('hidden');
      } else {
        approvalBadge.classList.add('hidden');
      }
    }

    // Pending manual reviews → dashboard sidebar badge
    try {
      var prData = await api('GET', '/api/portal/pending-reviews');
      var prCount = prData ? (prData.count || 0) : 0;
      var dashBadge = document.getElementById('dashboard-badge');
      if (dashBadge) {
        if (prCount > 0) {
          dashBadge.textContent = prCount;
          dashBadge.classList.remove('hidden');
          dashBadge.title = prCount + ' step(s) waiting for manual review';
        } else {
          dashBadge.classList.add('hidden');
        }
      }
      window._pendingReviews = prData || { count: 0, items: [] };
    } catch(e) {}

    buildAgentOptions();
    populateNodeSelect();
    renderCurrentView();
  } catch(e) { console.error('refresh error', e); }
}

async function refreshSidebar() {
  // Lightweight refresh: update agent status in sidebar without re-rendering current view
  try {
    var data = await api('GET', '/api/portal/state');
    if (!data) return;
    agents = data.agents || [];
    nodes = data.nodes || [];
    try { _refreshNodeSwitcher(); } catch(e) {}
    messages = data.messages || [];
    var rawApprovals = data.approvals || {};
    approvals = [].concat(rawApprovals.pending || []).concat(rawApprovals.history || []);
    var agentBadge2 = document.getElementById('agent-count-badge');
    if (agentBadge2) agentBadge2.textContent = agents.length;
    var nodeCountEl2 = document.getElementById('node-count');
    if (nodeCountEl2) nodeCountEl2.textContent = nodes.length;
    var pendingApprovals = approvals.filter(function(a){ return a.status === 'pending'; }).length;
    var approvalBadge = document.getElementById('approval-badge');
    if (approvalBadge) {
      if (pendingApprovals > 0) { approvalBadge.textContent = pendingApprovals; approvalBadge.classList.remove('hidden'); }
      else { approvalBadge.classList.add('hidden'); }
    }
    buildAgentOptions();
    // Update project count and global projects list
    try {
      var pData = await api('GET', '/api/portal/projects');
      if (pData) projects = pData.projects || [];
      var projCount = document.getElementById('project-count');
      if (projCount && pData) projCount.textContent = projects.length;
    } catch(e){}
    // Update event log and task count (but NOT chat messages)
    if (currentAgent) {
      loadAgentEventLog(currentAgent);
    }
  } catch(e) {}
