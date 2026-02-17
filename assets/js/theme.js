/* ============================================================
   GeoVision – Theme Toggle  (sun / moon)
   ============================================================ */
(function () {
  'use strict';

  const STORAGE_KEY = 'gv-theme';

  // Neutral monochrome SVG icons — inherit currentColor, no emoji color
  const SVG_SUN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
  const SVG_MOON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

  /* --- Initialise on page load --------------------------------------- */
  function initTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
    }
    updateIcons();
  }

  /* --- Toggle -------------------------------------------------------- */
  function toggleTheme() {
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    if (isLight) {
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem(STORAGE_KEY, 'dark');
    } else {
      document.documentElement.setAttribute('data-theme', 'light');
      localStorage.setItem(STORAGE_KEY, 'light');
    }
    updateIcons();
  }

  /* --- Sync icons ---------------------------------------------------- */
  function updateIcons() {
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    document.querySelectorAll('.theme-toggle').forEach(function (btn) {
      btn.innerHTML = isLight ? SVG_MOON : SVG_SUN;
      btn.setAttribute('aria-label', isLight ? 'Ativar modo escuro' : 'Ativar modo claro');
      btn.setAttribute('title',      isLight ? 'Modo Escuro' : 'Modo Claro');
    });
  }

  window.toggleTheme = toggleTheme;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTheme);
  } else {
    initTheme();
  }
})();
