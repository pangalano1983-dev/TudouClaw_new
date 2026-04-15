loadAvailableModels();

// ============ Agent management ============
function populateNodeSelect() {
  const sel = document.getElementById('ca-node');
  if (!sel) return;
  sel.innerHTML = '<option value="local">Local (this machine)</option>';
  nodes.filter(n => !n.is_self && n.status === 'online').forEach(n => {
    const opt = document.createElement('option');
    opt.value = n.node_id;
    opt.textContent = `${n.name} (${n.url})`;
    sel.appendChild(opt);
  });
