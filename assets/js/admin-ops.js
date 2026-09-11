import {
  ApiError, OperationsApi, button, capabilities, card, collection, emptyState,
  encodePath, finiteNumber, formatDate, installLogout, isRecord, node, optionalString,
  pill, replace, requiredString, safeId, sectionHeading, sentence, setBusy, setStatus,
  table, toLocalInput, visibleError,
} from "./operations-ui.js";

const NAVIGATION = Object.freeze({
  dashboard: { label: "Resumen", view: "dashboard", group: "Visión general", icon: "⌂" },
  organizations: { label: "Clientes y organizaciones", view: "organizations", group: "Clientes", icon: "◎" },
  assets: { label: "Activos", view: "assets", group: "Clientes", icon: "◇" },
  orders: { label: "Pedidos", view: "orders", group: "Ejecución", icon: "▤" },
  jobs: { label: "Tareas", view: "jobs", group: "Ejecución", icon: "✓" },
  missions: { label: "Misiones", view: "missions", group: "Ejecución", icon: "⌁" },
  processing: { label: "Procesamiento", view: "processing", group: "Ejecución", icon: "◌" },
  reports_qa: { label: "Calidad de informes", view: "reports-qa", group: "Ejecución", icon: "◫" },
  contractors: { label: "Colaboradores", view: "contractors", group: "Red externa", icon: "♙" },
  inventory: { label: "Proveedores e inventario", view: "inventory", group: "Red externa", icon: "▦" },
  finance_sync: { label: "Sincronización financiera", view: "finance-sync", group: "Plataforma", icon: "⇄" },
  integrations: { label: "Integraciones", view: "integrations", group: "Plataforma", icon: "⌘" },
  system_health: { label: "Estado del sistema", view: "system-health", group: "Plataforma", icon: "♥" },
});
const NAV_ORDER = Object.freeze(Object.keys(NAVIGATION));
const MISSION_TRANSITIONS = Object.freeze({
  DRAFT: ["PLANNED", "CANCELLED"], PLANNED: ["SCHEDULED", "IN_PROGRESS", "CANCELLED", "FAILED"],
  SCHEDULED: ["IN_PROGRESS", "CANCELLED", "FAILED"], IN_PROGRESS: ["DATA_CAPTURED", "NEEDS_REFLIGHT", "CANCELLED", "FAILED"],
  DATA_CAPTURED: ["PROCESSING", "COMPLETED", "NEEDS_REFLIGHT", "FAILED"], PROCESSING: ["COMPLETED", "NEEDS_REFLIGHT", "FAILED"],
  NEEDS_REFLIGHT: ["PLANNED", "CANCELLED"], COMPLETED: [], CANCELLED: [], FAILED: [],
});
const API = new OperationsApi();
const state = {
  experience: null, capabilities: new Set(), permissions: new Set(), visibleKeys: [], current: "",
  dashboard: null, queues: null, jobs: null, contractors: null, orders: null, missions: null, companies: null, workflowJob: null,
};
const elements = {
  app: document.getElementById("operations-app"), loading: document.getElementById("operations-loading"),
  denied: document.getElementById("operations-denied"), deniedMessage: document.getElementById("operations-denied-message"),
  nav: document.getElementById("operations-navigation"), sidebar: document.getElementById("operations-sidebar"),
  scrim: document.getElementById("sidebar-scrim"), menu: document.getElementById("operations-menu"),
  title: document.getElementById("operations-view-title"), view: document.getElementById("operations-view"),
  status: document.getElementById("operations-status"), refresh: document.getElementById("operations-refresh"),
  dialog: document.getElementById("job-workflow-dialog"), workflow: document.getElementById("job-workflow-form"),
  feedback: document.getElementById("workflow-feedback"),
};

function expectedPath(key) { return `/admin.html?view=${NAVIGATION[key].view}`; }

function validateExperience(payload) {
  if (!isRecord(payload) || payload.surface !== "INTERNAL_OPERATIONS" || !isRecord(payload.actor)) throw new Error("Experiencia de Operaciones no válida");
  requiredString(payload.actor.user_id, "actor.user_id");
  if (!Array.isArray(payload.actor.roles) || !payload.actor.roles.some((role) => typeof role === "string" && role.trim())) throw new Error("Roles de Operaciones no válidos");
  if (!Array.isArray(payload.actor.permissions) || !Array.isArray(payload.navigation)) throw new Error("Autorización de Operaciones no válida");
  const granted = capabilities(payload.capabilities, NAV_ORDER);
  const visible = new Set();
  payload.navigation.forEach((item) => {
    if (!isRecord(item) || typeof item.key !== "string" || !granted.has(item.key)) return;
    if (item.capability !== item.key || !NAVIGATION[item.key]) return;
    if (item.label !== NAVIGATION[item.key].label || item.path !== expectedPath(item.key)) return;
    visible.add(item.key);
  });
  const visibleKeys = NAV_ORDER.filter((key) => visible.has(key));
  if (!visibleKeys.length) throw new Error("La navegación de Operaciones no está disponible");
  return { actor: payload.actor, capabilities: granted, visibleKeys, permissions: new Set(payload.actor.permissions.filter((item) => typeof item === "string")) };
}

function can(key) { return state.capabilities.has(key) && state.visibleKeys.includes(key); }
function showDenied(error) {
  document.body.dataset.operationsState = "denied"; elements.loading.hidden = true; elements.app.hidden = true; elements.denied.hidden = false;
  elements.deniedMessage.textContent = error instanceof ApiError && error.status === 401
    ? "Tu sesión ha caducado. Inicia sesión de nuevo para solicitar acceso verificado."
    : "Tu cuenta no tiene permiso para utilizar este espacio.";
}

function groupNavigation() {
  const groups = new Map();
  state.visibleKeys.forEach((key) => { const group = NAVIGATION[key].group; if (!groups.has(group)) groups.set(group, []); groups.get(group).push(key); });
  replace(elements.nav, ...Array.from(groups.entries()).map(([label, keys]) => {
    const wrapper = node("section", { className: "nav-group", attrs: { "aria-labelledby": `nav-${label.toLowerCase()}` } });
    wrapper.appendChild(node("h2", { className: "nav-group-label", text: label, id: `nav-${label.toLowerCase()}` }));
    keys.forEach((key) => {
      const item = NAVIGATION[key];
      const control = node("button", { className: "nav-link", type: "button", dataset: { capability: key, view: item.view }, attrs: { "aria-current": "false" } }, [
        node("span", { className: "nav-icon", text: item.icon, attrs: { "aria-hidden": "true" } }), node("span", { text: item.label }),
      ]);
      control.addEventListener("click", () => navigate(key)); wrapper.appendChild(control);
    });
    return wrapper;
  }));
}

function closeSidebar() { elements.sidebar.dataset.open = "false"; elements.scrim.hidden = true; elements.menu.setAttribute("aria-expanded", "false"); elements.menu.setAttribute("aria-label", "Abrir navegación"); }
function setActiveNavigation() { elements.nav.querySelectorAll(".nav-link").forEach((item) => item.setAttribute("aria-current", item.dataset.capability === state.current ? "page" : "false")); }
function keyFromLocation() { const requested = new URLSearchParams(location.search).get("view") || "dashboard"; return state.visibleKeys.find((key) => NAVIGATION[key].view === requested) || state.visibleKeys[0]; }
async function navigate(key, options = {}) {
  if (!can(key)) return; state.current = key; setActiveNavigation(); elements.title.textContent = NAVIGATION[key].label;
  if (!options.popstate) history.pushState({ operationsView: key }, "", expectedPath(key)); closeSidebar(); await renderCurrent(Boolean(options.force));
}

async function dashboardData(force = false) { if (!state.dashboard || force) state.dashboard = await API.get("/operations/dashboard"); return state.dashboard; }
async function queueData(force = false) { if (!state.queues || force) state.queues = await API.get("/operations/queues?limit=100"); return state.queues; }
function numberCard(label, value, note = "") { return node("article", { className: "kpi-card" }, [node("span", { className: "kpi-label", text: label }), node("strong", { className: "kpi-value", text: finiteNumber(value).toLocaleString() }), node("span", { className: "kpi-note", text: note })]); }
function recentList(items) {
  const rows = collection(items);
  if (!rows.length) return emptyState("Sin cambios recientes", "La actividad operativa reciente aparecerá aquí.");
  return node("ul", { className: "activity-list" }, rows.map((item) => node("li", {}, [node("div", {}, [node("strong", { text: optionalString(item.title, "Elemento operativo") }), node("span", { text: `${sentence(item.target_type, "Elemento")} · ${formatDate(item.updated_at)}` })]), pill(item.status)])));
}

async function renderDashboard(force) {
  const [dashboard, queues] = await Promise.all([dashboardData(force), queueData(force)]);
  if (!isRecord(dashboard) || !isRecord(dashboard.totals) || !isRecord(dashboard.attention) || !isRecord(queues)) throw new Error("Respuesta del resumen no válida");
  const totals = [["organizations","Clientes","organizations"],["assets","Activos","assets"],["orders","Pedidos","orders"],["jobs","Tareas","jobs"],["missions","Misiones","missions"],["processing","Trabajos de procesamiento","processing_jobs"],["reports_qa","Informes pendientes de calidad","reports_review"],["contractors","Colaboradores activos","contractors"]].filter(([cap]) => can(cap));
  const attention = Object.entries(dashboard.attention).filter(([, value]) => finiteNumber(value) > 0);
  const health = isRecord(dashboard.health) ? dashboard.health : null;
  replace(elements.view,
    sectionHeading("Operaciones de un vistazo", `Verificado: ${formatDate(dashboard.generated_at)}. Los totales respetan tu rol interno.`),
    node("div", { className: "kpi-grid" }, totals.map(([, label, field]) => numberCard(label, dashboard.totals[field], "Total actual"))),
    node("div", { className: "content-grid" }, [
      card("Requiere atención", node("div", { className: "card-body" }, attention.length ? node("ul", { className: "detail-list" }, attention.map(([key, value]) => node("li", {}, [node("span", { text: sentence(key) }), node("strong", { text: finiteNumber(value).toLocaleString() })]))) : emptyState("Colas despejadas", "No hay elementos fallidos, bloqueados o pendientes de revisión.")), "one-third"),
      card("Cambios operativos recientes", node("div", { className: "card-body" }, recentList(dashboard.recent)), "two-thirds"),
      health ? card("Estado del sistema", node("div", { className: "card-body" }, [pill(health.status), node("ul", { className: "detail-list" }, [["Eventos no entregados",health.event_dead_letters],["Notificaciones no entregadas",health.notification_dead_letters],["Integraciones no entregadas",health.integration_dead_letters],["Fallos de procesamiento",health.processing_failures]].map(([label,value]) => node("li", {}, [node("span", { text: label }), node("strong", { text: finiteNumber(value).toLocaleString() })])))])) : null,
      state.permissions.has("platform:admin") ? card("Herramientas anteriores", node("div", { className: "card-body" }, [node("p", { text: "Las herramientas anteriores se conservan temporalmente solo para funciones que todavía no han migrado." }), node("a", { className: "button button-secondary", text: "Abrir herramientas anteriores", href: "admin-legacy.html", attrs: { "data-compatibility": "platform-admin" } })])) : null,
    ])
  );
}

function queueRows(kind, items) {
  const rows = collection(items);
  if (kind === "jobs") return rows.map((item) => [node("strong", { text: optionalString(item.job_number, "Tarea") }), optionalString(item.title, "Tarea sin título"), pill(item.state), sentence(item.priority), sentence(item.assignee_type), formatDate(item.scheduled_start)]);
  if (kind === "processing") return rows.map((item) => {
    const actions = node("div", { className: "table-actions" });
    if (finiteNumber(item.retries_remaining) > 0 && ["FAILED","RETRY_WAIT","NEEDS_REVIEW"].includes(optionalString(item.status).toUpperCase())) actions.appendChild(button("Reintentar", { variant: "primary", onClick: () => retryProcessing(item) }));
    return [pill(item.status), sentence(item.stage, "Sin iniciar"), `${finiteNumber(item.retry_count)} / ${finiteNumber(item.max_retries)}`, node("span", { className: item.error_message ? "error-detail" : "", text: optionalString(item.error_message, "—") }), formatDate(item.next_poll_at), actions];
  });
  if (kind === "reports") return rows.map((item) => {
    const actions = node("div", { className: "table-actions" });
    const status = optionalString(item.status).toUpperCase();
    if (status === "REVIEW_REQUIRED" && state.permissions.has("report:review")) actions.appendChild(button("Aprobar", { variant: "primary", onClick: () => transitionReport(item, "approve") }));
    if (status === "APPROVED" && state.permissions.has("report:publish")) actions.appendChild(button("Publicar", { variant: "primary", onClick: () => transitionReport(item, "publish") }));
    return [optionalString(item.title, "Informe"), pill(item.status), sentence(item.qa_level), finiteNumber(item.revision).toLocaleString(), formatDate(item.updated_at), actions];
  });
  return rows.map((item) => [optionalString(item.provider, "Proveedor"), sentence(item.resource_type), pill(item.status), `${finiteNumber(item.attempts)} / ${finiteNumber(item.max_attempts)}`, node("span", { className: item.error_message ? "error-detail" : "", text: optionalString(item.error_message, "—") }), formatDate(item.next_attempt_at)]);
}

async function retryProcessing(item) {
  setStatus(elements.status, "Reintentando el procesamiento…");
  try { await API.post(`/processing/jobs/${encodePath(item.id)}/retry`, {}); state.queues = null; state.dashboard = null; await renderCurrent(true); setStatus(elements.status, "Reintento de procesamiento en cola.", "success"); }
  catch (error) { setStatus(elements.status, visibleError(error), "error"); }
}
async function renderProcessing(force) { const queues = await queueData(force); const rows = queueRows("processing", queues.processing); replace(elements.view, sectionHeading("Cola de procesamiento", "Los fallos muestran diagnósticos seguros, reintentos restantes y el próximo intento."), rows.length ? card(null, table(["Estado","Etapa","Reintentos","Fallo","Próxima consulta","Acción"], rows, { label: "Cola de procesamiento" })) : emptyState("Sin trabajos de procesamiento", "No hay trabajos activos o fallidos en esta cola.")); }
async function transitionReport(item, action) {
  const permission = action === "approve" ? "report:review" : "report:publish";
  if (!state.permissions.has(permission)) return;
  setStatus(elements.status, `${sentence(action)} report…`);
  try {
    await API.post(`/reports/${encodePath(item.id)}/${action}`, { expected_lifecycle_version: finiteNumber(item.lifecycle_version, 1), note: null });
    state.queues = null; state.dashboard = null; await renderCurrent(true); setStatus(elements.status, action === "approve" ? "Informe aprobado." : "Informe publicado.", "success");
  } catch (error) { setStatus(elements.status, visibleError(error), "error"); }
}
async function renderReports(force) { const queues = await queueData(force); const rows = queueRows("reports", queues.reports_qa); replace(elements.view, sectionHeading("Calidad de informes", "Los revisores autorizados pueden aprobar y publicar informes mediante el ciclo controlado."), rows.length ? card(null, table(["Informe","Estado","Nivel de calidad","Revisión","Actualizado","Acción"], rows, { label: "Informes pendientes de revisión de calidad" })) : emptyState("Sin informes pendientes", "La cola de revisión está despejada.")); }
async function renderIntegrations(force, finance = false) {
  const [queues, usage] = await Promise.all([
    queueData(force),
    finance ? API.get("/internal/economics/location-usage/summary?days=30") : Promise.resolve(null),
  ]);
  const rows = queueRows("integrations", queues.integrations);
  const title = finance ? "Sincronización financiera" : "Entrega de integraciones";
  const content = [sectionHeading(title, "Los diagnósticos muestran el estado sin exponer credenciales de proveedores.")];
  if (finance) {
    if (!isRecord(usage) || !Array.isArray(usage.items)) throw new Error("El resumen de uso de ubicación no es válido");
    const usageRows = usage.items.map((item) => [
      sentence(item.provider, "Proveedor"),
      sentence(item.service, "Servicio"),
      finiteNumber(item.call_count).toLocaleString(),
      finiteNumber(item.quantity).toLocaleString(),
      optionalString(item.currency, "Sin precio"),
      item.currency ? finiteNumber(item.total_cost).toLocaleString() : "Sin precio",
    ]);
    content.push(
      node("div", { className: "kpi-grid" }, [numberCard("Llamadas a API de ubicación", usage.total_calls, "Últimos 30 días")]),
      usageRows.length
        ? card("Uso de proveedores de ubicación", table(["Proveedor", "Servicio", "Llamadas", "Cantidad", "Moneda", "Coste"], usageRows, { label: "Uso de proveedores de ubicación en los últimos 30 días" }))
        : emptyState("Sin uso de ubicación", "No se registraron llamadas de pago en los últimos 30 días."),
    );
  }
  content.push(rows.length
    ? card(null, table(["Proveedor", "Recurso", "Estado", "Intentos", "Fallo", "Próximo intento"], rows, { label: `Cola de ${title.toLowerCase()}` }))
    : emptyState("Sin problemas de entrega", "No hay entregas pendientes, fallidas o agotadas visibles para tu rol."));
  replace(elements.view, ...content);
}

async function loadJobs(force = false) { if (!state.jobs || force) state.jobs = collection(await API.get("/operations/jobs?limit=200")); return state.jobs; }
async function loadContractors(force = false) { if (!can("contractors")) return []; if (!state.contractors || force) state.contractors = collection(await API.get("/operations/contractors?limit=200")); return state.contractors; }
async function renderJobs(force) {
  const jobs = await loadJobs(force);
  const rows = jobs.map((job) => [node("strong", { text: optionalString(job.job_number, "Tarea") }), optionalString(job.title, "Tarea sin título"), pill(job.state), sentence(job.priority), job.assigned_contractor_id ? "Colaborador" : job.assigned_user_id ? "Personal interno" : "Sin asignar", formatDate(job.scheduled_start), node("div", { className: "table-actions" }, button("Gestionar", { variant: "primary", onClick: () => openWorkflow(job) }))]);
  replace(elements.view, sectionHeading("Tareas de ejecución", "Asigna recursos, programa el trabajo y registra cambios de estado con control de versiones."), rows.length ? card(null, table(["Tarea","Título","Estado","Prioridad","Responsable","Horario","Acción"], rows, { label: "Tareas de ejecución" })) : emptyState("Sin tareas", "Todavía no se han creado tareas de ejecución."));
}

async function openWorkflow(job) {
  state.workflowJob = job;
  document.getElementById("workflow-job-id").value = optionalString(job.id); document.getElementById("workflow-version").value = String(finiteNumber(job.lifecycle_version, 1));
  document.getElementById("workflow-state").value = ""; document.getElementById("workflow-state").disabled = false; document.getElementById("workflow-start").value = toLocalInput(job.scheduled_start); document.getElementById("workflow-end").value = toLocalInput(job.scheduled_end); document.getElementById("workflow-cost").value = ""; document.getElementById("workflow-location").value = ""; document.getElementById("workflow-reason").value = "";
  delete elements.feedback.dataset.tone; elements.feedback.textContent = ""; document.getElementById("job-workflow-title").textContent = `Ofrecer o actualizar ${optionalString(job.job_number, "tarea")}`;
  const select = document.getElementById("workflow-contractor"); replace(select, node("option", { text: can("contractors") ? "Mantener asignación actual" : "No tienes permiso para asignar colaboradores", attrs: { value: "" } })); select.disabled = !can("contractors");
  if (can("contractors")) {
    try { (await loadContractors()).filter((item) => optionalString(item.status).toUpperCase() === "ACTIVE" && optionalString(item.availability).toUpperCase() !== "UNAVAILABLE").forEach((item) => select.appendChild(node("option", { text: `${optionalString(item.display_name, "Colaborador")} · ${sentence(item.availability)}`, attrs: { value: optionalString(item.id) } }))); }
    catch (error) { elements.feedback.textContent = visibleError(error); }
  }
  select.onchange = () => {
    const offering = Boolean(select.value);
    document.getElementById("workflow-state").disabled = offering;
    elements.feedback.textContent = offering ? "El horario y la ubicación se enviarán como oferta. La tarea solo se asigna después de la aceptación." : "";
  };
  elements.dialog.showModal();
}

async function saveWorkflow(event) {
  event.preventDefault(); if (event.submitter?.value === "cancel") { elements.dialog.close(); return; }
  const id = encodePath(document.getElementById("workflow-job-id").value); let version = finiteNumber(document.getElementById("workflow-version").value, 1); const job = state.workflowJob;
  if (!isRecord(job) || safeId(job.id) !== decodeURIComponent(id)) return;
  const contractorId = optionalString(document.getElementById("workflow-contractor").value); const nextState = optionalString(document.getElementById("workflow-state").value);
  const start = document.getElementById("workflow-start").value; const end = document.getElementById("workflow-end").value; const costValue = document.getElementById("workflow-cost").value; const costAmount = costValue === "" ? null : Math.round(Number(costValue) * 100); const locationLabel = optionalString(document.getElementById("workflow-location").value); const reason = optionalString(document.getElementById("workflow-reason").value);
  const submit = document.getElementById("workflow-save"); submit.disabled = true; delete elements.feedback.dataset.tone; elements.feedback.textContent = "Guardando cambios verificados…";
  try {
    let result = null;
    if (contractorId && can("contractors")) {
      if ((start && !end) || (!start && end)) throw new Error("Debes indicar las dos fechas de la oferta.");
      if (costAmount !== null && (!Number.isFinite(costAmount) || costAmount < 0)) throw new Error("Introduce un coste acordado válido.");
      result = await API.post("/operations/assignments", { contractor_id: contractorId, order_id: optionalString(job.order_id) || null, fulfilment_job_id: job.id, title: optionalString(job.title, "Tarea asignada"), location: locationLabel ? { label: locationLabel, country: "España" } : {}, window_start: start ? new Date(start).toISOString() : null, window_end: end ? new Date(end).toISOString() : null, requirements: isRecord(job.requirements) ? job.requirements : {}, agreed_cost_amount: costAmount, cost_currency: costAmount === null ? null : "EUR", internal_notes: reason || null });
    } else {
      const originalStart = toLocalInput(job.scheduled_start); const originalEnd = toLocalInput(job.scheduled_end);
      if (start !== originalStart || end !== originalEnd) { if (!start || !end) throw new Error("Debes indicar las dos fechas del horario."); result = await API.patch(`/operations/jobs/${id}/schedule`, { scheduled_start: new Date(start).toISOString(), scheduled_end: new Date(end).toISOString(), expected_version: version }); version = finiteNumber(result?.lifecycle_version, version); }
      if (nextState) result = await API.patch(`/operations/jobs/${id}/state`, { state: nextState, reason: reason || null, expected_version: version });
    }
    if (!result) throw new Error("Elige una asignación, un horario o un cambio de estado.");
    state.jobs = null; state.queues = null; state.dashboard = null; elements.dialog.close(); await renderCurrent(true); setStatus(elements.status, contractorId ? "Oferta enviada. La asignación comienza únicamente tras la aceptación." : "Tarea actualizada y registrada en el historial.", "success");
  } catch (error) { elements.feedback.dataset.tone = "error"; elements.feedback.textContent = error instanceof Error ? error.message : "No se pudo actualizar la tarea."; }
  finally { submit.disabled = false; }
}

async function renderContractors(force) {
  const contractors = await loadContractors(force);
  const resourceLabels = { EMPLOYEE: "Empleado", FREELANCER: "Profesional autónomo", PARTNER_COMPANY: "Empresa asociada", FIELD_TECHNICIAN: "Técnico de campo", DRONE_OPERATOR: "Operador de drones", SECTOR_SPECIALIST: "Especialista sectorial" };
  const rows = contractors.map((item) => [optionalString(item.display_name, "Colaborador"), resourceLabels[optionalString(item.resource_type).toUpperCase()] || sentence(item.resource_type), pill(item.status), pill(item.availability), optionalString(item.region, "—"), optionalString(item.country_code, "—"), item.quality_score == null ? "Pendiente" : `${finiteNumber(item.quality_score).toLocaleString("es-ES")} / 100`, collection(item.document_refs).length.toLocaleString("es-ES"), collection(item.capabilities).map((cap) => optionalString(cap.code || cap.name)).filter(Boolean).join(", ") || "—"]);
  replace(elements.view, sectionHeading("Red de colaboradores", "Disponibilidad, cobertura, documentación, calidad y capacidades para asignar trabajo."), rows.length ? card(null, table(["Colaborador","Tipo","Estado","Disponibilidad","Región","País","Calidad","Documentos","Capacidades"], rows, { label: "Red de colaboradores" })) : emptyState("Sin colaboradores", "No hay colaboradores activos registrados."));
}
async function renderOrders(force) {
  if (!state.orders || force) state.orders = collection(await API.get("/orders/internal?limit=200"));
  const rows = state.orders.map((item) => [optionalString(item.order_number, "Order"), sentence(item.order_type), pill(item.fulfilment_status), pill(item.payment_status), `${finiteNumber(item.item_count)} item${finiteNumber(item.item_count) === 1 ? "" : "s"}`, formatDate(item.created_at)]);
  replace(elements.view, sectionHeading("Pedidos", "Compromisos comerciales transferidos a la ejecución interna."), rows.length ? card(null, table(["Pedido","Tipo","Ejecución","Pago","Elementos","Creado"], rows, { label: "Pedidos internos" })) : emptyState("Sin pedidos", "No hay pedidos comerciales disponibles."));
}
async function renderMissions(force) {
  if (!state.missions || force) state.missions = collection(await API.get("/missions/internal?limit=200"));
  const rows = state.missions.map((item) => [optionalString(item.acquisition_number, "Mission"), optionalString(item.title, "Untitled mission"), sentence(item.acquisition_type), pill(item.state), formatDate(item.scheduled_start), formatDate(item.updated_at), missionActions(item)]);
  replace(elements.view, sectionHeading("Misiones", "Avanza el trabajo de adquisición con un motivo auditable."), rows.length ? card(null, table(["Misión","Título","Tipo","Estado","Programada","Actualizada","Acción"], rows, { label: "Misiones internas" })) : emptyState("Sin misiones", "No hay misiones planificadas actualmente."));
}
function missionActions(item) {
  const transitions = MISSION_TRANSITIONS[optionalString(item.state).toUpperCase()] || [];
  if (!transitions.length) return node("span", { text: "Ciclo completado" });
  const label = optionalString(item.acquisition_number, "mission");
  const select = node("select", { attrs: { "aria-label": `Nuevo estado de ${label}` } }, [node("option", { text: "Elegir estado", attrs: { value: "" } }), ...transitions.map((value) => node("option", { text: sentence(value), attrs: { value } }))]);
  const reason = node("input", { attrs: { type: "text", maxlength: "2000", placeholder: "Motivo", "aria-label": `Motivo para cambiar ${label}` } });
  return node("div", { className: "table-actions lifecycle-action" }, [select, reason, button("Aplicar", { variant: "primary", onClick: () => transitionMission(item, select.value, reason.value) })]);
}
async function transitionMission(item, nextState, reason) {
  if (!(MISSION_TRANSITIONS[optionalString(item.state).toUpperCase()] || []).includes(nextState)) { setStatus(elements.status, "Elige un estado válido para la misión.", "error"); return; }
  setStatus(elements.status, `Cambiando la misión a ${sentence(nextState).toLowerCase()}…`);
  try {
    await API.patch(`/missions/internal/${encodePath(item.id)}/state`, { state: nextState, reason: optionalString(reason) || "Transición desde el portal de Operaciones", expected_version: finiteNumber(item.lifecycle_version, 1) });
    state.missions = null; state.dashboard = null; await renderCurrent(true); setStatus(elements.status, "Ciclo de la misión actualizado.", "success");
  } catch (error) { setStatus(elements.status, visibleError(error), "error"); }
}
async function renderOrganizations(force) {
  const dashboard = await dashboardData(force);
  if (state.permissions.has("platform:admin")) {
    if (!state.companies || force) state.companies = collection(await API.get("/admin/companies?per_page=100"));
    const rows = state.companies.map((item) => [optionalString(item.name, "Organización"), optionalString(item.email, "—"), pill(item.status), sentence(item.subscription_plan), finiteNumber(item.current_users).toLocaleString("es-ES"), finiteNumber(item.current_sites).toLocaleString("es-ES")]);
    replace(elements.view, sectionHeading("Clientes y organizaciones", `${finiteNumber(dashboard?.totals?.organizations)} organizaciones cliente activas.`), rows.length ? card(null, table(["Organización","Contacto","Estado","Plan","Usuarios","Emplazamientos"], rows, { label: "Organizaciones cliente" })) : emptyState("Sin organizaciones", "No hay organizaciones cliente activas registradas.")); return;
  }
  replace(elements.view, sectionHeading("Clientes y organizaciones", "Las identidades de clientes se presentan de forma agregada para este rol interno."), numberCard("Organizaciones activas", dashboard?.totals?.organizations, "Los registros detallados requieren permiso de administración de plataforma."));
}
async function renderAggregate(totalKey, title, description, force) {
  const dashboard = await dashboardData(force);
  replace(elements.view, sectionHeading(title, description), node("div", { className: "kpi-grid" }, [numberCard(title, dashboard?.totals?.[totalKey], "Visible para tu rol verificado")]), card("Límite operativo", node("div", { className: "card-body" }, emptyState("Sin registro general expuesto", "Abre el trabajo del cliente desde una tarea, misión o cola de revisión asignada. Esta vista respeta los límites entre clientes."))));
}
async function renderSystemHealth(force) {
  const dashboard = await dashboardData(force); const health = dashboard.health;
  if (!isRecord(health)) { replace(elements.view, emptyState("Estado no disponible", "El estado del sistema no está incluido para este rol.")); return; }
  replace(elements.view, sectionHeading("Estado del sistema", `Comprobado ${formatDate(dashboard.generated_at)}.`), node("div", { className: "kpi-grid" }, [node("article", { className: "kpi-card" }, [node("span", { className: "kpi-label", text: "Estado general" }), pill(health.status)]), numberCard("Eventos sin procesar", health.event_dead_letters), numberCard("Notificaciones sin procesar", health.notification_dead_letters), numberCard("Integraciones sin procesar", health.integration_dead_letters), numberCard("Fallos de procesamiento", health.processing_failures)]));
}

async function renderCurrent(force = false) {
  if (!can(state.current)) return; setBusy(elements.view, true); setStatus(elements.status, "");
  try {
    const renderers = {
      dashboard: () => renderDashboard(force), organizations: () => renderOrganizations(force), assets: () => renderAggregate("assets", "Activos", "El acceso respeta los límites del cliente y espacio de trabajo; los totales generales son solo internos.", force), orders: () => renderOrders(force), jobs: () => renderJobs(force), missions: () => renderMissions(force), processing: () => renderProcessing(force), reports_qa: () => renderReports(force), contractors: () => renderContractors(force), inventory: () => renderAggregate("orders", "Proveedores e inventario", "El stock de referencia y la coordinación de proveedores siguen la ejecución de pedidos.", force), finance_sync: () => renderIntegrations(force, true), integrations: () => renderIntegrations(force, false), system_health: () => renderSystemHealth(force),
    };
    await renderers[state.current]();
  } catch (error) { replace(elements.view, emptyState("No se ha podido cargar esta vista", visibleError(error))); setStatus(elements.status, visibleError(error), "error"); }
  finally { setBusy(elements.view, false); }
}

async function init() {
  installLogout(document.getElementById("operations-logout"), document.getElementById("denied-logout"));
  elements.menu.addEventListener("click", () => { const open = elements.sidebar.dataset.open !== "true"; elements.sidebar.dataset.open = String(open); elements.scrim.hidden = !open; elements.menu.setAttribute("aria-expanded", String(open)); elements.menu.setAttribute("aria-label", open ? "Cerrar navegación" : "Abrir navegación"); });
  elements.scrim.addEventListener("click", closeSidebar); elements.refresh.addEventListener("click", () => renderCurrent(true)); elements.workflow.addEventListener("submit", saveWorkflow);
  window.addEventListener("popstate", async () => { const key = keyFromLocation(); await navigate(key, { popstate: true }); });
  try {
    const experience = validateExperience(await API.get("/operations/experience"));
    state.experience = experience; state.capabilities = experience.capabilities; state.permissions = experience.permissions; state.visibleKeys = experience.visibleKeys; groupNavigation();
    const roles = experience.actor.roles.map((role) => sentence(role)); document.getElementById("operations-user-name").textContent = roles[0] || "Equipo de Operaciones"; document.getElementById("operations-user-role").textContent = roles.slice(1).join(", ") || "Rol interno verificado"; document.getElementById("operations-avatar").textContent = (roles[0]?.charAt(0) || "G").toUpperCase();
    elements.loading.hidden = true; elements.app.hidden = false; elements.dialog.hidden = false; document.body.dataset.operationsState = "ready"; state.current = keyFromLocation(); setActiveNavigation(); elements.title.textContent = NAVIGATION[state.current].label; history.replaceState({ operationsView: state.current }, "", expectedPath(state.current));
    window.GeoVisionOperations = Object.freeze({ ownsNavigation: true, surface: "INTERNAL_OPERATIONS" }); await renderCurrent();
  } catch (error) { showDenied(error); }
}

init();
