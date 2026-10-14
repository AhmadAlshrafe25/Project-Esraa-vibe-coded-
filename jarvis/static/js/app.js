/**
 * PROJECT EZRA // HOLOGRAPHIC NEURAL CLIENT CONTROLLER v3
 * Manages WebSocket telemetry, state machine, waveform, chat, quick actions.
 */

class EzraHUD {
  constructor() {
    this.ws         = null;
    this.isMuted    = false;
    this.isRobotic  = false;
    this.isSleeping = false;
    this.isMicOn    = false;

    // Gauge circumference for r=40: 2πr ≈ 251.3
    this.CIRC = 251.3;

    this._bindEls();
    this._initClock();
    this._initWaveform();
    this._initKeyboard();
    this._connectWS();
  }

  /* ─── DOM BINDINGS ─── */
  _bindEls() {
    this.statusLbl  = document.getElementById('statusLbl');
    this.statusDot  = document.getElementById('statusDot');
    this.dwellVal   = document.getElementById('dwellVal');
    this.bioUser    = document.getElementById('bioUser');
    this.engineEl   = document.getElementById('activeEngine');
    this.distroEl   = document.getElementById('distroName');
    this.clockEl    = document.getElementById('hudClock');
    this.cpuVal     = document.getElementById('cpuVal');
    this.cpuBar     = document.getElementById('cpuBar');
    this.ramVal     = document.getElementById('ramVal');
    this.ramBar     = document.getElementById('ramBar');
    this.uptimeVal  = document.getElementById('uptimeVal');
    this.diskVal    = document.getElementById('diskVal');
    this.lidVal     = document.getElementById('lidVal');
    this.subTag     = document.getElementById('subTag');
    this.subTs      = document.getElementById('subTs');
    this.subText    = document.getElementById('subText');
    this.chatLog    = document.getElementById('chatLog');
    this.liveSttTxt = document.getElementById('liveSttTxt');
    this.memList    = document.getElementById('memList');
    this.memCount   = document.getElementById('memCount');
    this.micBtn     = document.getElementById('micBtn');
    this.hexL       = document.getElementById('hexL');
    this.hexR       = document.getElementById('hexR');
    this.synapseEl  = document.getElementById('synapseVal');
    this.latencyEl  = document.getElementById('latencyVal');
    this.volVal     = document.getElementById('volVal');
    this.volSlider  = document.getElementById('volSlider');
    this.sleepBtn   = document.getElementById('sleepBtn');
    this.waveCanvas = document.getElementById('waveformCanvas');

    if (this.micBtn) {
      this.micBtn.addEventListener('click', () => this._toggleMic());
    }

    // Volume display live
    if (this.volSlider) {
      this.volSlider.addEventListener('input', () => {
        if (this.volVal) this.volVal.textContent = this.volSlider.value;
      });
    }
  }

  /* ─── CLOCK ─── */
  _initClock() {
    const tick = () => {
      const n = new Date();
      const pad = v => String(v).padStart(2, '0');
      if (this.clockEl) this.clockEl.textContent = `${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
    };
    tick();
    setInterval(tick, 1000);
  }

  /* ─── WEBSOCKET ─── */
  _connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.ws = new WebSocket(`${proto}//${location.host}/ws`);

    this.ws.onopen = () => {
      console.log('[Ezra] WebSocket connected.');
      this._appendChat('sys', 'Neural link established. Laptop mic active — speak freely.');
      this._send({ type: 'get_status' });
    };

    this.ws.onmessage = e => {
      try { this._handleMsg(JSON.parse(e.data)); }
      catch (err) { console.error('[Ezra] WS parse error:', err); }
    };

    this.ws.onclose = () => {
      console.warn('[Ezra] WS closed, reconnecting in 2s…');
      setTimeout(() => this._connectWS(), 2000);
    };

    this.ws.onerror = err => console.error('[Ezra] WS error:', err);
  }

  _send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN)
      this.ws.send(JSON.stringify(obj));
  }

  /* ─── MESSAGE HANDLER ─── */
  _handleMsg(data) {
    switch (data.type) {
      case 'telemetry':    this._updateTelemetry(data); break;
      case 'state_change': this._setState(data.state, data.detail); break;
      case 'speech':
        this._updateSubtitle(data.speaker || 'EZRA', data.text);
        if (data.speaker === 'EZRA') this._appendChat('ezra', data.text);
        break;
      case 'live_stt':
        if (this.liveSttTxt)
          this.liveSttTxt.textContent = data.text || 'Listening…';
        break;
      case 'memories':     this._updateMemories(data.items); break;
      case 'audio_level':
        this._audioLevel = data.level || 0;
        if (window.ezraBrain) window.ezraBrain.setAudioLevel(this._audioLevel);
        break;
      case 'user_speech':
        this._appendChat('user', data.text);
        if (this.liveSttTxt) this.liveSttTxt.textContent = data.text;
        break;
      default: break;
    }
  }

  /* ─── STATE MACHINE ─── */
  _setState(state, detail) {
    document.body.className = `state-${state}`;

    const labels = {
      idle:      'STANDBY // READY',
      listening: 'LISTENING',
      thinking:  'PROCESSING…',
      speaking:  'SPEAKING',
      sleep:     'STANDBY MODE',
    };
    if (this.statusLbl) this.statusLbl.textContent = labels[state] || state.toUpperCase();

    // Mic button glow
    if (this.micBtn) this.micBtn.classList.toggle('active', state === 'listening');

    if (window.ezraBrain) window.ezraBrain.setState(state);
  }

  /* ─── TELEMETRY ─── */
  _updateTelemetry(d) {
    // CPU gauge (stroke-dashoffset: CIRC=full off → 0=full on)
    if (this.cpuVal && this.cpuBar) {
      const cpu = Math.round(d.cpu || 0);
      this.cpuVal.textContent = `${cpu}%`;
      this.cpuBar.style.strokeDashoffset = this.CIRC - (this.CIRC * cpu / 100);
    }
    if (this.ramVal && this.ramBar) {
      const ram = Math.round(d.ram || 0);
      this.ramVal.textContent = `${ram}%`;
      this.ramBar.style.strokeDashoffset = this.CIRC - (this.CIRC * ram / 100);
    }
    if (this.uptimeVal && d.uptime)    this.uptimeVal.textContent = d.uptime;
    if (this.diskVal   && d.disk)      this.diskVal.textContent   = `${d.disk}%`;
    if (this.lidVal    && d.lid_status) this.lidVal.textContent   = d.lid_status.toUpperCase();
    if (this.distroEl  && d.distro)    this.distroEl.textContent  = d.distro.toUpperCase();
    if (this.engineEl  && d.engine)    this.engineEl.textContent  = d.engine.toUpperCase();
    if (this.dwellVal  && d.dwell_sec !== undefined)
      this.dwellVal.textContent = `${Number(d.dwell_sec).toFixed(1)}s`;
    if (this.bioUser   && d.user_name)
      this.bioUser.textContent = `${d.user_name.toUpperCase()} // ${(d.tier || 'VERIFIED').toUpperCase()}`;

    // Sci-fi hex streams
    const rh = () => Math.floor(Math.random() * 0xFFFFFF).toString(16).toUpperCase().padStart(6,'0');
    if (this.hexL) this.hexL.textContent = `0x${rh().slice(0,4)}`;
    if (this.hexR) this.hexR.textContent = `0x${rh()}`;

    // Synthetic synapse/latency churn
    if (this.synapseEl)
      this.synapseEl.textContent = `${(140000 + Math.floor(Math.random()*20000)).toLocaleString()}/s`;
    if (this.latencyEl && d.latency_ms !== undefined)
      this.latencyEl.textContent = `${d.latency_ms}ms`;
  }

  /* ─── SUBTITLES ─── */
  _updateSubtitle(speaker, text) {
    if (this.subTag)  this.subTag.textContent  = `${speaker} // RESPONSE`;
    if (this.subText) this.subText.textContent = text;
    if (this.subTs) {
      const n = new Date();
      const pad = v => String(v).padStart(2,'0');
      this.subTs.textContent = `${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
    }
  }

  /* ─── CHAT LOG ─── */
  _appendChat(type, text) {
    if (!this.chatLog || !text) return;
    const el = document.createElement('div');
    el.className = `chat-msg ${type}`;
    const who = { user: '[YOU]', ezra: '[EZRA]', sys: '[SYSTEM]' }[type] || '[SYS]';
    el.innerHTML = `<span class="msg-who">${who}</span><span class="msg-body">${this._esc(text)}</span>`;
    this.chatLog.appendChild(el);
    this.chatLog.scrollTop = this.chatLog.scrollHeight;
  }

  _esc(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  /* ─── MEMORIES ─── */
  _updateMemories(items) {
    if (!this.memList) return;
    if (!items || !items.length) {
      this.memList.innerHTML = '<div class="mem-item empty">No memories stored yet.</div>';
      if (this.memCount) this.memCount.textContent = '0';
      return;
    }
    if (this.memCount) this.memCount.textContent = String(items.length);
    this.memList.innerHTML = items.slice(-5).reverse().map(item => {
      const txt = typeof item === 'string' ? item : (item.memory || item.text || JSON.stringify(item));
      return `<div class="mem-item">${this._esc(txt)}</div>`;
    }).join('');
  }

  /* ─── MIC ─── */
  _toggleMic() {
    this.isMicOn = !this.isMicOn;
    this._send({ type: 'voice_trigger', action: this.isMicOn ? 'start' : 'stop' });
    this._setState(this.isMicOn ? 'listening' : 'idle');
  }

  /* ─── KEYBOARD ─── */
  _initKeyboard() {
    let spaceDown = false;

    window.addEventListener('keydown', e => {
      if (e.code === 'Space' && document.activeElement !== document.getElementById('commandInput')) {
        const ptt = document.getElementById('pttCheck');
        if (ptt && ptt.checked && !spaceDown) {
          e.preventDefault(); spaceDown = true;
          this.isMicOn = true;
          this._send({ type: 'voice_trigger', action: 'start' });
          this._setState('listening');
        }
      }
      if (e.key === 'Enter' && document.activeElement === document.getElementById('commandInput')) {
        this.sendCommand();
      }
    });

    window.addEventListener('keyup', e => {
      if (e.code === 'Space') {
        const ptt = document.getElementById('pttCheck');
        if (ptt && ptt.checked && spaceDown) {
          spaceDown = false; this.isMicOn = false;
          this._send({ type: 'voice_trigger', action: 'stop' });
          this._setState('idle');
        }
      }
    });
  }

  /* ─── SEND TEXT COMMAND ─── */
  sendCommand() {
    const input = document.getElementById('commandInput');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    this._appendChat('user', text);
    input.value = '';
    this._send({ type: 'chat', text });
    this._setState('thinking');
  }

  /* ─── WAVEFORM ─── */
  _initWaveform() {
    if (!this.waveCanvas) return;
    const ctx = this.waveCanvas.getContext('2d');
    const W = this.waveCanvas.width;
    const H = this.waveCanvas.height;
    this._audioLevel = 0;

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      const bars = 52;
      const step = W / bars;
      const lvl  = this._audioLevel || 0;

      for (let i = 0; i < bars; i++) {
        const dist  = Math.abs(i - bars / 2) / (bars / 2);
        const fade  = Math.max(0.08, 1 - dist * 0.85);
        const noise = Math.sin(performance.now() * 0.009 + i * 0.45) * 0.35 + 0.65;
        const bH    = Math.max(2, fade * lvl * 30 * noise + (fade * 2.5));

        const x = i * step + 1.5;
        const y = (H - bH) / 2;

        // Alternate red / amber colour per bar
        ctx.fillStyle = i % 3 === 0 ? '#ffb703' : '#ff1a40';
        ctx.shadowColor = '#ff1a40';
        ctx.shadowBlur  = 5;
        ctx.fillRect(x, y, step - 2.5, bH);
        ctx.shadowBlur  = 0;
      }
      requestAnimationFrame(draw);
    };
    draw();
  }
}

/* ──────────────────────────────────────────────
   GLOBALS — bridge for inline HTML handlers
────────────────────────────────────────────── */
const hud = new EzraHUD();

function sendCommand() { hud.sendCommand(); }

function executeQuickAction(name) {
  hud._send({ type: 'action', action: name });
}

function toggleMute() {
  hud.isMuted = !hud.isMuted;
  const btn = document.getElementById('muteBtn');
  if (btn) {
    btn.classList.toggle('active', hud.isMuted);
    btn.querySelector('.act-lbl').textContent = hud.isMuted ? 'Unmute' : 'Mute Voice';
  }
  hud._send({ type: 'control', action: 'mute', value: hud.isMuted });
}

function toggleRobotic() {
  hud.isRobotic = !hud.isRobotic;
  const btn = document.getElementById('robotBtn');
  if (btn) {
    btn.classList.toggle('active', hud.isRobotic);
    btn.querySelector('.act-lbl').textContent = hud.isRobotic ? 'Neural Voice' : 'Robot Mode';
  }
  hud._send({ type: 'control', action: 'robotic_voice', value: hud.isRobotic });
}

function toggleSleep() {
  hud.isSleeping = !hud.isSleeping;
  const btn = document.getElementById('sleepBtn');
  if (btn) {
    btn.classList.toggle('active', hud.isSleeping);
    btn.querySelector('.sleep-lbl').textContent = hud.isSleeping ? 'WAKE' : 'STANDBY';
  }
  hud._send({ type: 'control', action: 'sleep', value: hud.isSleeping });
}

function changeVolume(val) {
  if (hud.volVal) hud.volVal.textContent = val;
  hud._send({ type: 'control', action: 'volume', value: parseInt(val, 10) });
}
