}

// ============ Channels ============
let channelList = [];
const channelTypeLabels = {
  slack:'Slack', telegram:'Telegram', discord:'Discord',
  dingtalk:'DingTalk', feishu:'Feishu', webhook:'Webhook', wechat_work:'WeChat Work'
};
const channelTypeIcons = {
  slack:'💬', telegram:'✈️', discord:'🎮',
  dingtalk:'🔔', feishu:'🐦', webhook:'🌐', wechat_work:'💼'
};

function renderChannels(container) {
  const c = container || document.getElementById('content');
  if (!container) c.style.padding = '24px';
  const epoch = _renderEpoch;
  api('GET', '/api/portal/channels').then(data => {
    if (!data || epoch !== _renderEpoch) return;
    channelList = data.channels || [];
    var chCountEl = document.getElementById('channel-count');
    if (chCountEl) chCountEl.textContent = channelList.length;
    c.innerHTML = `
      <div style="display:flex;gap:24px">
        <div style="flex:1;max-width:700px">
          <h3 style="font-size:14px;margin-bottom:12px;color:var(--text2)">Configured Channels</h3>
          ${channelList.length===0?'<div style="color:var(--text3);padding:20px">No channels configured. Click "+ Add Channel" to connect a messaging platform.</div>':''}
          <div style="display:grid;gap:12px">
            ${channelList.map(ch => `
              <div class="card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start">
                  <div>
                    <div style="font-weight:600;font-size:15px">
                      ${channelTypeIcons[ch.channel_type]||'🔗'} ${esc(ch.name)}
                      <span class="tag ${ch.enabled?'tag-green':'tag-red'}" style="font-size:10px;margin-left:6px">${ch.enabled?'active':'disabled'}</span>
                      <span class="tag tag-blue" style="font-size:10px;margin-left:4px">${channelTypeLabels[ch.channel_type]||ch.channel_type}</span>
                      <span class="tag" style="font-size:10px;margin-left:4px;background:${ch.mode==='polling'?'rgba(251,191,36,0.15);color:#f59e0b':'rgba(96,165,250,0.15);color:#60a5fa'}">${ch.mode==='polling'?'Polling':'Webhook'}</span>
                    </div>
                    <div style="font-size:12px;color:var(--text3);margin-top:4px">
                      Agent: <strong>${esc(ch.agent_id ? (agents.find(a=>a.id===ch.agent_id)||{}).name || ch.agent_id : '(unbound)')}</strong>
                    </div>
                    ${ch.mode==='webhook' ? '<div style="font-size:12px;color:var(--text3);margin-top:2px">Webhook URL: <code style="font-size:11px;background:var(--surface2);padding:2px 6px;border-radius:4px">/api/portal/channels/'+ch.id+'/webhook</code></div>' : ''}
                    ${ch.webhook_url ? '<div style="font-size:12px;color:var(--text3);margin-top:2px">Outbound: '+esc(ch.webhook_url)+'</div>' : ''}
                  </div>
                </div>
                <div style="margin-top:10px;display:flex;gap:6px">
                  <button class="btn btn-sm btn-ghost" onclick="editChannel('${esc(ch.id)}')">Edit</button>
                  <button class="btn btn-sm btn-ghost" onclick="testChannel('${esc(ch.id)}')">Test</button>
                  <button class="btn btn-sm btn-danger" onclick="deleteChannel('${esc(ch.id)}')">Delete</button>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
        <div style="width:320px">
          <h3 style="font-size:14px;margin-bottom:12px;color:var(--text2)">Event Log</h3>
          <div id="channel-event-log" style="font-size:12px"></div>
        </div>
      </div>
    `;
    loadChannelEvents();
  });
}

async function loadChannelEvents() {
  const data = await api('GET', '/api/portal/channels/events');
  if (!data) return;
  const el = document.getElementById('channel-event-log');
  if (!el) return;
  const events = data.events || [];
  if (events.length === 0) {
    el.innerHTML = '<div style="color:var(--text3);padding:8px">No events yet</div>';
    return;
  }
  el.innerHTML = events.slice(-50).reverse().map(e => `
    <div style="padding:6px 0;border-bottom:1px solid var(--border)">
      <div style="display:flex;justify-content:space-between">
        <span style="color:${e.direction==='inbound'?'var(--accent)':'var(--green)'}">${e.direction==='inbound'?'⬇':'⬆'} ${esc(e.platform)}</span>
        <span style="color:var(--text3);font-size:11px">${new Date(e.timestamp*1000).toLocaleTimeString()}</span>
      </div>
      <div style="color:var(--text2);margin-top:2px">${esc(e.sender||'system')}: ${esc((e.text||'').slice(0,100))}</div>
      ${e.reply ? '<div style="color:var(--green);margin-top:2px">↳ '+esc(e.reply.slice(0,100))+'</div>' : ''}
    </div>
  `).join('');
}

async function addChannel() {
  const name = document.getElementById('ac-name').value.trim();
  const channel_type = document.getElementById('ac-type').value;
  const agent_id = document.getElementById('ac-agent').value;
  const mode = (document.getElementById('ac-mode') || {}).value || 'polling';
  const bot_token = document.getElementById('ac-token').value.trim();
  const signing_secret = document.getElementById('ac-secret').value.trim();
  const webhook_url = document.getElementById('ac-webhook').value.trim();
  const app_id = document.getElementById('ac-appid').value.trim();
  const app_secret = document.getElementById('ac-appsecret').value.trim();
  if (!name) { alert('Channel name is required'); return; }
  await api('POST', '/api/portal/channels', {
    name, channel_type, agent_id, mode, bot_token, signing_secret,
    webhook_url, app_id, app_secret
  });
  hideModal('add-channel');
  ['ac-name','ac-token','ac-secret','ac-webhook','ac-appid','ac-appsecret'].forEach(id => {
    const el = document.getElementById(id); if(el) el.value = '';
  });
  renderChannels();
}

function editChannel(id) {
  const ch = channelList.find(x => x.id === id);
  if (!ch) return;
  document.getElementById('ec-name').value = ch.name;
  document.getElementById('ec-type').value = ch.channel_type;
  document.getElementById('ec-agent').value = ch.agent_id || '';
  var modeEl = document.getElementById('ec-mode');
  if (modeEl) { modeEl.value = ch.mode || 'polling'; }
  var wgEl = document.getElementById('ec-webhook-group');
  if (wgEl) { wgEl.style.display = (ch.mode === 'webhook') ? '' : 'none'; }
  document.getElementById('ec-token').value = ch.bot_token || '';
  document.getElementById('ec-secret').value = ch.signing_secret || '';
  document.getElementById('ec-webhook').value = ch.webhook_url || '';
  document.getElementById('ec-appid').value = ch.app_id || '';
  document.getElementById('ec-appsecret').value = ch.app_secret || '';
  document.getElementById('ec-enabled').value = String(ch.enabled);
  window._editChannelId = id;
  showModal('edit-channel');
}

async function saveChannel() {
  const id = window._editChannelId;
  if (!id) return;
  const body = {
    name: document.getElementById('ec-name').value.trim(),
    channel_type: document.getElementById('ec-type').value,
    agent_id: document.getElementById('ec-agent').value,
    mode: (document.getElementById('ec-mode') || {}).value || 'polling',
    bot_token: document.getElementById('ec-token').value.trim(),
    signing_secret: document.getElementById('ec-secret').value.trim(),
    webhook_url: document.getElementById('ec-webhook').value.trim(),
    app_id: document.getElementById('ec-appid').value.trim(),
    app_secret: document.getElementById('ec-appsecret').value.trim(),
    enabled: document.getElementById('ec-enabled').value === 'true',
  };
  await api('POST', `/api/portal/channels/${id}/update`, body);
  hideModal('edit-channel');
  renderChannels();
}

async function deleteChannel(id) {
  if (!confirm('Delete this channel?')) return;
  await api('DELETE', `/api/portal/channels/${id}`);
  renderChannels();
}

async function testChannel(id) {
  // Show inline toast instead of alert
  var btn = event && event.target ? event.target : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Testing...'; }
  try {
    const data = await api('POST', `/api/portal/channels/${id}/test`);
    if (!data) return;
    var ok = data.success;
    var msg = ok ? (data.message || 'Connected!') : ('Failed: ' + (data.error || 'unknown'));
    if (ok && data.polling) msg += ' · Polling: ' + data.polling;
    // Find or create toast container near the card
    var card = btn ? btn.closest('.card') : null;
    var toast = document.createElement('div');
    toast.style.cssText = 'margin-top:8px;padding:8px 12px;border-radius:6px;font-size:12px;transition:opacity 0.3s;'
      + (ok ? 'background:rgba(16,185,129,0.12);color:#10b981;border:1px solid rgba(16,185,129,0.25)'
           : 'background:rgba(239,68,68,0.12);color:#ef4444;border:1px solid rgba(239,68,68,0.25)');
    toast.textContent = (ok ? '✓ ' : '✗ ') + msg;
    if (card) { card.appendChild(toast); } else { document.body.appendChild(toast); }
    setTimeout(function(){ toast.style.opacity = '0'; setTimeout(function(){ toast.remove(); }, 300); }, 5000);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Test'; }
  }
