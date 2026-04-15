}

// ============ Agent option helpers ============
function buildAgentOptions() {
  const selIds = ['ac-agent', 'ec-agent', 'del-from', 'del-to'];
  selIds.forEach(selId => {
    const sel = document.getElementById(selId);
    if (!sel) return;
    const curVal = sel.value;
    sel.innerHTML = '<option value="">(none)</option>';
    agents.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.id;
      opt.textContent = (a.role||'general') + '-' + a.name;
      if (curVal === a.id) opt.selected = true;
      sel.appendChild(opt);
    });
  });
