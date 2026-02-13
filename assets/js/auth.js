// assets/js/auth.js
// Production auth flows (email/password + Google OAuth). No demo fallbacks.

(function () {
  function apiBase() {
    return (typeof window !== 'undefined' && window.API_BASE) ? window.API_BASE : 'http://127.0.0.1:8010';
  }

  function setToast(msg, type) {
    try {
      localStorage.setItem('gv_toast', JSON.stringify({ msg: String(msg || ''), type: String(type || 'info'), ts: Date.now() }));
    } catch (_) {}
  }

  function show(box, msg) {
    if (!box) return;
    box.textContent = msg;
    box.style.display = 'block';
    try {
      box.setAttribute('aria-hidden', 'false');
      box.focus();
    } catch (_) {}
  }

  function hide(box) {
    if (!box) return;
    box.style.display = 'none';
    box.textContent = '';
    try { box.setAttribute('aria-hidden', 'true'); } catch (_) {}
  }

  async function readErrorMessage(res) {
    const text = await res.text().catch(() => '');
    if (!text) return `Erro (${res.status})`;
    try {
      const data = JSON.parse(text);
      return data.detail || data.message || text;
    } catch (_) {
      return text;
    }
  }

  function persistSession(data, fallbackEmail) {
    const token = data && (data.access_token || data.token);
    if (!token) throw new Error('Token não recebido do servidor.');

    localStorage.setItem('gv_token', token);
    if (data && data.user) {
      localStorage.setItem('gv_user', JSON.stringify(data.user));
      if (data.user.email) localStorage.setItem('gv_email', String(data.user.email));
      if (data.user.role) localStorage.setItem('gv_role', String(data.user.role));
    } else if (fallbackEmail) {
      localStorage.setItem('gv_user', JSON.stringify({ email: fallbackEmail }));
      localStorage.setItem('gv_email', String(fallbackEmail));
    }

    try {
      if (data && data.account && data.account.id) localStorage.setItem('gv_account_id', String(data.account.id));
    } catch (_) {}
  }

  document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('login-form');
    if (!form) return;

    const emailInput = document.getElementById('login-email');
    const passwordInput = document.getElementById('login-password');
    const submitBtn = document.getElementById('login-submit') || form.querySelector("button[type='submit']");

    const successBox = document.getElementById('success-box');
    const errorBox = document.getElementById('error-box');

    const googleBtn = document.getElementById('google-btn');
    const forgotLink = document.getElementById('forgot-link');
    const toggleCreate = document.getElementById('toggle-create');
    const createForm = document.getElementById('create-form');
    const createCancel = document.getElementById('create-cancel');
    const createSubmit = document.getElementById('create-submit');

    function redirectAfterAuth(role) {
      const r = String(role || '').toLowerCase();
      window.location.href = (r === 'admin') ? 'admin.html' : 'dashboard.html';
    }

    if (googleBtn && !googleBtn.dataset.gvBound) {
      googleBtn.addEventListener('click', () => {
        window.location.href = `${apiBase()}/auth/google/login`;
      });
      googleBtn.dataset.gvBound = '1';
    }

    if (forgotLink && !forgotLink.dataset.gvBound) {
      forgotLink.addEventListener('click', async (e) => {
        e.preventDefault();
        hide(errorBox);
        hide(successBox);
        const email = (emailInput?.value || '').trim().toLowerCase();
        if (!email) {
          show(errorBox, 'Insira o seu email para recuperar a palavra-passe.');
          return;
        }
        try {
          const res = await fetch(`${apiBase()}/auth/forgot-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
          });
          if (!res.ok) throw new Error(await readErrorMessage(res));
          show(successBox, 'Se a conta existir, enviámos um link de redefinição para o seu email.');
        } catch (err) {
          show(errorBox, err && err.message ? err.message : 'Não foi possível enviar o email.');
        }
      });
      forgotLink.dataset.gvBound = '1';
    }

    if (toggleCreate && createForm && !toggleCreate.dataset.gvBound) {
      toggleCreate.addEventListener('click', () => {
        const isOpen = createForm.style.display !== 'none';
        createForm.style.display = isOpen ? 'none' : 'grid';
        createForm.setAttribute('aria-hidden', isOpen ? 'true' : 'false');
        toggleCreate.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
      });
      toggleCreate.dataset.gvBound = '1';
    }

    if (createCancel && createForm && !createCancel.dataset.gvBound) {
      createCancel.addEventListener('click', () => {
        createForm.style.display = 'none';
        createForm.setAttribute('aria-hidden', 'true');
        if (toggleCreate) toggleCreate.setAttribute('aria-expanded', 'false');
      });
      createCancel.dataset.gvBound = '1';
    }

    if (createForm && !createForm.dataset.gvHandler) {
      createForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        hide(errorBox);
        hide(successBox);

        const email = (document.getElementById('create-email')?.value || '').trim().toLowerCase();
        const password = (document.getElementById('create-password')?.value || '').trim();
        const confirm = (document.getElementById('create-password-confirm')?.value || '').trim();
        const sector_focus = (document.getElementById('create-sector')?.value || 'agro').trim();

        if (!email || !password || !sector_focus) {
          show(errorBox, 'Preencha email, palavra-passe e tipo de conta.');
          return;
        }
        if (password !== confirm) {
          show(errorBox, 'As palavras-passe não coincidem.');
          return;
        }

        if (createSubmit) createSubmit.disabled = true;
        try {
          const res = await fetch(`${apiBase()}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, sector_focus }),
          });
          if (!res.ok) throw new Error(await readErrorMessage(res));
          const data = await res.json().catch(() => ({}));
          persistSession(data, email);
          setToast('Conta criada com sucesso.', 'success');
          redirectAfterAuth((data.user && data.user.role) || 'cliente');
        } catch (err) {
          show(errorBox, err && err.message ? err.message : 'Erro ao criar conta.');
        } finally {
          if (createSubmit) createSubmit.disabled = false;
        }
      });
      createForm.dataset.gvHandler = '1';
    }

    if (!form.dataset.gvHandler) {
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

        if (submitBtn) submitBtn.disabled = true;
        try {
          const res = await fetch(`${apiBase()}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
          });
          if (!res.ok) throw new Error(await readErrorMessage(res));
          const data = await res.json().catch(() => ({}));
          persistSession(data, email);
          setToast('Login bem-sucedido.', 'success');
          redirectAfterAuth((data.user && data.user.role) || 'cliente');
        } catch (err) {
          show(errorBox, err && err.message ? err.message : 'Erro no login.');
        } finally {
          if (submitBtn) submitBtn.disabled = false;
        }
      });
      form.dataset.gvHandler = '1';
    }
  });
})();
