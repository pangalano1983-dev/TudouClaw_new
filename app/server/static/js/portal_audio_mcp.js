}

// ============ Audio MCP: TTS (Speaker) + STT (Microphone) ============
var _audioLastTs = 0;
var _audioPolling = false;
var _ttsEnabled = {};  // per agent TTS auto-read toggle
var _sttActive = {};   // per agent STT recording state

function _toggleTTS(agentId) {
  _ttsEnabled[agentId] = !_ttsEnabled[agentId];
  var btn = document.getElementById('tts-btn-' + agentId);
  if (!btn) return;
  var icon = btn.querySelector('.material-symbols-outlined');
  if (_ttsEnabled[agentId]) {
    icon.style.color = 'var(--primary)';
    icon.textContent = 'volume_up';
    btn.style.background = 'rgba(203,201,255,0.15)';
    btn.title = '自动朗读已开启 — 点击关闭';
  } else {
    icon.style.color = 'var(--text3)';
    icon.textContent = 'volume_off';
    btn.style.background = 'none';
    btn.title = '自动朗读开关 (Auto TTS)';
    if (window.speechSynthesis) speechSynthesis.cancel();
  }
}

function _autoSpeak(agentId, text) {
  // Called when agent finishes a reply — auto-speak if TTS toggle is on
  if (!_ttsEnabled[agentId]) return;
  if (!text || !text.trim()) return;
  if (!window.speechSynthesis) return;
  // Cancel any ongoing speech first
  speechSynthesis.cancel();
  var utt = new SpeechSynthesisUtterance(text);
  utt.lang = 'zh-CN';
  utt.rate = 1.0;
  speechSynthesis.speak(utt);
}

function _speakBubble(btnEl) {
  // Find the message text from the parent chat-msg element
  var msgEl = btnEl.closest('.chat-msg');
  if (!msgEl) return;
  var contentEl = msgEl.querySelector('.chat-msg-content');
  if (!contentEl) return;
  var text = contentEl._rawText || contentEl.textContent || '';
  if (!text.trim()) return;

  var icon = btnEl.querySelector('.material-symbols-outlined');
  if (!window.speechSynthesis) { alert('您的浏览器不支持语音合成 (TTS)'); return; }

  // If already speaking, stop
  if (speechSynthesis.speaking) {
    speechSynthesis.cancel();
    if (icon) { icon.style.color = ''; icon.textContent = 'volume_up'; }
    return;
  }

  var utt = new SpeechSynthesisUtterance(text);
  utt.lang = 'zh-CN';
  utt.rate = 1.0;
  if (icon) { icon.style.color = 'var(--primary)'; icon.textContent = 'stop_circle'; }
  utt.onend = function() {
    if (icon) { icon.style.color = ''; icon.textContent = 'volume_up'; }
  };
  utt.onerror = function() {
    if (icon) { icon.style.color = ''; icon.textContent = 'volume_up'; }
  };
  speechSynthesis.speak(utt);
}

function _toggleSTT(agentId) {
  if (_sttActive[agentId]) {
    // Stop recording
    if (_sttActive[agentId].recognition) {
      try { _sttActive[agentId].recognition.stop(); } catch(e) {}
    }
    _sttActive[agentId] = null;
    var btn = document.getElementById('stt-btn-' + agentId);
    if (btn) {
      var icon = btn.querySelector('.material-symbols-outlined');
      icon.style.color = 'var(--text3)';
      icon.textContent = 'mic';
      btn.style.background = 'none';
      btn.title = '语音输入 (STT Microphone)';
    }
    return;
  }
  // Start recording
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) { alert('您的浏览器不支持语音识别 (Speech Recognition)'); return; }
  var recognition = new SpeechRecognition();
  recognition.lang = 'zh-CN';
  recognition.continuous = true;
  recognition.interimResults = true;
  var inputEl = document.getElementById('chat-input-' + agentId);
  recognition.onresult = function(e) {
    var transcript = '';
    for (var i = 0; i < e.results.length; i++) {
      transcript += e.results[i][0].transcript;
    }
    if (inputEl) inputEl.value = transcript;
  };
  recognition.onerror = function(e) {
    console.warn('STT error:', e.error);
    _toggleSTT(agentId); // auto-stop on error
  };
  recognition.onend = function() {
    // Auto-restart if still active
    if (_sttActive[agentId]) {
      try { recognition.start(); } catch(e) { _toggleSTT(agentId); }
    }
  };
  recognition.start();
  _sttActive[agentId] = { recognition: recognition };
  var btn = document.getElementById('stt-btn-' + agentId);
  if (btn) {
    var icon = btn.querySelector('.material-symbols-outlined');
    icon.style.color = '#E91E63';
    icon.textContent = 'mic';
    btn.style.background = 'rgba(233,30,99,0.15)';
    btn.title = '正在录音 — 点击停止';
  }
}
var _sttRecognition = null;

var _audioFetching = false;  // Guard against overlapping audio poll requests
function _startAudioPolling() {
  if (_audioPolling) return;
  _audioPolling = true;
  setInterval(async function() {
    if (_audioFetching) return;  // Skip if previous poll still in-flight
    _audioFetching = true;
    try {
      var resp = await api('GET', '/api/portal/audio/events?since=' + _audioLastTs);
      if (!resp || !resp.events) { _audioFetching = false; return; }
      resp.events.forEach(function(evt) {
        _audioLastTs = Math.max(_audioLastTs, evt.ts || 0);
        if (evt.type === 'tts_speak') _handleTTS(evt);
        else if (evt.type === 'stt_listen') _handleSTTListen(evt);
        else if (evt.type === 'stt_start') _handleSTTStart(evt);
        else if (evt.type === 'stt_stop') _handleSTTStop();
      });
    } catch(e) {}
    _audioFetching = false;
  }, 2000);  // Poll every 2 seconds
}

function _handleTTS(evt) {
  if (!window.speechSynthesis) { console.warn('TTS not supported'); return; }
  var utterance = new SpeechSynthesisUtterance(evt.text);
  utterance.lang = evt.lang || 'zh-CN';
  utterance.rate = evt.rate || 1.0;
  if (evt.voice) {
    var voices = speechSynthesis.getVoices();
    var match = voices.find(function(v) { return v.name.includes(evt.voice); });
    if (match) utterance.voice = match;
  }
  // Show speaking indicator
  var bubble = document.getElementById('robot-bubble-' + evt.agent_id);
  if (bubble) { bubble.textContent = '🔊 Speaking...'; bubble.style.background = '#E91E63'; }
  utterance.onend = function() {
    if (bubble) { bubble.textContent = '工作中...'; bubble.style.background = 'var(--primary)'; }
  };
  speechSynthesis.speak(utterance);
}

function _handleSTTListen(evt) {
  if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
    console.warn('STT not supported'); return;
  }
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var recognition = new SpeechRecognition();
  recognition.lang = evt.lang || 'zh-CN';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onresult = function(e) {
    var transcript = e.results[0][0].transcript;
    if (transcript && evt.agent_id) {
      // Send recognized text as user message to the agent
      var input = document.getElementById('chat-input-' + evt.agent_id);
      if (input) { input.value = transcript; sendAgentMsg(evt.agent_id); }
    }
  };
  recognition.onerror = function(e) { console.warn('STT error:', e.error); };
  recognition.start();
  // Auto-stop after duration
  if (evt.duration) setTimeout(function() { try { recognition.stop(); } catch(e){} }, evt.duration * 1000);
}

function _handleSTTStart(evt) {
  if (_sttRecognition) { try { _sttRecognition.stop(); } catch(e){} }
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;
  _sttRecognition = new SpeechRecognition();
  _sttRecognition.lang = evt.lang || 'zh-CN';
  _sttRecognition.continuous = true;
  _sttRecognition.interimResults = false;
  _sttRecognition.onresult = function(e) {
    for (var i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) {
        var transcript = e.results[i][0].transcript;
        if (transcript && evt.agent_id) {
          var input = document.getElementById('chat-input-' + evt.agent_id);
          if (input) { input.value = transcript; sendAgentMsg(evt.agent_id); }
        }
      }
    }
  };
  _sttRecognition.start();
}

function _handleSTTStop() {
  if (_sttRecognition) { try { _sttRecognition.stop(); } catch(e){} _sttRecognition = null; }
