// Explicit deployment mode only. This controls presentation, never authorization.
(function () {
  'use strict';
  if (window.GV_RUNTIME?.mode !== 'pilot') return;
  document.documentElement.dataset.pilot = 'true';
  document.documentElement.lang = 'es';
  document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('login-form');
    if (!form) return;
    for (const id of ['google-btn', 'microsoft-btn', 'forgot-link', 'forgot-email-link', 'toggle-create', 'create-form', 'forgot-email-overlay']) {
      const element = document.getElementById(id);
      if (element) { element.hidden = true; element.disabled = true; element.setAttribute('aria-hidden', 'true'); }
    }
    form.querySelectorAll('.split').forEach(element => { element.hidden = true; });
    document.querySelectorAll('[data-lang], .gv-chat-toggle').forEach(element => { element.hidden = true; });
    document.getElementById('pilot-notice').hidden = false;
    const hint = document.querySelector('.shell > .hint');
    if (hint) hint.hidden = true;
    const toggle = document.querySelector('[data-target="login-password"]');
    if (toggle) {
      toggle.textContent = 'Ver'; toggle.title = 'Mostrar contraseña'; toggle.setAttribute('aria-label', toggle.title);
      toggle.addEventListener('click', () => {
        const visible = document.getElementById('login-password').type === 'text';
        toggle.textContent = visible ? 'Ocultar' : 'Ver';
        toggle.title = visible ? 'Ocultar contraseña' : 'Mostrar contraseña';
        toggle.setAttribute('aria-label', toggle.title);
      });
    }
    const submit = document.getElementById('login-submit');
    const status = document.createElement('div');
    status.className = 'pilot-status';
    status.id = 'pilot-service-status';
    const text = document.createElement('span');
    text.setAttribute('role', 'status');
    text.setAttribute('aria-live', 'polite');
    const check = document.createElement('button');
    check.type = 'button'; check.className = 'btn-ghost'; check.textContent = 'Comprobar servicio'; check.hidden = true;
    status.append(text, check); form.after(status);
    let ready = false;
    let checking = false;
    function unavailable() {
      ready = false;
      submit.disabled = true;
      text.textContent = 'El servicio no está disponible. Puedes comprobar su estado sin enviar tu contraseña.';
      check.hidden = false;
    }
    async function checkService() {
      if (checking) return;
      checking = true; ready = false; submit.disabled = true; check.hidden = true;
      text.textContent = 'Comprobando el servicio…';
      const controller = new AbortController();
      const warmup = setTimeout(() => { text.textContent = 'Preparando el servicio de pruebas. El primer acceso puede tardar un momento…'; }, 5000);
      const timeout = setTimeout(() => controller.abort(), 110000);
      try {
        const response = await fetch(`${window.API_BASE}/ready`, { method: 'GET', cache: 'no-store', credentials: 'same-origin', redirect: 'error', signal: controller.signal });
        if (!response.ok) throw new Error('service_not_ready');
        const body = await response.json();
        if (body?.status !== 'ready') throw new Error('service_not_ready');
        ready = true; submit.disabled = false;
        text.textContent = 'Servicio disponible. Puedes iniciar sesión.';
      } catch (_) { unavailable(); }
      finally { clearTimeout(warmup); clearTimeout(timeout); checking = false; }
    }
    window.GV_PILOT_UI = Object.freeze({ isReady: () => ready, unavailable });
    check.addEventListener('click', checkService);
    checkService(); // A single health read, never an automatic login or retry.
  });
})();
