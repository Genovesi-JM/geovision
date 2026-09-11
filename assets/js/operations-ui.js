const SESSION_KEYS = Object.freeze([
  "gv_token", "gv_refresh_token", "gv_user", "gv_email", "gv_name", "gv_role",
  "gv_account_id", "gv_account_name", "gv_workspace_id", "gv_organization_id",
  "gv_toast", "gv_active_sector",
]);

export class ApiError extends Error {
  constructor(status, message, code = "request_failed") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const STATUS_LABELS_ES = Object.freeze({
  ACTIVE: "Activo", AVAILABLE: "Disponible", COMPLETED: "Completada",
  SUCCEEDED: "Correcto", READY: "Lista", APPROVED: "Aprobado",
  HEALTHY: "Correcto", FAILED: "Fallido", ERROR: "Error",
  BLOCKED: "Bloqueada", CANCELLED: "Cancelada", REJECTED: "Rechazado",
  UNHEALTHY: "No disponible", WAITING_INPUT: "Esperando información",
  PENDING: "Pendiente", LIMITED: "Disponibilidad limitada",
  QA_REVIEW: "Revisión de calidad", RETRYING: "Reintentando",
  RETRY_WAIT: "Esperando reintento", DEGRADED: "Degradado",
  OFFERED: "Ofrecida", ACCEPTED: "Aceptada", DECLINED: "Rechazada",
  IN_PROGRESS: "En curso", ASSIGNED: "Asignada", SCHEDULED: "Programada",
  PLANNED: "Planificada", NEEDS_REVIEW: "Requiere revisión",
  REVIEW_REQUIRED: "Revisión requerida", PUBLISHED: "Publicado",
  UNAVAILABLE: "No disponible", ON_HOLD: "En espera", INACTIVE: "Inactivo",
  LOW: "Baja", NORMAL: "Normal", HIGH: "Alta", URGENT: "Urgente",
});

export function statusLabel(value, fallback = "Desconocido") {
  const key = optionalString(value).toUpperCase();
  return STATUS_LABELS_ES[key] || sentence(value, fallback);
}

export function readAccessToken() {
  const token = localStorage.getItem("gv_token");
  return typeof token === "string" && token.trim() ? token.trim() : "";
}

export function clearSession() {
  SESSION_KEYS.forEach((key) => localStorage.removeItem(key));
  sessionStorage.removeItem("gv_pending_invitation");
}

export function signOut(destination = "index.html") {
  clearSession();
  window.location.assign(destination);
}

function extractError(payload, fallback) {
  const detail = payload && typeof payload === "object" ? payload.detail : null;
  if (typeof detail === "string" && detail.trim()) return { message: detail, code: "request_failed" };
  if (detail && typeof detail === "object") {
    const message = typeof detail.message === "string" && detail.message.trim() ? detail.message : fallback;
    const code = typeof detail.code === "string" && detail.code.trim() ? detail.code : "request_failed";
    return { message, code };
  }
  return { message: fallback, code: "request_failed" };
}

export class OperationsApi {
  constructor(baseUrl = window.API_BASE || "http://127.0.0.1:8010") {
    this.baseUrl = String(baseUrl).replace(/\/$/, "");
  }

  async request(path, options = {}) {
    const token = readAccessToken();
    if (!token) throw new ApiError(401, "Inicia sesión para continuar.", "missing_session");
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    headers.set("Authorization", `Bearer ${token}`);
    let body = options.body;
    if (body !== undefined && body !== null && !(body instanceof Blob) && !(body instanceof FormData) && typeof body !== "string") {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(body);
    }
    const response = await fetch(`${this.baseUrl}${path}`, { ...options, headers, body, credentials: "omit" });
    let payload = null;
    if (response.status !== 204) {
      const raw = await response.text();
      if (raw) {
        try { payload = JSON.parse(raw); } catch { payload = null; }
      }
    }
    if (!response.ok) {
      const fallback = response.status === 401 ? "Tu sesión ha caducado." : response.status === 403 ? "No tienes acceso a este espacio." : `La solicitud ha fallado (${response.status}).`;
      const problem = extractError(payload, fallback);
      throw new ApiError(response.status, problem.message, problem.code);
    }
    return payload;
  }

  get(path) { return this.request(path); }
  post(path, body) { return this.request(path, { method: "POST", body }); }
  patch(path, body) { return this.request(path, { method: "PATCH", body }); }
}

export function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function requiredString(value, field) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`Campo no válido: ${field}`);
  return value.trim();
}

export function optionalString(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

export function finiteNumber(value, fallback = 0) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function collection(value, field = "items") {
  if (Array.isArray(value)) return value.filter(isRecord);
  if (isRecord(value) && Array.isArray(value[field])) return value[field].filter(isRecord);
  return [];
}

export function capabilities(value, allowlist) {
  if (!Array.isArray(value)) throw new Error("La lista de capacidades no es válida");
  const allowed = new Set(allowlist);
  return new Set(value.filter((item) => typeof item === "string" && allowed.has(item)));
}

export function node(tag, options = {}, children = []) {
  const element = document.createElement(tag);
  if (options.className) element.className = options.className;
  if (options.text !== undefined) element.textContent = String(options.text);
  if (options.id) element.id = options.id;
  if (options.type) element.type = options.type;
  if (options.href) element.setAttribute("href", options.href);
  if (options.title) element.title = options.title;
  if (options.hidden) element.hidden = true;
  if (options.dataset) Object.entries(options.dataset).forEach(([key, value]) => { element.dataset[key] = String(value); });
  if (options.attrs) Object.entries(options.attrs).forEach(([key, value]) => {
    if (value !== undefined && value !== null) element.setAttribute(key, String(value));
  });
  const values = Array.isArray(children) ? children : [children];
  values.forEach((child) => {
    if (child instanceof Node) element.appendChild(child);
    else if (child !== undefined && child !== null) element.appendChild(document.createTextNode(String(child)));
  });
  return element;
}

export function replace(target, ...children) {
  target.replaceChildren(...children.filter(Boolean));
}

export function formatDate(value, options = {}) {
  if (!value) return "Sin programar";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Sin programar";
  return new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short", ...options }).format(date);
}

export function toLocalInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

export function sentence(value, fallback = "Desconocido") {
  const input = optionalString(value, fallback).replace(/[_-]+/g, " ").toLowerCase();
  return input.charAt(0).toUpperCase() + input.slice(1);
}

export function statusTone(value) {
  const status = optionalString(value).toUpperCase();
  if (["ACTIVE", "AVAILABLE", "COMPLETED", "SUCCEEDED", "READY", "APPROVED", "HEALTHY"].includes(status)) return "positive";
  if (["FAILED", "ERROR", "BLOCKED", "CANCELLED", "REJECTED", "UNHEALTHY"].includes(status)) return "danger";
  if (["WAITING_INPUT", "PENDING", "LIMITED", "QA_REVIEW", "RETRYING", "DEGRADED"].includes(status)) return "warning";
  return "neutral";
}

export function pill(value) {
  return node("span", { className: "status-pill", text: statusLabel(value), attrs: { "data-tone": statusTone(value) } });
}

export function button(label, options = {}) {
  const element = node("button", {
    className: `button ${options.variant === "primary" ? "button-primary" : options.variant === "danger" ? "button-danger" : "button-secondary"}`,
    text: label,
    type: ["button", "submit", "reset"].includes(options.type) ? options.type : "button",
    dataset: options.dataset,
    attrs: options.attrs,
  });
  if (options.onClick) element.addEventListener("click", options.onClick);
  return element;
}

export function emptyState(title, message) {
  return node("div", { className: "empty-state" }, [node("h2", { text: title }), node("p", { text: message })]);
}

export function sectionHeading(title, description, action = null) {
  return node("div", { className: "section-heading" }, [
    node("div", {}, [node("h2", { text: title }), node("p", { text: description })]),
    action,
  ]);
}

export function card(title, body, className = "") {
  const content = body instanceof Node ? body : node("div", { className: "card-body" }, body);
  return node("article", { className: `content-card ${className}`.trim() }, [
    title ? node("div", { className: "card-header" }, node("h2", { text: title })) : null,
    content,
  ]);
}

export function table(headers, rows, options = {}) {
  const tableElement = node("table", { className: `data-table ${options.compact ? "compact" : ""}`.trim() });
  const headRow = node("tr");
  headers.forEach((header) => headRow.appendChild(node("th", { text: header, attrs: { scope: "col" } })));
  tableElement.appendChild(node("thead", {}, headRow));
  const body = node("tbody");
  rows.forEach((cells) => {
    const row = node("tr");
    cells.forEach((cell) => row.appendChild(node("td", {}, cell)));
    body.appendChild(row);
  });
  tableElement.appendChild(body);
  return node("div", { className: "table-scroll", attrs: { tabindex: "0", "aria-label": options.label || "Tabla de datos desplazable" } }, tableElement);
}

export function setStatus(element, message = "", tone = "") {
  element.textContent = message;
  if (tone) element.dataset.tone = tone;
  else delete element.dataset.tone;
}

export function safeId(value) {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value) ? value : "";
}

export function safeFilename(value) {
  const name = optionalString(value, "deliverable.bin").replace(/[\\/\0-\x1f]/g, "_");
  return name.slice(0, 255) || "deliverable.bin";
}

export function encodePath(value) {
  const id = safeId(value);
  if (!id) throw new Error("Invalid resource identifier");
  return encodeURIComponent(id);
}

export function visibleError(error) {
  if (error instanceof ApiError) return error.message;
  return "No se pudieron cargar los datos verificados. Inténtalo de nuevo.";
}

export function setBusy(element, busy) {
  element.setAttribute("aria-busy", busy ? "true" : "false");
}

export function installLogout(...buttons) {
  buttons.filter(Boolean).forEach((item) => item.addEventListener("click", () => signOut()));
}
