/* assets/js/dashboard.js
   Dashboard helpers: placeholder chart rendering (uses simple canvas) and card refresh simulation.
   Replace with real chart library (Chart.js, ApexCharts) as needed.
*/

(function () {
  const GVDashboard = window.GVDashboard || {};

  function initCharts() {
    // Simple placeholder: draw a sparkline on elements with data-sparkline
    document.querySelectorAll("[data-sparkline]").forEach((el) => {
      try {
        const data = JSON.parse(el.getAttribute("data-sparkline") || "[]");
        const canvas = document.createElement("canvas");
        canvas.width = el.clientWidth || 200;
        canvas.height = 40;
        el.appendChild(canvas);
        const ctx = canvas.getContext("2d");
        ctx.strokeStyle = "#2b7cff";
        ctx.beginPath();
        data.forEach((v, i) => {
          const x = (i / Math.max(1, data.length - 1)) * canvas.width;
          const y = canvas.height - (v / Math.max(...data)) * canvas.height;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
      } catch (e) {
        // ignore malformed data
      }
    });
  }

  function refreshCards() {
    document.querySelectorAll("[data-refresh-card]").forEach((el) => {
      const key = el.getAttribute("data-refresh-card");
      if (!key) return;
      // fake refresh: random number
      el.textContent = Math.floor(Math.random() * 1000);
    });
  }

  function initDashboard() {
    initCharts();
    refreshCards();
    // allow manual refresh event
    document.addEventListener("gv:dashboard:refresh", refreshCards);
  }

  GVDashboard.initDashboard = initDashboard;
  window.GVDashboard = GVDashboard;

  document.addEventListener("DOMContentLoaded", initDashboard);
})();

import { API_BASE } from "./config.js";

async function loadDashboard() {
    const email = localStorage.getItem("gv_email");
    const res = await fetch(`${API_BASE}/users/by-email/${email}`);
    const user = await res.json();

    loadServices(user.id);
    loadHardware(user.id);
    loadOrders(user.id);
}
