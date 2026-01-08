// assets/js/auth.js
console.log("auth loaded ✅");

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("login-form");
  if (!form) return;
  if (form.dataset && form.dataset.gvHandler === '1') return;

  const emailInput = document.getElementById("login-email");
  const passwordInput = document.getElementById("login-password");
  const successBox = document.getElementById("success-box");
  const errorBox = document.getElementById("error-box");
  const submitBtn = form.querySelector("button[type='submit']");
  const googleLink = document.getElementById('google-login');

  function show(box, msg) {
    if (!box) return;
    box.textContent = msg;
    box.style.display = "block";
    // make it visible to assistive tech and focus so screen readers announce it
    try {
      box.setAttribute("aria-hidden", "false");
      box.focus();
    } catch (e) {
      // ignore if not focusable
    }
  }
  function hide(box) {
  
  function setToastAndNavigate(msg, type, url) {
    try { localStorage.setItem('gv_toast', JSON.stringify({ msg: String(msg || ''), type: String(type || 'info'), ts: Date.now() })); } catch (e) {}
    window.location.href = url;
  }
    if (!box) return;
    box.style.display = "none";
    box.textContent = "";
    try {
      box.setAttribute("aria-hidden", "true");
    } catch (e) {}
  }

  // Google login: avoid file:// and send to backend base
  if (googleLink && !googleLink.dataset.gvGoogle) {
    googleLink.addEventListener('click', function (e) {
      e.preventDefault();
      const api = window.API_BASE || "http://127.0.0.1:8010";
      const target = api + "/auth/google/login";
      try { googleLink.setAttribute('aria-busy','true'); } catch (err) {}
      window.location.href = target;
    });
    googleLink.dataset.gvGoogle = '1';
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hide(errorBox);
    hide(successBox);

    // announce busy state for assistive tech
    try {
      form.setAttribute("aria-busy", "true");
    } catch (e) {}

    const email = (emailInput?.value || "").trim().toLowerCase();
    const password = (passwordInput?.value || "").trim();

    if (!email || !password) {
      show(errorBox, "Por favor preencha todos os campos.");
      return;
    }

    const API_BASE = window.API_BASE || "http://127.0.0.1:8090";

    try {
      if (submitBtn) {
        submitBtn.disabled = true;
        // ensure text wrapper for visual hiding when spinner used
        if (!submitBtn.querySelector('.btn-text')) {
          const span = document.createElement('span');
          span.className = 'btn-text';
          span.textContent = submitBtn.textContent;
          submitBtn.textContent = '';
          submitBtn.appendChild(span);
        }
        submitBtn.classList.add('loading');
        submitBtn.querySelector('.btn-text').classList.add('visually-hidden');
        // add spinner element
        if (!submitBtn.querySelector('.spinner')) {
          const s = document.createElement('span');
          s.className = 'spinner';
          s.setAttribute('aria-hidden', 'true');
          submitBtn.prepend(s);
        }
      }

      // tenta backend real
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      // fallback demo se o backend falhar ou estiver offline
      if (!res.ok) {
        // DEMO simples (igual à hint da tua página)
        const DEMO_USERS = {
          "teste@admin.com": { password: "123456", role: "admin" },
          "teste@clientes.com": { password: "123456", role: "cliente" },
        };

        const demo = DEMO_USERS[email];
        if (!demo || demo.password !== password) {
          const txt = await res.text().catch(() => "");
          throw new Error(txt || "Credenciais incorretas ou servidor indisponível.");
        }

        localStorage.setItem("gv_token", "demo-token");
        localStorage.setItem("gv_user", JSON.stringify({ email, role: demo.role }));
        // persist toast and navigate immediately; toast shown by app.js on next page
        setToastAndNavigate("Credenciais corretas! A abrir o painel…", 'success', demo.role === "admin" ? "admin.html" : "dashboard.html");
        return;
      }

      const data = await res.json().catch(() => ({}));
      const token = data.access_token || data.token;

      if (!token) throw new Error("Token não recebido do servidor.");

    localStorage.setItem("gv_token", token);
    localStorage.setItem("gv_user", JSON.stringify(data.user || { email }));`r`n    try { if (data.account && data.account.id) localStorage.setItem('gv_account_id', data.account.id); } catch(e) {}
    try { localStorage.setItem('gv_email', email); } catch(e) {}
    try { localStorage.setItem('gv_role', (data.user && data.user.role) || (email === 'teste@admin.com' ? 'admin' : 'cliente')); } catch(e) {}
        
        // persist toast and navigate immediately; toast shown by app.js on next page
        setToastAndNavigate("Login bem-sucedido! A abrir o painel…", 'success', isAdmin ? "admin.html" : "dashboard.html");
    } catch (err) {
      console.error(err);
      show(errorBox, err.message || "Erro no login.");
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.classList.remove('loading');
        const txt = submitBtn.querySelector('.btn-text');
        if (txt) {
          txt.classList.remove('visually-hidden');
        } else {
          submitBtn.textContent = 'Iniciar Sessão';
        }
        const sp = submitBtn.querySelector('.spinner');
        if (sp) sp.remove();
      }
      try {
        form.removeAttribute("aria-busy");
      } catch (e) {}
    }
  });
  try { form.dataset.gvHandler = '1'; window.GV_LOGIN_ATTACHED = true; } catch (e) {}

  // create-account handlers (legacy)
  try {
    const showCreate = document.getElementById('show-create-btn');
    const createForm = document.getElementById('create-form');
    const createCancel = document.getElementById('create-cancel');
    if (showCreate && createForm) {
      showCreate.addEventListener('click', function () {
        const expanded = showCreate.getAttribute('aria-expanded') === 'true';
        showCreate.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        if (expanded) {
          createForm.style.display = 'none'; createForm.setAttribute('aria-hidden','true');
        } else { createForm.style.display = 'block'; createForm.setAttribute('aria-hidden','false'); }
      });
    }

    if (createForm && createForm.dataset.gvHandler !== '1') {
      createForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        const email = (document.getElementById('create-email')?.value || '').trim().toLowerCase();
        const password = (document.getElementById('create-password')?.value || '').trim();
        const confirm = (document.getElementById('create-password-confirm')?.value || '').trim();
        if (!email || !password) { alert('Preencha email e senha.'); return; }
        if (password !== confirm) { alert('As senhas não coincidem.'); return; }
        try {
          const res = await fetch((window.API_BASE||'http://127.0.0.1:8010') + '/auth/register', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password })
          });
          if (!res.ok) {
            // fallback demo
            localStorage.setItem('gv_token','demo-token');
            localStorage.setItem('gv_user', JSON.stringify({ email, role: 'cliente' }));
            try { localStorage.setItem('gv_email', email); } catch(e) {}
            try { localStorage.setItem('gv_role', 'cliente'); } catch(e) {}
            try { localStorage.setItem('gv_toast', JSON.stringify({ msg: 'Conta criada (modo demo). A redirecionar…', type: 'success', ts: Date.now() })); } catch(e) {}
            window.location.href = 'dashboard.html';
            return;
          }
          const data = await res.json().catch(()=>({}));
          const token = data.access_token || data.token;
          if (!token) { try { localStorage.setItem('gv_toast', JSON.stringify({ msg: 'Conta criada. Faça login.', type: 'success', ts: Date.now() })); } catch(e) {} ; window.location.href='login.html'; return; }
          localStorage.setItem('gv_token', token);
          localStorage.setItem('gv_user', JSON.stringify(data.user || { email }));
          try { localStorage.setItem('gv_email', email); } catch(e) {}
          try { localStorage.setItem('gv_role', (data.user && data.user.role) || 'cliente'); } catch(e) {}
          try { localStorage.setItem('gv_toast', JSON.stringify({ msg: 'Conta criada com sucesso — a abrir painel…', type: 'success', ts: Date.now() })); } catch(e) {}
          window.location.href = 'dashboard.html';
        } catch (err) { console.error(err); alert('Erro ao criar conta.'); }
      });
      createForm.dataset.gvHandler = '1';
    }

    if (createCancel) createCancel.addEventListener('click', function(){ if (createForm) { createForm.style.display='none'; createForm.setAttribute('aria-hidden','true'); } });
  } catch(e) { console.error('create-account attach failed (legacy)', e); }
});
