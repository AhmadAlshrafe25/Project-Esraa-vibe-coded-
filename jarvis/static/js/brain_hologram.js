/**
 * ==============================================================================
 * PROJECT EZRA // 3D HOLOGRAPHIC NEURAL BRAIN ENGINE
 * Renders interactive 3D cerebral hemispheres, synaptic lightning arcs,
 * rotating gyroscope rings, and concentric floor radar pedestal.
 * Direct match to Ezra Holographic Brain Reference.
 * ==============================================================================
 */

class EzraBrainHologram {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');

    this.nodes = [];
    this.synapses = [];
    this.sparks = [];
    this.audioLevel = 0.0;
    this.state = 'idle'; // 'idle' | 'listening' | 'thinking' | 'speaking'

    // Rotation angles
    this.rotX = 0.12;
    this.rotY = 0.0;
    this.rotZ = 0.0;
    this.autoRotSpeed = 0.008;

    // Mouse drag interaction
    this.isDragging = false;
    this.lastMouseX = 0;
    this.lastMouseY = 0;

    // Concentric Orbiting HUD Rings
    this.rings = [
      { radius: 180, tiltX: 0.35, tiltZ: 0.2, angle: 0, speed: 0.012, ticks: 36, color: '#ff1a40' },
      { radius: 215, tiltX: -0.4, tiltZ: -0.25, angle: 0, speed: -0.009, ticks: 48, color: '#ff4d6d' },
      { radius: 250, tiltX: 0.15, tiltZ: 0.6, angle: 0, speed: 0.006, ticks: 64, color: '#ffb703' }
    ];

    // Pedestal floor rings
    this.pedestalRadius = 240;
    this.radarAngle = 0;

    this.initCanvasSize();
    this.generateBrainMesh();
    this.setupInteractions();
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  initCanvasSize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.width = rect.width || 800;
    this.height = rect.height || 600;
    this.canvas.width = this.width * window.devicePixelRatio;
    this.canvas.height = this.height * window.devicePixelRatio;
    this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    window.addEventListener('resize', () => {
      const r = this.canvas.parentElement.getBoundingClientRect();
      this.width = r.width || 800;
      this.height = r.height || 600;
      this.canvas.width = this.width * window.devicePixelRatio;
      this.canvas.height = this.height * window.devicePixelRatio;
      this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    });
  }

  generateBrainMesh() {
    this.nodes = [];
    this.synapses = [];
    const totalNodes = 650;

    // Mathematical anatomical brain generator (Cerebral Cortex + Cerebellum + Brainstem)
    for (let i = 0; i < totalNodes; i++) {
      // Left hemisphere vs Right hemisphere (-1 or +1)
      const hemi = (i % 2 === 0) ? 1 : -1;
      const u = Math.random();
      const v = Math.random();
      const theta = u * 2.0 * Math.PI;
      const phi = Math.acos(2.0 * v - 1.0);

      // Anatomical brain ellipsoid formula with sulci/gyri cortical convolutions
      const rBase = 110.0;
      // Ellipsoidal axes (length x width x height)
      let rx = Math.sin(phi) * Math.cos(theta);
      let ry = Math.sin(phi) * Math.sin(theta);
      let rz = Math.cos(phi);

      // Hemisphere split along X-axis
      rx = (Math.abs(rx) * 0.85 + 0.18) * hemi;
      ry = ry * 1.25 - 0.15; // elongated front-to-back
      rz = rz * 0.95 + 0.1;

      // Add intricate cortical folds (sulci / gyri wrinkling waves)
      const foldNoise = Math.sin(rx * 14.0) * Math.cos(ry * 14.0) * Math.sin(rz * 14.0) * 12.0;
      const dist = rBase + foldNoise;

      let x = rx * dist;
      let y = ry * dist;
      let z = rz * dist;

      // Flatten bottom for brainstem connection
      if (z < -50 && Math.abs(x) < 40 && Math.abs(y) < 40) {
        z = z * 1.2;
      }

      this.nodes.push({
        baseX: x,
        baseY: y,
        baseZ: z,
        x: x,
        y: y,
        z: z,
        hemi: hemi,
        pulsePhase: Math.random() * Math.PI * 2,
        glowIntensity: 0.3 + Math.random() * 0.7,
        size: 1.2 + Math.random() * 1.8
      });
    }

    // Connect nearest neighbors within each hemisphere (Synaptic Network)
    for (let i = 0; i < this.nodes.length; i++) {
      let connections = 0;
      for (let j = i + 1; j < this.nodes.length; j++) {
        const n1 = this.nodes[i];
        const n2 = this.nodes[j];
        if (n1.hemi === n2.hemi) {
          const dx = n1.baseX - n2.baseX;
          const dy = n1.baseY - n2.baseY;
          const dz = n1.baseZ - n2.baseZ;
          const d2 = dx * dx + dy * dy + dz * dz;
          if (d2 < 34 * 34 && connections < 3) {
            this.synapses.push({ a: i, b: j, baseAlpha: 0.18 + Math.random() * 0.25 });
            connections++;
          }
        }
      }
    }
  }

  setupInteractions() {
    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.isDragging) return;
      const dx = e.clientX - this.lastMouseX;
      const dy = e.clientY - this.lastMouseY;
      this.rotY += dx * 0.008;
      this.rotX += dy * 0.008;
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    // Touch support for mobile / tablets
    this.canvas.addEventListener('touchstart', (e) => {
      if (e.touches.length > 0) {
        this.isDragging = true;
        this.lastMouseX = e.touches[0].clientX;
        this.lastMouseY = e.touches[0].clientY;
      }
    });

    window.addEventListener('touchmove', (e) => {
      if (!this.isDragging || e.touches.length === 0) return;
      const dx = e.touches[0].clientX - this.lastMouseX;
      const dy = e.touches[0].clientY - this.lastMouseY;
      this.rotY += dx * 0.008;
      this.rotX += dy * 0.008;
      this.lastMouseX = e.touches[0].clientX;
      this.lastMouseY = e.touches[0].clientY;
    });

    window.addEventListener('touchend', () => {
      this.isDragging = false;
    });
  }

  setState(newState) {
    this.state = newState;
    const body = document.body;
    body.classList.remove('state-idle', 'state-listening', 'state-thinking', 'state-speaking');
    body.classList.add(`state-${newState}`);

    const statusLabel = document.getElementById('statusLabel');
    if (statusLabel) {
      if (newState === 'idle') statusLabel.textContent = 'SYSTEM STANDBY // LISTENING';
      else if (newState === 'listening') statusLabel.textContent = 'MIC ENGAGED // CAPTURING VOICE';
      else if (newState === 'thinking') statusLabel.textContent = 'NEURAL REASONING // AI THINKING';
      else if (newState === 'speaking') statusLabel.textContent = 'EZRA VOCALIZING // BROADCASTING';
    }
  }

  setAudioLevel(lvl) {
    // Clamped 0.0 to 1.0
    this.audioLevel = Math.max(0.0, Math.min(1.0, lvl));
  }

  triggerSynapticSpark() {
    if (this.synapses.length === 0) return;
    const randSyn = this.synapses[Math.floor(Math.random() * this.synapses.length)];
    this.sparks.push({
      synapse: randSyn,
      progress: 0.0,
      speed: 0.05 + Math.random() * 0.08,
      color: (Math.random() > 0.4) ? '#ffb703' : '#ffffff'
    });
  }

  project3D(x, y, z, cx, cy) {
    // 3D Rotation Matrix
    const cosX = Math.cos(this.rotX);
    const sinX = Math.sin(this.rotX);
    const cosY = Math.cos(this.rotY);
    const sinY = Math.sin(this.rotY);

    // Rotate Y
    let x1 = x * cosY + z * sinY;
    let y1 = y;
    let z1 = -x * sinY + z * cosY;

    // Rotate X
    let x2 = x1;
    let y2 = y1 * cosX - z1 * sinX;
    let z2 = y1 * sinX + z1 * cosX;

    // Perspective Projection
    const fov = 520;
    const scale = fov / (fov + z2 + 200);
    const px = cx + x2 * scale;
    const py = cy + y2 * scale;

    return { x: px, y: py, z: z2, scale: scale };
  }

  drawPedestalRings(cx, cy) {
    const ctx = this.ctx;
    const floorY = cy + 130;
    this.radarAngle += 0.015;

    ctx.save();
    ctx.translate(cx, floorY);
    ctx.scale(1.0, 0.32); // Isometric 3D tilt

    // 1. Outer glow ring
    ctx.beginPath();
    ctx.arc(0, 0, this.pedestalRadius, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 26, 64, 0.35)';
    ctx.lineWidth = 2;
    ctx.stroke();

    // 2. Inner segmented ring
    ctx.beginPath();
    ctx.arc(0, 0, this.pedestalRadius * 0.75, 0, Math.PI * 2);
    ctx.setLineDash([8, 12]);
    ctx.strokeStyle = 'rgba(255, 183, 3, 0.4)';
    ctx.stroke();
    ctx.setLineDash([]);

    // 3. Azimuth Degree Ticks
    for (let a = 0; a < Math.PI * 2; a += Math.PI / 16) {
      const x1 = Math.cos(a) * (this.pedestalRadius - 8);
      const y1 = Math.sin(a) * (this.pedestalRadius - 8);
      const x2 = Math.cos(a) * this.pedestalRadius;
      const y2 = Math.sin(a) * this.pedestalRadius;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = 'rgba(255, 26, 64, 0.6)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // 4. Radar Sweep Sector
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.arc(0, 0, this.pedestalRadius, this.radarAngle, this.radarAngle + 0.45);
    ctx.closePath();
    const grad = ctx.createRadialGradient(0, 0, 10, 0, 0, this.pedestalRadius);
    grad.addColorStop(0, 'rgba(255, 26, 64, 0.25)');
    grad.addColorStop(1, 'rgba(255, 26, 64, 0.0)');
    ctx.fillStyle = grad;
    ctx.fill();

    // 5. Audio Reactive Ripple Ring
    if (this.audioLevel > 0.05) {
      const audioR = this.pedestalRadius * (0.6 + this.audioLevel * 0.5);
      ctx.beginPath();
      ctx.arc(0, 0, audioR, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(255, 77, 109, ${0.4 + this.audioLevel * 0.5})`;
      ctx.lineWidth = 2.5;
      ctx.stroke();
    }

    ctx.restore();
  }

  drawOrbitingRings(cx, cy) {
    const ctx = this.ctx;

    this.rings.forEach((ring, idx) => {
      ring.angle += ring.speed;
      const count = ring.ticks;
      const step = (Math.PI * 2) / count;

      ctx.save();
      ctx.translate(cx, cy);

      for (let i = 0; i < count; i++) {
        const a = i * step + ring.angle;
        // 3D Parametric Circle tilted
        let x = Math.cos(a) * ring.radius;
        let y = Math.sin(a) * ring.radius * Math.cos(ring.tiltX);
        let z = Math.sin(a) * ring.radius * Math.sin(ring.tiltZ);

        // Apply brain rotation
        const proj = this.project3D(x, y, z, 0, 0);
        if (proj.scale > 0) {
          ctx.beginPath();
          ctx.arc(proj.x, proj.y, 1.2 * proj.scale, 0, Math.PI * 2);
          ctx.fillStyle = ring.color;
          ctx.globalAlpha = 0.4 * proj.scale;
          ctx.fill();
        }
      }
      ctx.restore();
    });
  }

  animate() {
    const ctx = this.ctx;
    const cx = this.width / 2;
    const cy = this.height / 2;

    // Clear Canvas
    ctx.clearRect(0, 0, this.width, this.height);

    // Auto rotate brain if not manually dragging
    if (!this.isDragging) {
      let speed = this.autoRotSpeed;
      if (this.state === 'thinking') speed = 0.024;
      else if (this.state === 'speaking') speed = 0.014;
      this.rotY += speed;
    }

    // 1. Draw Hologram Pedestal Radar Floor
    this.drawPedestalRings(cx, cy);

    // 2. Draw Orbiting HUD Gyroscope Rings
    this.drawOrbitingRings(cx, cy);

    // 3. Audio & State Dynamics on Brain Nodes
    const timeNow = performance.now() * 0.003;
    const audioScale = 1.0 + (this.state === 'listening' ? this.audioLevel * 0.35 : 0.0);
    const thinkingExtra = (this.state === 'thinking') ? Math.sin(timeNow * 8) * 3 : 0;

    // Project all nodes
    const projectedNodes = this.nodes.map((node) => {
      const breath = Math.sin(timeNow + node.pulsePhase) * 2.5;
      const curX = node.baseX * audioScale + (node.hemi * thinkingExtra);
      const curY = node.baseY * audioScale + breath;
      const curZ = node.baseZ * audioScale;

      const p = this.project3D(curX, curY, curZ, cx, cy);
      return { p, node };
    });

    // Sort by depth (painter's algorithm)
    projectedNodes.sort((a, b) => b.p.z - a.p.z);

    // 4. Draw Synaptic Fiber Lines
    ctx.lineWidth = 1.0;
    for (let s of this.synapses) {
      const p1 = projectedNodes[s.a].p;
      const p2 = projectedNodes[s.b].p;
      if (p1.scale > 0 && p2.scale > 0) {
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);

        let alpha = s.baseAlpha * p1.scale;
        if (this.state === 'thinking') alpha = Math.min(1.0, alpha * 2.2);
        else if (this.state === 'speaking') alpha = Math.min(1.0, alpha * (1.2 + this.audioLevel));

        ctx.strokeStyle = (this.state === 'thinking') 
          ? `rgba(255, 183, 3, ${alpha})`
          : `rgba(255, 26, 64, ${alpha})`;
        ctx.stroke();
      }
    }

    // 5. Draw Synaptic Lightning Sparks (during Thinking / Speaking)
    if (this.state === 'thinking' && Math.random() < 0.35) {
      this.triggerSynapticSpark();
    } else if (this.state === 'speaking' && Math.random() < 0.20) {
      this.triggerSynapticSpark();
    }

    for (let i = this.sparks.length - 1; i >= 0; i--) {
      const sp = this.sparks[i];
      sp.progress += sp.speed;
      if (sp.progress >= 1.0) {
        this.sparks.splice(i, 1);
        continue;
      }
      const p1 = projectedNodes[sp.synapse.a].p;
      const p2 = projectedNodes[sp.synapse.b].p;
      const sx = p1.x + (p2.x - p1.x) * sp.progress;
      const sy = p1.y + (p2.y - p1.y) * sp.progress;

      ctx.beginPath();
      ctx.arc(sx, sy, 2.5 * p1.scale, 0, Math.PI * 2);
      ctx.fillStyle = sp.color;
      ctx.shadowColor = sp.color;
      ctx.shadowBlur = 10;
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    // 6. Draw Brain Particle Nodes with Glowing Core
    for (let item of projectedNodes) {
      const p = item.p;
      const node = item.node;
      if (p.scale > 0) {
        const radius = node.size * p.scale;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);

        let glow = '#ff1a40';
        if (this.state === 'thinking' && Math.sin(timeNow * 4 + node.pulsePhase) > 0.4) {
          glow = '#ffb703';
        } else if (this.state === 'speaking') {
          glow = '#ff4d6d';
        }

        ctx.fillStyle = glow;
        ctx.shadowColor = glow;
        ctx.shadowBlur = 6 * p.scale;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    }

    // Loop
    requestAnimationFrame(this.animate);
  }
}

// Instantiate globally when DOM is ready
window.addEventListener('DOMContentLoaded', () => {
  window.ezraBrain = new EzraBrainHologram('brainCanvas');
});
