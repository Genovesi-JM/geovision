/* assets/js/session.js
   Persistent session awareness for public pages.
   - If gv_token exists → replaces "Portal" link with user avatar + dropdown
   - If no token → keeps "Portal" / guest CTA
   Loaded on: index.html, loja.html, about.html, sectors.html, login.html
*/
(function () {
  'use strict';

  // Inject session dropdown CSS
  const css = document.createElement('style');
  css.textContent = `
    .gv-session-menu { position: relative; }
    .gv-session-btn {
      display: flex; align-items: center; gap: .5rem;
      background: rgba(34,197,94,.12); border: 1px solid rgba(34,197,94,.25);
      border-radius: 40px; padding: .35rem .8rem .35rem .35rem;
      cursor: pointer; color: var(--text-primary, #e2e8f0);
      font-size: .85rem; font-weight: 500; transition: all .2s;
    }
    .gv-session-btn:hover { background: rgba(34,197,94,.2); border-color: rgba(34,197,94,.4); }
    .gv-session-avatar {
      width: 30px; height: 30px; border-radius: 50%;
      background: linear-gradient(135deg, #22c55e, #06b6d4);
      display: flex; align-items: center; justify-content: center;
      font-size: .7rem; font-weight: 700; color: #020617;
      flex-shrink: 0;
    }
    .gv-session-avatar-lg {
      width: 40px; height: 40px; border-radius: 50%;
      background: linear-gradient(135deg, #22c55e, #06b6d4);
      display: flex; align-items: center; justify-content: center;
      font-size: .85rem; font-weight: 700; color: #020617;
      flex-shrink: 0;
    }
    .gv-session-name { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .gv-session-btn svg { opacity: .6; transition: transform .2s; }
    .gv-session-btn[aria-expanded="true"] svg { transform: rotate(180deg); }

    .gv-session-dropdown {
      display: none; position: absolute; top: calc(100% + 8px); right: 0;
      background: #0f1a2e; border: 1px solid rgba(95,212,255,.2);
      border-radius: 12px; min-width: 230px; padding: .5rem 0;
      box-shadow: 0 14px 40px rgba(0,0,0,.7); z-index: 10000;
    }
    .gv-session-dropdown.open { display: block; }

    .gv-session-info {
      display: flex; align-items: center; gap: .65rem;
      padding: .75rem 1rem;
    }
    .gv-session-user-name { font-weight: 600; font-size: .85rem; color: #f1f5f9; }
    .gv-session-user-role { font-size: .72rem; color: #94a3b8; margin-top: 2px; }

    .gv-session-divider {
      height: 1px; background: rgba(95,212,255,.1); margin: .3rem 0;
    }

    .gv-session-item {
      display: flex; align-items: center; gap: .6rem;
      padding: .6rem 1rem; color: #cbd5e1; text-decoration: none;
      font-size: .82rem; font-weight: 500; transition: background .15s;
      border: none; background: none; width: 100%; text-align: left; cursor: pointer;
    }
    .gv-session-item:hover { background: rgba(34,197,94,.1); color: #22c55e; }
    .gv-session-item i { width: 16px; text-align: center; font-size: .8rem; }

    .gv-session-logout { color: #f87171 !important; }
    .gv-session-logout:hover { background: rgba(248,113,113,.1) !important; color: #ef4444 !important; }

    /* Mobile: inside .navbar-nav.show */
    @media (max-width: 768px) {
      .gv-session-menu { width: 100%; }
      .gv-session-btn {
        width: 100%; justify-content: center;
        border-radius: 8px; padding: .7rem 1rem;
        border: none; background: rgba(34,197,94,.15);
      }
      .gv-session-dropdown {
        position: static; border: none; border-radius: 0;
        background: rgba(15,26,46,.8); box-shadow: none;
        border-top: 1px solid rgba(95,212,255,.1);
        min-width: unset;
      }
      .gv-session-dropdown.open { display: block; }
    }
  `;
  document.head.appendChild(css);

  function getSession() {
    const token = localStorage.getItem('gv_token');
    if (!token) return null;
    const name = localStorage.getItem('gv_name') || '';
    const email = localStorage.getItem('gv_email') || '';
    const role = localStorage.getItem('gv_role') || 'cliente';
    return { token, name, email, role };
  }

  function getInitials(name, email) {
    if (name && name.trim()) {
      const parts = name.trim().split(/\s+/);
      return parts.length >= 2
        ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
        : parts[0].substring(0, 2).toUpperCase();
    }
    if (email) return email.substring(0, 2).toUpperCase();
    return 'U';
  }

  function getDashboardUrl(role) {
    return role === 'admin' ? 'admin.html' : 'dashboard.html';
  }

  function initSession() {
    const session = getSession();
    const portalLink = document.querySelector('.navbar-nav .btn-nav[href="login.html"]');
    if (!portalLink) return;

    if (!session) {
      // No session — keep Portal link as-is (guest mode)
      return;
    }

    // ---- Logged-in state ----
    const initials = getInitials(session.name, session.email);
    const displayName = session.name || session.email || 'Utilizador';
    const dashUrl = getDashboardUrl(session.role);
    const roleLabel = session.role === 'admin' ? 'Administrador' : 'Cliente';

    // Create user menu container
    const userMenu = document.createElement('div');
    userMenu.className = 'gv-session-menu';
    userMenu.innerHTML = `
      <button class="gv-session-btn" aria-label="Menu de utilizador" aria-expanded="false">
        <span class="gv-session-avatar">${initials}</span>
        <span class="gv-session-name">${displayName.split(' ')[0]}</span>
        <svg width="10" height="6" viewBox="0 0 10 6" fill="currentColor"><path d="M1 1l4 4 4-4"/></svg>
      </button>
      <div class="gv-session-dropdown">
        <div class="gv-session-info">
          <div class="gv-session-avatar-lg">${initials}</div>
          <div>
            <div class="gv-session-user-name">${displayName}</div>
            <div class="gv-session-user-role">${roleLabel}</div>
          </div>
        </div>
        <div class="gv-session-divider"></div>
        <a href="${dashUrl}" class="gv-session-item">
          <i class="fa-solid fa-gauge"></i> Painel de Controlo
        </a>
        <a href="loja.html" class="gv-session-item">
          <i class="fa-solid fa-store"></i> Loja & Serviços
        </a>
        <div class="gv-session-divider"></div>
        <button class="gv-session-item gv-session-logout" id="gv-logout-btn">
          <i class="fa-solid fa-right-from-bracket"></i> Terminar Sessão
        </button>
      </div>
    `;

    // Replace the Portal link
    portalLink.replaceWith(userMenu);

    // Toggle dropdown
    const btn = userMenu.querySelector('.gv-session-btn');
    const dropdown = userMenu.querySelector('.gv-session-dropdown');

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const open = dropdown.classList.toggle('open');
      btn.setAttribute('aria-expanded', open);
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (!userMenu.contains(e.target)) {
        dropdown.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
      }
    });

    // Logout
    userMenu.querySelector('#gv-logout-btn').addEventListener('click', () => {
      ['gv_token', 'gv_refresh_token', 'gv_user', 'gv_email', 'gv_name',
       'gv_role', 'gv_account_id', 'gv_account_name', 'gv_toast'].forEach(k => localStorage.removeItem(k));
      window.location.href = 'index.html';
    });

    // Prevent mobile menu from closing when interacting with dropdown
    userMenu.querySelectorAll('a, button').forEach(el => {
      el.addEventListener('click', (e) => e.stopPropagation());
    });

    // If on login.html, redirect to dashboard
    if (window.location.pathname.endsWith('login.html') || window.location.pathname.endsWith('login')) {
      window.location.replace(dashUrl);
    }
  }

  document.addEventListener('DOMContentLoaded', initSession);
  window.GV = window.GV || {};
  window.GV.initSession = initSession;
})();
