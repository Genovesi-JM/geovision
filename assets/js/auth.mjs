// assets/js/auth.mjs
import { API_BASE as MODULE_API_BASE } from './config.mjs';

const API_BASE = MODULE_API_BASE || window.API_BASE || 'http://127.0.0.1:8010';

console.log('auth.mjs loaded (module) ✅');

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('login-form');
  if (!form) return;
  if (form.dataset && form.dataset.gvHandler === '1') return;

  const emailInput = document.getElementById('login-email');
  const passwordInput = document.getElementById('login-password');
  const successBox = document.getElementById('success-box');
  const errorBox = document.getElementById('error-box');
  const submitBtn = form.querySelector("button[type='submit']");

  function show(box, msg) {
    if (!box) return;
    box.textContent = msg;
    box.style.display = 'block';
    try {
      box.setAttribute('aria-hidden', 'false');
      box.focus();
    } catch (e) {}
  }
  function hide(box) {
    if (!box) return;
    box.style.display = 'none';
    box.textContent = '';
    try { box.setAttribute('aria-hidden', 'true'); } catch (e) {}
  }

  function ensureSpinner(btn) {
    if (!btn) return null;
    let spinner = btn.querySelector('.spinner');
    if (!spinner) {
      spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      btn.prepend(spinner);
    }
    return spinner;
  }

  function setToastAndNavigate(msg, type, url) {
    try {
      localStorage.setItem('gv_toast', JSON.stringify({ msg: String(msg || ''), type: String(type || 'info'), ts: Date.now() }));
    } catch (e) {}
    // navigate immediately; toast will be shown on next page load by app.js
    window.location.href = url;
  }

  async function readErrorMessage(res) {
    const text = await res.text().catch(() => '');
    if (!text) return `Erro (${res.status})`;
    try {
      const data = JSON.parse(text);
      return data.detail || data.message || text;
    } catch {
      return text;
    }
  }

  // Google login handler: ensure we hit the backend over HTTP instead of file://
  const googleLink = document.getElementById('google-login');
  if (googleLink && !googleLink.dataset.gvGoogle) {
    googleLink.addEventListener('click', (e) => {
      e.preventDefault();
      const target = `${API_BASE}/auth/google/login`;
      try { googleLink.setAttribute('aria-busy', 'true'); } catch (err) {}
      window.location.href = target;
    });
    googleLink.dataset.gvGoogle = '1';
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    hide(errorBox);
    hide(successBox);

    const email = (emailInput?.value || '').trim().toLowerCase();
    const password = (passwordInput?.value || '').trim();

    if (!email || !password) {
      show(errorBox, 'Por favor preencha todos os campos.');
      return;
    }

    try {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.classList.add('loading');
        submitBtn.querySelector('.btn-text')?.classList.add('visually-hidden');
        ensureSpinner(submitBtn);
      }
      form.setAttribute('aria-busy', 'true');

      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) throw new Error(await readErrorMessage(res));

      const data = await res.json().catch(() => ({}));
      const token = data.access_token || data.token;
      if (!token) throw new Error('Token não recebido do servidor.');

      localStorage.setItem('gv_token', token);
      localStorage.setItem('gv_user', JSON.stringify(data.user || { email }));
      try { if (data.account && data.account.id) localStorage.setItem('gv_account_id', data.account.id); } catch(e) {}
      try { localStorage.setItem('gv_email', (data.user && data.user.email) || email); } catch(e) {}
      try { if (data.user && data.user.role) localStorage.setItem('gv_role', data.user.role); } catch(e) {}

      const isAdmin = (data.user && data.user.role === 'admin');
      setToastAndNavigate('Login bem-sucedido! A abrir o painel…', 'success', isAdmin ? 'admin.html' : 'dashboard.html');
    } catch (err) {
      console.error(err);
      show(errorBox, err.message || 'Erro no login.');
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.classList.remove('loading');
        submitBtn.querySelector('.btn-text')?.classList.remove('visually-hidden');
        const sp = submitBtn.querySelector('.spinner');
        if (sp) sp.remove();
      }
      try { form.removeAttribute('aria-busy'); } catch (e) {}
    }
  });
  // mark handler attached so fallbacks don't double-attach
  try { form.dataset.gvHandler = '1'; window.GV_LOGIN_ATTACHED = true; } catch(e) {}
  // create-account handlers (module)
  try {
    const showCreate = document.getElementById('show-create-btn');
    const createForm = document.getElementById('create-form');
    const createCancel = document.getElementById('create-cancel');
    if (showCreate && createForm) {
      showCreate.addEventListener('click', () => {
        const expanded = showCreate.getAttribute('aria-expanded') === 'true';
        showCreate.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        if (expanded) {
          createForm.style.display = 'none';
          createForm.setAttribute('aria-hidden','true');
        } else {
          createForm.style.display = 'block';
          createForm.setAttribute('aria-hidden','false');
        }
      });
    }

    if (createForm && !createForm.dataset.gvHandler) {
      createForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = (document.getElementById('create-email')?.value || '').trim().toLowerCase();
        const password = (document.getElementById('create-password')?.value || '').trim();
        const confirm = (document.getElementById('create-password-confirm')?.value || '').trim();
        if (!email || !password) return alert('Preencha email e senha.');
        if (password !== confirm) return alert('As senhas não coincidem.');
        try {
          const res = await fetch(`${API_BASE}/auth/register`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
          });
          if (!res.ok) throw new Error(await readErrorMessage(res));
          const data = await res.json().catch(()=>({}));
          const token = data.access_token || data.token || data.token_access;
          if (!token) {
            // still navigate and store a toast
            setToastAndNavigate('Conta criada. Faça login.', 'success', 'login.html');
            return;
          }
          localStorage.setItem('gv_token', token);
          localStorage.setItem('gv_user', JSON.stringify(data.user || { email }));
          try { if (data.account && data.account.id) localStorage.setItem('gv_account_id', data.account.id); } catch(e) {}
          try { localStorage.setItem('gv_email', email); } catch(e) {}
          try { localStorage.setItem('gv_role', (data.user && data.user.role) || 'cliente'); } catch(e) {}
          setToastAndNavigate('Conta criada com sucesso — a abrir painel…', 'success', 'dashboard.html');
        } catch (err) {
          console.error('create-account', err);
          alert('Erro ao criar conta. Tente novamente.');
        }
      });
      createForm.dataset.gvHandler = '1';
    }

    if (createCancel) {
      createCancel.addEventListener('click', () => {
        const createForm = document.getElementById('create-form');
        if (createForm) {
          createForm.style.display = 'none';
          createForm.setAttribute('aria-hidden','true');
        }
      });
    }
  } catch(e) { console.error('create-account attach failed', e); }
});

