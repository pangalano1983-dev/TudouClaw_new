}

// ============ Agent events log ============
async function loadAgentEvents(agentId) {
  try {
    const data = await api('GET', `/api/portal/agent/${agentId}/events`);
    if (!data) return;
    const c = document.getElementById('content');
    c.style.padding = '24px';
    c.innerHTML = `
      <button class="btn btn-ghost btn-sm" onclick="renderAgentChat('${agentId}')" style="margin-bottom:12px">← Back to Chat</button>
      <div class="event-log">
        ${(data.events||[]).map(e => `
          <div class="event-item">
            <span class="time">${new Date(e.timestamp*1000).toLocaleTimeString()}</span>
            <span class="kind ${e.kind}">${e.kind}</span>
            <span class="data">${esc(JSON.stringify(e.data).slice(0,200))}</span>
          </div>
        `).join('')}
      </div>
    `;
  } catch(e) {}
