/**
 * ==============================================================================
 * PROJECT EZRA // HOLOGRAPHIC JARVIS CLIENT CONTROLLER
 * Manages WebSocket telemetry, audio visualizer, chat stream, and quick actions.
 * ==============================================================================
 */

class EzraClientController {
  constructor() {
    this.ws = null;
    this.isMuted = false;
    this.isRobotic = false;
    this.isSleeping = false;
    this.isMicActive = false;
    this.audioContext = null;
    this.analyser = null;
    this.microphone = null;
    this.audioData = new Uint8Array(64);

    this.waveformCanvas = document.getElementById('waveformCanvas');
    this.waveformCtx = this.waveformCanvas ? this.waveformCanvas.getContext('2d') : null;

    this.initClock();
    this.initWebSocket();
    this.initKeyboardShortcuts();
    this.initWaveform();
  }

  initClock() {
    const clockEl = document.getElementById('hudClock');
    const updateTime = () => {
      const now = new Date();
      const h = String(now.getHours()).padStart(2, '0');
      const m = String(now.getMinutes()).padStart(2, '0');
      const s = String(now.getSeconds()).padStart(2, '0');
      if (clockEl) clockEl.textContent = `${h}:${m}:${s}`;
    };
    updateTime();
    setInterval(updateTime, 1000);
  }

  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('[Ezra WS] Connected to Neural Core.');
      this.appendChatMsg('system', 'Neural Link established. Connected to local JARVIS daemon.');
      // Fetch initial status
      this.sendMessage({ type: 'get_status' });
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleServerMessage(data);
      } catch (err) {
        console.error('[Ezra WS] Parse error:', err);
      }
    };

    this.ws.onclose = () => {
      console.warn('[Ezra WS] Connection closed. Reconnecting in 2s...');
      setTimeout(() => this.initWebSocket(), 2000);
    };

    this.ws.onerror = (err) => {
      console.error('[Ezra WS] Error:', err);
    };
  }

  sendMessage(msg) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  handleServerMessage(data) {
    switch (data.type) {
      case 'telemetry':
        this.updateTelemetry(data);
        break;

      case 'state_change':
        this.updateState(data.state, data.detail);
        break;

      case 'speech':
        this.updateSubtitles(data.speaker || 'EZRA', data.text);
        if (data.speaker === 'EZRA') {
          this.appendChatMsg('ezra', data.text);
        }
        break;

      case 'live_stt':
        const lp = document.getElementById('livePreviewText');
        if (lp) lp.textContent = data.text || 'Listening...';
        break;

      case 'memories':
        this.updateMemories(data.items);
        break;

      case 'audio_level':
        if (window.ezraBrain) {
          window.ezraBrain.setAudioLevel(data.level || 0);
        }
        break;

      default:
        break;
    }
  }

  updateTelemetry(data) {
    // 1. CPU Gauge (stroke-dashoffset: 264 max -> 0 full)
    const cpuVal = document.getElementById('cpuVal');
    const cpuBar = document.getElementById('cpuBar');
    if (cpuVal && cpuBar) {
      const cpu = Math.round(data.cpu || 0);
      cpuVal.textContent = `${cpu}%`;
      const offset = 264 - (264 * cpu) / 100;
      cpuBar.style.strokeDashoffset = offset;
    }

    // 2. RAM Gauge
    const ramVal = document.getElementById('ramVal');
    const ramBar = document.getElementById('ramBar');
    if (ramVal && ramBar) {
      const ram = Math.round(data.ram || 0);
      ramVal.textContent = `${ram}%`;
      const offset = 264 - (264 * ram) / 100;
      ramBar.style.strokeDashoffset = offset;
    }

    // 3. Lines
    const uptimeVal = document.getElementById('uptimeVal');
    if (uptimeVal && data.uptime) uptimeVal.textContent = data.uptime;

    const diskVal = document.getElementById('diskVal');
    if (diskVal && data.disk) diskVal.textContent = `${data.disk}%`;

    const lidVal = document.getElementById('lidVal');
    if (lidVal && data.lid_status) lidVal.textContent = data.lid_status.toUpperCase();

    const distroName = document.getElementById('distroName');
    if (distroName && data.distro) distroName.textContent = data.distro.toUpperCase();

    const dwellVal = document.getElementById('dwellVal');
    if (dwellVal && data.dwell_sec !== undefined) {
      dwellVal.textContent = `${Number(data.dwell_sec).toFixed(1)}s`;
    }

    const bioUser = document.getElementById('bioUser');
    if (bioUser && data.user_name) {
      bioUser.textContent = `${data.user_name.toUpperCase()} // ${data.tier ? data.tier.toUpperCase() : 'VERIFIED'}`;
    }

    const activeEngine = document.getElementById('activeEngine');
    if (activeEngine && data.engine) {
      activeEngine.textContent = data.engine.toUpperCase();
    }

    // Hex stream randomizer for sci-fi atmosphere
    const hexL = document.getElementById('hexStreamL');
    if (hexL) {
      hexL.textContent = `0x${Math.floor(Math.random()*16777215).toString(16).toUpperCase().padStart(6,'0')}`;
    }
  }

  updateState(state, detail) {
    if (window.ezraBrain) {
      window.ezraBrain.setState(state);
    }
    const micBtn = document.getElementById('micBtn');
    if (micBtn) {
      if (state === 'listening') micBtn.classList.add('active');
      else micBtn.classList.remove('active');
    }
  }

  updateSubtitles(speaker, text) {
    const subTag = document.getElementById('subTag');
    const subContent = document.getElementById('subContent');
    const subTime = document.getElementById('subTime');

    if (subTag) subTag.textContent = `${speaker} // RESPONSE`;
    if (subContent) subContent.textContent = `"${text}"`;
    if (subTime) {
      const now = new Date();
      subTime.textContent = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;
    }
  }

  appendChatMsg(type, text) {
    const log = document.getElementById('chatLog');
    if (!log || !text) return;

    const msg = document.createElement('div');
    msg.className = `chat-msg ${type}`;

    let author = '[EZRA]';
    if (type === 'user') author = '[YOU]';
    else if (type === 'system') author = '[SYSTEM]';

    msg.innerHTML = `<span class="msg-author">${author}</span> <span class="msg-body">${this.escapeHtml(text)}</span>`;
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;
  }

  escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  updateMemories(items) {
    const list = document.getElementById('memoryList');
    const count = document.getElementById('memCount');
    if (!list) return;

    if (!items || items.length === 0) {
      list.innerHTML = '<div class="mem-item empty">No memories stored yet.</div>';
      if (count) count.textContent = '0';
      return;
    }

    if (count) count.textContent = String(items.length);
    list.innerHTML = items.slice(-5).reverse().map((item) => {
      const txt = typeof item === 'string' ? item : (item.memory || item.text || JSON.stringify(item));
      return `<div class="mem-item">${this.escapeHtml(txt)}</div>`;
    }).join('');
  }

  initWaveform() {
    if (!this.waveformCtx || !this.waveformCanvas) return;
    const ctx = this.waveformCtx;
    const w = this.waveformCanvas.width;
    const h = this.waveformCanvas.height;

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      const bars = 48;
      const step = w / bars;
      const audioLvl = (window.ezraBrain ? window.ezraBrain.audioLevel : 0) || 0;

      for (let i = 0; i < bars; i++) {
        // Futuristic equalizer waveform
        const centerDist = Math.abs(i - bars / 2) / (bars / 2);
        const factor = Math.max(0.1, 1.0 - centerDist);
        const noise = Math.sin(performance.now() * 0.01 + i * 0.4) * 0.3 + 0.7;
        const barH = Math.max(3, (factor * audioLvl * 32 + (factor * 3)) * noise);

        const x = i * step + 2;
        const y = (h - barH) / 2;

        ctx.fillStyle = (i % 2 === 0) ? '#ff1a40' : '#ffb703';
        ctx.shadowColor = '#ff1a40';
        ctx.shadowBlur = 4;
        ctx.fillRect(x, y, step - 3, barH);
        ctx.shadowBlur = 0;
      }
      requestAnimationFrame(draw);
    };
    draw();
  }

  initKeyboardShortcuts() {
    let spaceDown = false;
    window.addEventListener('keydown', (e) => {
      // Spacebar for Push-to-Talk (if not currently focused inside input field)
      if (e.code === 'Space' && document.activeElement !== document.getElementById('commandInput')) {
        const pttCheck = document.getElementById('pttCheck');
        if (pttCheck && pttCheck.checked && !spaceDown) {
          e.preventDefault();
          spaceDown = true;
          this.triggerMic('start');
        }
      }

      // Enter to dispatch command if input focused
      if (e.key === 'Enter' && document.activeElement === document.getElementById('commandInput')) {
        this.sendCommand();
      }
    });

    window.addEventListener('keyup', (e) => {
      if (e.code === 'Space') {
        const pttCheck = document.getElementById('pttCheck');
        if (pttCheck && pttCheck.checked && spaceDown) {
          spaceDown = false;
          this.triggerMic('stop');
        }
      }
    });

    const micBtn = document.getElementById('micBtn');
    if (micBtn) {
      micBtn.addEventListener('click', () => {
        this.toggleMic();
      });
    }
  }

  toggleMic() {
    this.isMicActive = !this.isMicActive;
    this.triggerMic(this.isMicActive ? 'start' : 'stop');
  }

  triggerMic(action) {
    this.sendMessage({
      type: 'voice_trigger',
      action: action
    });
    if (action === 'start') {
      this.updateState('listening');
    } else {
      this.updateState('idle');
    }
  }

  sendCommand() {
    const input = document.getElementById('commandInput');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    this.appendChatMsg('user', text);
    input.value = '';

    this.sendMessage({
      type: 'chat',
      text: text
    });

    this.updateState('thinking');
  }
}

// Global functions for inline HTML event handlers
const controller = new EzraClientController();

function sendCommand() {
  controller.sendCommand();
}

function executeQuickAction(actionName) {
  controller.sendMessage({
    type: 'action',
    action: actionName
  });
}

function toggleMute() {
  controller.isMuted = !controller.isMuted;
  const btn = document.getElementById('muteToggleBtn');
  if (btn) {
    btn.classList.toggle('active', controller.isMuted);
    btn.querySelector('.btn-txt').textContent = controller.isMuted ? 'Unmute Voice' : 'Mute Voice';
  }
  controller.sendMessage({
    type: 'control',
    action: 'mute',
    value: controller.isMuted
  });
}

function toggleRobotic() {
  controller.isRobotic = !controller.isRobotic;
  const btn = document.getElementById('robotToggleBtn');
  if (btn) {
    btn.classList.toggle('active', controller.isRobotic);
    btn.querySelector('.btn-txt').textContent = controller.isRobotic ? 'Neural Voice' : 'Robot Synth';
  }
  controller.sendMessage({
    type: 'control',
    action: 'robotic_voice',
    value: controller.isRobotic
  });
}

function toggleSleep() {
  controller.isSleeping = !controller.isSleeping;
  const btn = document.getElementById('sleepToggleBtn');
  if (btn) {
    btn.classList.toggle('active', controller.isSleeping);
    btn.querySelector('.sleep-txt').textContent = controller.isSleeping ? 'WAKE' : 'STANDBY';
  }
  controller.sendMessage({
    type: 'control',
    action: 'sleep',
    value: controller.isSleeping
  });
}

function changeVolume(val) {
  controller.sendMessage({
    type: 'control',
    action: 'volume',
    value: parseInt(val, 10)
  });
}
