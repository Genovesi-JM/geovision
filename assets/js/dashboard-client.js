const SESSION_EMAIL_KEY = "gv_email";
const SESSION_ROLE_KEY = "gv_role";
const SESSION_ACCOUNT_KEY = "gv_account_id";
const SESSION_ACTIVE_SECTOR_KEY = "gv_active_sector";
const API_BASE = window.API_BASE || "http://127.0.0.1:8010";

/* HTML escaping utility (XSS prevention) */
function escapeHTML(str) {
  if (str == null) return "";
  const d = document.createElement("div");
  d.textContent = String(str);
  return d.innerHTML;
}

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

/* ── Empty portfolio — real data comes from backend APIs ── */
function buildDemoPortfolioForSector(sector, accountName) {
  return {
    services: [],
    hardware: [],
    reports: [],
    alerts: [],
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
  if (!tbody) return;
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
      <td>${escapeHTML(svc.type)}</td>
      <td>${escapeHTML(svc.location)}</td>
      <td>${escapeHTML(svc.hectares)}</td>
      <td>
        <span class="status-pill">
          <span class="status-pill-dot"></span>${escapeHTML(svc.status)}
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
  if (!tbody) return;
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
      <td>${escapeHTML(hw.name)}</td>
      <td>${escapeHTML(hw.location)}</td>
      <td>
        <span class="status-pill">
          <span class="status-pill-dot"></span>${escapeHTML(hw.status)}
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
  if (!tbody) return;
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
      <td>${escapeHTML(rep.title)}</td>
      <td>${escapeHTML(rep.service)}</td>
      <td>${escapeHTML(rep.eta)}</td>
      <td>${escapeHTML(rep.status)}</td>
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

async function loadKpis(accountId, activeSector) {
  // Map of KPI ids to DOM element ids for generic KPIs
  const genericPlaceholders = {
    services_active: "kpi-services",
    hardware_active: "kpi-hardware",
    reports_ready: "kpi-reports",
    alerts_open: "kpi-alerts",
  };
  
  // Sector-specific KPI mappings (first 4 KPIs of each sector)
  const sectorKpiMapping = {
    agro: ["ndvi_avg", "water_stress", "hectares_monitored", "yield_estimate"],
    mining: ["extraction_volume", "slope_stability", "sensors_active", "geotechnical_alerts"],
    construction: ["progress_percent", "conformity_index", "pending_inspections", "volume_earthwork"],
    infrastructure: ["km_monitored", "structural_integrity", "vibration_sensors", "maintenance_alerts"],
    solar: ["panel_efficiency", "irradiance_avg", "anomaly_panels", "energy_generated"],
    demining: ["area_cleared", "objects_detected", "progress_rate", "priority_zones"],
  };
  
  try {
    const sectorParam = activeSector ? `?sector=${activeSector}` : "";
    const summary = await apiGet(`/kpi/summary${sectorParam}`, accountId);
    
    if (summary && summary.items && summary.items.length > 0) {
      // Get the KPI card elements
      const kpiCards = document.querySelectorAll(".kpi-card");
      const kpiLabels = ["kpi-services", "kpi-hardware", "kpi-reports", "kpi-alerts"];
      const labelTexts = {
        "kpi-services": ".kpi-label",
        "kpi-hardware": ".kpi-label", 
        "kpi-reports": ".kpi-label",
        "kpi-alerts": ".kpi-label"
      };
      
      // Update up to 4 KPIs in the dashboard cards
      summary.items.slice(0, 4).forEach((item, index) => {
        const card = kpiCards[index];
        if (card) {
          const labelEl = card.querySelector(".kpi-label");
          const valueEl = card.querySelector(".kpi-value");
          
          if (labelEl) labelEl.textContent = item.label;
          if (valueEl) {
            valueEl.textContent = item.value + (item.unit || "");
            // Add status class for visual feedback
            valueEl.className = "kpi-value";
            if (item.status === "warning") valueEl.classList.add("kpi-warning");
            if (item.status === "critical") valueEl.classList.add("kpi-critical");
          }
          
          // Store description as data attribute for tooltips/chatbot
          card.dataset.kpiDescription = item.description || "";
          card.dataset.kpiId = item.id;
        }
      });
    }
  } catch (err) {
    console.warn("KPI fallback to generic", err);
  }
}

async function loadAlerts(accountId, activeSector) {
  try {
    const sectorParam = activeSector ? `?sector=${activeSector}` : "";
    const alertsData = await apiGet(`/kpi/alerts${sectorParam}`, accountId);
    
    const container = document.getElementById("alerts-list");
    if (!container) return;
    
    container.innerHTML = "";
    
    if (!alertsData || !alertsData.alerts || !alertsData.alerts.length) {
      container.innerHTML = '<div class="dash-empty">Sem alertas ativos.</div>';
      document.getElementById("kpi-alerts")?.textContent || "0";
      return;
    }
    
    alertsData.alerts.forEach((alert) => {
      const div = document.createElement("div");
      div.className = `alert-item alert-${escapeHTML(alert.severity)}`;
      div.innerHTML = `
        <div class="alert-header">
          <span class="alert-severity ${escapeHTML(alert.severity)}">${escapeHTML(alert.severity).toUpperCase()}</span>
          <span class="alert-title">${escapeHTML(alert.title)}</span>
        </div>
        <div class="alert-description">${escapeHTML(alert.description)}</div>
        ${alert.location ? `<div class="alert-location"><i class="fa-solid fa-location-dot"></i> ${escapeHTML(alert.location)}</div>` : ""}
      `;
      container.appendChild(div);
    });
    
    // Update alert count
    const alertKpi = document.getElementById("kpi-alerts");
    if (alertKpi) {
      alertKpi.textContent = alertsData.total;
      if (alertsData.critical_count > 0) {
        alertKpi.classList.add("kpi-critical");
      } else if (alertsData.warning_count > 0) {
        alertKpi.classList.add("kpi-warning");
      }
    }
  } catch (err) {
    console.warn("Alerts fallback", err);
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
        <td>Pedido ${escapeHTML(String(o.id).slice(0, 8))}</td>
        <td>Loja GeoVision</td>
        <td>${created}</td>
        <td>${escapeHTML(o.status || "-")}</td>
      `;
      tbody.appendChild(tr);
    });

    document.getElementById("kpi-reports").textContent = String(orders.length);
  } catch (err) {
    console.warn("orders reports fallback", err);
  }
}

function toggleModal(show) {
  const modal = document.getElementById("account-modal");
  if (!modal) return;
  if (show) {
    modal.classList.add("open");
  } else {
    modal.classList.remove("open");
  }
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

  // ── Bind modal & global buttons early (before any render that could throw) ──
  const openModal = document.getElementById("open-account-modal");
  const cancelBtn = document.getElementById("account-cancel");
  const createBtn = document.getElementById("account-create");
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

  // ── Bind modal buttons early — BEFORE any await/render that could throw ──
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
    createBtn.onclick = () => {
      const accId = localStorage.getItem(SESSION_ACCOUNT_KEY) || null;
      handleAccountCreate(accId, loadDashboard);
    };
    createBtn.dataset.gvBound = "1";
  }

  let currentAccountId = accountIdHint || localStorage.getItem(SESSION_ACCOUNT_KEY) || null;
  let activeSector = activeSectorHint !== undefined ? activeSectorHint : (localStorage.getItem(SESSION_ACTIVE_SECTOR_KEY) || null);
  let meData = null;
  try {
    meData = await apiGet("/me", currentAccountId);
  } catch (err) {
    console.warn("me fallback", err);
  }

  const emailPill = document.getElementById("user-email-pill");
  const dashTitle = document.getElementById("dash-title");

  if (meData && meData.user) {
    const email = meData.user.email || "—";
    if (emailPill) emailPill.textContent = email;
    localStorage.setItem(SESSION_EMAIL_KEY, email);

    const accounts = meData.accounts || [];
    currentAccountId = currentAccountId || meData.default_account_id || (accounts[0] && accounts[0].id) || null;
    if (currentAccountId) localStorage.setItem(SESSION_ACCOUNT_KEY, currentAccountId);
    populateAccountSwitcher(accounts, currentAccountId);
    const active = accounts.find((a) => a.id === currentAccountId) || accounts[0];
    if (active) renderAccountMeta(active);
  } else {
    const email = localStorage.getItem(SESSION_EMAIL_KEY) || "—";
    if (emailPill) emailPill.textContent = email;
    if (dashTitle) dashTitle.textContent = `Olá, ${email}`;
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

  // Load KPIs from backend (sector-specific)
  await loadKpis(currentAccountId, activeSector);
  
  // Load alerts from backend (sector-specific)
  await loadAlerts(currentAccountId, activeSector);

  renderServices(portfolio);
  renderHardware(portfolio);
  // Reports are loaded by loadReports() in dashboard.html from /me/documents API
  // renderReports(portfolio);   // REMOVED — was overwriting real API docs
  // renderAlerts from portfolio is now replaced by loadAlerts from backend

  // Orders override reports — now handled by loadReports() in dashboard.html
  // await loadOrdersOverrideReports(currentAccountId);  // REMOVED — was clearing reports table

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
}

document.addEventListener("DOMContentLoaded", () => loadDashboard());