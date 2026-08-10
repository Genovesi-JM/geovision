const SESSION_EMAIL_KEY = "gv_email";
const SESSION_ROLE_KEY = "gv_role";
const SESSION_ACCOUNT_KEY = "gv_account_id";
const SESSION_ACTIVE_SECTOR_KEY = "gv_active_sector";
const API_BASE = window.API_BASE || "http://127.0.0.1:8010";
// i18n helper for dynamically-generated strings (falls back to the key if missing).
const T = (key) => (window.t && window.t(key)) || key;

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

let iotSelectedDevice = null;
let iotSocket = null;

function iotValueLabel(reading) {
  const value = typeof reading.value === "boolean" ? (reading.value ? "Sim" : "Não") : reading.value;
  return `${value ?? "—"}${reading.unit ? ` ${reading.unit}` : ""}`;
}

async function loadIoTHardware(accountId) {
  const tbody = document.querySelector("#hardware-table tbody");
  const empty = document.getElementById("hardware-empty");
  if (!tbody) return;
  initKitPanel(accountId);
  try {
    const devices = await apiGet("/iot/devices", accountId) || [];
    tbody.innerHTML = "";
    empty.style.display = devices.length ? "none" : "block";
    const kpi = document.getElementById("kpi-hardware"); if (kpi) kpi.textContent = String(devices.length);
    devices.forEach((device) => {
      const stale = !device.last_seen_at || Date.now() - new Date(device.last_seen_at).getTime() > 120000;
      const tr = document.createElement("tr"); tr.className = "iot-device-row";
      tr.innerHTML = `<td>${escapeHTML(device.name)}</td><td>${escapeHTML(device.site_name || "—")}</td><td><span class="status-pill"><span class="status-pill-dot"></span>${escapeHTML(stale ? T("iot.status.stale") : device.status)}</span></td><td>${device.last_seen_at ? escapeHTML(new Date(device.last_seen_at).toLocaleString()) : T("iot.status.never")}</td>`;
      tr.onclick = () => showIotDevice(device, accountId); tbody.appendChild(tr);
    });
    if (iotSelectedDevice) {
      const fresh = devices.find((d) => d.id === iotSelectedDevice.id);
      if (fresh) await showIotDevice(fresh, accountId, false);
    }
  } catch (error) {
    console.warn("IoT hardware unavailable", error); tbody.innerHTML = ""; empty.style.display = "block";
  }
}

async function showIotDevice(device, accountId, reconnect = true) {
  iotSelectedDevice = device;
  const panel = document.getElementById("iot-device-detail"); panel.style.display = "block";
  document.getElementById("iot-device-title").textContent = device.name;
  const meta = document.getElementById("iot-device-meta");
  meta.innerHTML = `${escapeHTML(device.device_uid)} · ${escapeHTML(device.site_name || "—")} · ${escapeHTML(device.transport)}`;
  if (typeof device.latitude === "number" && typeof device.longitude === "number") {
    meta.innerHTML += ` · <a href="https://www.google.com/maps?q=${device.latitude},${device.longitude}" target="_blank" rel="noopener" style="color:#22c55e;">📍 ${T("iot.openMaps")}</a>`;
  }
  renderIotReadings(device.readings || []);
  const select = document.getElementById("iot-chart-channel");
  const previous = select.value; select.innerHTML = "";
  (device.readings || []).filter((r) => typeof r.value === "number").forEach((r) => { const option = document.createElement("option"); option.value = r.channel; option.textContent = r.channel; select.appendChild(option); });
  if ([...select.options].some((o) => o.value === previous)) select.value = previous;
  select.onchange = () => loadIotChart(device.id, select.value, accountId);
  if (select.value) await loadIotChart(device.id, select.value, accountId);
  document.getElementById("iot-refresh-device").onclick = () => loadIoTHardware(accountId);
  document.getElementById("iot-download-csv").onclick = () => downloadIotCsv(device.id, accountId);
  document.getElementById("iot-download-report").onclick = () => downloadIotReport(device.id, accountId);
  document.getElementById("iot-diagnostics").onclick = () => sendIotCommand(device.id, "request_diagnostics", accountId);
  document.getElementById("iot-beacon").onclick = () => sendIotCommand(device.id, "beacon_on", accountId);
  if (reconnect) connectIotSocket(device.id, accountId);
}

function renderIotReadings(readings) {
  const grid = document.getElementById("iot-reading-cards"); grid.innerHTML = "";
  readings.forEach((reading) => { const card = document.createElement("div"); card.className = "iot-reading"; card.innerHTML = `<div class="iot-reading-key">${escapeHTML(reading.channel)}</div><div class="iot-reading-value">${escapeHTML(iotValueLabel(reading))}</div><div class="iot-reading-time">${reading.at ? escapeHTML(new Date(reading.at).toLocaleString()) : T("iot.reading.noData")} · ${escapeHTML(reading.quality || "unknown")}</div>`; grid.appendChild(card); });
}

async function loadIotChart(deviceId, channel, accountId) {
  const rows = await apiGet(`/iot/devices/${deviceId}/telemetry?channel=${encodeURIComponent(channel)}&limit=200`, accountId) || [];
  const svg = document.getElementById("iot-history-chart"); svg.innerHTML = "";
  const numeric = rows.filter((r) => typeof r.value === "number");
  if (!numeric.length) { svg.innerHTML = '<text x="450" y="120" text-anchor="middle" fill="#64748b">Sem dados históricos</text>'; return; }
  const values = numeric.map((r) => r.value), min = Math.min(...values), max = Math.max(...values), span = Math.max(max - min, 1);
  const points = numeric.map((r, index) => `${30 + index * 840 / Math.max(numeric.length - 1, 1)},${210 - (r.value - min) * 170 / span}`).join(" ");
  svg.innerHTML = `<line x1="30" y1="210" x2="870" y2="210" stroke="#334155"/><line x1="30" y1="40" x2="30" y2="210" stroke="#334155"/><polyline points="${points}" fill="none" stroke="#22c55e" stroke-width="3"/><text x="35" y="32" fill="#94a3b8">${escapeHTML(String(max.toFixed(2)))}</text><text x="35" y="230" fill="#94a3b8">${escapeHTML(String(min.toFixed(2)))}</text>`;
  document.getElementById("iot-chart-title").textContent = `${T("iot.chart.history")} · ${channel}`;
}

function connectIotSocket(deviceId, accountId) {
  if (iotSocket) iotSocket.close();
  const wsBase = API_BASE.replace(/^http/, "ws"); iotSocket = new WebSocket(`${wsBase}/iot/ws`);
  const status = document.getElementById("iot-live-status"); status.textContent = T("iot.live.connecting");
  iotSocket.onopen = () => iotSocket.send(JSON.stringify({ token: localStorage.getItem("gv_token"), device_id: deviceId }));
  iotSocket.onmessage = async (message) => { const event = JSON.parse(message.data); if (event.type === "ready") { status.textContent = T("iot.live.online"); return; } if (event.type === "telemetry") { renderIotReadings(event.readings || []); const selected = document.getElementById("iot-chart-channel").value; if (selected) await loadIotChart(deviceId, selected, accountId); } if (event.type?.startsWith("alert.")) status.textContent = event.type === "alert.triggered" ? T("iot.live.alert") : T("iot.live.online"); };
  iotSocket.onclose = () => { status.textContent = T("iot.live.offline"); };
}

async function sendIotCommand(deviceId, name, accountId) {
  if (!window.confirm(`${T("iot.command.confirm")} ${name}?`)) return;
  const result = await apiPost(`/iot/devices/${deviceId}/commands`, { name, arguments: {}, confirmed: true, reason: "Supervised dashboard demonstration", fail_safe_state: "off" }, accountId);
  document.getElementById("iot-command-result").textContent = result?.message || T("iot.command.sent");
}

async function downloadIotCsv(deviceId, accountId) {
  const response = await fetch(`${API_BASE}/iot/devices/${deviceId}/telemetry.csv`, { headers: authHeaders(accountId) });
  if (!response.ok) throw new Error(await response.text()); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `${deviceId}-telemetry.csv`; link.click(); URL.revokeObjectURL(url);
}

async function downloadIotReport(deviceId, accountId) {
  const result = document.getElementById("iot-command-result");
  try {
    const response = await fetch(`${API_BASE}/iot/devices/${deviceId}/report.pdf`, { headers: authHeaders(accountId) });
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `${deviceId}-report.pdf`; link.click(); URL.revokeObjectURL(url);
    if (result) result.textContent = T("iot.report.generated");
  } catch (error) {
    if (result) result.textContent = `${T("iot.report.failed")}: ${error.message || error}`;
  }
}

async function initKitPanel(accountId) {
  const kitSel = document.getElementById("iot-kit-select");
  const siteSel = document.getElementById("iot-kit-site");
  const detail = document.getElementById("iot-kit-detail");
  const result = document.getElementById("iot-kit-result");
  if (!kitSel || !siteSel) return;
  try {
    const kits = await apiGet("/iot/kits", accountId) || [];
    kitSel.innerHTML = "";
    kits.forEach((k) => { const o = document.createElement("option"); o.value = k.id; o.textContent = `${k.name} · $${k.price_usd}`; o._kit = k; kitSel.appendChild(o); });
    const sitesRaw = await apiGet("/mobile/sites", accountId) || [];
    const sites = Array.isArray(sitesRaw) ? sitesRaw : (sitesRaw.items || []);
    siteSel.innerHTML = "";
    sites.forEach((s) => { const o = document.createElement("option"); o.value = s.id; o.textContent = s.name; siteSel.appendChild(o); });
    const showDetail = () => {
      const k = kitSel.selectedOptions[0] && kitSel.selectedOptions[0]._kit;
      if (!k) { detail.textContent = ""; return; }
      detail.innerHTML = `<strong>${escapeHTML(k.summary || "")}</strong><br>${T("iot.kit.components")} (~$${k.bom_total_usd}): ${(k.diy_bom || []).map((b) => escapeHTML(b.part)).join(", ")}<br>KPIs: ${(k.kpis || []).map(escapeHTML).join(", ")}`;
    };
    kitSel.onchange = showDetail; showDetail();
  } catch (error) {
    console.warn("Kit catalogue unavailable", error);
  }
  document.getElementById("iot-kit-provision").onclick = async () => {
    const kitId = kitSel.value, siteId = siteSel.value;
    if (!siteId) { result.innerHTML = `<span style="color:#f87171;">${T("iot.kit.needSite")}</span>`; return; }
    result.textContent = T("iot.kit.creating");
    try {
      const res = await apiPost(`/iot/kits/${kitId}/provision`, { site_id: siteId }, accountId);
      result.innerHTML = `<span style="color:#22c55e;">${T("iot.kit.created")}: <strong>${escapeHTML(res.name)}</strong> (${escapeHTML(res.device_uid)}).</span> ${T("iot.kit.token")}: <code>${escapeHTML(res.provisioning.token)}</code>`;
      await loadIoTHardware(accountId);
    } catch (error) {
      result.innerHTML = `<span style="color:#f87171;">${T("insp.error")}: ${escapeHTML(String(error.message || error))}</span>`;
    }
  };
}

let iotMap = null;
let iotMapLayer = null;
async function renderDeviceMap() {
  if (typeof L === "undefined") { console.warn("Leaflet not loaded"); return; }
  const el = document.getElementById("iot-map");
  if (!el) return;
  if (!iotMap) {
    iotMap = L.map(el, { scrollWheelZoom: true }).setView([-8.83, 13.23], 6); // Angola default
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(iotMap);
    iotMapLayer = L.layerGroup().addTo(iotMap);
  }
  setTimeout(() => iotMap.invalidateSize(), 120);
  try {
    const devices = await apiGet("/iot/devices", currentAccountId) || [];
    iotMapLayer.clearLayers();
    const located = devices.filter((d) => typeof d.latitude === "number" && typeof d.longitude === "number");
    const emptyMsg = document.getElementById("iot-map-empty");
    if (emptyMsg) emptyMsg.style.display = located.length ? "none" : "block";
    const bounds = [];
    located.forEach((d) => {
      const stale = !d.last_seen_at || Date.now() - new Date(d.last_seen_at).getTime() > 120000;
      const color = stale ? "#94a3b8" : (d.status === "online" ? "#22c55e" : "#f59e0b");
      const maps = `https://www.google.com/maps?q=${d.latitude},${d.longitude}`;
      const marker = L.circleMarker([d.latitude, d.longitude], { radius: 9, color, fillColor: color, fillOpacity: 0.85, weight: 2 });
      marker.bindPopup(`<strong>${escapeHTML(d.name)}</strong><br>${escapeHTML(d.site_name || "")} · ${escapeHTML(stale ? T("iot.status.stale") : d.status)}<br><a href="${maps}" target="_blank" rel="noopener">📍 ${T("iot.openMaps")}</a>`);
      marker.addTo(iotMapLayer);
      bounds.push([d.latitude, d.longitude]);
    });
    if (bounds.length) iotMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
  } catch (error) {
    console.warn("device map load failed", error);
  }
}
window.gvRenderDeviceMap = renderDeviceMap;

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

// ── P1: operational home — IoT device-health summary + real device alerts ──
async function loadOperationalHome(accountId) {
  try {
    const devices = await apiGet("/iot/devices", accountId) || [];
    let alerts = [];
    try { alerts = await apiGet("/iot/alerts", accountId) || []; } catch (e) { /* no alerts scope */ }
    if (!devices.length) return; // no IoT deployment: leave generic KPIs/alerts as-is

    const now = Date.now();
    const stale = (d) => !d.last_seen_at || now - new Date(d.last_seen_at).getTime() > 120000;
    const online = devices.filter((d) => d.status === "online" && !stale(d)).length;
    const lowBatt = devices.filter((d) => typeof d.battery_percent === "number" && d.battery_percent > 0 && d.battery_percent < 20).length;
    const needsAttention = devices.filter((d) => stale(d) || d.status === "offline").length;
    const openStates = ["pending", "triggered", "notified", "acknowledged", "assigned"];
    const openAlerts = (alerts || []).filter((a) => openStates.includes(a.status));
    const critical = openAlerts.filter((a) => a.severity === "critical").length;
    const seenTimes = devices.map((d) => d.last_seen_at).filter(Boolean).map((s) => new Date(s).getTime());
    const lastSync = seenTimes.length ? new Date(Math.max(...seenTimes)) : null;

    const card = document.getElementById("iot-health-card");
    if (card) card.style.display = "block";
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("ioth-online", `${online}/${devices.length}`);
    set("ioth-critical", String(critical));
    set("ioth-battery", String(lowBatt));
    set("ioth-stale", String(needsAttention));
    const ls = document.getElementById("iot-health-lastsync");
    if (ls) ls.textContent = lastSync ? `${T("dash.iot.lastSync")}: ${lastSync.toLocaleString()}` : "";

    // Home "Alertas & Atenção" now shows the real device-alert lifecycle
    const container = document.getElementById("alerts-list");
    if (container) {
      if (!openAlerts.length) {
        container.innerHTML = `<div class="dash-empty">${T("dash.iot.noDeviceAlerts")}</div>`;
      } else {
        container.innerHTML = "";
        openAlerts.slice(0, 6).forEach((a) => {
          const div = document.createElement("div");
          div.className = `alert-item alert-${escapeHTML(a.severity)}`;
          div.innerHTML = `<div class="alert-header"><span class="alert-severity ${escapeHTML(a.severity)}">${escapeHTML(a.severity).toUpperCase()}</span><span class="alert-title">${escapeHTML(a.message || a.channel || "")}</span></div><div class="alert-description">${escapeHTML(a.status)}${a.value != null ? ` · ${escapeHTML(String(a.value))}` : ""}</div>`;
          container.appendChild(div);
        });
      }
    }
    const kpiA = document.getElementById("kpi-alerts");
    if (kpiA) kpiA.textContent = String(openAlerts.length);
  } catch (err) {
    console.warn("operational home unavailable", err);
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
  await loadIoTHardware(currentAccountId);
  await loadOperationalHome(currentAccountId);
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
