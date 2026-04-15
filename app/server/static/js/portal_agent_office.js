}

// ============ AI Agent Office ============
var _officeAnimFrame = null;
var _officeRobots = [];
var _officeCurrentNode = 'all';

// 像素机器人颜色方案
var _robotColors = {
  coder:    {body:'#4CAF50', eye:'#fff', accent:'#81C784'},
  pm:       {body:'#FF9800', eye:'#fff', accent:'#FFB74D'},
  architect:{body:'#2196F3', eye:'#fff', accent:'#64B5F6'},
  tester:   {body:'#9C27B0', eye:'#fff', accent:'#CE93D8'},
  devops:   {body:'#F44336', eye:'#fff', accent:'#E57373'},
  writer:   {body:'#00BCD4', eye:'#fff', accent:'#4DD0E1'},
  security: {body:'#607D8B', eye:'#fff', accent:'#90A4AE'},
  general:  {body:'#CBC1FF', eye:'#fff', accent:'#9B8FFF'},
  designer: {body:'#E91E63', eye:'#fff', accent:'#F48FB1'},
  hr:       {body:'#CDDC39', eye:'#fff', accent:'#DCE775'},
  marketing:{body:'#FF5722', eye:'#fff', accent:'#FF8A65'},
  data_analyst:{body:'#3F51B5', eye:'#fff', accent:'#7986CB'},
  support:  {body:'#009688', eye:'#fff', accent:'#4DB6AC'},
};

function _getRobotColor(role) {
  return _robotColors[role] || _robotColors['general'];
}

/* Resolve robot role key from agent profile — use robot_avatar config first */
function _resolveRobotRole(a) {
  // robot_avatar field: "robot_coder" → "coder", "robot_cto" → "cto"
  if (a.robot_avatar) {
    var r = a.robot_avatar.replace(/^robot_/, '');
    if (_robotColors[r]) return r;
  }
  // Fallback to agent role
  return a.role || 'general';
}

/* Generate a tiny pixel-robot avatar as a data-URL (32×36 canvas) */
function _miniRobotDataURL(role) {
  var c = document.createElement('canvas');
  c.width = 32; c.height = 36;
  var ctx = c.getContext('2d');
  var col = _getRobotColor(role);
  var s = 2, cx = 16, cy = 14;
  // head
  ctx.fillStyle = col.body;
  ctx.fillRect(cx-4*s, cy-5*s, 8*s, 7*s);
  // antenna
  ctx.fillStyle = col.accent;
  ctx.fillRect(cx-s, cy-7*s, 2*s, 2*s);
  // eyes
  ctx.fillStyle = col.eye;
  ctx.fillRect(cx+s, cy-3*s, 2*s, 2*s);
  ctx.fillRect(cx-3*s, cy-3*s, 2*s, 2*s);
  ctx.fillStyle = '#333';
  ctx.fillRect(cx+s, cy-3*s, s, 2*s);
  ctx.fillRect(cx-3*s, cy-3*s, s, 2*s);
  // mouth
  ctx.fillStyle = '#333';
  ctx.fillRect(cx-s, cy, 2*s, s);
  // body
  ctx.fillStyle = col.body;
  ctx.fillRect(cx-3*s, cy+2*s, 6*s, 6*s);
  // chest emblem
  ctx.fillStyle = col.accent;
  ctx.fillRect(cx-s, cy+3*s, 2*s, 2*s);
  // arms
  ctx.fillStyle = col.body;
  ctx.fillRect(cx-5*s, cy+3*s, 2*s, 3*s);
  ctx.fillRect(cx+3*s, cy+3*s, 2*s, 3*s);
  // legs
  ctx.fillStyle = col.accent;
  ctx.fillRect(cx-2*s, cy+8*s, 2*s, 2*s);
  ctx.fillRect(cx, cy+8*s, 2*s, 2*s);
  return c.toDataURL();
}

function renderMessages() {
  var c = document.getElementById('content');
  c.style.padding = '0';

  // 上下分栏：上=办公室场景，下=消息列表
  c.innerHTML = '' +
    '<div style="display:flex;flex-direction:column;height:100%;overflow:hidden">' +
      '<!-- 上半：办公室像素场景 -->' +
      '<div style="flex:0 0 320px;position:relative;background:#1a1a2e;border-bottom:3px solid var(--primary);overflow:hidden">' +
        '<canvas id="office-canvas" style="width:100%;height:100%;display:block"></canvas>' +
        '<!-- Node tabs bar -->' +
        '<div style="position:absolute;top:8px;left:16px;right:16px;display:flex;align-items:center;gap:6px;z-index:10">' +
          '<span class="material-symbols-outlined" style="font-size:18px;color:var(--primary)">apartment</span>' +
          '<span style="font-family:monospace;font-size:11px;color:var(--primary);font-weight:800">AI AGENT OFFICE</span>' +
          '<div id="office-node-tabs" style="display:flex;gap:4px;margin-left:12px"></div>' +
          '<span id="office-agent-count" style="font-size:10px;color:var(--text3);margin-left:auto;background:rgba(255,255,255,0.1);padding:2px 8px;border-radius:10px"></span>' +
        '</div>' +
      '</div>' +
      '<!-- 下半：消息列表 -->' +
      '<div style="flex:1;overflow-y:auto;padding:16px 20px;background:var(--bg)" id="office-messages">' +
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">' +
          '<span class="material-symbols-outlined" style="font-size:18px;color:var(--primary)">forum</span>' +
          '<span style="font-size:14px;font-weight:700">Agent Messages</span>' +
          '<span style="font-size:11px;color:var(--text3)" id="office-msg-count"></span>' +
        '</div>' +
        '<div id="office-msg-list" style="display:flex;flex-direction:column;gap:8px"></div>' +
      '</div>' +
    '</div>';

  _initOfficeScene();
  _renderOfficeMessages();
}

function _renderOfficeMessages() {
  var list = document.getElementById('office-msg-list');
  var countEl = document.getElementById('office-msg-count');
  if (!list) return;
  if (countEl) countEl.textContent = messages.length ? '(' + messages.length + ')' : '';

  if (messages.length === 0) {
    list.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text3);font-size:12px"><span class="material-symbols-outlined" style="font-size:32px;display:block;margin-bottom:8px;opacity:0.4">forum</span>暂无 Agent 间消息<br>当 Agent 之间互相通信时，消息将显示在这里</div>';
    return;
  }

  list.innerHTML = messages.slice().reverse().map(function(m) {
    var statusColor = m.status === 'completed' ? '#3fb950' : m.status === 'pending' ? '#f0883e' : 'var(--primary)';
    var statusIcon = m.status === 'completed' ? 'check_circle' : m.status === 'pending' ? 'schedule' : 'sync';
    var typeIcon = m.msg_type === 'task' ? 'assignment' : m.msg_type === 'response' ? 'reply' : 'chat';
    var fromName = m.from_agent_name || agentName(m.from_agent);
    var toName = m.to_agent_name || agentName(m.to_agent);
    return '<div style="background:var(--surface);border-radius:10px;padding:12px 14px;border:1px solid rgba(255,255,255,0.05);font-size:12px">' +
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">' +
        '<span class="material-symbols-outlined" style="font-size:14px;color:var(--primary)">' + typeIcon + '</span>' +
        '<span style="font-weight:700;color:var(--text)">' + esc(fromName) + '</span>' +
        '<span class="material-symbols-outlined" style="font-size:12px;color:var(--text3)">arrow_forward</span>' +
        '<span style="font-weight:700;color:var(--text)">' + esc(toName) + '</span>' +
        '<span style="margin-left:auto;font-size:10px;color:var(--text3)">' + new Date(m.timestamp * 1000).toLocaleTimeString() + '</span>' +
        '<span style="font-size:10px;color:' + statusColor + ';font-weight:700">' + esc(m.status) + '</span>' +
      '</div>' +
      '<div style="color:var(--text3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc((m.content || '').slice(0, 200)) + '</div>' +
    '</div>';
  }).join('');
}

// ── roundRect polyfill (Safari < 16, older browsers) ──
if (typeof CanvasRenderingContext2D !== 'undefined' &&
    !CanvasRenderingContext2D.prototype.roundRect) {
  CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {
    if (typeof r === 'number') r = [r, r, r, r];
    var tl = r[0] || 0, tr = r[1] || tl, br = r[2] || tl, bl = r[3] || tl;
    this.moveTo(x + tl, y);
    this.lineTo(x + w - tr, y);
    this.quadraticCurveTo(x + w, y, x + w, y + tr);
    this.lineTo(x + w, y + h - br);
    this.quadraticCurveTo(x + w, y + h, x + w - br, y + h);
    this.lineTo(x + bl, y + h);
    this.quadraticCurveTo(x, y + h, x, y + h - bl);
    this.lineTo(x, y + tl);
    this.quadraticCurveTo(x, y, x + tl, y);
    this.closePath();
    return this;
  };
}

// ── Node tabs rendering for office ──

function _renderNodeTabs() {
  var tabsEl = document.getElementById('office-node-tabs');
  if (!tabsEl) return;

  // Extract unique nodes from agents
  var nodeMap = {};
  agents.forEach(function(a) {
    var nid = a.node_id || 'local';
    if (!nodeMap[nid]) {
      nodeMap[nid] = {
        id: nid,
        name: nid === 'local' ? 'Local' : nid,
        count: 0,
        busy: 0
      };
    }
    nodeMap[nid].count++;
    if (a.status === 'busy') nodeMap[nid].busy++;
  });

  var nodes = Object.values(nodeMap).sort(function(a, b) {
    if (a.id === 'local') return -1;
    if (b.id === 'local') return 1;
    return a.id.localeCompare(b.id);
  });

  var html = '<div onclick="_switchOfficeNode(\'all\')" class="office-tab" ' +
    'style="cursor:pointer;padding:2px 8px;border-radius:8px;font-size:10px;' +
    (_officeCurrentNode === 'all' ? 'background:var(--primary);color:#fff' : 'background:rgba(255,255,255,0.08);color:var(--text3)') + '">' +
    'All (' + agents.length + ')</div>';

  nodes.forEach(function(n) {
    var isActive = _officeCurrentNode === n.node_id;
    var statusDot = '🟢';
    html += '<div onclick="_switchOfficeNode(\'' + esc(n.node_id) + '\')" class="office-tab" ' +
      'style="cursor:pointer;padding:2px 8px;border-radius:8px;font-size:10px;' +
      (isActive ? 'background:var(--primary);color:#fff' : 'background:rgba(255,255,255,0.08);color:var(--text3)') + '">' +
      statusDot + ' ' + esc(n.name) + ' (' + n.count + ')</div>';
  });

  tabsEl.innerHTML = html;
}

function _switchOfficeNode(nodeId) {
  _officeCurrentNode = nodeId;
  _initOfficeScene();
  _renderNodeTabs();
}

// ── 像素办公室场景 Canvas 引擎 ──

function _initOfficeScene() {
  var canvas = document.getElementById('office-canvas');
  if (!canvas) return;
  var parent = canvas.parentElement;
  var dpr = window.devicePixelRatio || 1;
  canvas.width = parent.clientWidth * dpr;
  canvas.height = parent.clientHeight * dpr;
  var ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  var W = parent.clientWidth;
  var H = parent.clientHeight;

  // Filter agents by current node selection
  var filteredAgents = _officeCurrentNode === 'all' ?
    agents :
    agents.filter(function(a) { return (a.node_id || 'local') === _officeCurrentNode; });

  // Render node tabs
  _renderNodeTabs();

  // 生成办公桌位置（最多 8 张桌子）
  var deskCount = Math.min(filteredAgents.length, 8);
  var deskSpacing = W / (deskCount + 1);
  var deskY = H * 0.42; // 桌子 Y 位置
  var floorY = H * 0.75; // 地板走动 Y 位置

  // 初始化机器人状态
  _officeRobots = filteredAgents.slice(0, 12).map(function(a, i) {
    var deskIdx = i < deskCount ? i : -1;
    var robotRole = _resolveRobotRole(a);
    var col = _getRobotColor(robotRole);
    // Detect learning state from self_improvement stats
    var si = a.self_improvement || {};
    var isLearning = si.is_learning || false;
    var isBusyOrLearning = a.status === 'busy' || isLearning;
    // Determine bubble text
    var bubble = '';
    if (a.status === 'busy') bubble = '工作中...';
    else if (isLearning) bubble = '📖 学习中...';
    else if (si.learning_queue_count > 0) bubble = '📋 待学习: ' + si.learning_queue_count;
    return {
      id: a.id,
      name: a.name || 'Agent',
      role: robotRole,
      status: a.status || 'idle',
      isLearning: isLearning,
      color: col,
      // 桌子位置
      deskX: deskIdx >= 0 ? deskSpacing * (deskIdx + 1) : 0,
      deskY: deskY,
      // 当前位置（动画用）
      x: deskIdx >= 0 ? deskSpacing * (deskIdx + 1) : 60 + Math.random() * (W - 120),
      y: isBusyOrLearning ? deskY - 16 : floorY,
      // 走路方向和速度
      vx: (Math.random() > 0.5 ? 1 : -1) * (0.3 + Math.random() * 0.5),
      walkFrame: Math.floor(Math.random() * 4),
      walkTimer: 0,
      // 气泡
      bubbleText: bubble,
      bubbleTimer: 0,
      facingRight: Math.random() > 0.5,
    };
  });

  var agentCountEl = document.getElementById('office-agent-count');
  if (agentCountEl) {
    var busyCount = filteredAgents.filter(function(a){return a.status==='busy'}).length;
    agentCountEl.textContent = filteredAgents.length + ' agents · ' + busyCount + ' working';
  }

  // 动画循环
  if (_officeAnimFrame) cancelAnimationFrame(_officeAnimFrame);

  function animate() {
    // 检查是否还在当前视图
    if (!document.getElementById('office-canvas')) {
      _officeAnimFrame = null;
      return;
    }

    ctx.clearRect(0, 0, W, H);

    // ── 背景：夜间办公室 ──
    // 天花板
    ctx.fillStyle = '#12122a';
    ctx.fillRect(0, 0, W, 30);

    // 墙壁
    var wallGrad = ctx.createLinearGradient(0, 30, 0, H * 0.65);
    wallGrad.addColorStop(0, '#1a1a3e');
    wallGrad.addColorStop(1, '#16213e');
    ctx.fillStyle = wallGrad;
    ctx.fillRect(0, 30, W, H * 0.65 - 30);

    // 窗户（像素风格）
    var winCount = Math.floor(W / 200);
    for (var wi = 0; wi < winCount; wi++) {
      var wx = 100 + wi * 200;
      // 窗框
      ctx.fillStyle = '#2a2a5a';
      ctx.fillRect(wx - 32, 50, 64, 50);
      // 窗户玻璃（蓝紫色夜空）
      ctx.fillStyle = '#1e3a5f';
      ctx.fillRect(wx - 28, 54, 25, 42);
      ctx.fillRect(wx + 3, 54, 25, 42);
      // 星星
      ctx.fillStyle = '#fff';
      ctx.fillRect(wx - 20, 60, 2, 2);
      ctx.fillRect(wx + 10, 68, 2, 2);
      ctx.fillRect(wx - 10, 75, 2, 2);
    }

    // 地板
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, H * 0.65, W, H * 0.35);
    // 地板网格线
    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    ctx.lineWidth = 1;
    for (var gy = H * 0.65; gy < H; gy += 20) {
      ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke();
    }

    // ── 绘制办公桌 ──
    for (var di = 0; di < deskCount; di++) {
      var dx = deskSpacing * (di + 1);
      var dy = deskY;
      // 桌面
      ctx.fillStyle = '#3d2b1f';
      ctx.fillRect(dx - 28, dy + 10, 56, 8);
      // 桌腿
      ctx.fillStyle = '#2a1f15';
      ctx.fillRect(dx - 24, dy + 18, 4, 22);
      ctx.fillRect(dx + 20, dy + 18, 4, 22);
      // 电脑显示器
      ctx.fillStyle = '#333';
      ctx.fillRect(dx - 12, dy - 14, 24, 20);
      // 屏幕（蓝光 = 有人在用，灰色 = 空闲）
      var deskRobot = _officeRobots.find(function(r){return r.status === 'busy' && r.deskX === dx;});
      ctx.fillStyle = deskRobot ? '#4a90d9' : '#222';
      ctx.fillRect(dx - 10, dy - 12, 20, 16);
      // 显示器支架
      ctx.fillStyle = '#555';
      ctx.fillRect(dx - 2, dy + 6, 4, 4);
      // 键盘
      ctx.fillStyle = '#444';
      ctx.fillRect(dx - 10, dy + 12, 20, 4);
    }

    // ── 更新和绘制机器人 ──
    _officeRobots.forEach(function(r) {
      // 从 agents 数据同步状态
      var agentData = agents.find(function(a){return a.id === r.id;});
      if (agentData) {
        r.status = agentData.status || 'idle';
        // Sync learning state
        var si = agentData.self_improvement || {};
        r.isLearning = si.is_learning || false;
        // Update color from profile (in case avatar changed)
        var robotRole = _resolveRobotRole(agentData);
        r.role = robotRole;
        r.color = _getRobotColor(robotRole);
      }

      var isBusyOrLearning = r.status === 'busy' || r.isLearning;

      if (isBusyOrLearning) {
        // BUSY or LEARNING: 坐在桌子前
        if (r.deskX > 0) {
          r.x += (r.deskX - r.x) * 0.08;
          r.y += ((r.deskY - 16) - r.y) * 0.08;
        }
        if (r.status === 'busy') {
          r.bubbleText = '工作中...';
        } else if (r.isLearning) {
          r.bubbleText = '📖 学习中...';
        }
      } else {
        // IDLE: 在地板上来回走
        r.y += (floorY - r.y) * 0.05;
        r.x += r.vx;
        r.facingRight = r.vx > 0;
        // 碰到边界反弹
        if (r.x < 30 || r.x > W - 30) {
          r.vx = -r.vx;
          r.facingRight = r.vx > 0;
        }
        // 随机转向
        if (Math.random() < 0.003) r.vx = -r.vx;
        // Show queued learning count if any
        var si2 = agentData ? (agentData.self_improvement || {}) : {};
        if (si2.learning_queue_count > 0) {
          r.bubbleText = '📋 待学习';
        } else {
          r.bubbleText = '';
        }
      }

      // 走路动画帧
      r.walkTimer++;
      if (r.walkTimer > 10) {
        r.walkTimer = 0;
        r.walkFrame = (r.walkFrame + 1) % 4;
      }

      _drawPixelRobot(ctx, r);
    });

    _officeAnimFrame = requestAnimationFrame(animate);
  }

  animate();
}

function _drawPixelRobot(ctx, r) {
  var x = Math.round(r.x);
  var y = Math.round(r.y);
  var s = 3; // 像素尺寸
  var col = r.color;
  var isBusy = r.status === 'busy' || r.isLearning;
  var frame = r.walkFrame;

  ctx.save();

  // ── 气泡（工作中/学习中...）──
  if (r.bubbleText) {
    ctx.font = '10px "Plus Jakarta Sans", sans-serif';
    var tw = ctx.measureText(r.bubbleText).width;
    var bx = x - tw / 2 - 6;
    var by = y - 36;
    // 气泡背景 — 学习用绿色底，工作用深色底
    var bubbleBg = r.isLearning ? 'rgba(76,175,80,0.85)' : 'rgba(0,0,0,0.7)';
    ctx.fillStyle = bubbleBg;
    ctx.beginPath();
    ctx.roundRect(bx, by, tw + 12, 18, 4);
    ctx.fill();
    // 气泡文字 — 学习用白色，工作用金色
    ctx.fillStyle = r.isLearning ? '#fff' : '#FFD700';
    ctx.fillText(r.bubbleText, bx + 6, by + 13);
    // 小三角
    ctx.fillStyle = bubbleBg;
    ctx.beginPath();
    ctx.moveTo(x - 3, by + 18);
    ctx.lineTo(x + 3, by + 18);
    ctx.lineTo(x, by + 23);
    ctx.fill();
  }

  // ── 头部 ──
  ctx.fillStyle = col.body;
  ctx.fillRect(x - 4*s, y - 5*s, 8*s, 7*s);

  // 天线
  ctx.fillStyle = col.accent;
  ctx.fillRect(x - s, y - 7*s, 2*s, 2*s);
  // 天线灯（busy 时闪烁）
  if (isBusy && Math.floor(Date.now() / 400) % 2 === 0) {
    ctx.fillStyle = '#FF0';
    ctx.fillRect(x - s, y - 8*s, 2*s, s);
  }

  // 眼睛
  ctx.fillStyle = col.eye;
  if (r.facingRight) {
    ctx.fillRect(x + s, y - 3*s, 2*s, 2*s);
    ctx.fillRect(x - 2*s, y - 3*s, 2*s, 2*s);
    // 瞳孔
    ctx.fillStyle = '#333';
    ctx.fillRect(x + 2*s, y - 3*s, s, 2*s);
    ctx.fillRect(x - s, y - 3*s, s, 2*s);
  } else {
    ctx.fillRect(x + s, y - 3*s, 2*s, 2*s);
    ctx.fillRect(x - 3*s, y - 3*s, 2*s, 2*s);
    ctx.fillStyle = '#333';
    ctx.fillRect(x + s, y - 3*s, s, 2*s);
    ctx.fillRect(x - 3*s, y - 3*s, s, 2*s);
  }

  // 嘴巴
  ctx.fillStyle = '#333';
  ctx.fillRect(x - s, y, 2*s, s);

  // ── 身体 ──
  ctx.fillStyle = col.body;
  ctx.fillRect(x - 3*s, y + 2*s, 6*s, 6*s);

  // 胸前标志
  ctx.fillStyle = col.accent;
  ctx.fillRect(x - s, y + 3*s, 2*s, 2*s);

  // ── 手臂 ──
  if (isBusy) {
    // busy: 手臂伸向前方（敲键盘）
    var armBob = Math.floor(Date.now() / 200) % 2;
    ctx.fillStyle = col.body;
    ctx.fillRect(x - 5*s, y + 3*s, 2*s, 3*s + armBob*s);
    ctx.fillRect(x + 3*s, y + 3*s, 2*s, 3*s + (1-armBob)*s);
  } else {
    // idle: 手臂随走路摆动
    var armSwing = (frame % 2 === 0) ? 1 : -1;
    ctx.fillStyle = col.body;
    ctx.fillRect(x - 5*s, y + (3 + armSwing)*s, 2*s, 3*s);
    ctx.fillRect(x + 3*s, y + (3 - armSwing)*s, 2*s, 3*s);
  }

  // ── 腿 ──
  ctx.fillStyle = col.accent;
  if (isBusy) {
    // 坐着
    ctx.fillRect(x - 2*s, y + 8*s, 2*s, 2*s);
    ctx.fillRect(x, y + 8*s, 2*s, 2*s);
  } else {
    // 走路
    var legOffset = (frame < 2) ? 1 : -1;
    ctx.fillRect(x - 2*s, y + 8*s + legOffset*s, 2*s, 3*s);
    ctx.fillRect(x, y + 8*s - legOffset*s, 2*s, 3*s);
  }

  // ── 名牌 ──
  ctx.font = 'bold 9px "Plus Jakarta Sans", sans-serif';
  var nameW = ctx.measureText(r.name).width;
  ctx.fillStyle = 'rgba(0,0,0,0.6)';
  ctx.beginPath();
  ctx.roundRect(x - nameW/2 - 4, y + 12*s, nameW + 8, 14, 3);
  ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.fillText(r.name, x - nameW/2, y + 12*s + 10);

  ctx.restore();
