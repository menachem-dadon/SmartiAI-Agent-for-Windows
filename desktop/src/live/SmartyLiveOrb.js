// SmartyLiveOrb.js — רכיב עיגול לייב דינמי לסמארטי
export class SmartyLiveOrb {
      constructor(canvas, options = {}) {
        this.canvas = canvas;
        this.gl = canvas.getContext('webgl', { alpha: true, antialias: true, premultipliedAlpha: false });

        // Current interpolated parameters
        this.current = {
          speed: 0.45,
          wildness: 0.15,
          energy: 0.10,
          swirl: 0.20,
          cloudDetail: 0.75,
          colDeep: [0.075, 0.335, 0.920],   // #1355EA (Deep Cobalt Blue from video)
          colLight: [0.715, 0.795, 0.980],  // #B6CBFA (Soft Periwinkle from video)
          colFoam: [1.000, 1.000, 1.000]    // #FFFFFF (Cloud Wisp White)
        };

        // Target parameters for smooth damping
        this.target = JSON.parse(JSON.stringify(this.current));
        Object.assign(this.target, options);

        // Accumulated phase time so changing `speed` never causes visual jumps
        this.phaseTime = 0;
        this.windPhase = 0;
        this.lastTimestamp = performance.now();
        this.pulseBoost = 0;

        if (!this.gl) throw new Error('WebGL unavailable');
        this.destroyed = false;
        this.reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
        this.onContextLost = event => { event.preventDefault(); this.destroy(); };
        this.canvas.addEventListener('webglcontextlost', this.onContextLost);
        try { this._initWebGL(); } catch (error) { this.destroy(); throw error; }
        this.resize();
        this.observer = new ResizeObserver(() => this.resize());
        this.observer.observe(this.canvas);
        this._animate = this._animate.bind(this);
        this.rafId = requestAnimationFrame(this._animate);
      }

      destroy() {
        if (this.destroyed) return;
        this.destroyed = true;
        cancelAnimationFrame(this.rafId);
        this.observer?.disconnect();
        this.canvas.removeEventListener('webglcontextlost', this.onContextLost);
        if (this.gl) {
          for (const shader of this.shaders || []) this.gl.deleteShader(shader);
          if (this.buffer) this.gl.deleteBuffer(this.buffer);
          if (this.program) this.gl.deleteProgram(this.program);
        }
      }

      _initWebGL() {
        const gl = this.gl;
        if (!gl) return;
        this.shaders = [];

        const vsSource = `
          attribute vec2 a_position;
          varying vec2 v_uv;
          void main() {
            v_uv = a_position * 0.5 + 0.5;
            gl_Position = vec4(a_position, 0.0, 1.0);
          }
        `;

        const fsSource = `
          precision highp float;
          varying vec2 v_uv;

          uniform vec2 u_resolution;
          uniform float u_phase;
          uniform float u_wind;
          uniform float u_wildness;
          uniform float u_energy;
          uniform float u_swirl;
          uniform float u_cloudDetail;
          uniform vec3 u_colDeep;
          uniform vec3 u_colLight;
          uniform vec3 u_colFoam;

          // 2D Simplex-style hash & value/gradient noise for silky clouds
          vec2 hash2(vec2 p) {
            p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
            return -1.0 + 2.0 * fract(sin(p) * 43758.5453123);
          }

          float gradientNoise(vec2 p) {
            vec2 i = floor(p);
            vec2 f = fract(p);
            vec2 u = f * f * (3.0 - 2.0 * f);

            return mix(
              mix(dot(hash2(i + vec2(0.0, 0.0)), f - vec2(0.0, 0.0)),
                  dot(hash2(i + vec2(1.0, 0.0)), f - vec2(1.0, 0.0)), u.x),
              mix(dot(hash2(i + vec2(0.0, 1.0)), f - vec2(0.0, 1.0)),
                  dot(hash2(i + vec2(1.0, 1.0)), f - vec2(1.0, 1.0)), u.x),
              u.y
            );
          }

          // Rotational octave matrix to avoid grid artifacts
          const mat2 m2 = mat2(0.80, -0.60, 0.60, 0.80);

          float fbm(vec2 p) {
            float v = 0.0;
            float a = 0.5;
            for (int i = 0; i < 6; i++) {
              v += a * gradientNoise(p);
              p = m2 * p * 2.03 + vec2(1.7, 9.2);
              a *= 0.5;
            }
            return v;
          }

          void main() {
            // Normalized coordinates centered at (0,0), radius ~ 1.0
            vec2 p = (v_uv - 0.5) * 2.0;
            float r = length(p);

            // Crisp anti-aliased circle mask with subtle breathing from voice energy
            float maxRadius = 0.96 + 0.025 * sin(u_phase * 2.2) * u_energy;
            float circleAlpha = 1.0 - smoothstep(maxRadius - 0.018, maxRadius, r);
            if (circleAlpha <= 0.001) {
              gl_FragColor = vec4(0.0);
              return;
            }

            // Spherical lens distortion so the fluid feels contained inside a 3D orb
            float sphereZ = sqrt(max(0.0, 1.0 - min(1.0, r * r * 0.88)));
            vec2 sphereUV = p / (0.68 + 0.32 * sphereZ);

            // Rotational swirl around center driven by u_swirl and u_wildness
            float swirlStrength = (u_swirl * 1.35 + u_wildness * 0.75) * (1.0 - r * 0.45);
            float swirlAngle = swirlStrength * sin(u_phase * 0.65 + r * 2.2);
            float cs = cos(swirlAngle);
            float sn = sin(swirlAngle);
            vec2 q = mat2(cs, -sn, sn, cs) * sphereUV;

            // Domain Warping Layer 1 (Large fluid currents)
            vec2 warp1 = vec2(
              fbm(q * 1.35 + vec2(u_phase * 0.42, -u_wind * 0.35)),
              fbm(q * 1.35 + vec2(-u_wind * 0.38, u_phase * 0.48) + vec2(5.2, 1.3))
            );

            // Domain Warping Layer 2 (Turbulent eddies & cloud curls)
            float warpAmp = mix(0.22, 1.65, u_wildness) + u_energy * 0.55;
            vec2 warpedPos = q + warp1 * warpAmp;

            vec2 warp2 = vec2(
              fbm(warpedPos * 2.1 - vec2(u_wind * 0.6, u_phase * 0.55)),
              fbm(warpedPos * 2.1 + vec2(u_phase * 0.6, u_wind * 0.5) + vec2(2.8, 7.1))
            );

            // Base horizon wave (In idle mode: top is deep cobalt blue, bottom is soft periwinkle)
            // Note: in WebGL v_uv.y = 1.0 is top, v_uv.y = 0.0 is bottom
            float waveArch = 0.18 * cos(q.x * 2.1 - u_phase * 0.55)
                           + 0.10 * sin(q.x * 3.7 + u_phase * 0.85);

            // As wildness increases, the calm horizon breaks into full 360-degree churning clouds
            float horizonField = mix(
              (q.y - waveArch),
              (warpedPos.y * 0.55 + warp1.x * 0.85 + warp2.y * 0.75),
              smoothstep(0.0, 0.95, u_wildness)
            );

            // High-frequency wispy cloud fibers (like cirrus/cumulus edges in the video)
            float wispy = fbm(warpedPos * (3.2 + u_cloudDetail * 2.5) + warp2 * 1.4 + vec2(u_wind, -u_phase * 0.4));
            float fineMist = fbm(warpedPos * 6.5 - warp1 * 2.0 + vec2(-u_phase * 0.8, u_wind * 0.7));

            float combinedField = horizonField + wispy * (0.38 + 0.45 * u_wildness) + fineMist * 0.16 * u_cloudDetail;

            // Transition softness between light periwinkle and deep blue
            float blueMask = smoothstep(-0.18, 0.34, combinedField);

            // Base blend between lower periwinkle and upper deep cobalt blue
            vec3 color = mix(u_colLight, u_colDeep, blueMask);

            // Luminous White Cloud Ridge right at the interface boundary + inside turbulent eddies
            // Notice in the video how a bright white misty band hugs the boundary between light & dark blue
            float boundaryDist = abs(combinedField - 0.04);
            float ridgeWidth = mix(0.22, 0.38, u_wildness + u_energy * 0.3);
            float whiteRidge = exp(-pow(boundaryDist / ridgeWidth, 1.75));

            // Add wispy cloud filaments inside both regions when wildness is active
            float internalClouds = smoothstep(0.08, 0.62, wispy + warp2.x * 0.5) * (0.35 + 0.65 * u_wildness);
            float whiteAmount = clamp(whiteRidge * (0.82 + 0.35 * wispy) + internalClouds * 0.58, 0.0, 1.0);

            color = mix(color, u_colFoam, whiteAmount);

            // Occasional soft periwinkle wash during high turbulence (like 00:09 & 00:31 in the video)
            float mistWash = smoothstep(0.45, 0.95, warp1.y + warp2.x * 0.6) * u_wildness * 0.45;
            color = mix(color, mix(u_colLight, u_colFoam, 0.45), mistWash);

            // Subtle 3D inner spherical rim lighting (soft bright top-left, gentle pastel bottom edge)
            float rim = smoothstep(0.55, 0.98, r);
            vec3 rimTint = mix(u_colFoam, u_colLight, 0.5);
            color = mix(color, rimTint, rim * 0.18);

            gl_FragColor = vec4(color, circleAlpha);
          }
        `;

        const compile = (type, src) => {
          const s = gl.createShader(type);
          this.shaders.push(s);
          gl.shaderSource(s, src);
          gl.compileShader(s);
          if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error('Live orb shader compilation failed');
          return s;
        };

        const vs = compile(gl.VERTEX_SHADER, vsSource);
        const fs = compile(gl.FRAGMENT_SHADER, fsSource);
        this.program = gl.createProgram();
        gl.attachShader(this.program, vs);
        gl.attachShader(this.program, fs);
        gl.linkProgram(this.program);
        if (!gl.getProgramParameter(this.program, gl.LINK_STATUS)) throw new Error('Live orb shader link failed');
        gl.useProgram(this.program);

        const buf = this.buffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferData(
          gl.ARRAY_BUFFER,
          new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
          gl.STATIC_DRAW
        );

        const posLoc = gl.getAttribLocation(this.program, 'a_position');
        gl.enableVertexAttribArray(posLoc);
        gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

        this.uniforms = {
          resolution: gl.getUniformLocation(this.program, 'u_resolution'),
          phase: gl.getUniformLocation(this.program, 'u_phase'),
          wind: gl.getUniformLocation(this.program, 'u_wind'),
          wildness: gl.getUniformLocation(this.program, 'u_wildness'),
          energy: gl.getUniformLocation(this.program, 'u_energy'),
          swirl: gl.getUniformLocation(this.program, 'u_swirl'),
          cloudDetail: gl.getUniformLocation(this.program, 'u_cloudDetail'),
          colDeep: gl.getUniformLocation(this.program, 'u_colDeep'),
          colLight: gl.getUniformLocation(this.program, 'u_colLight'),
          colFoam: gl.getUniformLocation(this.program, 'u_colFoam')
        };
      }

      resize() {
        if (!this.canvas || !this.gl) return;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const rect = this.canvas.getBoundingClientRect();
        const w = Math.max(1, Math.round(rect.width * dpr));
        const h = Math.max(1, Math.round(rect.height * dpr));
        if (this.canvas.width !== w || this.canvas.height !== h) {
          this.canvas.width = w;
          this.canvas.height = h;
          this.gl.viewport(0, 0, w, h);
        }
      }

      /**
       * Update orb parameters programmatically
       * @param {Object} params - { speed, wildness, energy, swirl, cloudDetail, colDeep, colLight, colFoam }
       */
      setParams(params = {}) {
        if (typeof params.speed === 'number') this.target.speed = Math.max(0, Math.min(5, params.speed));
        if (typeof params.wildness === 'number') this.target.wildness = Math.max(0, Math.min(1, params.wildness));
        if (typeof params.energy === 'number') this.target.energy = Math.max(0, Math.min(1, params.energy));
        if (typeof params.swirl === 'number') this.target.swirl = Math.max(0, Math.min(1, params.swirl));
        if (typeof params.cloudDetail === 'number') this.target.cloudDetail = Math.max(0, Math.min(1, params.cloudDetail));
        if (Array.isArray(params.colDeep)) this.target.colDeep = params.colDeep;
        if (Array.isArray(params.colLight)) this.target.colLight = params.colLight;
        if (Array.isArray(params.colFoam)) this.target.colFoam = params.colFoam;
      }

      /**
       * Switch between named conversation states for Smarty Live Mode
       */
      setState(stateName) {
        if (this.reducedMotion.matches || this.canvas.closest('[data-reduced-motion="true"]')) stateName = 'idle';
        const presets = {
          idle:           { speed: 0.45, wildness: 0.15, energy: 0.08, swirl: 0.18, cloudDetail: 0.75 },
          listening:      { speed: 0.80, wildness: 0.32, energy: 0.25, swirl: 0.30, cloudDetail: 0.80 },
          userSpeaking:   { speed: 1.75, wildness: 0.72, energy: 0.70, swirl: 0.52, cloudDetail: 0.85 },
          smartySpeaking: { speed: 2.55, wildness: 0.94, energy: 0.90, swirl: 0.68, cloudDetail: 0.92 },
          thinking:       { speed: 1.95, wildness: 0.58, energy: 0.40, swirl: 0.92, cloudDetail: 0.70 }
        };
        if (presets[stateName]) {
          this.setParams(presets[stateName]);
        }
      }

      /**
       * Feed normalized audio RMS level (0.0 to 1.0) in real time
       */
      feedAudioLevel(level) {
        if (this.reducedMotion.matches || this.canvas.closest('[data-reduced-motion="true"]')) return;
        const clamped = Math.max(0, Math.min(1, level));
        this.setParams({
          speed: 0.50 + clamped * 2.45,
          wildness: 0.16 + clamped * 0.82,
          energy: 0.10 + clamped * 0.90,
          swirl: 0.20 + clamped * 0.58
        });
      }

      /**
       * Trigger an immediate energetic burst
       */
      pulse(intensity = 0.85) {
        this.pulseBoost = Math.max(this.pulseBoost, intensity);
      }

      _animate(now) {
        if (this.destroyed) return;
        const dt = Math.min(0.05, (now - this.lastTimestamp) / 1000);
        this.lastTimestamp = now;

        // Smooth exponential damping toward target parameters
        const lerpRate = 1.0 - Math.exp(-dt * 6.5);
        this.current.speed += (this.target.speed - this.current.speed) * lerpRate;
        this.current.wildness += (this.target.wildness - this.current.wildness) * lerpRate;
        this.current.energy += (this.target.energy - this.current.energy) * lerpRate;
        this.current.swirl += (this.target.swirl - this.current.swirl) * lerpRate;
        this.current.cloudDetail += (this.target.cloudDetail - this.current.cloudDetail) * lerpRate;

        for (let i = 0; i < 3; i++) {
          this.current.colDeep[i] += (this.target.colDeep[i] - this.current.colDeep[i]) * lerpRate;
          this.current.colLight[i] += (this.target.colLight[i] - this.current.colLight[i]) * lerpRate;
          this.current.colFoam[i] += (this.target.colFoam[i] - this.current.colFoam[i]) * lerpRate;
        }

        // Decay pulse boost
        if (this.pulseBoost > 0.001) {
          this.pulseBoost *= Math.exp(-dt * 3.2);
        } else {
          this.pulseBoost = 0;
        }

        const effectiveSpeed = (this.reducedMotion.matches || this.canvas.closest('[data-reduced-motion="true"]')) ? 0 : this.current.speed + this.pulseBoost * 1.8;
        const effectiveWildness = Math.min(1.0, this.current.wildness + this.pulseBoost * 0.45);
        const effectiveEnergy = Math.min(1.0, this.current.energy + this.pulseBoost * 0.5);

        this.phaseTime += dt * effectiveSpeed;
        this.windPhase += dt * (effectiveSpeed * (0.7 + effectiveWildness * 0.9));

        const gl = this.gl;
        if (gl) {
          gl.useProgram(this.program);
          gl.uniform2f(this.uniforms.resolution, this.canvas.width, this.canvas.height);
          gl.uniform1f(this.uniforms.phase, this.phaseTime);
          gl.uniform1f(this.uniforms.wind, this.windPhase);
          gl.uniform1f(this.uniforms.wildness, effectiveWildness);
          gl.uniform1f(this.uniforms.energy, effectiveEnergy);
          gl.uniform1f(this.uniforms.swirl, this.current.swirl);
          gl.uniform1f(this.uniforms.cloudDetail, this.current.cloudDetail);
          gl.uniform3fv(this.uniforms.colDeep, this.current.colDeep);
          gl.uniform3fv(this.uniforms.colLight, this.current.colLight);
          gl.uniform3fv(this.uniforms.colFoam, this.current.colFoam);

          gl.drawArrays(gl.TRIANGLES, 0, 6);
        }

        this.rafId = requestAnimationFrame(this._animate);
      }
    }

// דוגמת שימוש בסמארטי:
// const canvas = document.getElementById('smartyOrbCanvas');
// const orb = new SmartyLiveOrb(canvas);
//
// 1. בעת שסמארטי או המשתמש מדברים (ערבול פראי ומהיר כמו בסרטון):
// orb.setState('smartySpeaking');
//
// 2. שליטה ישירה מהקוד על הקצב והפראות:
// orb.setParams({ speed: 2.5, wildness: 0.92, energy: 0.88, swirl: 0.65 });
//
// 3. חיבור בזמן אמת לעוצמת קול (0.0 עד 1.0):
// orb.feedAudioLevel(currentRmsVolume);
