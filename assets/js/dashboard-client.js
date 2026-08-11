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
  wireDeviceTabs(device.id, accountId);
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
  // Refresh the command-history tab so the queued command shows immediately.
  if (typeof iotTabLoaded !== "undefined") iotTabLoaded.commands = false;
  const cmdPanel = document.getElementById("iot-dtab-commands");
  if (cmdPanel && cmdPanel.style.display !== "none") { iotTabLoaded.commands = true; loadDeviceCommands(deviceId, accountId); }
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

// ── P3: device workspace tabs — analytics/health, calibration, commands, audit ──
let iotDetailDeviceId = null;
let iotDetailAccountId = null;
const iotTabLoaded = {};

function wireDeviceTabs(deviceId, accountId) {
  iotDetailDeviceId = deviceId;
  iotDetailAccountId = accountId;
  Object.keys(iotTabLoaded).forEach((k) => delete iotTabLoaded[k]); // new device -> reload tabs on demand
  document.querySelectorAll("#iot-detail-tabs .alert-filter").forEach((btn) => {
    btn.onclick = () => activateDeviceTab(btn.dataset.dtab);
  });
  activateDeviceTab("analytics");
}

function activateDeviceTab(tab) {
  document.querySelectorAll("#iot-detail-tabs .alert-filter").forEach((b) => b.classList.toggle("active", b.dataset.dtab === tab));
  ["analytics", "calibration", "commands", "audit"].forEach((t) => {
    const el = document.getElementById(`iot-dtab-${t}`);
    if (el) el.style.display = t === tab ? "block" : "none";
  });
  if (iotTabLoaded[tab]) return;
  iotTabLoaded[tab] = true;
  if (tab === "analytics") loadDeviceAnalytics(iotDetailDeviceId, iotDetailAccountId);
  else if (tab === "calibration") loadDeviceCalibration(iotDetailDeviceId, iotDetailAccountId);
  else if (tab === "commands") loadDeviceCommands(iotDetailDeviceId, iotDetailAccountId);
  else if (tab === "audit") loadDeviceAudit(iotDetailDeviceId, iotDetailAccountId);
}

function fmtDuration(sec) {
  if (sec == null) return "—";
  if (sec < 60) return `${Math.round(sec)}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}

async function loadDeviceAnalytics(deviceId, accountId) {
  const host = document.getElementById("iot-dtab-analytics");
  if (!host) return;
  host.innerHTML = `<div class="alert-console-empty">${T("common.loading")}</div>`;
  try {
    const a = await apiGet(`/iot/devices/${deviceId}/analytics?days=30`, accountId);
    const o = a.overview || {}; const inc = a.incidents || {};
    const comp = o.completeness_pct;
    const compClass = comp == null ? "" : (comp >= 90 ? "good" : comp >= 60 ? "warn" : "bad");
    const metrics = [
      { l: T("iot.an.status"), v: o.stale ? T("iot.status.stale") : (o.device_status || "—"), c: o.stale ? "bad" : "good" },
      { l: T("iot.an.readings"), v: o.total_readings ?? "—" },
      { l: T("iot.an.channels"), v: o.channels_reporting ?? "—" },
      { l: T("iot.an.completeness"), v: comp == null ? "—" : `${comp}%`, c: compClass },
      { l: T("iot.an.dataSpan"), v: o.data_span_ratio == null ? "—" : `${Math.round(o.data_span_ratio * 100)}%` },
      { l: T("iot.an.openIncidents"), v: inc.open ?? 0, c: (inc.open || 0) > 0 ? "warn" : "good" },
      { l: T("iot.an.mtta"), v: fmtDuration(inc.mtta_seconds) },
      { l: T("iot.an.mttr"), v: fmtDuration(inc.mttr_seconds) },
    ];
    let html = `<div class="metric-strip">` + metrics.map((m) => `<div class="metric"><div class="metric-label">${escapeHTML(m.l)}</div><div class="metric-value ${m.c || ""}">${escapeHTML(String(m.v))}</div></div>`).join("") + `</div>`;
    if ((a.channels || []).length) {
      html += `<div class="iot-subtitle">${T("iot.an.channelStats")}</div>`;
      html += `<table class="data-table"><thead><tr><th>${T("iot.an.channel")}</th><th>${T("iot.an.samples")}</th><th>${T("iot.an.min")}</th><th>${T("iot.an.avg")}</th><th>${T("iot.an.max")}</th><th>${T("iot.an.last")}</th><th>${T("iot.an.inRange")}</th><th>${T("iot.an.runHours")}</th></tr></thead><tbody>`;
      const fmt = (x) => x == null ? "—" : String(x);
      a.channels.forEach((s) => {
        const tir = s.time_in_range_pct == null ? "—" : `${s.time_in_range_pct}%`;
        const run = s.estimated_on_hours == null ? "—" : `${s.estimated_on_hours}h`;
        html += `<tr><td>${escapeHTML(s.channel)}${s.unit ? ` <span style="color:#64748b">(${escapeHTML(s.unit)})</span>` : ""}</td><td>${s.samples}</td><td>${escapeHTML(fmt(s.min))}</td><td>${escapeHTML(fmt(s.avg))}</td><td>${escapeHTML(fmt(s.max))}</td><td>${escapeHTML(fmt(s.last))}</td><td>${tir}</td><td>${run}</td></tr>`;
      });
      html += `</tbody></table>`;
    }
    if ((a.recommendations || []).length) {
      html += `<div class="iot-subtitle">${T("iot.an.recommendations")}</div>`;
      html += `<ul class="rec-list">` + a.recommendations.map((r) => `<li>${escapeHTML(r)}</li>`).join("") + `</ul>`;
    }
    host.innerHTML = html;
  } catch (err) {
    host.innerHTML = `<div class="alert-console-empty">${T("iot.an.failed")}: ${escapeHTML(err.message || String(err))}</div>`;
  }
}

async function loadDeviceCalibration(deviceId, accountId) {
  const host = document.getElementById("iot-dtab-calibration");
  if (!host) return;
  host.innerHTML = `<div class="alert-console-empty">${T("common.loading")}</div>`;
  try {
    const data = await apiGet(`/iot/devices/${deviceId}/calibrations`, accountId);
    const channels = data.channels || []; const records = data.records || [];
    const opts = channels.map((c) => `<option value="${escapeHTML(c.id)}">${escapeHTML(c.label)}${c.unit ? ` (${escapeHTML(c.unit)})` : ""}</option>`).join("");
    let html = channels.length ? `<form class="cal-form" id="cal-form">
      <label>${T("iot.cal.channel")}<select id="cal-channel">${opts}</select></label>
      <label>${T("iot.cal.offset")}<input type="number" step="any" id="cal-offset" value="0"></label>
      <label>${T("iot.cal.scale")}<input type="number" step="any" id="cal-scale" value="1"></label>
      <label>${T("iot.cal.reference")}<input type="number" step="any" id="cal-reference"></label>
      <label>${T("iot.cal.measured")}<input type="number" step="any" id="cal-measured"></label>
      <label style="flex:1;min-width:180px;">${T("iot.cal.notes")}<input type="text" id="cal-notes"></label>
      <button type="submit" class="btn btn-primary">${T("iot.cal.save")}</button>
    </form>` : `<div class="alert-console-empty">${T("iot.cal.noChannels")}</div>`;
    html += `<div class="iot-subtitle">${T("iot.cal.history")}</div>`;
    if (records.length) {
      html += `<table class="data-table"><thead><tr><th>${T("iot.an.channel")}</th><th>${T("iot.cal.offset")}</th><th>${T("iot.cal.scale")}</th><th>${T("iot.cal.reference")}</th><th>${T("iot.cal.measured")}</th><th>${T("iot.cal.notes")}</th><th>${T("iot.cal.when")}</th></tr></thead><tbody>`;
      records.forEach((r) => {
        html += `<tr><td>${escapeHTML(r.channel_label)}</td><td>${r.offset}</td><td>${r.scale}</td><td>${r.reference_value ?? "—"}</td><td>${r.measured_value ?? "—"}</td><td>${escapeHTML(r.notes || "—")}</td><td>${escapeHTML(new Date(r.calibrated_at).toLocaleString())}</td></tr>`;
      });
      html += `</tbody></table>`;
    } else {
      html += `<div class="alert-console-empty">${T("iot.cal.noHistory")}</div>`;
    }
    host.innerHTML = html;
    const form = document.getElementById("cal-form");
    if (form) form.onsubmit = async (e) => {
      e.preventDefault();
      const channelId = document.getElementById("cal-channel").value;
      const numOrNull = (id) => { const v = document.getElementById(id).value; return v === "" ? null : parseFloat(v); };
      const body = {
        offset: parseFloat(document.getElementById("cal-offset").value) || 0,
        scale: parseFloat(document.getElementById("cal-scale").value) || 1,
        reference_value: numOrNull("cal-reference"),
        measured_value: numOrNull("cal-measured"),
        notes: document.getElementById("cal-notes").value || null,
      };
      try {
        await apiPost(`/iot/channels/${channelId}/calibrations`, body, accountId);
        loadDeviceCalibration(deviceId, accountId);
      } catch (err) {
        window.alert(`${T("iot.cal.failed")}: ${err.message || err}`);
      }
    };
  } catch (err) {
    host.innerHTML = `<div class="alert-console-empty">${T("iot.cal.failed")}: ${escapeHTML(err.message || String(err))}</div>`;
  }
}

function cmdStatusClass(s) {
  if (["acknowledged", "completed", "confirmed"].includes(s)) return "resolved";
  if (["timed_out", "failed", "rejected"].includes(s)) return "open";
  return "acknowledged";
}

async function loadDeviceCommands(deviceId, accountId) {
  const host = document.getElementById("iot-dtab-commands");
  if (!host) return;
  host.innerHTML = `<div class="alert-console-empty">${T("common.loading")}</div>`;
  try {
    const rows = await apiGet(`/iot/devices/${deviceId}/commands`, accountId) || [];
    if (!rows.length) { host.innerHTML = `<div class="alert-console-empty">${T("iot.cmd.none")}</div>`; return; }
    let html = `<table class="data-table"><thead><tr><th>${T("iot.cmd.name")}</th><th>${T("iot.cmd.status")}</th><th>${T("iot.cmd.reason")}</th><th>${T("iot.cmd.failsafe")}</th><th>${T("iot.cmd.when")}</th></tr></thead><tbody>`;
    rows.forEach((r) => {
      html += `<tr><td>${escapeHTML(r.name)}</td><td><span class="alert-status-pill ${cmdStatusClass(r.status)}">${escapeHTML(r.status)}</span></td><td>${escapeHTML(r.reason || "—")}</td><td>${escapeHTML(r.fail_safe_state || "—")}</td><td>${escapeHTML(new Date(r.created_at).toLocaleString())}</td></tr>`;
    });
    html += `</tbody></table>`;
    host.innerHTML = html;
  } catch (err) {
    host.innerHTML = `<div class="alert-console-empty">${T("iot.cmd.failed")}: ${escapeHTML(err.message || String(err))}</div>`;
  }
}

async function loadDeviceAudit(deviceId, accountId) {
  const host = document.getElementById("iot-dtab-audit");
  if (!host) return;
  host.innerHTML = `<div class="alert-console-empty">${T("common.loading")}</div>`;
  try {
    const rows = await apiGet(`/iot/devices/${deviceId}/audit`, accountId) || [];
    if (!rows.length) { host.innerHTML = `<div class="alert-console-empty">${T("iot.audit.none")}</div>`; return; }
    host.innerHTML = rows.map((r) => `<div class="audit-row"><span class="audit-time">${escapeHTML(new Date(r.created_at).toLocaleString())}</span><span class="audit-action">${escapeHTML(r.action)}</span><span class="audit-user">${escapeHTML(r.user_email || "—")}</span></div>`).join("");
  } catch (err) {
    host.innerHTML = `<div class="alert-console-empty">${T("iot.audit.failed")}: ${escapeHTML(err.message || String(err))}</div>`;
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

// ── P4: geospatial workspace — sites, devices, alerts, layer control ──
let iotMap = null;
let geoLayers = null; // { sites, devices, alerts } layer groups
let geoWired = false;
const geoLayerOn = { sites: true, devices: true, alerts: true };
const geoSiteMarkers = {};
const geoDeviceMarkers = {};

function deviceIsStale(d) { return !d.last_seen_at || Date.now() - new Date(d.last_seen_at).getTime() > 120000; }
function deviceColor(d) { return deviceIsStale(d) ? "#94a3b8" : (d.status === "online" ? "#22c55e" : "#f59e0b"); }

function wireGeoWorkspace() {
  if (geoWired) return;
  geoWired = true;
  document.querySelectorAll("#geo-layers .alert-filter").forEach((btn) => {
    btn.onclick = () => {
      const layer = btn.dataset.layer;
      geoLayerOn[layer] = !geoLayerOn[layer];
      btn.classList.toggle("active", geoLayerOn[layer]);
      applyGeoLayerVisibility();
    };
  });
  const refresh = document.getElementById("geo-refresh");
  if (refresh) refresh.onclick = () => renderDeviceMap();
}

function applyGeoLayerVisibility() {
  if (!iotMap || !geoLayers) return;
  ["sites", "devices", "alerts"].forEach((k) => {
    if (geoLayerOn[k]) { if (!iotMap.hasLayer(geoLayers[k])) geoLayers[k].addTo(iotMap); }
    else if (iotMap.hasLayer(geoLayers[k])) iotMap.removeLayer(geoLayers[k]);
  });
}

async function renderDeviceMap() {
  if (typeof L === "undefined") { console.warn("Leaflet not loaded"); return; }
  const el = document.getElementById("iot-map");
  if (!el) return;
  wireGeoWorkspace();
  const accountId = alertAccountId();
  if (!iotMap) {
    iotMap = L.map(el, { scrollWheelZoom: true }).setView([-8.83, 13.23], 6); // Angola default
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(iotMap);
    geoLayers = { sites: L.layerGroup().addTo(iotMap), devices: L.layerGroup().addTo(iotMap), alerts: L.layerGroup().addTo(iotMap) };
  }
  setTimeout(() => iotMap.invalidateSize(), 120);
  try {
    const [devices, sites, alerts] = await Promise.all([
      apiGet("/iot/devices", accountId).catch(() => []),
      apiGet("/mobile/sites", accountId).catch(() => []),
      apiGet("/iot/alerts", accountId).catch(() => []),
    ]);
    Object.values(geoLayers).forEach((l) => l.clearLayers());
    Object.keys(geoSiteMarkers).forEach((k) => delete geoSiteMarkers[k]);
    Object.keys(geoDeviceMarkers).forEach((k) => delete geoDeviceMarkers[k]);

    // Open alerts per device.
    const openStates = ["pending", "triggered", "notified", "acknowledged", "assigned"];
    const openByDevice = {};
    (alerts || []).filter((a) => openStates.includes(a.status)).forEach((a) => {
      openByDevice[a.device_id] = (openByDevice[a.device_id] || 0) + 1;
    });

    const bounds = [];
    // Sites: marker + area circle sized by hectares.
    (sites || []).forEach((s) => {
      const lat = s.center && s.center.lat, lng = s.center && s.center.lng;
      if (!lat || !lng) return; // 0/0 = no coordinates
      const deviceCount = (devices || []).filter((d) => d.site_name === s.name).length;
      const siteAlerts = (devices || []).filter((d) => d.site_name === s.name).reduce((n, d) => n + (openByDevice[d.id] || 0), 0);
      if (s.total_hectares > 0) {
        const radiusM = Math.sqrt((s.total_hectares * 10000) / Math.PI);
        L.circle([lat, lng], { radius: radiusM, color: "#38bdf8", weight: 1, fillColor: "#38bdf8", fillOpacity: 0.08 }).addTo(geoLayers.sites);
      }
      const marker = L.marker([lat, lng]);
      marker.bindPopup(`<strong>${escapeHTML(s.name)}</strong><br>${escapeHTML(s.sector || "")}${s.total_hectares ? ` · ${s.total_hectares} ha` : ""}<br>${deviceCount} ${escapeHTML(T("geo.devices"))}${siteAlerts ? ` · ${siteAlerts} ${escapeHTML(T("geo.alerts"))}` : ""}`);
      marker.addTo(geoLayers.sites);
      geoSiteMarkers[s.id] = { marker, lat, lng };
      bounds.push([lat, lng]);
    });

    // Devices: status-coloured markers; alert ring for devices with open alerts.
    const located = (devices || []).filter((d) => typeof d.latitude === "number" && typeof d.longitude === "number");
    located.forEach((d) => {
      const color = deviceColor(d);
      const maps = `https://www.google.com/maps?q=${d.latitude},${d.longitude}`;
      const marker = L.circleMarker([d.latitude, d.longitude], { radius: 9, color, fillColor: color, fillOpacity: 0.85, weight: 2 });
      marker.bindPopup(`<strong>${escapeHTML(d.name)}</strong><br>${escapeHTML(d.site_name || "")} · ${escapeHTML(deviceIsStale(d) ? T("iot.status.stale") : d.status)}${openByDevice[d.id] ? `<br>⚠ ${openByDevice[d.id]} ${escapeHTML(T("geo.alerts"))}` : ""}<br><a href="${maps}" target="_blank" rel="noopener">📍 ${T("iot.openMaps")}</a>`);
      marker.addTo(geoLayers.devices);
      geoDeviceMarkers[d.id] = { marker, lat: d.latitude, lng: d.longitude };
      bounds.push([d.latitude, d.longitude]);
      if (openByDevice[d.id]) {
        L.circleMarker([d.latitude, d.longitude], { radius: 16, color: "#ef4444", weight: 2, fill: false, opacity: 0.8 }).addTo(geoLayers.alerts);
      }
    });

    const emptyMsg = document.getElementById("iot-map-empty");
    if (emptyMsg) emptyMsg.style.display = bounds.length ? "none" : "block";
    if (bounds.length) iotMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    applyGeoLayerVisibility();
    renderGeoSide(sites || [], devices || [], openByDevice);
  } catch (error) {
    console.warn("geospatial workspace load failed", error);
  }
}

function renderGeoSide(sites, devices, openByDevice) {
  const host = document.getElementById("geo-side");
  if (!host) return;
  let html = "";
  const locatedSites = sites.filter((s) => s.center && s.center.lat && s.center.lng);
  html += `<div class="geo-side-title">${T("geo.sitesTitle")} (${locatedSites.length})</div>`;
  if (!locatedSites.length) {
    html += `<div class="geo-empty">${T("geo.noSites")}</div>`;
  } else {
    locatedSites.forEach((s) => {
      const siteDevices = devices.filter((d) => d.site_name === s.name);
      const siteAlerts = siteDevices.reduce((n, d) => n + (openByDevice[d.id] || 0), 0);
      html += `<div class="geo-item" data-focus-site="${escapeHTML(s.id)}">
        <div class="geo-item-name"><i class="fa-solid fa-location-dot" style="color:#38bdf8"></i> ${escapeHTML(s.name)}${siteAlerts ? ` <span class="geo-badge-alert">${siteAlerts} ⚠</span>` : ""}</div>
        <div class="geo-item-meta"><span>${escapeHTML(s.sector || "—")}</span>${s.total_hectares ? `<span>${s.total_hectares} ha</span>` : ""}<span>${siteDevices.length} ${escapeHTML(T("geo.devices"))}</span></div>
      </div>`;
    });
  }
  const locatedDevices = devices.filter((d) => typeof d.latitude === "number" && typeof d.longitude === "number");
  html += `<div class="geo-side-title" style="margin-top:.75rem;">${T("geo.devicesTitle")} (${locatedDevices.length})</div>`;
  if (!locatedDevices.length) {
    html += `<div class="geo-empty">${T("geo.noDevices")}</div>`;
  } else {
    locatedDevices.forEach((d) => {
      html += `<div class="geo-item" data-focus-device="${escapeHTML(d.id)}">
        <div class="geo-item-name"><span class="geo-dot" style="background:${deviceColor(d)}"></span> ${escapeHTML(d.name)}${openByDevice[d.id] ? ` <span class="geo-badge-alert">${openByDevice[d.id]} ⚠</span>` : ""}</div>
        <div class="geo-item-meta"><span>${escapeHTML(d.site_name || "—")}</span><span>${escapeHTML(deviceIsStale(d) ? T("iot.status.stale") : d.status)}</span></div>
      </div>`;
    });
  }
  host.innerHTML = html;
  host.querySelectorAll("[data-focus-site]").forEach((el) => {
    el.onclick = () => { const m = geoSiteMarkers[el.dataset.focusSite]; if (m) { iotMap.setView([m.lat, m.lng], 14); m.marker.openPopup(); } };
  });
  host.querySelectorAll("[data-focus-device]").forEach((el) => {
    el.onclick = () => { const m = geoDeviceMarkers[el.dataset.focusDevice]; if (m) { iotMap.setView([m.lat, m.lng], 15); m.marker.openPopup(); } };
  });
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
    if (!devices.length) { renderPersonaHome(accountId, [], [], 0); return; } // no IoT deployment

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

    // Home "Alertas & Atenção" merges sector/KPI alerts (rendered earlier by
    // loadAlerts) with the real device-alert lifecycle, device issues on top.
    const container = document.getElementById("alerts-list");
    if (container) {
      // Drop any "no alerts" placeholder left by loadAlerts, keep real items.
      container.querySelectorAll(".dash-empty").forEach((el) => el.remove());
      const kpiAlertCount = container.querySelectorAll(".alert-item").length;
      openAlerts.slice(0, 6).reverse().forEach((a) => {
        const div = document.createElement("div");
        div.className = `alert-item alert-${escapeHTML(a.severity)}`;
        div.innerHTML = `<div class="alert-header"><span class="alert-severity ${escapeHTML(a.severity)}">${escapeHTML(a.severity).toUpperCase()}</span><span class="alert-title">${escapeHTML(a.message || a.channel || "")}</span></div><div class="alert-description">${escapeHTML(a.status)}${a.value != null ? ` · ${escapeHTML(String(a.value))}` : ""}</div>`;
        container.insertBefore(div, container.firstChild);
      });
      if (!container.querySelector(".alert-item")) {
        container.innerHTML = `<div class="dash-empty">${T("dash.iot.noDeviceAlerts")}</div>`;
      }
      const kpiA = document.getElementById("kpi-alerts");
      if (kpiA) kpiA.textContent = String(kpiAlertCount + openAlerts.length);
    }
    renderPersonaHome(accountId, devices, openAlerts, needsAttention);
  } catch (err) {
    console.warn("operational home unavailable", err);
  }
}

// ── Persona-adaptive experience (simple shell vs advanced console) ──
function gvDefaultExperience(account) {
  const et = ((account && account.entity_type) || "").toLowerCase();
  return /empresa|enterprise|company|organi|corp|gov|multi/.test(et) ? "advanced" : "simple";
}
function gvApplyExperience(mode) {
  document.body.setAttribute("data-exp", mode);
  document.querySelectorAll("#exp-toggle .exp-btn").forEach((b) => b.classList.toggle("active", b.dataset.exp === mode));
  // If a now-hidden advanced view is active, fall back to the home overview.
  if (mode === "simple") {
    const activeAdv = document.querySelector(".sidebar-link.active[data-adv]");
    if (activeAdv && typeof window.switchView === "function") window.switchView("dashboard");
  }
}
function initExperience(account) {
  const key = "gv_experience_" + (localStorage.getItem(SESSION_ACCOUNT_KEY) || "default");
  const mode = localStorage.getItem(key) || gvDefaultExperience(account);
  gvApplyExperience(mode);
  document.querySelectorAll("#exp-toggle .exp-btn").forEach((b) => {
    b.onclick = () => { localStorage.setItem(key, b.dataset.exp); gvApplyExperience(b.dataset.exp); };
  });
}

// ── Persona "today" home (simple experience: farm / site / device) ──
function personaFor(accountId) {
  return localStorage.getItem("gv_persona_" + accountId) || localStorage.getItem("gv_persona") || null;
}
function renderPersonaHome(accountId, devices, openAlerts, needsAttention) {
  const card = document.getElementById("persona-home");
  if (!card) return;
  const simple = document.body.getAttribute("data-exp") === "simple";
  const persona = personaFor(accountId);
  const simplePersonas = ["farm", "site", "device"];
  if (!simple && !(persona && simplePersonas.includes(persona))) { card.style.display = "none"; return; }
  card.style.display = "block";

  const hour = new Date().getHours();
  const greet = hour < 12 ? T("persona.morning") : hour < 19 ? T("persona.afternoon") : T("persona.evening");
  const g = document.getElementById("persona-greeting"); if (g) g.textContent = greet;

  const critical = openAlerts.filter((a) => a.severity === "critical");
  const warnings = openAlerts.filter((a) => a.severity !== "critical");
  let headline = "", action = "";
  if (critical.length) {
    headline = `<span class="pill critical">${T("dash.iot.critical")}</span>${escapeHTML(critical[0].message || critical[0].channel || "")}`;
    action = `<button class="btn btn-primary" onclick="switchView('alerts')">${T("persona.viewAlert")}</button>`;
  } else if (warnings.length) {
    headline = `<span class="pill warning">${escapeHTML(warnings[0].severity).toUpperCase()}</span>${escapeHTML(warnings[0].message || warnings[0].channel || "")}`;
    action = `<button class="btn btn-primary" onclick="switchView('alerts')">${T("persona.viewAlert")}</button>`;
  } else if (needsAttention > 0) {
    headline = `<span class="pill warning">!</span>${needsAttention} ${T("dash.iot.attention")}`;
    action = `<button class="btn btn-primary" onclick="switchView('hardware')">${T("dash.nav.hardware")}</button>`;
  } else {
    headline = `<span class="pill ok">✓</span>${T("persona.allGood")}`;
    action = `<button class="btn btn-ghost" onclick="switchView('hardware')">${T("dash.nav.hardware")}</button>`;
  }
  action += ` <a class="btn btn-ghost" href="loja.html">${T("dash.nav.store")}</a>`;
  const h = document.getElementById("persona-headline"); if (h) h.innerHTML = headline;
  const a = document.getElementById("persona-actions"); if (a) a.innerHTML = action;
}

// ── P5: commercial / entitlement panel ──
function formatKitLabel(raw) {
  if (!raw) return "";
  const s = String(raw).replace(/^geovision-/i, "").replace(/^DIY[:_-]/i, "").replace(/_/g, " ");
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

async function loadEntitlement(accountId) {
  const card = document.getElementById("entitlement-card");
  if (!card) return;
  try {
    const e = await apiGet("/me/entitlement", accountId);
    if (!e || !e.has_company) return;
    card.style.display = "block";
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("ent-tier", (e.tier || "—").toString().replace(/\b\w/g, (c) => c.toUpperCase()));
    set("ent-kit", formatKitLabel(e.kit) || "—");
    set("ent-days", e.days_remaining == null ? "—" : String(e.days_remaining));
    set("ent-devices", e.devices_deployed ?? "—");
    const used = e.sensors_used || 0, allow = e.sensor_allowance || 0;
    const pct = allow > 0 ? Math.min(100, Math.round((100 * used) / allow)) : 0;
    set("ent-sensors-label", `${used} / ${allow}`);
    const bar = document.getElementById("ent-sensors-bar");
    if (bar) { bar.style.width = `${pct}%`; bar.className = "ent-bar-fill" + (pct >= 90 ? " bad" : pct >= 75 ? " warn" : ""); }
    const status = document.getElementById("ent-status");
    if (status) {
      status.textContent = T("ent.status." + e.status) || e.status;
      status.className = "badge ent-" + e.status;
    }
    const kitsEl = document.getElementById("ent-kits");
    if (kitsEl) {
      const labels = (e.kits_deployed || []).map(formatKitLabel).filter(Boolean);
      kitsEl.textContent = labels.length ? `${T("ent.kitsDeployed")}: ${labels.join(", ")}` : "";
    }
    const derived = document.getElementById("ent-derived");
    if (derived) derived.style.display = e.derived ? "block" : "none";
  } catch (err) {
    console.warn("entitlement load failed", err);
  }
}

// ── P5: connect device analytics reports + asset inspections into Reports view ──
async function loadDeviceReports(accountId) {
  const card = document.getElementById("device-reports-card");
  const list = document.getElementById("device-reports-list");
  if (!card || !list) return;
  try {
    const devices = await apiGet("/iot/devices", accountId) || [];
    if (!devices.length) { card.style.display = "none"; return; }
    card.style.display = "block";
    list.innerHTML = "";
    devices.forEach((d) => {
      const row = document.createElement("div");
      row.className = "alert-item";
      row.innerHTML = `<div class="alert-header"><span class="alert-title"><i class="fa-solid fa-microchip"></i> ${escapeHTML(d.name)}</span><span style="margin-left:auto;display:flex;gap:.4rem;">` +
        `<button class="btn btn-primary" data-report="${escapeHTML(d.id)}"><i class="fa-solid fa-file-pdf"></i> ${T("iot.report.pdf")}</button>` +
        `<button class="btn btn-ghost" data-csv="${escapeHTML(d.id)}"><i class="fa-solid fa-file-csv"></i> CSV</button></span></div>` +
        `<div class="alert-description">${escapeHTML(d.site_name || "—")} · ${escapeHTML(deviceIsStale(d) ? T("iot.status.stale") : d.status)}</div>`;
      list.appendChild(row);
    });
    list.querySelectorAll("button[data-report]").forEach((b) => { b.onclick = () => downloadIotReport(b.dataset.report, accountId); });
    list.querySelectorAll("button[data-csv]").forEach((b) => { b.onclick = () => downloadIotCsv(b.dataset.csv, accountId); });
  } catch (err) {
    console.warn("device reports load failed", err);
    card.style.display = "none";
  }
}

async function loadInspections(accountId) {
  const card = document.getElementById("inspections-card");
  const host = document.getElementById("inspections-list");
  if (!card || !host) return;
  try {
    const rows = await apiGet("/construction/inspections", accountId) || [];
    if (!rows.length) { card.style.display = "none"; return; }
    card.style.display = "block";
    const resultClass = (r) => r === "pass" ? "resolved" : (r === "fail" ? "open" : "acknowledged");
    host.innerHTML = `<table class="data-table"><thead><tr><th>${T("rep.insp.asset")}</th><th>${T("rep.insp.category")}</th><th>${T("rep.insp.result")}</th><th>${T("rep.insp.inspector")}</th><th>${T("common.date")}</th></tr></thead><tbody>` +
      rows.map((r) => `<tr><td>${escapeHTML((r.asset_id || "—").slice(0, 8))}</td><td>${escapeHTML(r.category || "—")}</td><td><span class="alert-status-pill ${resultClass(r.result)}">${escapeHTML(r.result || "—")}</span></td><td>${escapeHTML(r.inspector_name || "—")}</td><td>${escapeHTML(r.created_at ? new Date(r.created_at).toLocaleString() : "—")}</td></tr>`).join("") +
      `</tbody></table>`;
  } catch (err) {
    card.style.display = "none"; // inspections unavailable for this account type
  }
}

window.gvLoadDeviceReports = (id) => { const a = id || alertAccountId(); loadDeviceReports(a); loadInspections(a); };

// ── P2: IoT alert console + intervention workflow ──
const ALERT_OPEN_STATES = ["pending", "triggered", "notified"];
let alertConsoleFilter = "open";
let alertConsoleWired = false;
let alertConsoleData = { alerts: [], deviceNames: {} };

function alertAccountId() { return localStorage.getItem(SESSION_ACCOUNT_KEY) || null; }

function wireAlertConsole() {
  if (alertConsoleWired) return;
  alertConsoleWired = true;
  document.querySelectorAll("#alert-filters .alert-filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      alertConsoleFilter = btn.dataset.filter;
      document.querySelectorAll("#alert-filters .alert-filter").forEach((b) => b.classList.toggle("active", b === btn));
      renderAlertConsole();
    });
  });
  const refresh = document.getElementById("alert-refresh");
  if (refresh) refresh.addEventListener("click", () => loadAlertConsole());
}

async function loadAlertConsole() {
  wireAlertConsole();
  const accountId = alertAccountId();
  try {
    const [devices, alerts] = await Promise.all([
      apiGet("/iot/devices", accountId).catch(() => []),
      apiGet("/iot/alerts", accountId).catch(() => []),
    ]);
    const deviceNames = {};
    (devices || []).forEach((d) => { deviceNames[d.id] = d.name || d.device_uid; });
    alertConsoleData = { alerts: alerts || [], deviceNames };
    updateAlertConsoleSummary();
    renderAlertConsole();
  } catch (err) {
    console.warn("alert console load failed", err);
  }
}

function updateAlertConsoleSummary() {
  const a = alertConsoleData.alerts;
  const open = a.filter((x) => ALERT_OPEN_STATES.includes(x.status));
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = String(v); };
  set("ac-open", open.length);
  set("ac-critical", open.filter((x) => x.severity === "critical").length);
  set("ac-ack", a.filter((x) => x.status === "acknowledged" || x.status === "assigned").length);
  set("ac-resolved", a.filter((x) => x.status === "resolved").length);
}

function alertMatchesFilter(a) {
  switch (alertConsoleFilter) {
    case "open": return ALERT_OPEN_STATES.includes(a.status);
    case "acknowledged": return a.status === "acknowledged";
    case "assigned": return a.status === "assigned";
    case "resolved": return a.status === "resolved";
    case "closed": return a.status === "closed";
    default: return true;
  }
}

function alertFmtTime(iso) { return iso ? new Date(iso).toLocaleString() : "—"; }

function renderAlertConsole() {
  const container = document.getElementById("alert-console");
  if (!container) return;
  const list = alertConsoleData.alerts
    .filter(alertMatchesFilter)
    .sort((a, b) => (b.opened_at || "").localeCompare(a.opened_at || ""));
  if (!list.length) {
    container.innerHTML = `<div class="alert-console-empty">${T("dash.alerts.none")}</div>`;
    return;
  }
  container.innerHTML = "";
  list.forEach((a) => {
    const sev = ["critical", "warning", "info"].includes(a.severity) ? a.severity : "info";
    const stClass = ALERT_OPEN_STATES.includes(a.status) ? "open" : a.status;
    const device = alertConsoleData.deviceNames[a.device_id] || a.device_id || "—";
    const div = document.createElement("div");
    div.className = `alert-item ${sev}`;
    const tl = [`<span><i class="fa-solid fa-bell"></i>${T("dash.alerts.tl.opened")}: ${escapeHTML(alertFmtTime(a.opened_at))}</span>`];
    if (a.acknowledged_at) tl.push(`<span><i class="fa-solid fa-user-check"></i>${T("dash.alerts.tl.acknowledged")}: ${escapeHTML(alertFmtTime(a.acknowledged_at))}</span>`);
    if (a.assigned_to) tl.push(`<span><i class="fa-solid fa-user-gear"></i>${T("dash.alerts.tl.assigned")}: ${escapeHTML(a.assigned_to)}</span>`);
    if (a.resolved_at) tl.push(`<span><i class="fa-solid fa-circle-check"></i>${T("dash.alerts.tl.resolved")}: ${escapeHTML(alertFmtTime(a.resolved_at))}</span>`);
    if (a.closed_at) tl.push(`<span><i class="fa-solid fa-lock"></i>${T("dash.alerts.tl.closed")}: ${escapeHTML(alertFmtTime(a.closed_at))}</span>`);
    const actions = [];
    if (a.status === "triggered" || a.status === "notified") actions.push(`<button class="btn btn-primary" data-act="ack" data-id="${escapeHTML(a.id)}">${T("dash.alerts.act.acknowledge")}</button>`);
    if (a.status === "acknowledged" || a.status === "assigned") actions.push(`<button class="btn btn-ghost" data-act="assign" data-id="${escapeHTML(a.id)}">${T(a.status === "assigned" ? "dash.alerts.act.reassign" : "dash.alerts.act.assign")}</button>`);
    if (["resolved", "acknowledged", "assigned"].includes(a.status)) actions.push(`<button class="btn btn-ghost" data-act="close" data-id="${escapeHTML(a.id)}">${T("dash.alerts.act.close")}</button>`);
    div.innerHTML =
      `<div class="alert-header">` +
        `<span class="alert-severity ${sev}">${escapeHTML(a.severity).toUpperCase()}</span>` +
        `<span class="alert-title">${escapeHTML(a.message || a.channel || "")}</span>` +
        `<span class="alert-status-pill ${stClass}">${escapeHTML(T("dash.alerts.state." + a.status))}</span>` +
      `</div>` +
      `<div class="alert-description"><i class="fa-solid fa-microchip"></i> ${escapeHTML(device)}${a.value != null ? ` · ${escapeHTML(a.channel || "")}=${escapeHTML(String(a.value))}` : ""}</div>` +
      `<div class="alert-timeline">${tl.join("")}</div>` +
      (actions.length ? `<div class="alert-actions">${actions.join("")}</div>` : "");
    container.appendChild(div);
  });
  container.querySelectorAll("button[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => handleAlertAction(btn.dataset.act, btn.dataset.id));
  });
}

async function handleAlertAction(act, id) {
  const accountId = alertAccountId();
  try {
    if (act === "ack") {
      await apiPost(`/iot/alerts/${id}/acknowledge`, {}, accountId);
    } else if (act === "assign") {
      const assignee = window.prompt(T("dash.alerts.assignPrompt"));
      if (!assignee) return;
      await apiPost(`/iot/alerts/${id}/assign`, { assignee_id: assignee.trim() }, accountId);
    } else if (act === "close") {
      if (!window.confirm(T("dash.alerts.closeConfirm"))) return;
      await apiPost(`/iot/alerts/${id}/close`, {}, accountId);
    }
    await loadAlertConsole();
  } catch (err) {
    window.alert(`${T("dash.alerts.actionFailed")}: ${err.message || err}`);
  }
}

window.gvLoadAlertConsole = loadAlertConsole;

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

  // Individual workspaces only offer consumer-relevant sectors; industrial
  // ones (mining, construction, infrastructure) are for organisations.
  const MODAL_INDIVIDUAL_SECTORS = ["agro", "ambiental"];
  function filterModalSectors() {
    const entity = document.getElementById("account-entity-input")?.value || "org";
    const sel = document.getElementById("account-sector-input");
    if (!sel) return;
    const individual = entity === "individual";
    [...sel.options].forEach((o) => { const ok = !individual || MODAL_INDIVIDUAL_SECTORS.includes(o.value); o.hidden = !ok; o.disabled = !ok; });
    const current = [...sel.options].find((o) => o.value === sel.value);
    if (!current || current.hidden) sel.value = "agro";
  }
  const entitySel = document.getElementById("account-entity-input");
  if (entitySel && !entitySel.dataset.gvBound) { entitySel.addEventListener("change", filterModalSectors); entitySel.dataset.gvBound = "1"; }

  // ── Bind modal buttons early — BEFORE any await/render that could throw ──
  if (openModal && !openModal.dataset.gvBound) {
    openModal.onclick = () => {
      const name = document.getElementById("account-name-input");
      if (name) name.value = "";
      filterModalSectors();
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

  // Persona-adaptive experience: individuals default to the simple shell,
  // organisations to the full advanced console (user can switch).
  initExperience(activeAccount);

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
  await loadEntitlement(currentAccountId);
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
