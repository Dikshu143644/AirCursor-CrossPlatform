// AirCursor Web Remote & PWA Controller
// 100% Offline Capable, Zero External Dependencies

(function () {
  'use strict';

  // State
  const pairingParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  let accessToken = pairingParams.get('token') || sessionStorage.getItem('aircursor-access-token') || '';
  if (accessToken) {
    sessionStorage.setItem('aircursor-access-token', accessToken);
    if (window.location.hash) history.replaceState(null, '', window.location.pathname + window.location.search);
  }
  let trackingActive = false;
  let scrollModeActive = false;
  let isGyroStreaming = false;
  let touchActive = false;
  let lastTouchX = 0;
  let lastTouchY = 0;

  // DOM Elements
  const statusBadge = document.getElementById('status-badge');
  const statusText = document.getElementById('status-text');
  const modeBadge = document.getElementById('mode-badge');
  const valYaw = document.getElementById('val-yaw');
  const valPitch = document.getElementById('val-pitch');
  const valRoll = document.getElementById('val-roll');
  const valFps = document.getElementById('val-fps');
  const valSamples = document.getElementById('val-samples');
  const valUptime = document.getElementById('val-uptime');
  
  const btnToggleTracking = document.getElementById('btn-toggle-tracking');
  const btnRecenter = document.getElementById('btn-recenter');
  const btnToggleScroll = document.getElementById('btn-toggle-scroll');
  const btnLeftClick = document.getElementById('btn-left-click');
  const btnRightClick = document.getElementById('btn-right-click');
  const btnDouble = document.getElementById('btn-double');
  const btnGyro = document.getElementById('btn-gyro');

  const trackpad = document.getElementById('trackpad');
  const trackpadDot = document.getElementById('trackpad-dot');

  const rangeSensitivity = document.getElementById('range-sensitivity');
  const valSensitivity = document.getElementById('val-sensitivity');
  const rangeDeadzone = document.getElementById('range-deadzone');
  const valDeadzone = document.getElementById('val-deadzone');
  const rangeDwell = document.getElementById('range-dwell');
  const valDwell = document.getElementById('val-dwell');
  const toggleSmartDwell = document.getElementById('toggle-smart-dwell');

  // Register PWA Service Worker
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').then(
        (reg) => console.log('[PWA] ServiceWorker registered with scope:', reg.scope),
        (err) => console.warn('[PWA] ServiceWorker registration failed:', err)
      );
    });
  }

  // API Call Helpers
  function getAuthorizationHeaders() {
    if (!accessToken) {
      accessToken = window.prompt('Enter the AirCursor pairing token displayed on the host computer:') || '';
      if (accessToken) sessionStorage.setItem('aircursor-access-token', accessToken);
    }
    if (!accessToken) return null;
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + accessToken
    };
  }

  async function handleUnauthorized(response) {
    if (response && response.status === 401) {
      accessToken = '';
      sessionStorage.removeItem('aircursor-access-token');
      alert('AirCursor pairing token rejected. Scan the host QR code again.');
      return true;
    }
    return false;
  }

  async function postAction(actionName) {
    try {
      const headers = getAuthorizationHeaders();
      if (!headers) return;
      const res = await fetch('/api/action', {
        method: 'POST',
        headers,
        body: JSON.stringify({ action: actionName })
      });
      if (await handleUnauthorized(res)) return;
      const data = await res.json();
      updateUIStatus(data);
    } catch (err) {
      console.warn('Action failed:', actionName, err);
    }
  }

  async function postTelemetry(yaw, pitch, roll) {
    try {
      const headers = getAuthorizationHeaders();
      if (!headers) return;
      const response = await fetch('/api/telemetry', {
        method: 'POST',
        headers,
        body: JSON.stringify({ yaw: yaw, pitch: pitch, roll: roll })
      });
      await handleUnauthorized(response);
    } catch (err) {
      // Ignore network jitter
    }
  }

  async function updateSettings(key, val) {
    try {
      const headers = getAuthorizationHeaders();
      if (!headers) return;
      const payload = {};
      payload[key] = val;
      const response = await fetch('/api/settings', {
        method: 'POST',
        headers,
        body: JSON.stringify(payload)
      });
      await handleUnauthorized(response);
    } catch (err) {
      console.warn('Failed to update setting:', key, err);
    }
  }

  // Update UI Elements
  function updateUIStatus(data) {
    if (!data) return;

    if (data.tracking !== undefined) {
      trackingActive = data.tracking;
      if (trackingActive) {
        statusBadge.className = 'status-badge active';
        statusText.textContent = 'TRACKING';
        if (btnToggleTracking) btnToggleTracking.textContent = '⏸ Pause Tracking';
      } else {
        statusBadge.className = 'status-badge paused';
        statusText.textContent = 'PAUSED';
        if (btnToggleTracking) btnToggleTracking.textContent = '▶ Resume Tracking';
      }
    }

    if (data.mode && modeBadge) {
      modeBadge.textContent = data.mode.toUpperCase();
    }

    if (data.telemetry) {
      if (valYaw) valYaw.textContent = data.telemetry.yaw ? data.telemetry.yaw.toFixed(1) + '°' : '0.0°';
      if (valPitch) valPitch.textContent = data.telemetry.pitch ? data.telemetry.pitch.toFixed(1) + '°' : '0.0°';
      if (valRoll) valRoll.textContent = data.telemetry.roll ? data.telemetry.roll.toFixed(1) + '°' : '0.0°';
    }

    if (data.fps !== undefined && valFps) {
      valFps.textContent = Math.round(data.fps) + ' Hz';
    }

    if (data.sensors && valSamples) {
      valSamples.textContent = data.sensors.samples_received || 0;
    }

    if (data.uptime_seconds !== undefined && valUptime) {
      const s = Math.floor(data.uptime_seconds);
      const mins = Math.floor(s / 60);
      const secs = s % 60;
      valUptime.textContent = mins + 'm ' + secs + 's';
    }

    if (data.scroll_mode !== undefined) {
      scrollModeActive = data.scroll_mode;
      if (btnToggleScroll) {
        btnToggleScroll.className = scrollModeActive ? 'btn btn-accent' : 'btn';
        btnToggleScroll.textContent = scrollModeActive ? '📜 Scroll: ON' : '🖱 Mode: POINTER';
      }
    }
  }

  // Poll server status regularly
  async function fetchStatus() {
    try {
      const res = await fetch('/status');
      if (res.ok) {
        const data = await res.json();
        updateUIStatus(data);
      }
    } catch (err) {
      statusBadge.className = 'status-badge';
      statusText.textContent = 'CONNECTING...';
    }
  }

  // Fetch settings on startup
  async function fetchSettings() {
    try {
      const res = await fetch('/api/settings');
      if (res.ok) {
        const cfg = await res.json();
        if (cfg.pointer) {
          if (rangeSensitivity && cfg.pointer.sensitivity !== undefined) {
            rangeSensitivity.value = cfg.pointer.sensitivity;
            valSensitivity.textContent = cfg.pointer.sensitivity.toFixed(1) + 'x';
          }
          if (rangeDeadzone && cfg.pointer.deadzone !== undefined) {
            rangeDeadzone.value = cfg.pointer.deadzone;
            valDeadzone.textContent = cfg.pointer.deadzone.toFixed(1) + '°/s';
          }
        }
        if (cfg.dwell) {
          if (rangeDwell && cfg.dwell.duration !== undefined) {
            rangeDwell.value = cfg.dwell.duration;
            valDwell.textContent = cfg.dwell.duration.toFixed(2) + 's';
          }
          if (toggleSmartDwell && cfg.dwell.smart !== undefined) {
            toggleSmartDwell.checked = cfg.dwell.smart;
          }
        }
      }
    } catch (err) {
      console.warn('Could not fetch settings:', err);
    }
  }

  // Button Listeners
  if (btnToggleTracking) {
    btnToggleTracking.addEventListener('click', () => postAction('toggle_tracking'));
  }
  if (btnRecenter) {
    btnRecenter.addEventListener('click', () => postAction('recenter'));
  }
  if (btnToggleScroll) {
    btnToggleScroll.addEventListener('click', () => postAction('toggle_scroll'));
  }
  if (btnLeftClick) {
    btnLeftClick.addEventListener('click', () => postAction('left_click'));
  }
  if (btnRightClick) {
    btnRightClick.addEventListener('click', () => postAction('right_click'));
  }
  if (btnDouble) {
    btnDouble.addEventListener('click', () => postAction('double_click'));
  }

  // Sliders
  if (rangeSensitivity) {
    rangeSensitivity.addEventListener('input', (e) => {
      const v = parseFloat(e.target.value);
      valSensitivity.textContent = v.toFixed(1) + 'x';
      updateSettings('sensitivity', v);
    });
  }
  if (rangeDeadzone) {
    rangeDeadzone.addEventListener('input', (e) => {
      const v = parseFloat(e.target.value);
      valDeadzone.textContent = v.toFixed(1) + '°/s';
      updateSettings('deadzone', v);
    });
  }
  if (rangeDwell) {
    rangeDwell.addEventListener('input', (e) => {
      const v = parseFloat(e.target.value);
      valDwell.textContent = v.toFixed(2) + 's';
      updateSettings('dwell_duration', v);
    });
  }
  if (toggleSmartDwell) {
    toggleSmartDwell.addEventListener('change', (e) => {
      updateSettings('smart_dwell', e.target.checked);
    });
  }

  // Trackpad Touch Gestures
  if (trackpad) {
    const handleStart = (x, y) => {
      touchActive = true;
      lastTouchX = x;
      lastTouchY = y;
      trackpad.classList.add('active');
      if (trackpadDot) {
        trackpadDot.style.display = 'block';
        trackpadDot.style.left = x + 'px';
        trackpadDot.style.top = y + 'px';
      }
    };

    const handleMove = (x, y) => {
      if (!touchActive) return;
      const dx = x - lastTouchX;
      const dy = y - lastTouchY;
      lastTouchX = x;
      lastTouchY = y;
      if (trackpadDot) {
        trackpadDot.style.left = x + 'px';
        trackpadDot.style.top = y + 'px';
      }
      // Send relative motion via telemetry API (simulated yaw/pitch delta)
      postTelemetry(dx * 0.15, dy * 0.15, 0.0);
    };

    const handleEnd = () => {
      touchActive = false;
      trackpad.classList.remove('active');
      if (trackpadDot) {
        trackpadDot.style.display = 'none';
      }
    };

    trackpad.addEventListener('pointerdown', (e) => {
      const rect = trackpad.getBoundingClientRect();
      handleStart(e.clientX - rect.left, e.clientY - rect.top);
      trackpad.setPointerCapture(e.pointerId);
    });
    trackpad.addEventListener('pointermove', (e) => {
      const rect = trackpad.getBoundingClientRect();
      handleMove(e.clientX - rect.left, e.clientY - rect.top);
    });
    trackpad.addEventListener('pointerup', handleEnd);
    trackpad.addEventListener('pointercancel', handleEnd);
  }

  // DeviceOrientation (Mobile Gyroscope Streamer)
  if (btnGyro) {
    btnGyro.addEventListener('click', async () => {
      if (isGyroStreaming) {
        window.removeEventListener('deviceorientation', handleOrientation);
        isGyroStreaming = false;
        btnGyro.textContent = '📱 Stream Phone Gyro';
        btnGyro.classList.remove('btn-primary');
        return;
      }

      // iOS 13+ permission request
      if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
        try {
          const perm = await DeviceOrientationEvent.requestPermission();
          if (perm !== 'granted') {
            alert('Sensor permission denied');
            return;
          }
        } catch (e) {
          console.warn('Orientation permission error:', e);
        }
      }

      window.addEventListener('deviceorientation', handleOrientation);
      isGyroStreaming = true;
      btnGyro.textContent = '⏹ Stop Gyro Stream';
      btnGyro.classList.add('btn-primary');
    });

    let lastSend = 0;
    function handleOrientation(e) {
      const now = performance.now();
      if (now - lastSend < 20) return; // limit to 50Hz
      lastSend = now;
      const alpha = e.alpha || 0; // z / yaw
      const beta = e.beta || 0;   // x / pitch
      const gamma = e.gamma || 0; // y / roll
      postTelemetry(alpha, beta, gamma);
    }
  }

  // Startup
  fetchStatus();
  fetchSettings();
  setInterval(fetchStatus, 750);

})();
