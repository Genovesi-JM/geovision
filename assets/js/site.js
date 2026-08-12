/* assets/js/site.js
   Small UX helpers for public pages: menu toggle, smooth scroll, basic video modal

   Usage: include <script src="assets/js/site.js"></script> in public pages.
   It exposes a global `GV` object with `initSite()` if you prefer manual init.
*/

(function () {
  /* ── HTML escaping utility (prevents XSS in innerHTML) ── */
  function escapeHTML(str) {
    if (str == null) return "";
    const d = document.createElement("div");
    d.textContent = String(str);
    return d.innerHTML;
  }
  window.escapeHTML = escapeHTML;

  const GV = window.GV || {};

  function initMenuToggle() {
    const menuToggle = document.getElementById("menu-toggle");
    // Support both navbar patterns: #main-nav (.nav-links) and .navbar-nav
    const nav = document.getElementById("main-nav") || document.querySelector(".navbar-nav");
    const langToggle = document.querySelector(".lang-toggle");
    if (!menuToggle || !nav) return;

    if (menuToggle.dataset.gvMenuToggle === "ready") return;
    menuToggle.dataset.gvMenuToggle = "ready";

    if (!nav.id) nav.id = "main-nav";
    menuToggle.setAttribute("aria-controls", nav.id);
    menuToggle.setAttribute("aria-expanded", "false");

    const langParent = langToggle && langToggle.parentNode;
    const langNextSibling = langToggle && langToggle.nextSibling;

    function closeMenu() {
      nav.classList.remove("show");
      menuToggle.setAttribute("aria-expanded", "false");
      if (langToggle) langToggle.classList.remove("show");
    }

    function syncResponsiveLayout() {
      const isMobile = window.innerWidth <= 768;
      if (langToggle && isMobile && langToggle.parentNode !== nav) {
        nav.appendChild(langToggle);
      } else if (langToggle && !isMobile && langToggle.parentNode !== langParent) {
        if (langNextSibling && langNextSibling.parentNode === langParent) {
          langParent.insertBefore(langToggle, langNextSibling);
        } else {
          langParent.appendChild(langToggle);
        }
      }
      if (!isMobile) closeMenu();
    }

    // On mobile, move lang-toggle inside the nav dropdown so it flows below links
    syncResponsiveLayout();

    menuToggle.addEventListener("click", () => {
      const open = !nav.classList.contains("show");
      nav.classList.toggle("show", open);
      menuToggle.setAttribute("aria-expanded", String(open));
      if (langToggle) langToggle.classList.toggle("show", open);
    });
    // Close menu when clicking a nav link (mobile UX)
    nav.querySelectorAll("a").forEach((a) => {
      a.addEventListener("click", closeMenu);
    });

    window.addEventListener("resize", syncResponsiveLayout);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
    });
  }

  function initSmoothAnchors() {
    document.querySelectorAll('a[href^="#"]').forEach((a) => {
      a.addEventListener("click", (e) => {
        const href = a.getAttribute("href");
        if (href === "#") return;
        if (!href.startsWith("#")) return;
        e.preventDefault();
        const el = document.querySelector(href);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function initVideoModal() {
    // Generic video modal: elements with data-video-id will open embed modal
    const modal = document.getElementById("video-modal");
    if (!modal) return;
    const dialog = modal.querySelector(".video-modal-dialog");
    const content = modal.querySelector(".video-modal-content");
    const backdrop = modal.querySelector(".video-modal-backdrop");
    const closeBtns = modal.querySelectorAll(".video-modal-close");

    function openVideo(id) {
      if (!/^[a-zA-Z0-9_-]+$/.test(id)) return;
      content.innerHTML = `<iframe width="560" height="315" src="https://www.youtube.com/embed/${id}?rel=0" frameborder="0" allowfullscreen></iframe>`;
      modal.style.display = "block";
    }

    function closeVideo() {
      modal.style.display = "none";
      content.innerHTML = "";
    }

    document.querySelectorAll("[data-video-id]").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.getAttribute("data-video-id");
        if (id) openVideo(id);
      });
    });

    backdrop && backdrop.addEventListener("click", closeVideo);
    closeBtns.forEach((b) => b.addEventListener("click", closeVideo));
  }

  function initPasswordToggles() {
    document.querySelectorAll(".toggle-password[data-target]").forEach((button) => {
      if (button.dataset.gvPasswordToggle === "ready") return;
      button.dataset.gvPasswordToggle = "ready";

      button.addEventListener("click", () => {
        const input = document.getElementById(button.dataset.target);
        if (!input || (input.type !== "password" && input.type !== "text")) return;

        const reveal = input.type === "password";
        input.type = reveal ? "text" : "password";
        button.setAttribute("aria-pressed", String(reveal));

        const icon = button.querySelector("i");
        if (icon) {
          icon.classList.toggle("fa-eye", !reveal);
          icon.classList.toggle("fa-eye-slash", reveal);
        }
      });
    });
  }

  function initOverlays() {
    const overlays = document.querySelectorAll("[data-overlay]");
    if (!overlays.length) return;

    function setOpen(overlay, open) {
      if (!overlay) return;
      overlay.classList.toggle("show", open);
      overlay.setAttribute("aria-hidden", String(!open));

      if (overlay.id) {
        document.querySelectorAll(`[data-overlay-open="${overlay.id}"]`).forEach((trigger) => {
          trigger.setAttribute("aria-expanded", String(open));
        });
      }

      if (open) {
        const focusTarget = overlay.querySelector("[data-overlay-close], button, a, input, select, textarea");
        if (focusTarget) focusTarget.focus();
      }
    }

    document.querySelectorAll("[data-overlay-open]").forEach((trigger) => {
      if (trigger.dataset.gvOverlayTrigger === "ready") return;
      trigger.dataset.gvOverlayTrigger = "ready";
      const open = () => setOpen(document.getElementById(trigger.dataset.overlayOpen), true);
      trigger.addEventListener("click", open);
      trigger.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        open();
      });
    });

    overlays.forEach((overlay) => {
      if (overlay.dataset.gvOverlay === "ready") return;
      overlay.dataset.gvOverlay = "ready";
      overlay.setAttribute("aria-hidden", String(!overlay.classList.contains("show")));
      overlay.querySelectorAll("[data-overlay-close]").forEach((button) => {
        button.addEventListener("click", () => setOpen(overlay, false));
      });
      overlay.addEventListener("click", (event) => {
        if (event.target === overlay) setOpen(overlay, false);
      });
    });

    if (document.body.dataset.gvOverlayEscape !== "ready") {
      document.body.dataset.gvOverlayEscape = "ready";
      document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        document.querySelectorAll("[data-overlay].show").forEach((overlay) => setOpen(overlay, false));
      });
    }
  }

  function initSite() {
    initMenuToggle();
    initSmoothAnchors();
    initVideoModal();
    initPasswordToggles();
    initOverlays();
  }

  GV.initSite = initSite;
  window.GV = GV;

  // Auto-update copyright year in footers
  function updateCopyrightYear() {
    var y = new Date().getFullYear();
    document.querySelectorAll('.footer-copyright').forEach(function(el) {
      el.textContent = el.textContent.replace(/© \d{4}/, '© ' + y);
    });
  }

  // Auto init on DOM ready (safe to call multiple times)
  document.addEventListener("DOMContentLoaded", function() {
    initSite();
    // Run after i18n may have applied translations
    setTimeout(updateCopyrightYear, 150);
  });
})();
