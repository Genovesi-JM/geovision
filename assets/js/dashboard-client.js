const SESSION_EMAIL_KEY = "gv_email";
const SESSION_ROLE_KEY = "gv_role";
const SESSION_ACCOUNT_KEY = "gv_account_id";
const API_BASE = window.API_BASE || "http://127.0.0.1:8010";

function buildDemoPortfolio(account) {
  const sector = (account && account.sector_focus) || "generic";

  if (sector === "agro") {
    return {
      name: account?.name || "Operações Agro",
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
      name: account?.name || "Operações Mining",
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

  if (sector === "infrastructure" || sector === "construction") {
    return {
      name: account?.name || "Infra & Construção",
      services: [
        { type: "Inspeção ponte", location: "Luena", hectares: "-", status: "processamento" },
      ],
      hardware: [
        { name: "Sensor vibração", location: "Ponte principal", status: "online" },
      ],
      reports: [],
      alerts: ["Sem alertas críticos no momento."],
    };
  }

  return {
    name: account?.name || "Conta GeoVision",
    services: [
      { type: "Missão drone", location: "Cliente GeoVision", hectares: "-", status: "planeado" },
    ],
    hardware: [],
    reports: [],
    alerts: ["Sem alertas críticos no momento."],
  };
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

async function loadDashboard(accountIdHint) {
  requireSession();

  let currentAccountId = accountIdHint || localStorage.getItem(SESSION_ACCOUNT_KEY) || null;
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
  const portfolio = buildDemoPortfolio(activeAccount);

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
      await loadDashboard(val);
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