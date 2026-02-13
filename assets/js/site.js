/* assets/js/site.js
   Small UX helpers for public pages: menu toggle, smooth scroll, basic video modal

   Usage: include <script src="assets/js/site.js"></script> in public pages.
   It exposes a global `GV` object with `initSite()` if you prefer manual init.
*/

(function () {
  const GV = window.GV || {};

  function initMenuToggle() {
    const menuToggle = document.getElementById("menu-toggle");
    // Support both navbar patterns: #main-nav (.nav-links) and .navbar-nav
    const nav = document.getElementById("main-nav") || document.querySelector(".navbar-nav");
    const langToggle = document.querySelector(".lang-toggle");
    if (!menuToggle || !nav) return;
    menuToggle.addEventListener("click", () => {
      nav.classList.toggle("show");
      if (langToggle) langToggle.classList.toggle("show");
    });
    // Close menu when clicking a nav link (mobile UX)
    nav.querySelectorAll("a").forEach((a) => {
      a.addEventListener("click", () => {
        nav.classList.remove("show");
        if (langToggle) langToggle.classList.remove("show");
      });
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

  function initSite() {
    initMenuToggle();
    initSmoothAnchors();
    initVideoModal();
  }

  GV.initSite = initSite;
  window.GV = GV;

  // Auto init on DOM ready (safe to call multiple times)
  document.addEventListener("DOMContentLoaded", initSite);
})();
