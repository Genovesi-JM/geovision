import {
  ApiError, OperationsApi, button, capabilities, card, collection, emptyState,
  encodePath, finiteNumber, formatDate, installLogout, isRecord, node, optionalString,
  pill, replace, requiredString, safeId, sectionHeading, sentence, setBusy, setStatus,
  table, toLocalInput, visibleError,
} from "./operations-ui.js";

const NAVIGATION = Object.freeze({
  dashboard: { label: "Dashboard", view: "dashboard", group: "Overview", icon: "⌂" },
  organizations: { label: "Customers / Organizations", view: "organizations", group: "Customers", icon: "◎" },
  assets: { label: "Assets", view: "assets", group: "Customers", icon: "◇" },
  orders: { label: "Orders", view: "orders", group: "Delivery", icon: "▤" },
  jobs: { label: "Jobs", view: "jobs", group: "Delivery", icon: "✓" },
  missions: { label: "Missions", view: "missions", group: "Delivery", icon: "⌁" },
  processing: { label: "Processing", view: "processing", group: "Delivery", icon: "◌" },
  reports_qa: { label: "Reports QA", view: "reports-qa", group: "Delivery", icon: "◫" },
  contractors: { label: "Contractors", view: "contractors", group: "Network", icon: "♙" },
  inventory: { label: "Suppliers / Inventory", view: "inventory", group: "Network", icon: "▦" },
  finance_sync: { label: "Finance sync", view: "finance-sync", group: "Platform", icon: "⇄" },
  integrations: { label: "Integrations", view: "integrations", group: "Platform", icon: "⌘" },
  system_health: { label: "System health", view: "system-health", group: "Platform", icon: "♥" },
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
  if (!isRecord(payload) || payload.surface !== "INTERNAL_OPERATIONS" || !isRecord(payload.actor)) throw new Error("Invalid Operations experience");
  requiredString(payload.actor.user_id, "actor.user_id");
  if (!Array.isArray(payload.actor.roles) || !payload.actor.roles.some((role) => typeof role === "string" && role.trim())) throw new Error("Invalid Operations roles");
  if (!Array.isArray(payload.actor.permissions) || !Array.isArray(payload.navigation)) throw new Error("Invalid Operations authorization");
  const granted = capabilities(payload.capabilities, NAV_ORDER);
  const visible = new Set();
  payload.navigation.forEach((item) => {
    if (!isRecord(item) || typeof item.key !== "string" || !granted.has(item.key)) return;
    if (item.capability !== item.key || !NAVIGATION[item.key]) return;
    if (item.label !== NAVIGATION[item.key].label || item.path !== expectedPath(item.key)) return;
    visible.add(item.key);
  });
  const visibleKeys = NAV_ORDER.filter((key) => visible.has(key));
  if (!visibleKeys.length) throw new Error("Operations navigation is unavailable");
  return { actor: payload.actor, capabilities: granted, visibleKeys, permissions: new Set(payload.actor.permissions.filter((item) => typeof item === "string")) };
}

function can(key) { return state.capabilities.has(key) && state.visibleKeys.includes(key); }
function showDenied(error) {
  document.body.dataset.operationsState = "denied"; elements.loading.hidden = true; elements.app.hidden = true; elements.denied.hidden = false;
  elements.deniedMessage.textContent = error instanceof ApiError && error.status === 401
    ? "Your session has expired. Sign in again to request verified access."
    : "Your signed-in account does not have permission to use this workspace.";
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

function closeSidebar() { elements.sidebar.dataset.open = "false"; elements.scrim.hidden = true; elements.menu.setAttribute("aria-expanded", "false"); elements.menu.setAttribute("aria-label", "Open navigation"); }
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
  if (!rows.length) return emptyState("No recent changes", "Recent operational activity will appear here.");
  return node("ul", { className: "activity-list" }, rows.map((item) => node("li", {}, [node("div", {}, [node("strong", { text: optionalString(item.title, "Operational item") }), node("span", { text: `${sentence(item.target_type, "Item")} · ${formatDate(item.updated_at)}` })]), pill(item.status)])));
}

async function renderDashboard(force) {
  const [dashboard, queues] = await Promise.all([dashboardData(force), queueData(force)]);
  if (!isRecord(dashboard) || !isRecord(dashboard.totals) || !isRecord(dashboard.attention) || !isRecord(queues)) throw new Error("Invalid dashboard response");
  const totals = [["organizations","Customers","organizations"],["assets","Assets","assets"],["orders","Orders","orders"],["jobs","Jobs","jobs"],["missions","Missions","missions"],["processing","Processing jobs","processing_jobs"],["reports_qa","Reports awaiting QA","reports_review"],["contractors","Active contractors","contractors"]].filter(([cap]) => can(cap));
  const attention = Object.entries(dashboard.attention).filter(([, value]) => finiteNumber(value) > 0);
  const health = isRecord(dashboard.health) ? dashboard.health : null;
  replace(elements.view,
    sectionHeading("Operations at a glance", `Verified ${formatDate(dashboard.generated_at)}. Counts reflect your internal role.`),
    node("div", { className: "kpi-grid" }, totals.map(([, label, field]) => numberCard(label, dashboard.totals[field], "Current total"))),
    node("div", { className: "content-grid" }, [
      card("Needs attention", node("div", { className: "card-body" }, attention.length ? node("ul", { className: "detail-list" }, attention.map(([key, value]) => node("li", {}, [node("span", { text: sentence(key) }), node("strong", { text: finiteNumber(value).toLocaleString() })]))) : emptyState("Queues are clear", "No failed, blocked or review items require attention.")), "one-third"),
      card("Recent operational changes", node("div", { className: "card-body" }, recentList(dashboard.recent)), "two-thirds"),
      health ? card("System health", node("div", { className: "card-body" }, [pill(health.status), node("ul", { className: "detail-list" }, [["Event dead letters",health.event_dead_letters],["Notification dead letters",health.notification_dead_letters],["Integration dead letters",health.integration_dead_letters],["Processing failures",health.processing_failures]].map(([label,value]) => node("li", {}, [node("span", { text: label }), node("strong", { text: finiteNumber(value).toLocaleString() })])))])) : null,
      state.permissions.has("platform:admin") ? card("Legacy platform administration", node("div", { className: "card-body" }, [node("p", { text: "Company, user, site, document, connector, product, payment and audit tools remain available during the Operations migration." }), node("a", { className: "button button-secondary", text: "Open legacy administration", href: "admin-legacy.html", attrs: { "data-compatibility": "platform-admin" } })])) : null,
    ])
  );
}

function queueRows(kind, items) {
  const rows = collection(items);
  if (kind === "jobs") return rows.map((item) => [node("strong", { text: optionalString(item.job_number, "Job") }), optionalString(item.title, "Untitled job"), pill(item.state), sentence(item.priority), sentence(item.assignee_type), formatDate(item.scheduled_start)]);
  if (kind === "processing") return rows.map((item) => {
    const actions = node("div", { className: "table-actions" });
    if (finiteNumber(item.retries_remaining) > 0 && ["FAILED","RETRY_WAIT","NEEDS_REVIEW"].includes(optionalString(item.status).toUpperCase())) actions.appendChild(button("Retry", { variant: "primary", onClick: () => retryProcessing(item) }));
    return [pill(item.status), sentence(item.stage, "Not started"), `${finiteNumber(item.retry_count)} / ${finiteNumber(item.max_retries)}`, node("span", { className: item.error_message ? "error-detail" : "", text: optionalString(item.error_message, "—") }), formatDate(item.next_poll_at), actions];
  });
  if (kind === "reports") return rows.map((item) => {
    const actions = node("div", { className: "table-actions" });
    const status = optionalString(item.status).toUpperCase();
    if (status === "REVIEW_REQUIRED" && state.permissions.has("report:review")) actions.appendChild(button("Approve", { variant: "primary", onClick: () => transitionReport(item, "approve") }));
    if (status === "APPROVED" && state.permissions.has("report:publish")) actions.appendChild(button("Publish", { variant: "primary", onClick: () => transitionReport(item, "publish") }));
    return [optionalString(item.title, "Report"), pill(item.status), sentence(item.qa_level), finiteNumber(item.revision).toLocaleString(), formatDate(item.updated_at), actions];
  });
  return rows.map((item) => [optionalString(item.provider, "Provider"), sentence(item.resource_type), pill(item.status), `${finiteNumber(item.attempts)} / ${finiteNumber(item.max_attempts)}`, node("span", { className: item.error_message ? "error-detail" : "", text: optionalString(item.error_message, "—") }), formatDate(item.next_attempt_at)]);
}

async function retryProcessing(item) {
  setStatus(elements.status, "Retrying processing job…");
  try { await API.post(`/processing/jobs/${encodePath(item.id)}/retry`, {}); state.queues = null; state.dashboard = null; await renderCurrent(true); setStatus(elements.status, "Processing retry queued.", "success"); }
  catch (error) { setStatus(elements.status, visibleError(error), "error"); }
}
async function renderProcessing(force) { const queues = await queueData(force); const rows = queueRows("processing", queues.processing); replace(elements.view, sectionHeading("Processing queue", "Failures expose safe diagnostics, retries remaining and their next attempt."), rows.length ? card(null, table(["Status","Stage","Retries","Failure","Next poll","Action"], rows, { label: "Processing queue" })) : emptyState("No processing work", "There are no active or failed processing jobs in this queue.")); }
async function transitionReport(item, action) {
  const permission = action === "approve" ? "report:review" : "report:publish";
  if (!state.permissions.has(permission)) return;
  setStatus(elements.status, `${sentence(action)} report…`);
  try {
    await API.post(`/reports/${encodePath(item.id)}/${action}`, { expected_lifecycle_version: finiteNumber(item.lifecycle_version, 1), note: null });
    state.queues = null; state.dashboard = null; await renderCurrent(true); setStatus(elements.status, `Report ${action === "approve" ? "approved" : "published"}.`, "success");
  } catch (error) { setStatus(elements.status, visibleError(error), "error"); }
}
async function renderReports(force) { const queues = await queueData(force); const rows = queueRows("reports", queues.reports_qa); replace(elements.view, sectionHeading("Reports QA", "Authorized reviewers can approve and publish reports through the canonical lifecycle."), rows.length ? card(null, table(["Report","Status","QA level","Revision","Updated","Action"], rows, { label: "Reports awaiting quality review" })) : emptyState("No reports awaiting QA", "The review queue is clear.")); }
async function renderIntegrations(force, finance = false) { const queues = await queueData(force); const rows = queueRows("integrations", queues.integrations); const title = finance ? "Finance sync" : "Integration delivery"; replace(elements.view, sectionHeading(title, "Safe queue diagnostics show delivery state without exposing provider credentials."), rows.length ? card(null, table(["Provider","Resource","Status","Attempts","Failure","Next attempt"], rows, { label: `${title} queue` })) : emptyState("No delivery issues", "No pending, failed or dead-letter deliveries are visible to your role.")); }

async function loadJobs(force = false) { if (!state.jobs || force) state.jobs = collection(await API.get("/operations/jobs?limit=200")); return state.jobs; }
async function loadContractors(force = false) { if (!can("contractors")) return []; if (!state.contractors || force) state.contractors = collection(await API.get("/operations/contractors?limit=200")); return state.contractors; }
async function renderJobs(force) {
  const jobs = await loadJobs(force);
  const rows = jobs.map((job) => [node("strong", { text: optionalString(job.job_number, "Job") }), optionalString(job.title, "Untitled job"), pill(job.state), sentence(job.priority), job.assigned_contractor_id ? "Contractor" : job.assigned_user_id ? "Staff" : "Unassigned", formatDate(job.scheduled_start), node("div", { className: "table-actions" }, button("Manage", { variant: "primary", onClick: () => openWorkflow(job) }))]);
  replace(elements.view, sectionHeading("Fulfilment jobs", "Assign delivery resources, schedule work and record state changes with lifecycle checks."), rows.length ? card(null, table(["Job","Title","State","Priority","Assignee","Schedule","Action"], rows, { label: "Fulfilment jobs" })) : emptyState("No jobs", "No fulfilment jobs have been created."));
}

async function openWorkflow(job) {
  state.workflowJob = job;
  document.getElementById("workflow-job-id").value = optionalString(job.id); document.getElementById("workflow-version").value = String(finiteNumber(job.lifecycle_version, 1));
  document.getElementById("workflow-state").value = ""; document.getElementById("workflow-state").disabled = false; document.getElementById("workflow-start").value = toLocalInput(job.scheduled_start); document.getElementById("workflow-end").value = toLocalInput(job.scheduled_end); document.getElementById("workflow-location").value = ""; document.getElementById("workflow-reason").value = "";
  delete elements.feedback.dataset.tone; elements.feedback.textContent = ""; document.getElementById("job-workflow-title").textContent = `Offer or update ${optionalString(job.job_number, "job")}`;
  const select = document.getElementById("workflow-contractor"); replace(select, node("option", { text: can("contractors") ? "Keep current assignment" : "Contractor assignment not permitted", attrs: { value: "" } })); select.disabled = !can("contractors");
  if (can("contractors")) {
    try { (await loadContractors()).filter((item) => optionalString(item.status).toUpperCase() === "ACTIVE" && optionalString(item.availability).toUpperCase() !== "UNAVAILABLE").forEach((item) => select.appendChild(node("option", { text: `${optionalString(item.display_name, "Contractor")} · ${sentence(item.availability)}`, attrs: { value: optionalString(item.id) } }))); }
    catch (error) { elements.feedback.textContent = visibleError(error); }
  }
  select.onchange = () => {
    const offering = Boolean(select.value);
    document.getElementById("workflow-state").disabled = offering;
    elements.feedback.textContent = offering ? "The schedule and location will be sent as a contractor offer. The job is assigned only after acceptance." : "";
  };
  elements.dialog.showModal();
}

async function saveWorkflow(event) {
  event.preventDefault(); if (event.submitter?.value === "cancel") { elements.dialog.close(); return; }
  const id = encodePath(document.getElementById("workflow-job-id").value); let version = finiteNumber(document.getElementById("workflow-version").value, 1); const job = state.workflowJob;
  if (!isRecord(job) || safeId(job.id) !== decodeURIComponent(id)) return;
  const contractorId = optionalString(document.getElementById("workflow-contractor").value); const nextState = optionalString(document.getElementById("workflow-state").value);
  const start = document.getElementById("workflow-start").value; const end = document.getElementById("workflow-end").value; const locationLabel = optionalString(document.getElementById("workflow-location").value); const reason = optionalString(document.getElementById("workflow-reason").value);
  const submit = document.getElementById("workflow-save"); submit.disabled = true; delete elements.feedback.dataset.tone; elements.feedback.textContent = "Saving verified workflow changes…";
  try {
    let result = null;
    if (contractorId && can("contractors")) {
      if ((start && !end) || (!start && end)) throw new Error("Both offer window dates are required.");
      result = await API.post("/operations/assignments", { contractor_id: contractorId, order_id: optionalString(job.order_id) || null, fulfilment_job_id: job.id, title: optionalString(job.title, "Assigned job"), location: locationLabel ? { label: locationLabel } : {}, window_start: start ? new Date(start).toISOString() : null, window_end: end ? new Date(end).toISOString() : null, requirements: isRecord(job.requirements) ? job.requirements : {}, internal_notes: reason || null });
    } else {
      const originalStart = toLocalInput(job.scheduled_start); const originalEnd = toLocalInput(job.scheduled_end);
      if (start !== originalStart || end !== originalEnd) { if (!start || !end) throw new Error("Both schedule dates are required."); result = await API.patch(`/operations/jobs/${id}/schedule`, { scheduled_start: new Date(start).toISOString(), scheduled_end: new Date(end).toISOString(), expected_version: version }); version = finiteNumber(result?.lifecycle_version, version); }
      if (nextState) result = await API.patch(`/operations/jobs/${id}/state`, { state: nextState, reason: reason || null, expected_version: version });
    }
    if (!result) throw new Error("Choose an assignment, schedule or state change.");
    state.jobs = null; state.queues = null; state.dashboard = null; elements.dialog.close(); await renderCurrent(true); setStatus(elements.status, contractorId ? "Contractor offer sent. Assignment begins only after acceptance." : "Job updated and audit history recorded.", "success");
  } catch (error) { elements.feedback.dataset.tone = "error"; elements.feedback.textContent = error instanceof Error ? error.message : "Job update failed."; }
  finally { submit.disabled = false; }
}

async function renderContractors(force) {
  const contractors = await loadContractors(force);
  const rows = contractors.map((item) => [optionalString(item.display_name, "Contractor"), sentence(item.resource_type), pill(item.status), pill(item.availability), optionalString(item.region, "—"), collection(item.capabilities).map((cap) => optionalString(cap.code || cap.name)).filter(Boolean).join(", ") || "—"]);
  replace(elements.view, sectionHeading("Contractor network", "Internal availability and capability matching for assignment workflows."), rows.length ? card(null, table(["Contractor","Type","Status","Availability","Region","Capabilities"], rows, { label: "Contractor network" })) : emptyState("No contractors", "No active contractors are registered."));
}
async function renderOrders(force) {
  if (!state.orders || force) state.orders = collection(await API.get("/orders/internal?limit=200"));
  const rows = state.orders.map((item) => [optionalString(item.order_number, "Order"), sentence(item.order_type), pill(item.fulfilment_status), pill(item.payment_status), `${finiteNumber(item.item_count)} item${finiteNumber(item.item_count) === 1 ? "" : "s"}`, formatDate(item.created_at)]);
  replace(elements.view, sectionHeading("Orders", "Commercial commitments handed into internal fulfilment."), rows.length ? card(null, table(["Order","Type","Fulfilment","Payment","Items","Created"], rows, { label: "Internal orders" })) : emptyState("No orders", "No commercial orders are available."));
}
async function renderMissions(force) {
  if (!state.missions || force) state.missions = collection(await API.get("/missions/internal?limit=200"));
  const rows = state.missions.map((item) => [optionalString(item.acquisition_number, "Mission"), optionalString(item.title, "Untitled mission"), sentence(item.acquisition_type), pill(item.state), formatDate(item.scheduled_start), formatDate(item.updated_at), missionActions(item)]);
  replace(elements.view, sectionHeading("Missions", "Advance acquisition work through the canonical lifecycle with an auditable reason."), rows.length ? card(null, table(["Mission","Title","Type","State","Scheduled","Updated","Action"], rows, { label: "Internal missions" })) : emptyState("No missions", "No missions are currently planned."));
}
function missionActions(item) {
  const transitions = MISSION_TRANSITIONS[optionalString(item.state).toUpperCase()] || [];
  if (!transitions.length) return node("span", { text: "Lifecycle complete" });
  const label = optionalString(item.acquisition_number, "mission");
  const select = node("select", { attrs: { "aria-label": `New state for ${label}` } }, [node("option", { text: "Choose state", attrs: { value: "" } }), ...transitions.map((value) => node("option", { text: sentence(value), attrs: { value } }))]);
  const reason = node("input", { attrs: { type: "text", maxlength: "2000", placeholder: "Reason", "aria-label": `Reason for changing ${label}` } });
  return node("div", { className: "table-actions lifecycle-action" }, [select, reason, button("Apply", { variant: "primary", onClick: () => transitionMission(item, select.value, reason.value) })]);
}
async function transitionMission(item, nextState, reason) {
  if (!(MISSION_TRANSITIONS[optionalString(item.state).toUpperCase()] || []).includes(nextState)) { setStatus(elements.status, "Choose a valid mission state.", "error"); return; }
  setStatus(elements.status, `Moving mission to ${sentence(nextState).toLowerCase()}…`);
  try {
    await API.patch(`/missions/internal/${encodePath(item.id)}/state`, { state: nextState, reason: optionalString(reason) || "Lifecycle transition from Operations portal", expected_version: finiteNumber(item.lifecycle_version, 1) });
    state.missions = null; state.dashboard = null; await renderCurrent(true); setStatus(elements.status, "Mission lifecycle updated.", "success");
  } catch (error) { setStatus(elements.status, visibleError(error), "error"); }
}
async function renderOrganizations(force) {
  const dashboard = await dashboardData(force);
  if (state.permissions.has("platform:admin")) {
    if (!state.companies || force) state.companies = collection(await API.get("/admin/companies?per_page=100"));
    const rows = state.companies.map((item) => [optionalString(item.name, "Organization"), optionalString(item.email, "—"), pill(item.status), sentence(item.subscription_plan), finiteNumber(item.current_users).toLocaleString(), finiteNumber(item.current_sites).toLocaleString()]);
    replace(elements.view, sectionHeading("Customers / Organizations", `${finiteNumber(dashboard?.totals?.organizations)} active customer organizations.`), rows.length ? card(null, table(["Organization","Contact","Status","Plan","Users","Sites"], rows, { label: "Customer organizations" })) : emptyState("No organizations", "No active customer organizations are registered.")); return;
  }
  replace(elements.view, sectionHeading("Customers / Organizations", "Customer identities are aggregated for this internal role."), numberCard("Active organizations", dashboard?.totals?.organizations, "Detailed customer records require platform administration permission."));
}
async function renderAggregate(totalKey, title, description, force) {
  const dashboard = await dashboardData(force);
  replace(elements.view, sectionHeading(title, description), node("div", { className: "kpi-grid" }, [numberCard(title, dashboard?.totals?.[totalKey], "Visible to your verified role")]), card("Operational boundary", node("div", { className: "card-body" }, emptyState("No broad registry exposed", "Use an assigned job, mission or review queue to open customer-scoped work. This view does not bypass tenant boundaries."))));
}
async function renderSystemHealth(force) {
  const dashboard = await dashboardData(force); const health = dashboard.health;
  if (!isRecord(health)) { replace(elements.view, emptyState("Health unavailable", "System health is not included for this role.")); return; }
  replace(elements.view, sectionHeading("System health", `Checked ${formatDate(dashboard.generated_at)}.`), node("div", { className: "kpi-grid" }, [node("article", { className: "kpi-card" }, [node("span", { className: "kpi-label", text: "Overall state" }), pill(health.status)]), numberCard("Event dead letters", health.event_dead_letters), numberCard("Notification dead letters", health.notification_dead_letters), numberCard("Integration dead letters", health.integration_dead_letters), numberCard("Processing failures", health.processing_failures)]));
}

async function renderCurrent(force = false) {
  if (!can(state.current)) return; setBusy(elements.view, true); setStatus(elements.status, "");
  try {
    const renderers = {
      dashboard: () => renderDashboard(force), organizations: () => renderOrganizations(force), assets: () => renderAggregate("assets", "Assets", "Asset access follows customer and workspace boundaries; broad counts are internal only.", force), orders: () => renderOrders(force), jobs: () => renderJobs(force), missions: () => renderMissions(force), processing: () => renderProcessing(force), reports_qa: () => renderReports(force), contractors: () => renderContractors(force), inventory: () => renderAggregate("orders", "Suppliers / Inventory", "Reference stock and supplier coordination follow order fulfilment.", force), finance_sync: () => renderIntegrations(force, true), integrations: () => renderIntegrations(force, false), system_health: () => renderSystemHealth(force),
    };
    await renderers[state.current]();
  } catch (error) { replace(elements.view, emptyState("This view could not load", visibleError(error))); setStatus(elements.status, visibleError(error), "error"); }
  finally { setBusy(elements.view, false); }
}

async function init() {
  installLogout(document.getElementById("operations-logout"), document.getElementById("denied-logout"));
  elements.menu.addEventListener("click", () => { const open = elements.sidebar.dataset.open !== "true"; elements.sidebar.dataset.open = String(open); elements.scrim.hidden = !open; elements.menu.setAttribute("aria-expanded", String(open)); elements.menu.setAttribute("aria-label", open ? "Close navigation" : "Open navigation"); });
  elements.scrim.addEventListener("click", closeSidebar); elements.refresh.addEventListener("click", () => renderCurrent(true)); elements.workflow.addEventListener("submit", saveWorkflow);
  window.addEventListener("popstate", async () => { const key = keyFromLocation(); await navigate(key, { popstate: true }); });
  try {
    const experience = validateExperience(await API.get("/operations/experience"));
    state.experience = experience; state.capabilities = experience.capabilities; state.permissions = experience.permissions; state.visibleKeys = experience.visibleKeys; groupNavigation();
    const roles = experience.actor.roles.map((role) => sentence(role)); document.getElementById("operations-user-name").textContent = roles[0] || "Operations staff"; document.getElementById("operations-user-role").textContent = roles.slice(1).join(", ") || "Verified internal role"; document.getElementById("operations-avatar").textContent = (roles[0]?.charAt(0) || "G").toUpperCase();
    elements.loading.hidden = true; elements.app.hidden = false; elements.dialog.hidden = false; document.body.dataset.operationsState = "ready"; state.current = keyFromLocation(); setActiveNavigation(); elements.title.textContent = NAVIGATION[state.current].label; history.replaceState({ operationsView: state.current }, "", expectedPath(state.current));
    window.GeoVisionOperations = Object.freeze({ ownsNavigation: true, surface: "INTERNAL_OPERATIONS" }); await renderCurrent();
  } catch (error) { showDenied(error); }
}

init();
