// ============ State ============
let agents = [], nodes = [], messages = [], approvals = [], auditLog = [], tokens = [], providers = [], projects = [];
let currentView = 'dashboard';
let currentAgent = null;
let currentProject = null;
let _renderEpoch = 0; // Guard: incremented on every view change to prevent async overwrites
// Admin context
let _adminCtx = { user_id: '', username: '', role: '', display_name: '', agent_ids: [], is_super: false };
let _settingsSubTab = 'providers'; // Current sub-tab inside Settings view
let _agentsSubTab = null; // Current node tab inside Agents view (null = first node)
