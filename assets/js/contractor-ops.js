import {
  ApiError, OperationsApi, button, capabilities, card, collection, emptyState,
  encodePath, finiteNumber, formatDate, installLogout, isRecord, node, optionalString,
  pill, replace, requiredString, safeFilename, safeId, sectionHeading, sentence,
  setBusy, setStatus, visibleError,
} from "./operations-ui.js";

const NAVIGATION = Object.freeze({
  my_jobs: { label: "Mis tareas", view: "jobs" },
  profile: { label: "Mi perfil", view: "profile" },
  documents: { label: "Documentación", view: "documents" },
});
const CAPABILITIES = Object.freeze(["my_jobs", "job_status", "uploads", "profile", "documents"]);
const TRANSITIONS = new Set(["IN_PROGRESS", "WAITING_INPUT", "QA_REVIEW"]);
const API = new OperationsApi();
const state = {
  capabilities: new Set(), visibleKeys: [], current: "", contractor: null, counts: null,
  jobs: null, offers: null, profile: null, detail: null,
};
const elements = {
  app: document.getElementById("contractor-app"), loading: document.getElementById("contractor-loading"),
  denied: document.getElementById("contractor-denied"), deniedMessage: document.getElementById("contractor-denied-message"),
  nav: document.getElementById("contractor-navigation"), menu: document.getElementById("contractor-menu"),
  title: document.getElementById("contractor-view-title"), view: document.getElementById("contractor-view"),
  status: document.getElementById("contractor-status"), refresh: document.getElementById("contractor-refresh"),
  uploadDialog: document.getElementById("contractor-upload-dialog"), uploadForm: document.getElementById("contractor-upload-form"),
  uploadFeedback: document.getElementById("upload-feedback"),
};

function expectedPath(key) { return `/contractor.html?view=${NAVIGATION[key].view}`; }
function validateExperience(payload) {
  if (!isRecord(payload) || payload.surface !== "CONTRACTOR" || !isRecord(payload.contractor)) throw new Error("Experiencia de colaborador no válida");
  requiredString(payload.contractor.id, "contractor.id"); requiredString(payload.contractor.display_name, "contractor.display_name");
  if (optionalString(payload.contractor.status).toUpperCase() !== "ACTIVE") throw new Error("Perfil de colaborador inactivo");
  if (!Array.isArray(payload.navigation) || !isRecord(payload.job_counts)) throw new Error("Autorización de colaborador no válida");
  const granted = capabilities(payload.capabilities, CAPABILITIES);
  const visible = new Set();
  payload.navigation.forEach((item) => {
    if (!isRecord(item) || !NAVIGATION[item.key] || item.capability !== item.key || !granted.has(item.key)) return;
    if (item.label !== NAVIGATION[item.key].label || item.path !== expectedPath(item.key)) return;
    visible.add(item.key);
  });
  const visibleKeys = Object.keys(NAVIGATION).filter((key) => visible.has(key));
  if (!visibleKeys.includes("my_jobs")) throw new Error("El acceso a Mis tareas no está disponible");
  return { capabilities: granted, visibleKeys, contractor: payload.contractor, counts: payload.job_counts };
}
function can(key) { return state.capabilities.has(key); }
function canNavigate(key) { return can(key) && state.visibleKeys.includes(key); }
function viewKeyFromLocation() {
  const requested = new URLSearchParams(location.search).get("view") || "jobs";
  return state.visibleKeys.find((key) => NAVIGATION[key].view === requested) || "my_jobs";
}
function jobIdFromLocation() { return safeId(new URLSearchParams(location.search).get("job")); }
function showDenied(error) {
  document.body.dataset.contractorState = "denied"; elements.loading.hidden = true; elements.app.hidden = true; elements.denied.hidden = false;
  elements.deniedMessage.textContent = error instanceof ApiError && error.status === 401
    ? "Tu sesión ha caducado. Inicia sesión de nuevo para solicitar acceso verificado."
    : "Esta cuenta no tiene acceso a un perfil activo de colaborador de GeoVision.";
}

function buildNavigation() {
  replace(elements.nav, ...state.visibleKeys.map((key) => {
    const control = node("button", { className: "nav-link", type: "button", text: NAVIGATION[key].label, dataset: { capability: key }, attrs: { "aria-current": "false" } });
    control.addEventListener("click", () => navigate(key)); return control;
  }));
}
function setActiveNavigation() { elements.nav.querySelectorAll(".nav-link").forEach((item) => item.setAttribute("aria-current", item.dataset.capability === state.current ? "page" : "false")); }
function closeMenu() { elements.nav.dataset.open = "false"; elements.menu.setAttribute("aria-expanded", "false"); elements.menu.setAttribute("aria-label", "Abrir navegación"); }
async function navigate(key, options = {}) {
  if (!canNavigate(key)) return; state.current = key; state.detail = null; setActiveNavigation(); elements.title.textContent = NAVIGATION[key].label;
  if (!options.popstate) history.pushState({ contractorView: key }, "", expectedPath(key)); closeMenu(); await renderCurrent(Boolean(options.force));
}

function scheduleText(job) {
  if (!job.scheduled_start) return "Abre los detalles para consultar la franja de la asignación";
  const end = job.scheduled_end ? ` – ${formatDate(job.scheduled_end)}` : "";
  return `${formatDate(job.scheduled_start)}${end}`;
}
function tagValues(value) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === "string") return item.trim();
    if (!isRecord(item)) return "";
    return optionalString(item.name || item.label || item.code || item.type);
  }).filter(Boolean).slice(0, 40);
}
function requirementValues(requirements) {
  if (!isRecord(requirements)) return [];
  const allowed = ["equipment", "capabilities", "skills", "certifications", "payloads"];
  const values = [];
  allowed.forEach((key) => {
    const value = requirements[key];
    if (Array.isArray(value)) values.push(...tagValues(value));
    else if (typeof value === "string" && value.trim()) values.push(value.trim());
  });
  return [...new Set(values)].slice(0, 40);
}
function requirementsList(requirements) {
  const values = requirementValues(requirements);
  return values.length ? node("ul", { className: "requirement-list", attrs: { "aria-label": "Equipo y capacidades requeridos" } }, values.map((value) => node("li", { text: value }))) : node("p", { text: "No se han indicado requisitos adicionales de equipo o capacidades." });
}

function jobCard(job) {
  const open = button("Ver detalles", { variant: "primary", onClick: () => openJob(job.id) });
  return node("article", { className: "job-card" }, [
    node("div", { className: "job-meta" }, [pill(job.state), node("span", { className: "kpi-note", text: sentence(job.priority) })]),
    node("h2", { text: optionalString(job.title, "Tarea asignada") }),
    node("p", { text: optionalString(job.job_number, "Tarea") }),
    node("p", { text: scheduleText(job) }), requirementsList(job.requirements),
    node("div", { className: "button-row" }, open),
  ]);
}

async function loadJobs(force = false) { if (!state.jobs || force) state.jobs = collection(await API.get("/operations/contractor/me/jobs?limit=100")); return state.jobs; }
async function loadOffers(force = false) { if (!state.offers || force) state.offers = collection(await API.get("/operations/contractor/me/assignments?status=OFFERED&limit=100")); return state.offers; }
function offerCard(offer) {
  const location = safeLocation(offer.location).map(([, value]) => value).join(" · ");
  const documents = Array.isArray(offer.required_documents) ? offer.required_documents.map((item) => typeof item === "string" ? item : optionalString(item.name || item.label || item.type)).filter(Boolean) : [];
  return node("article", { className: "job-card offer-card" }, [
    node("div", { className: "job-meta" }, [pill("OFFERED"), node("span", { className: "kpi-note", text: optionalString(offer.assignment_number, "Nueva oferta") })]),
    node("h2", { text: optionalString(offer.title, "Oferta de trabajo") }),
    node("p", { text: offer.window_start ? `${formatDate(offer.window_start)}${offer.window_end ? ` – ${formatDate(offer.window_end)}` : ""}` : "Horario pendiente de confirmación" }),
    location ? node("p", { text: location }) : null,
    requirementsList(offer.requirements),
    documents.length ? node("ul", { className: "requirement-list", attrs: { "aria-label": "Documentos requeridos" } }, documents.map((item) => node("li", { text: item }))) : null,
    node("div", { className: "button-row" }, [button("Aceptar asignación", { variant: "primary", onClick: () => decideAssignment(offer, "ACCEPTED") }), button("Rechazar", { variant: "danger", onClick: () => decideAssignment(offer, "DECLINED") })]),
  ]);
}
async function renderJobs(force) {
  const targetId = jobIdFromLocation();
  if (targetId) { await renderJobDetail(targetId, force); return; }
  const [jobs, offers] = await Promise.all([loadJobs(force), loadOffers(force)]);
  const counts = state.counts || {};
  replace(elements.view,
    node("div", { className: "kpi-grid" }, [
      ["Ofrecidas", counts.offered], ["Programadas", counts.scheduled], ["Activas", counts.active], ["En revisión", counts.review], ["Completadas", counts.completed],
    ].map(([label, value]) => node("article", { className: "kpi-card" }, [node("span", { className: "kpi-label", text: label }), node("strong", { className: "kpi-value", text: finiteNumber(value).toLocaleString() })]))),
    offers.length ? sectionHeading("Nuevas ofertas de trabajo", "Revisa horario, ubicación, remuneración y requisitos antes de aceptar.") : null,
    offers.length ? node("div", { className: "job-grid offers-grid" }, offers.map(offerCard)) : null,
    sectionHeading("Tareas asignadas", "Aquí solo aparece el trabajo asignado a este perfil."),
    jobs.length ? node("div", { className: "job-grid" }, jobs.map(jobCard)) : emptyState("Sin tareas asignadas", "El nuevo trabajo aparecerá aquí cuando GeoVision lo programe."),
  );
}

async function openJob(rawId) {
  const id = safeId(rawId); if (!id) return;
  history.pushState({ contractorView: "my_jobs", job: id }, "", `/contractor.html?view=jobs&job=${encodeURIComponent(id)}`);
  await renderJobDetail(id, false);
}
function safeLocation(locationValue) {
  if (!isRecord(locationValue)) return [];
  const labels = [["Ubicación", locationValue.label || locationValue.name || locationValue.address], ["Zona", locationValue.city || locationValue.region], ["País", locationValue.country]];
  const lat = Number(locationValue.latitude); const lon = Number(locationValue.longitude);
  if (Number.isFinite(lat) && Number.isFinite(lon)) labels.push(["Coordenadas", `${lat.toFixed(5)}, ${lon.toFixed(5)}`]);
  return labels.filter(([, value]) => typeof value === "string" && value.trim());
}
function detailList(rows) { return node("ul", { className: "detail-list" }, rows.map(([label, value]) => node("li", {}, [node("span", { text: label }), value instanceof Node ? value : node("strong", { text: value })]))); }

function assignmentActions(detail) {
  const assignment = detail.assignment;
  if (!isRecord(assignment) || optionalString(assignment.status).toUpperCase() !== "OFFERED") return null;
  return node("div", { className: "button-row" }, [
    button("Aceptar asignación", { variant: "primary", onClick: () => decideAssignment(assignment, "ACCEPTED", detail.id) }),
    button("Rechazar", { variant: "danger", onClick: () => decideAssignment(assignment, "DECLINED", detail.id) }),
  ]);
}
async function refreshExperience() {
  const experience = validateExperience(await API.get("/operations/contractor/me/experience"));
  state.counts = experience.counts; state.contractor = experience.contractor;
}
async function decideAssignment(assignment, decision, jobId = "") {
  if (!isRecord(assignment) || optionalString(assignment.status).toUpperCase() !== "OFFERED") return;
  setStatus(elements.status, decision === "ACCEPTED" ? "Aceptando asignación…" : "Rechazando asignación…");
  try {
    await API.post(`/operations/contractor/me/assignments/${encodePath(assignment.id)}/decision`, { decision, expected_version: finiteNumber(assignment.lifecycle_version, 1) });
    state.jobs = null; state.offers = null; state.detail = null; await refreshExperience(); setStatus(elements.status, decision === "ACCEPTED" ? "Asignación aceptada." : "Asignación rechazada.", "success");
    if (jobId && decision === "ACCEPTED") await renderJobDetail(jobId, true); else { history.replaceState({ contractorView: "my_jobs" }, "", expectedPath("my_jobs")); await renderJobs(true); }
  } catch (error) { setStatus(elements.status, visibleError(error), "error"); }
}

function statusActions(detail) {
  if (!can("job_status")) return null;
  const allowed = Array.isArray(detail.allowed_transitions) ? detail.allowed_transitions.filter((value) => TRANSITIONS.has(value)) : [];
  if (!allowed.length) return null;
  return node("div", { className: "button-row" }, allowed.map((next) => {
    if (next !== "WAITING_INPUT") return button(`Marcar: ${sentence(next)}`, { variant: "primary", onClick: () => updateJobState(detail, next) });
    const reason = node("input", { attrs: { type: "text", maxlength: "2000", placeholder: "Motivo obligatorio", "aria-label": "Motivo de espera de información" } });
    return node("div", { className: "waiting-input-action" }, [reason, button("Marcar en espera de información", { variant: "primary", onClick: () => updateJobState(detail, next, reason.value) })]);
  }));
}
async function updateJobState(detail, next, reason = "") {
  if (next === "WAITING_INPUT" && !optionalString(reason)) { setStatus(elements.status, "Añade un motivo antes de marcar esta tarea en espera.", "error"); return; }
  setStatus(elements.status, `Actualizando tarea a ${sentence(next).toLowerCase()}…`);
  try {
    const result = await API.patch(`/operations/contractor/me/jobs/${encodePath(detail.id)}/state`, { state: next, reason: optionalString(reason) || null, expected_version: finiteNumber(detail.lifecycle_version, 1) });
    state.detail = result; state.jobs = null; setStatus(elements.status, "Estado de la tarea actualizado.", "success"); renderJobDetailView(result);
  } catch (error) { setStatus(elements.status, visibleError(error), "error"); }
}

function acceptedAssignment(detail) { return isRecord(detail?.assignment) && ["ACCEPTED", "ACTIVE"].includes(optionalString(detail.assignment.status).toUpperCase()); }
function uploadTargets(detail) { return collection(detail.upload_targets).filter((target) => safeId(target.dataset_id) && optionalString(target.status).toUpperCase() !== "ARCHIVED"); }
function uploadAction(detail) {
  if (!can("uploads") || !acceptedAssignment(detail) || !uploadTargets(detail).length) return null;
  return button("Subir entrega", { variant: "primary", onClick: () => openUpload(detail) });
}
function openUpload(detail) {
  const targets = uploadTargets(detail); if (!targets.length || !acceptedAssignment(detail)) return;
  document.getElementById("upload-job-id").value = detail.id;
  const select = document.getElementById("upload-dataset");
  replace(select, node("option", { text: "Elige un destino aprobado", attrs: { value: "" } }), ...targets.map((target) => node("option", { text: `${optionalString(target.name, "Entrega")} · ${finiteNumber(target.file_count)} archivo${finiteNumber(target.file_count) === 1 ? "" : "s"}`, attrs: { value: target.dataset_id } })));
  document.getElementById("upload-file").value = ""; document.getElementById("upload-area").value = "raw"; elements.uploadFeedback.textContent = ""; delete elements.uploadFeedback.dataset.tone;
  elements.uploadDialog.showModal();
}

async function sha256Hex(file) {
  const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
function safeUploadUrl(value) {
  const url = new URL(requiredString(value, "upload_url"), location.href);
  const localHttp = url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname);
  if (url.protocol !== "https:" && !localHttp) throw new Error("El destino de subida no es seguro.");
  return url.href;
}
async function submitUpload(event) {
  event.preventDefault(); if (event.submitter?.value === "cancel") { elements.uploadDialog.close(); return; }
  const jobId = encodePath(document.getElementById("upload-job-id").value); const datasetId = safeId(document.getElementById("upload-dataset").value);
  const file = document.getElementById("upload-file").files?.[0]; const area = document.getElementById("upload-area").value;
  const targets = state.detail ? uploadTargets(state.detail) : [];
  if (!file || !datasetId || !targets.some((target) => target.dataset_id === datasetId) || !acceptedAssignment(state.detail)) { elements.uploadFeedback.dataset.tone = "error"; elements.uploadFeedback.textContent = "Elige un destino aprobado y un archivo."; return; }
  const submit = document.getElementById("upload-submit"); submit.disabled = true; elements.uploadFeedback.textContent = "Preparando la subida segura…";
  try {
    const initiated = await API.post(`/operations/contractor/me/jobs/${jobId}/uploads/initiate`, { dataset_id: datasetId, filename: safeFilename(file.name), content_type: optionalString(file.type) || null, size_bytes: file.size, object_area: area });
    if (!isRecord(initiated) || !safeId(initiated.upload_reference) || !isRecord(initiated.required_headers)) throw new Error("Autorización de subida no válida.");
    const headers = new Headers();
    Object.entries(initiated.required_headers).forEach(([key, value]) => { if (typeof value === "string") headers.set(key, value); });
    const uploadResponse = await fetch(safeUploadUrl(initiated.upload_url), { method: "PUT", headers, body: file, credentials: "omit" });
    if (!uploadResponse.ok) throw new Error("La transferencia del archivo no se ha completado.");
    elements.uploadFeedback.textContent = "Confirmando el archivo subido…";
    await API.post(`/operations/contractor/me/jobs/${jobId}/uploads/complete`, { dataset_id: datasetId, upload_reference: initiated.upload_reference, size_bytes: file.size, sha256_hash: await sha256Hex(file) });
    elements.uploadDialog.close(); state.detail = null; setStatus(elements.status, "Entrega subida y confirmada.", "success"); await renderJobDetail(document.getElementById("upload-job-id").value, true);
  } catch (error) { elements.uploadFeedback.dataset.tone = "error"; elements.uploadFeedback.textContent = error instanceof Error ? error.message : "La subida ha fallado."; }
  finally { submit.disabled = false; }
}

async function renderJobDetail(id, force) {
  setBusy(elements.view, true);
  try {
    if (!state.detail || state.detail.id !== id || force) state.detail = await API.get(`/operations/contractor/me/jobs/${encodePath(id)}`);
    renderJobDetailView(state.detail);
  } finally { setBusy(elements.view, false); }
}
function renderJobDetailView(detail) {
  if (!isRecord(detail) || !safeId(detail.id)) throw new Error("Detalle de tarea asignada no válido");
  const back = button("← Volver a Mis tareas", { onClick: async () => { history.pushState({ contractorView: "my_jobs" }, "", expectedPath("my_jobs")); state.detail = null; await renderJobs(false); } }); back.classList.add("detail-back");
  const assignment = isRecord(detail.assignment) ? detail.assignment : null;
  const scheduled = { ...detail, scheduled_start: detail.scheduled_start || assignment?.window_start, scheduled_end: detail.scheduled_end || assignment?.window_end };
  const locations = safeLocation(assignment?.location || detail.location);
  const requiredDocs = assignment && Array.isArray(assignment.required_documents) ? assignment.required_documents : [];
  const actionNodes = [assignmentActions(detail), statusActions(detail), uploadAction(detail)].filter(Boolean);
  replace(elements.view, back, sectionHeading(optionalString(detail.title, "Tarea asignada"), `${optionalString(detail.job_number, "Tarea")} · ${scheduleText(scheduled)}`),
    node("div", { className: "detail-grid" }, [
      card("Detalles de la tarea", node("div", { className: "card-body" }, [detailList([["Estado", pill(detail.state)],["Prioridad", sentence(detail.priority)],["Inicio", formatDate(scheduled.scheduled_start)],["Fin", formatDate(scheduled.scheduled_end)]]), node("h3", { text: "Equipo y capacidades requeridos" }), requirementsList(assignment?.requirements || detail.requirements), requiredDocs.length ? node("div", {}, [node("h3", { text: "Documentos requeridos" }), node("ul", { className: "requirement-list" }, requiredDocs.map((item) => node("li", { text: typeof item === "string" ? item : optionalString(item.name || item.label || item.type, "Documento requerido") })))]) : null, actionNodes.length ? node("div", { className: "card-body job-actions" }, actionNodes) : null])),
      card("Horario y ubicación", node("div", { className: "card-body" }, locations.length ? detailList(locations) : emptyState("Ubicación pendiente", "GeoVision todavía no ha publicado la ubicación de esta tarea."))),
    ])
  );
}

async function loadProfile(force = false) { if (!state.profile || force) state.profile = await API.get("/operations/contractor/me/profile"); return state.profile; }
function profileInput(label, name, value, options = {}) {
  const control = options.select ? node("select", { attrs: { name, id: `profile-${name}` } }, options.select.map((item) => node("option", { text: sentence(item), attrs: { value: item, selected: item === value ? "selected" : null } }))) : node("input", { attrs: { name, id: `profile-${name}`, value: optionalString(value), type: options.type || "text", maxlength: options.maxlength || 200 } });
  return node("label", {}, [node("span", { text: label }), control]);
}
async function renderProfile(force) {
  const profile = await loadProfile(force); if (!isRecord(profile)) throw new Error("Perfil de colaborador no válido");
  const form = node("form", { id: "contractor-profile-form" }, [
    node("div", { className: "form-grid" }, [profileInput("Nombre visible","display_name",profile.display_name), profileInput("Disponibilidad","availability",profile.availability,{select:["AVAILABLE","LIMITED","UNAVAILABLE"]}), profileInput("Correo de contacto","contact_email",profile.contact_email,{type:"email",maxlength:320}), profileInput("Teléfono de contacto","contact_phone",profile.contact_phone,{type:"tel",maxlength:50}), profileInput("Región","region",profile.region,{maxlength:120}), profileInput("Zonas de servicio (separadas por comas)","service_area",tagValues(profile.service_area).join(", "))]),
    node("p", { className: "form-feedback", id: "profile-feedback", attrs: { role: "status", "aria-live": "polite" } }),
    node("div", { className: "dialog-actions" }, button("Guardar perfil", { variant: "primary", type: "submit", attrs: { id: "profile-save" } })),
  ]);
  form.addEventListener("submit", saveProfile);
  const identity = detailList([["Tipo de vínculo", sentence(profile.resource_type)], ["País", optionalString(profile.country_code, "ES")], ["Capacidades verificadas", collection(profile.capabilities).map((item) => optionalString(item.name || item.code)).filter(Boolean).join(", ") || "Pendientes"], ["Equipos declarados", tagValues(profile.equipment).join(", ") || "Sin equipos declarados"]]);
  replace(elements.view, sectionHeading("Mi perfil profesional", "Mantén actualizados tus datos y disponibilidad. La validación documental y la evaluación de calidad corresponden a GeoVision."), node("div", { className: "content-grid" }, [card("Vínculo y capacidades", node("div", { className: "card-body" }, identity), "half"), card("Datos editables", form, "half")]));
}
async function saveProfile(event) {
  event.preventDefault(); const data = new FormData(event.currentTarget); const feedback = document.getElementById("profile-feedback"); const save = document.getElementById("profile-save"); save.disabled = true; feedback.textContent = "Guardando perfil…";
  try {
    state.profile = await API.patch("/operations/contractor/me/profile", { display_name: optionalString(data.get("display_name")), availability: optionalString(data.get("availability")), contact_email: optionalString(data.get("contact_email")) || null, contact_phone: optionalString(data.get("contact_phone")) || null, region: optionalString(data.get("region")) || null, service_area: optionalString(data.get("service_area")).split(",").map((item) => item.trim()).filter(Boolean).slice(0,100) });
    feedback.textContent = "Perfil guardado."; feedback.dataset.tone = "success"; document.getElementById("contractor-user-name").textContent = optionalString(state.profile.display_name, state.contractor.display_name);
  } catch (error) { feedback.textContent = visibleError(error); feedback.dataset.tone = "error"; }
  finally { save.disabled = false; }
}

function documentLabel(item) { return optionalString(item.name || item.label || item.title || item.type, "Documento de validación"); }
function documentStatus(item) { return optionalString(item.status || item.state, "Registrado"); }
async function renderDocuments(force) {
  const profile = await loadProfile(force); const documents = collection(profile.document_refs); const certifications = collection(profile.certifications);
  const renderItems = (items, emptyTitle) => items.length ? node("ul", { className: "activity-list" }, items.map((item) => node("li", {}, [node("div", {}, [node("strong", { text: documentLabel(item) }), item.expires_at ? node("span", { text: `Caduca ${formatDate(item.expires_at, { timeStyle: undefined })}` }) : null]), pill(documentStatus(item))]))) : emptyState(emptyTitle, "El equipo de GeoVision actualizará este registro después de revisarlo.");
  replace(elements.view, sectionHeading("Documentación y contratos", "Estado de validación en modo consulta. Las entregas de tareas se suben desde una asignación aceptada."), node("div", { className: "content-grid" }, [card("Documentos de validación", node("div", { className: "card-body" }, renderItems(documents, "Sin documentos validados")), "half"), card("Certificaciones", node("div", { className: "card-body" }, renderItems(certifications, "Sin certificaciones registradas")), "half")]));
}

async function renderCurrent(force = false) {
  setBusy(elements.view, true); setStatus(elements.status, "");
  try { if (state.current === "my_jobs") await renderJobs(force); else if (state.current === "profile") await renderProfile(force); else await renderDocuments(force); }
  catch (error) { replace(elements.view, emptyState("No se ha podido cargar esta vista", visibleError(error))); setStatus(elements.status, visibleError(error), "error"); }
  finally { setBusy(elements.view, false); }
}

async function init() {
  installLogout(document.getElementById("contractor-logout"), document.getElementById("contractor-denied-logout"));
  elements.menu.addEventListener("click", () => { const open = elements.nav.dataset.open !== "true"; elements.nav.dataset.open = String(open); elements.menu.setAttribute("aria-expanded", String(open)); elements.menu.setAttribute("aria-label", open ? "Cerrar navegación" : "Abrir navegación"); });
  elements.refresh.addEventListener("click", () => renderCurrent(true)); elements.uploadForm.addEventListener("submit", submitUpload);
  window.addEventListener("popstate", async () => { state.current = viewKeyFromLocation(); setActiveNavigation(); elements.title.textContent = NAVIGATION[state.current].label; state.detail = null; await renderCurrent(); });
  try {
    const experience = validateExperience(await API.get("/operations/contractor/me/experience")); state.capabilities = experience.capabilities; state.visibleKeys = experience.visibleKeys; state.contractor = experience.contractor; state.counts = experience.counts;
    buildNavigation(); document.getElementById("contractor-user-name").textContent = experience.contractor.display_name; state.current = viewKeyFromLocation(); setActiveNavigation(); elements.title.textContent = NAVIGATION[state.current].label;
    elements.loading.hidden = true; elements.app.hidden = false; elements.uploadDialog.hidden = false; document.body.dataset.contractorState = "ready"; window.GeoVisionContractor = Object.freeze({ ownsNavigation: true, surface: "CONTRACTOR" }); await renderCurrent();
  } catch (error) { showDenied(error); }
}

init();
