const SESSION_EMAIL_KEY = "gv_email";
const SESSION_ROLE_KEY = "gv_role";
const SESSION_ACCOUNT_KEY = "gv_account_id";
const SESSION_ACTIVE_SECTOR_KEY = "gv_active_sector";
const API_BASE = window.API_BASE || "http://127.0.0.1:8010";

const SECTOR_LABELS = {
  agro: "Agro & Pecuária",
  mining: "Mineração",
  demining: "Desminagem",
  construction: "Construção",
  infrastructure: "Infraestruturas",
  solar: "Solar",
};

function getSectorsFromAccount(account) {
  if (!account || !account.sector_focus) return ["generic"];
  const raw = account.sector_focus;
  if (raw.includes(",")) {
    return raw.split(",").map(s => s.trim()).filter(Boolean);
  }
  return [raw];
}

function buildDemoPortfolioForSector(sector, accountName) {
  if (sector === "agro") {
    return {
      name: accountName || "Operações Agro",
      services: [
        { type: "NDVI + Pulverização", location: "Huambo", hectares: 180, status: "em campo" },
        { type: "Mapeamento de talhão", location: "Benguela", hectares: 95, status: "processamento" },
      ],
      hardware: [
        { name: "Gateway IoT Pasto Norte", location: "Fazenda Rio Kunene", status: "online" },
      ],
      reports: [
        { title: "Relatório NDVI – Lote A", service: "NDVI", eta: "Hoje", status: "a enviar" },
      ],
      alerts: ["Zona de stress hídrico detectada no talhão 3."],
    };
  }

  if (sector === "mining") {
    return {
      name: accountName || "Operações Mining",
      services: [
        { type: "Levantamento LIDAR", location: "Mina Catoca", hectares: "-", status: "planeado" },
      ],
      hardware: [
        { name: "Sensor estrutural", location: "Pilha Norte", status: "online" },
      ],
      reports: [
        { title: "Modelo 3D talude", service: "LIDAR", eta: "+3 dias", status: "em processamento" },
      ],
      alerts: ["Aviso: movimento acima do limiar na frente 2."],
    };
  }

  if (sector === "construction") {
    return {
      name: accountName || "Operações Construção",
      services: [
        { type: "Levantamento topográfico", location: "Obra Talatona", hectares: 12, status: "em campo" },
        { type: "Inspeção estrutural", location: "Edifício Central", hectares: "-", status: "processamento" },
      ],
      hardware: [
        { name: "Sensor estrutural", location: "Torre Sul", status: "online" },
      ],
      reports: [
        { title: "Relatório topográfico", service: "Topografia", eta: "+2 dias", status: "em processamento" },
      ],
      alerts: ["Verificar estabilidade torre sul."],
    };
  }

  if (sector === "infrastructure") {
    return {
      name: accountName || "Infraestruturas",
      services: [
        { type: "Inspeção ponte", location: "Luena", hectares: "-", status: "processamento" },
        { type: "Monitorização estradas", location: "EN-100", hectares: "-", status: "em campo" },
      ],
      hardware: [
        { name: "Sensor vibração", location: "Ponte principal", status: "online" },
      ],
      reports: [],
      alerts: ["Sem alertas críticos no momento."],
    };
  }

  if (sector === "solar") {
    return {
      name: accountName || "Operações Solar",
      services: [
        { type: "Inspeção térmica painéis", location: "Parque Solar Namibe", hectares: 85, status: "planeado" },
      ],
      hardware: [
        { name: "Sensor irradiância", location: "Estação central", status: "online" },
      ],
      reports: [
        { title: "Análise eficiência Q4", service: "Térmico", eta: "+5 dias", status: "em processamento" },
      ],
      alerts: ["Painel B12 com temperatura elevada."],
    };
  }

  if (sector === "demining") {
    return {
      name: accountName || "Operações Desminagem",
      services: [
        { type: "Levantamento área", location: "Cuito Cuanavale", hectares: 45, status: "em campo" },
      ],
      hardware: [
        { name: "Drone deteção", location: "Base operacional", status: "online" },
      ],
      reports: [],
      alerts: ["Área prioridade alta identificada."],
    };
  }

  return {
    name: accountName || "Conta GeoVision",
    services: [
      { type: "Missão drone", location: "Cliente GeoVision", hectares: "-", status: "planeado" },
    ],
    hardware: [],
    reports: [],
    alerts: ["Sem alertas críticos no momento."],
  };
}

function buildDemoPortfolio(account, activeSector) {
  const sectors = getSectorsFromAccount(account);
  const accountName = account?.name;
  
  // If activeSector specified and valid, show only that sector
  if (activeSector && sectors.includes(activeSector)) {
    return buildDemoPortfolioForSector(activeSector, accountName);
  }
  
  // If single sector, return it directly
  if (sectors.length === 1) {
    return buildDemoPortfolioForSector(sectors[0], accountName);
  }
  
  // Multiple sectors: combine all data
  const combined = {
    name: accountName || "Multi-Setor",
    services: [],
    hardware: [],
    reports: [],
    alerts: [],
  };
  
  sectors.forEach(sector => {
    const p = buildDemoPortfolioForSector(sector, accountName);
    combined.services.push(...p.services.map(s => ({ ...s, sector })));
    combined.hardware.push(...p.hardware.map(h => ({ ...h, sector })));
    combined.reports.push(...p.reports.map(r => ({ ...r, sector })));
    combined.alerts.push(...p.alerts);
  });
  
  return combined;
}

function renderSectorTabs(account, activeSector, onTabClick) {
  const container = document.getElementById("sector-tabs");
  if (!container) return;
  
  const sectors = getSectorsFromAccount(account);
  
  // Hide tabs if single sector
  if (sectors.length <= 1) {
    container.style.display = "none";
    return;
  }
  
  container.style.display = "flex";
  container.innerHTML = "";
  
  // "Todos" tab for combined view
  const allTab = document.createElement("button");
  allTab.className = "sector-tab" + (!activeSector ? " active" : "");
  allTab.textContent = "Todos";
  allTab.onclick = () => onTabClick(null);
  container.appendChild(allTab);
  
  // Individual sector tabs
  sectors.forEach(sector => {
    const tab = document.createElement("button");
    tab.className = "sector-tab" + (activeSector === sector ? " active" : "");
    tab.textContent = SECTOR_LABELS[sector] || sector;
    tab.onclick = () => onTabClick(sector);
    container.appendChild(tab);
  });
}

function requireSession() {
  const token = localStorage.getItem("gv_token");
  if (!token) {
    window.location.href = "login.html";
  }
}

function authHeaders(accountId) {
  const token = localStorage.getItem("gv_token");
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (accountId) headers["X-Account-ID"] = accountId;
  return headers;
}

async function apiGet(path, accountId) {
  const res = await fetch(`${API_BASE}${path}`, { method: "GET", headers: authHeaders(accountId) });
  if (res.status === 401) {
    localStorage.removeItem("gv_token");
    window.location.href = "login.html";
    return null;
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPost(path, body, accountId) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: authHeaders(accountId),
    body: JSON.stringify(body || {}),
  });
  if (res.status === 401) {
    localStorage.removeItem("gv_token");
    window.location.href = "login.html";
    return null;
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderServices(portfolio) {
  const tbody = document.querySelector("#services-table tbody");
  const empty = document.getElementById("services-empty");
  tbody.innerHTML = "";

  if (!portfolio.services || !portfolio.services.length) {
    empty.style.display = "block";
    document.getElementById("services-badge").textContent = "0 ativos";
    return;
  }

  empty.style.display = "none";
  portfolio.services.forEach((svc) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${svc.type}</td>
      <td>${svc.location}</td>
      <td>${svc.hectares}</td>
      <td>
        <span class="status-pill">
          <span class="status-pill-dot"></span>${svc.status}
        </span>
      </td>
    `;
    tbody.appendChild(tr);
  });
  document.getElementById("services-badge").textContent = `${portfolio.services.length} ativos`;
  document.getElementById("kpi-services").textContent = portfolio.services.length;
}

function renderHardware(portfolio) {
  const tbody = document.querySelector("#hardware-table tbody");
  const empty = document.getElementById("hardware-empty");
  tbody.innerHTML = "";

  if (!portfolio.hardware || !portfolio.hardware.length) {
    empty.style.display = "block";
    document.getElementById("kpi-hardware").textContent = "0";
    return;
  }

  empty.style.display = "none";
  portfolio.hardware.forEach((hw) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${hw.name}</td>
      <td>${hw.location}</td>
      <td>
        <span class="status-pill">
          <span class="status-pill-dot"></span>${hw.status}
        </span>
      </td>
    `;
    tbody.appendChild(tr);
  });
  document.getElementById("kpi-hardware").textContent = portfolio.hardware.length;
}

function renderReports(portfolio) {
  const tbody = document.querySelector("#reports-table tbody");
  const empty = document.getElementById("reports-empty");
  tbody.innerHTML = "";

  if (!portfolio.reports || !portfolio.reports.length) {
    empty.style.display = "block";
    document.getElementById("kpi-reports").textContent = "0";
    return;
  }

  empty.style.display = "none";
  portfolio.reports.forEach((rep) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${rep.title}</td>
      <td>${rep.service}</td>
      <td>${rep.eta}</td>
      <td>${rep.status}</td>
    `;
    tbody.appendChild(tr);
  });
  document.getElementById("kpi-reports").textContent = portfolio.reports.length;
}

function renderAlerts(portfolio) {
  document.getElementById("kpi-alerts").textContent = (portfolio.alerts && portfolio.alerts.length) || "-";
  const container = document.getElementById("alerts-list");
  if (!container) return;
  container.innerHTML = "";
  const alerts = portfolio.alerts || [];
  if (!alerts.length) {
    container.innerHTML = '<div class="dash-empty">Sem alertas.</div>';
    return;
  }
  alerts.forEach((a) => {
    const div = document.createElement("div");
    div.className = "badge";
    div.textContent = a;
    container.appendChild(div);
  });
}

function populateAccountSwitcher(accounts, currentAccountId) {
  const select = document.getElementById("account-switcher");
  if (!select) return;
  select.innerHTML = "";
  accounts.forEach((acct) => {
    const opt = document.createElement("option");
    opt.value = acct.id;
    opt.textContent = `${acct.name}${acct.sector_focus ? ' · ' + acct.sector_focus : ''}`;
    if (acct.id === currentAccountId) opt.selected = true;
    select.appendChild(opt);
  });
}

function renderAccountMeta(account) {
  const titleEl = document.getElementById("dash-title");
  const metaEl = document.getElementById("dash-meta");
  const chips = document.getElementById("modules-chips");
  if (titleEl && account) titleEl.textContent = account.name || "Conta GeoVision";
  if (metaEl && account) metaEl.textContent = `${account.sector_focus || 'Setor'} · ${account.entity_type || 'Tipo'}`;
  if (chips) {
    chips.innerHTML = "";
    (account.modules_enabled || []).forEach((m) => {
      const span = document.createElement("span");
      span.className = "badge";
      span.textContent = m;
      chips.appendChild(span);
    });
  }
}

async function loadKpis(accountId) {
  const placeholders = {
    services_active: "kpi-services",
    hardware_active: "kpi-hardware",
    reports_ready: "kpi-reports",
    alerts_open: "kpi-alerts",
  };
  try {
    const summary = await apiGet("/kpi/summary", accountId);
    if (summary && summary.items) {
      summary.items.forEach((item) => {
        const elId = placeholders[item.id];
        if (elId) {
          const el = document.getElementById(elId);
          if (el) el.textContent = item.value;
        }
      });
    }
  } catch (err) {
    console.warn("KPI fallback", err);
  }
}

async function loadOrdersOverrideReports(accountId) {
  try {
    const orders = await apiGet("/orders", accountId);
    if (!orders || !Array.isArray(orders)) return;

    const tbody = document.querySelector("#reports-table tbody");
    const empty = document.getElementById("reports-empty");
    if (!tbody || !empty) return;

    tbody.innerHTML = "";
    if (!orders.length) {
      empty.style.display = "block";
      document.getElementById("kpi-reports").textContent = "0";
      return;
    }

    empty.style.display = "none";
    orders.forEach((o) => {
      const tr = document.createElement("tr");
      const created = o.created_at ? new Date(o.created_at).toLocaleString() : "-";
      tr.innerHTML = `
        <td>Pedido ${o.id.slice(0, 8)}</td>
        <td>Loja GeoVision</td>
        <td>${created}</td>
        <td>${o.status || "-"}</td>
      `;
      tbody.appendChild(tr);
    });

    document.getElementById("kpi-reports").textContent = String(orders.length);
  } catch (err) {
    console.warn("orders reports fallback", err);
  }
}

function toggleModal(show) {
  const backdrop = document.getElementById("account-modal-backdrop");
  if (!backdrop) return;
  backdrop.style.display = show ? "flex" : "none";
  backdrop.setAttribute("aria-hidden", show ? "false" : "true");
}

async function handleAccountCreate(currentAccountId, reloadFn) {
  const name = document.getElementById("account-name-input")?.value?.trim();
  const sector = document.getElementById("account-sector-input")?.value || "agro";
  const entity = document.getElementById("account-entity-input")?.value || "org";
  const modules = Array.from(document.querySelectorAll("#account-modules input[type=checkbox]:checked")).map((c) => c.value);
  if (!name) return alert("Indique um nome para a conta.");
  try {
    const created = await apiPost("/accounts", {
      name,
      sector_focus: sector,
      entity_type: entity,
      modules_enabled: modules,
    });
    const accountId = created.id;
    localStorage.setItem(SESSION_ACCOUNT_KEY, accountId);
    toggleModal(false);
    await reloadFn(accountId);
  } catch (err) {
    console.error("create-account", err);
    alert("Erro ao criar conta. Verifique se o backend está ativo.");
  }
}

async function loadDashboard(accountIdHint, activeSectorHint) {
  requireSession();

  let currentAccountId = accountIdHint || localStorage.getItem(SESSION_ACCOUNT_KEY) || null;
  let activeSector = activeSectorHint !== undefined ? activeSectorHint : (localStorage.getItem(SESSION_ACTIVE_SECTOR_KEY) || null);
  let meData = null;
  try {
    meData = await apiGet("/me", currentAccountId);
  } catch (err) {
    console.warn("me fallback", err);
  }

  if (meData && meData.user) {
    const email = meData.user.email || "cliente@geovision";
    document.getElementById("user-email-pill").textContent = email;
    localStorage.setItem(SESSION_EMAIL_KEY, email);

    const accounts = meData.accounts || [];
    currentAccountId = currentAccountId || meData.default_account_id || (accounts[0] && accounts[0].id) || null;
    if (currentAccountId) localStorage.setItem(SESSION_ACCOUNT_KEY, currentAccountId);
    populateAccountSwitcher(accounts, currentAccountId);
    const active = accounts.find((a) => a.id === currentAccountId) || accounts[0];
    if (active) renderAccountMeta(active);
  } else {
    const email = localStorage.getItem(SESSION_EMAIL_KEY) || "cliente@geovision";
    document.getElementById("user-email-pill").textContent = email;
    document.getElementById("dash-title").textContent = `Olá, ${email}`;
  }

  const activeAccount =
    (meData && meData.accounts && meData.accounts.find((a) => a.id === currentAccountId)) || null;
  
  // Render sector tabs for multi-sector accounts
  renderSectorTabs(activeAccount, activeSector, (newSector) => {
    if (newSector) {
      localStorage.setItem(SESSION_ACTIVE_SECTOR_KEY, newSector);
    } else {
      localStorage.removeItem(SESSION_ACTIVE_SECTOR_KEY);
    }
    loadDashboard(currentAccountId, newSector);
  });
  
  const portfolio = buildDemoPortfolio(activeAccount, activeSector);

  await loadKpis(currentAccountId);

  renderServices(portfolio);
  renderHardware(portfolio);
  renderReports(portfolio);
  renderAlerts(portfolio);

  // Enriquecer tabela de relatórios com pedidos reais da loja (se existirem)
  await loadOrdersOverrideReports(currentAccountId);

  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn && !logoutBtn.dataset.gvBound) {
    logoutBtn.addEventListener("click", () => {
      localStorage.removeItem("gv_token");
      localStorage.removeItem(SESSION_ROLE_KEY);
      localStorage.removeItem(SESSION_EMAIL_KEY);
      localStorage.removeItem(SESSION_ACCOUNT_KEY);
      window.location.href = "index.html";
    });
    logoutBtn.dataset.gvBound = "1";
  }

  const switcher = document.getElementById("account-switcher");
  if (switcher && !switcher.dataset.gvBound) {
    switcher.addEventListener("change", async (e) => {
      const val = e.target.value;
      localStorage.setItem(SESSION_ACCOUNT_KEY, val);
      localStorage.removeItem(SESSION_ACTIVE_SECTOR_KEY); // Reset sector filter on account change
      await loadDashboard(val, null);
    });
    switcher.dataset.gvBound = "1";
  }

  const openModal = document.getElementById("open-account-modal");
  const cancelBtn = document.getElementById("account-cancel");
  const createBtn = document.getElementById("account-create");

  if (openModal && !openModal.dataset.gvBound) {
    openModal.onclick = () => {
      const name = document.getElementById("account-name-input");
      if (name) name.value = "";
      toggleModal(true);
    };
    openModal.dataset.gvBound = "1";
  }
  if (cancelBtn && !cancelBtn.dataset.gvBound) {
    cancelBtn.onclick = () => toggleModal(false);
    cancelBtn.dataset.gvBound = "1";
  }
  if (createBtn && !createBtn.dataset.gvBound) {
    createBtn.onclick = () => handleAccountCreate(currentAccountId, loadDashboard);
    createBtn.dataset.gvBound = "1";
  }
}

document.addEventListener("DOMContentLoaded", () => loadDashboard());