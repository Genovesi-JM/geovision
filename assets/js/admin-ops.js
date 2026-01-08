const SESSION_EMAIL_KEY = "gv_email";
const SESSION_ROLE_KEY = "gv_role";

const PROJECT_PIPELINE = [
  {
    client: "Cooperativa AgroBenguela",
    service: "NDVI + Pulverização",
    region: "Huambo",
    status: "Em voo",
    next: "Processamento no Pix4D às 18h",
  },
  {
    client: "Fazenda Rio Kunene",
    service: "Mapeamento de pastagem",
    region: "Cunene",
    status: "Planeado",
    next: "Briefing com agrónomo - 08h",
  },
  {
    client: "Infraestruturas Sul",
    service: "Inspeção de ponte",
    region: "Lubango",
    status: "Processamento",
    next: "QA imagem térmica",
  },
  {
    client: "Mineração Lunda",
    service: "Levantamento LIDAR",
    region: "Lunda Sul",
    status: "Entrega",
    next: "Enviar relatório volumétrico",
  },
];

const REPORTS_READY = [
  {
    client: "Cooperativa AgroBenguela",
    report: "NDVI – Junho",
    eta: "12 Jun",
    owner: "João M.",
  },
  {
    client: "Infraestruturas Sul",
    report: "Inspeção ponte KM-34",
    eta: "Hoje",
    owner: "Sara D.",
  },
  {
    client: "Mineração Lunda",
    report: "Modelagem 3D – Pilha B",
    eta: "14 Jun",
    owner: "Carlos T.",
  },
];

const ALERTS = [
  "Drone PX-8 necessita de calibração antes da missão das 14h.",
  "Cliente Rio Kunene pediu atualização diária das rotas do rebanho.",
  "Verificar sensores de vibração instalados na ponte (alerta amarelo).",
];

function requireAdminRole() {
  const role = localStorage.getItem(SESSION_ROLE_KEY);
  if (role !== "admin") {
    window.location.href = "login.html";
  }
}

function renderKpis() {
  document.getElementById("kpi-projects").textContent = PROJECT_PIPELINE.length;
  document.getElementById("kpi-missions").textContent = "3";
  document.getElementById("kpi-reports").textContent = REPORTS_READY.length;
  document.getElementById("kpi-alerts").textContent = ALERTS.length;
}

function renderPipelineTable() {
  const tbody = document.getElementById("pipeline-body");
  tbody.innerHTML = "";
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
  ALERTS.forEach((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    list.appendChild(li);
  });
}

function initAdminOps() {
  requireAdminRole();
  const email = localStorage.getItem(SESSION_EMAIL_KEY) || "admin@geovision.co.ao";
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
