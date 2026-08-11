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
      if (data.user.name) localStorage.setItem('gv_name', String(data.user.name));
    } else if (fallbackEmail) {
      localStorage.setItem('gv_user', JSON.stringify({ email: fallbackEmail }));
      localStorage.setItem('gv_email', String(fallbackEmail));
    }

    try {
      if (data && data.account && data.account.id) localStorage.setItem('gv_account_id', String(data.account.id));
      if (data && data.account && data.account.name) localStorage.setItem('gv_account_name', String(data.account.name));
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
      const params = new URLSearchParams(window.location.search);
      const returnTo = params.get('return');
      // Strict validation: only allow relative paths starting with a
      // single slash and no protocol/scheme prefix (blocks //, javascript:,
      // data:, vbscript:, etc.)
      if (returnTo
          && returnTo.startsWith('/')
          && !returnTo.startsWith('//')
          && !/^[a-z]+:/i.test(returnTo)) {
        window.location.href = returnTo;
        return;
      }
      window.location.href = (r === 'admin') ? 'admin.html' : 'dashboard.html';
    }

    if (googleBtn && !googleBtn.dataset.gvBound) {
      googleBtn.addEventListener('click', () => {
        window.location.href = `${apiBase()}/auth/google/login`;
      });
      googleBtn.dataset.gvBound = '1';
    }

    const microsoftBtn = document.getElementById('microsoft-btn');
    if (microsoftBtn && !microsoftBtn.dataset.gvBound) {
      microsoftBtn.addEventListener('click', () => {
        window.location.href = `${apiBase()}/auth/microsoft/login`;
      });
      microsoftBtn.dataset.gvBound = '1';
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

    // ---- Account-creation wizard (email → password → setup) ----
    const wizardBack = document.getElementById('wizard-back');
    const wizardNext = document.getElementById('wizard-next');
    const WIZ_TOTAL = 3;
    let wizardStep = 1;
    const isValidEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

    // Individual/home customers only see consumer-relevant sectors — industrial
    // ones (mining, demining, construction, infrastructure) are org-only.
    const INDIVIDUAL_PERSONAS = ['farm', 'site', 'device'];
    const INDIVIDUAL_SECTORS = ['agro', 'solar'];
    function filterSectorsForPersona() {
      const sel = document.getElementById('create-sector');
      const persona = document.getElementById('create-persona')?.value || 'farm';
      if (!sel) return;
      const individual = INDIVIDUAL_PERSONAS.includes(persona);
      [...sel.options].forEach((o) => {
        const ok = !individual || INDIVIDUAL_SECTORS.includes(o.value);
        o.hidden = !ok; o.disabled = !ok;
      });
      const current = [...sel.options].find((o) => o.value === sel.value);
      if (!current || current.hidden) sel.value = individual ? 'agro' : sel.value;
    }

    function showWizardStep(n) {
      if (!createForm) return;
      wizardStep = Math.min(Math.max(n, 1), WIZ_TOTAL);
      createForm.querySelectorAll('.wizard-step').forEach((s) => {
        const active = Number(s.dataset.step) === wizardStep;
        s.classList.toggle('active', active);
        s.hidden = !active;
      });
      createForm.querySelectorAll('.wizard-dot').forEach((d) => {
        const step = Number(d.dataset.dot);
        d.classList.toggle('active', step === wizardStep);
        d.classList.toggle('done', step < wizardStep);
      });
      if (wizardBack) wizardBack.style.display = wizardStep > 1 ? '' : 'none';
      if (wizardNext) wizardNext.style.display = wizardStep < WIZ_TOTAL ? '' : 'none';
      if (createSubmit) createSubmit.style.display = wizardStep < WIZ_TOTAL ? 'none' : '';
      if (wizardStep === WIZ_TOTAL) filterSectorsForPersona();
      const first = createForm.querySelector(`.wizard-step[data-step="${wizardStep}"] input, .wizard-step[data-step="${wizardStep}"] select`);
      if (first) setTimeout(() => first.focus(), 30);
    }

    function validateWizardStep(n) {
      hide(errorBox);
      if (n === 1) {
        const email = (document.getElementById('create-email')?.value || '').trim().toLowerCase();
        const confirm = (document.getElementById('create-email-confirm')?.value || '').trim().toLowerCase();
        if (!isValidEmail(email)) { show(errorBox, 'Introduza um email válido.'); return false; }
        if (email !== confirm) { show(errorBox, 'Os emails não coincidem.'); return false; }
      } else if (n === 2) {
        const password = document.getElementById('create-password')?.value || '';
        const confirm = document.getElementById('create-password-confirm')?.value || '';
        if (password.length < 6) { show(errorBox, 'A palavra-passe deve ter pelo menos 6 caracteres.'); return false; }
        if (password !== confirm) { show(errorBox, 'As palavras-passe não coincidem.'); return false; }
      }
      return true;
    }

    function advanceWizard() {
      if (validateWizardStep(wizardStep) && wizardStep < WIZ_TOTAL) showWizardStep(wizardStep + 1);
    }

    if (toggleCreate && createForm && !toggleCreate.dataset.gvBound) {
      toggleCreate.addEventListener('click', () => {
        const isOpen = createForm.style.display !== 'none';
        createForm.style.display = isOpen ? 'none' : 'grid';
        createForm.setAttribute('aria-hidden', isOpen ? 'true' : 'false');
        toggleCreate.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
        if (!isOpen) { hide(errorBox); showWizardStep(1); }
      });
      toggleCreate.dataset.gvBound = '1';
    }

    if (wizardNext && !wizardNext.dataset.gvBound) {
      wizardNext.addEventListener('click', advanceWizard);
      wizardNext.dataset.gvBound = '1';
    }
    const createPersona = document.getElementById('create-persona');
    if (createPersona && !createPersona.dataset.gvBound) {
      createPersona.addEventListener('change', filterSectorsForPersona);
      createPersona.dataset.gvBound = '1';
    }
    if (wizardBack && !wizardBack.dataset.gvBound) {
      wizardBack.addEventListener('click', () => { hide(errorBox); showWizardStep(wizardStep - 1); });
      wizardBack.dataset.gvBound = '1';
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
        // Enter / submit before the last step just advances the wizard.
        if (wizardStep < WIZ_TOTAL) { advanceWizard(); return; }
        hide(errorBox);
        hide(successBox);

        const email = (document.getElementById('create-email')?.value || '').trim().toLowerCase();
        const password = document.getElementById('create-password')?.value || '';
        const sector_focus = (document.getElementById('create-sector')?.value || 'agro').trim();
        const persona = document.getElementById('create-persona')?.value || 'farm';
        const entity_type = ['construction', 'business', 'enterprise'].includes(persona) ? 'company' : 'individual';

        if (!validateWizardStep(1)) { showWizardStep(1); return; }
        if (!validateWizardStep(2)) { showWizardStep(2); return; }

        if (createSubmit) createSubmit.disabled = true;
        try {
          localStorage.setItem('gv_persona', persona);
          const res = await fetch(`${apiBase()}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, sector_focus, entity_type }),
          });
          if (!res.ok) throw new Error(await readErrorMessage(res));
          const data = await res.json().catch(() => ({}));
          persistSession(data, email);
          try { if (data.account && data.account.id) localStorage.setItem('gv_persona_' + data.account.id, persona); } catch (_) {}
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
