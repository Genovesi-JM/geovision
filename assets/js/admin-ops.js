const SESSION_EMAIL_KEY = "gv_email";
const SESSION_ROLE_KEY = "gv_role";

/* ── Data is loaded from the backend — no hardcoded demo content ── */
const PROJECT_PIPELINE = [];
const REPORTS_READY = [];
const ALERTS = [];

function requireAdminRole() {
  const role = localStorage.getItem(SESSION_ROLE_KEY);
  if (role !== "admin") {
    window.location.href = "login.html";
  }
}

function renderKpis() {
  document.getElementById("kpi-projects").textContent = PROJECT_PIPELINE.length || "0";
  document.getElementById("kpi-missions").textContent = "0";
  document.getElementById("kpi-reports").textContent = REPORTS_READY.length || "0";
  document.getElementById("kpi-alerts").textContent = ALERTS.length || "0";
}

function renderPipelineTable() {
  const tbody = document.getElementById("pipeline-body");
  tbody.innerHTML = "";
  if (!PROJECT_PIPELINE.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="5" style="text-align:center;color:var(--text-muted);">Sem projectos ativos.</td>';
    tbody.appendChild(tr);
    return;
  }
  PROJECT_PIPELINE.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.client}</td>
      <td>${row.service}</td>
      <td>${row.region}</td>
      <td>${row.status}</td>
      <td>${row.next}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderReportsTable() {
  const tbody = document.getElementById("reports-body");
  tbody.innerHTML = "";
  if (!REPORTS_READY.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="4" style="text-align:center;color:var(--text-muted);">Sem relatórios pendentes.</td>';
    tbody.appendChild(tr);
    return;
  }
  REPORTS_READY.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.client}</td>
      <td>${row.report}</td>
      <td>${row.eta}</td>
      <td>${row.owner}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderAlerts() {
  const list = document.getElementById("alerts-list");
  list.innerHTML = "";
  if (!ALERTS.length) {
    const li = document.createElement("li");
    li.style.color = "var(--text-muted)";
    li.textContent = "Sem alertas.";
    list.appendChild(li);
    return;
  }
  ALERTS.forEach((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    list.appendChild(li);
  });
}

function initAdminOps() {
  requireAdminRole();
  const email = localStorage.getItem(SESSION_EMAIL_KEY) || "—";
  const emailEl = document.getElementById("admin-email");
  if (emailEl) {
    emailEl.textContent = email;
  }

  renderKpis();
  renderPipelineTable();
  renderReportsTable();
  renderAlerts();

  const logoutBtn = document.getElementById("btn-admin-logout");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      localStorage.removeItem("gv_token");
      localStorage.removeItem("gv_role");
      localStorage.removeItem("gv_email");
      window.location.href = "index.html";
    });
  }
}

document.addEventListener("DOMContentLoaded", initAdminOps);
