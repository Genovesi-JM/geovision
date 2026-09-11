const KNOWN_CAPABILITIES = new Set([
  "overview",
  "assets",
  "actions",
  "monitoring",
  "services",
  "map",
  "analytics",
  "reports",
  "catalog",
  "orders",
  "billing",
  "team",
  "integrations",
  "settings",
]);

const KNOWN_GROUPS = new Set([
  "overview",
  "operations",
  "intelligence",
  "commercial",
  "management",
]);

const SUBSCRIPTION_STATES = new Set(["active", "expiring", "expired", "pending"]);
const TARGET_TYPES = new Set([
  "WORKSPACE",
  "ASSET",
  "ACTION",
  "SERVICE",
  "SERVICE_RESULT",
  "ORDER",
  "REPORT",
]);

const ROUTES = {
  overview: { panel: "dashboard", capability: "overview", label: "Overview" },
  assets: { panel: "assets", capability: "assets", label: "Assets" },
  actions: { panel: "actions", capability: "actions", label: "Actions" },
  monitoring: { panel: "hardware", capability: "monitoring", label: "Monitoring" },
  services: { panel: "services", capability: "services", label: "Services" },
  map: { panel: "map", capability: "map", label: "Map" },
  analytics: { panel: "analytics", capability: "analytics", label: "Analytics" },
  reports: { panel: "reports", capability: "reports", label: "Reports" },
  products: { panel: "products", capability: "catalog", label: "Products & Services" },
  orders: { panel: "orders", capability: "orders", label: "Orders" },
  billing: { panel: "billing", capability: "billing", label: "Billing" },
  team: { panel: "team", capability: "team", label: "Team" },
  integrations: { panel: "integrations", capability: "integrations", label: "Integrations" },
  settings: { panel: "settings", capability: "settings", label: "Settings" },
};

const ROUTE_ALIASES = {
  dashboard: "overview",
  home: "overview",
  portal: "overview",
  asset: "assets",
  action: "actions",
  hardware: "monitoring",
  service: "services",
  "service-result": "services",
  catalog: "products",
  "products-services": "products",
  order: "orders",
  report: "reports",
};

const TARGET_ROUTES = {
  WORKSPACE: "overview",
  ASSET: "assets",
  ACTION: "actions",
  SERVICE: "services",
  SERVICE_RESULT: "services",
  ORDER: "orders",
  REPORT: "reports",
};

const ROUTE_TARGET_PARAMS = {
  assets: "asset",
  actions: "action",
  services: "service",
  orders: "order",
  reports: "report",
};

const TARGET_PARAMS = {
  ASSET: "asset",
  ACTION: "action",
  SERVICE: "service",
  SERVICE_RESULT: "service_result",
  ORDER: "order",
  REPORT: "report",
};

const ACTION_BUCKETS = [
  ["critical", "Critical"],
  ["attention", "Needs attention"],
  ["scheduled", "Scheduled"],
  ["completed", "Completed"],
];

const SAFE_GEOMETRIES = new Set([
  "Point",
  "MultiPoint",
  "LineString",
  "MultiLineString",
  "Polygon",
  "MultiPolygon",
]);

const BASE_MAP_PROVIDERS = Object.freeze({
  openstreetmap: Object.freeze({
    host: "tile.openstreetmap.org",
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
  }),
  mapbox: Object.freeze({
    host: "api.mapbox.com",
    attribution: "© Mapbox © OpenStreetMap",
    maxZoom: 22,
  }),
});

const safeId = (value) =>
  typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value);
const isRecord = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const asString = (value, fallback = "") =>
  typeof value === "string" && value.trim() ? value.trim() : fallback;
const asArray = (value) => (Array.isArray(value) ? value : []);

function normalizeBaseMap(raw = window.GV_MAP_TILES) {
  if (!isRecord(raw)) return null;
  const provider = BASE_MAP_PROVIDERS[asString(raw.provider).toLowerCase()];
  const template = asString(raw.urlTemplate);
  if (!provider || !template.includes("{z}") || !template.includes("{x}") || !template.includes("{y}")) return null;
  try {
    const candidate = new URL(template.replace("{z}", "0").replace("{x}", "0").replace("{y}", "0"));
    if (candidate.protocol !== "https:" || candidate.hostname !== provider.host) return null;
  } catch (_) {
    return null;
  }
  const requestedZoom = Number(raw.maxZoom);
  return {
    urlTemplate: template,
    maxZoom: Number.isInteger(requestedZoom) && requestedZoom > 0
      ? Math.min(requestedZoom, provider.maxZoom)
      : provider.maxZoom,
    attribution: provider.attribution,
  };
}

function pointCoordinate(feature) {
  if (!isRecord(feature) || feature.geometry?.type !== "Point") return null;
  const coordinates = asArray(feature.geometry.coordinates).map(Number);
  if (coordinates.length < 2 || !coordinates.slice(0, 2).every(Number.isFinite)) return null;
  const [longitude, latitude] = coordinates;
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null;
  return { latitude, longitude };
}

function googleDirectionsUrl({ latitude, longitude }) {
  const url = new URL("https://www.google.com/maps/dir/");
  url.searchParams.set("api", "1");
  url.searchParams.set("destination", `${latitude},${longitude}`);
  url.searchParams.set("travelmode", "driving");
  return url.href;
}

function currentBrowserPosition() {
  if (!navigator.geolocation) return Promise.reject(new Error("Location is unavailable in this browser"));
  return new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      const latitude = Number(coords?.latitude);
      const longitude = Number(coords?.longitude);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        reject(new Error("The browser returned an invalid location"));
        return;
      }
      resolve({ latitude, longitude });
    },
    () => reject(new Error("Location permission is required to estimate a route")),
    { enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 },
  ));
}

function normalizeRouteEstimate(raw) {
  if (!isRecord(raw)) return null;
  const distanceMeters = Number(raw.distance_meters);
  const durationSeconds = Number(raw.duration_seconds);
  if (!Number.isInteger(distanceMeters) || distanceMeters < 0 ||
      !Number.isInteger(durationSeconds) || durationSeconds < 0) return null;
  return {
    distanceMeters,
    durationSeconds,
    simulated: raw.simulated === true,
    trafficAware: raw.traffic_aware === true,
  };
}

function routeDistance(meters) {
  return meters < 1000 ? `${meters} m` : `${(meters / 1000).toFixed(1)} km`;
}

function routeDuration(seconds) {
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} h ${remainder} min` : `${hours} h`;
}

function node(tag, options = {}, children = []) {
  const element = document.createElement(tag);
  if (options.className) element.className = options.className;
  if (options.text !== undefined) element.textContent = String(options.text);
  if (options.id) element.id = options.id;
  if (options.attrs) {
    Object.entries(options.attrs).forEach(([key, value]) => {
      if (value !== undefined && value !== null) element.setAttribute(key, String(value));
    });
  }
  if (options.dataset) {
    Object.entries(options.dataset).forEach(([key, value]) => {
      if (value !== undefined && value !== null) element.dataset[key] = String(value);
    });
  }
  const normalized = Array.isArray(children) ? children : [children];
  normalized.forEach((child) => {
    if (child instanceof Node) element.appendChild(child);
    else if (child !== undefined && child !== null) element.appendChild(document.createTextNode(String(child)));
  });
  return element;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(document.documentElement.lang || "pt", {
    dateStyle: "medium",
  }).format(date);
}

function formatMoney(value, currency = "AOA") {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  try {
    return new Intl.NumberFormat(document.documentElement.lang || "pt", {
      style: "currency",
      currency: asString(currency, "AOA"),
      maximumFractionDigits: 0,
    }).format(amount / 100);
  } catch (_) {
    return `${amount / 100} ${asString(currency, "AOA")}`;
  }
}

class PortalApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "PortalApiError";
    this.status = status;
  }
}

class PortalApi {
  constructor(apiBase, getWorkspaceId) {
    this.apiBase = String(apiBase || "").replace(/\/$/, "");
    this.getWorkspaceId = getWorkspaceId;
  }

  async request(path, options = {}) {
    const token = localStorage.getItem("gv_token");
    if (!token) {
      const returnTo = rememberSafeReturn();
      window.location.assign(`login.html?return=${encodeURIComponent(returnTo)}`);
      throw new PortalApiError(401, "Authentication required");
    }
    const workspaceId = Object.hasOwn(options, "workspaceId")
      ? options.workspaceId
      : this.getWorkspaceId();
    const headers = {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    };
    if (workspaceId && safeId(workspaceId)) headers["X-Workspace-ID"] = workspaceId;
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch(`${this.apiBase}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    if (response.status === 401) {
      localStorage.removeItem("gv_token");
      const returnTo = rememberSafeReturn();
      window.location.assign(`login.html?return=${encodeURIComponent(returnTo)}`);
      throw new PortalApiError(401, "Session expired");
    }
    if (!response.ok) {
      throw new PortalApiError(response.status, `Request failed (${response.status})`);
    }
    if (response.status === 204) return null;
    return response.json();
  }

  get(path, options) {
    return this.request(path, options);
  }

  post(path, body, options = {}) {
    return this.request(path, { ...options, method: "POST", body });
  }
}

function rememberSafeReturn() {
  const allowed = new URL(window.location.href);
  const destination = parseLocation(allowed);
  const params = new URLSearchParams();
  if (destination.route !== "overview") params.set("view", destination.route);
  if (destination.targetId) {
    params.set(TARGET_PARAMS[destination.targetType] || "target_id", destination.targetId);
  }
  if (destination.notificationId) params.set("notification", destination.notificationId);
  const safeQuery = params.toString();
  const returnTo = `/dashboard.html${safeQuery ? `?${safeQuery}` : ""}`;
  sessionStorage.setItem("gv_portal_return", returnTo);
  return returnTo;
}

function normalizeWorkspace(raw) {
  if (!isRecord(raw) || !safeId(raw.id) || !safeId(raw.organization_id)) return null;
  const role = asString(raw.role);
  if (!role) return null;
  const taxonomy = window.GV_SECTOR_TAXONOMY;
  const sectors = taxonomy?.normalizeSectors
    ? taxonomy.normalizeSectors(Array.isArray(raw.sectors) ? raw.sectors : raw.sector)
    : asArray(raw.sectors).filter((item) => typeof item === "string");
  const primarySector = sectors[0] || (taxonomy?.normalizeSector?.(raw.sector) ?? "");
  return {
    id: raw.id,
    organizationId: raw.organization_id,
    name: asString(raw.name, "Workspace"),
    organizationName: asString(raw.organization_name, "Organization"),
    role,
    sector: primarySector,
    sectors,
    modules: asArray(raw.modules_enabled).filter((item) => typeof item === "string"),
  };
}

function workspaceSectorLabel(workspace) {
  const labels = window.GV_SECTOR_TAXONOMY?.labels || {};
  const sectors = workspace?.sectors?.length ? workspace.sectors : [workspace?.sector].filter(Boolean);
  return sectors.map((sector) => labels[sector] || sector).join(" · ") || "—";
}

function normalizeAssetTree(rawNodes, depth = 0, seen = new Set()) {
  if (depth > 20) return [];
  const result = [];
  for (const raw of asArray(rawNodes).slice(0, 2000)) {
    if (!isRecord(raw) || !safeId(raw.id) || seen.has(raw.id)) continue;
    const nextSeen = new Set(seen);
    nextSeen.add(raw.id);
    result.push({
      id: raw.id,
      parentAssetId: safeId(raw.parent_asset_id) ? raw.parent_asset_id : null,
      name: asString(raw.name, "Asset"),
      sector: asString(raw.sector, "generic"),
      assetType: asString(raw.asset_type, "asset"),
      status: asString(raw.status, "unknown"),
      children: normalizeAssetTree(raw.children, depth + 1, nextSeen),
    });
  }
  return result;
}

function normalizeExperience(raw) {
  if (!isRecord(raw)) throw new Error("Invalid portal experience");
  const activeWorkspace = normalizeWorkspace(raw.active_workspace);
  if (
    !activeWorkspace ||
    !safeId(raw.active_workspace_id) ||
    raw.active_workspace_id !== activeWorkspace.id ||
    !safeId(raw.active_organization_id) ||
    raw.active_organization_id !== activeWorkspace.organizationId
  ) {
    throw new Error("Invalid active workspace");
  }
  if (!isRecord(raw.subscription) || !SUBSCRIPTION_STATES.has(raw.subscription.status)) {
    throw new Error("Invalid subscription context");
  }
  if (!isRecord(raw.feature_flags)) throw new Error("Invalid feature flags");

  const capabilities = new Set(
    asArray(raw.capabilities).filter((value) => KNOWN_CAPABILITIES.has(value)),
  );
  const permissions = new Set(
    asArray(raw.permissions).filter((value) => typeof value === "string" && value.length <= 100),
  );
  const featureFlags = {};
  KNOWN_CAPABILITIES.forEach((capability) => {
    featureFlags[capability] = raw.feature_flags[capability] === true;
  });

  const navigation = [];
  for (const group of asArray(raw.navigation)) {
    if (!isRecord(group) || !KNOWN_GROUPS.has(group.key)) continue;
    const items = [];
    for (const item of asArray(group.items)) {
      if (
        !isRecord(item) ||
        !KNOWN_CAPABILITIES.has(item.key) ||
        item.capability !== item.key ||
        !capabilities.has(item.key) ||
        featureFlags[item.key] !== true
      ) continue;
      items.push({
        key: item.key,
        label: asString(item.label, item.key),
        route: asString(item.route),
      });
    }
    if (items.length) navigation.push({ key: group.key, items });
  }

  const workspaces = asArray(raw.workspaces).map(normalizeWorkspace).filter(Boolean);
  if (!workspaces.some((item) => item.id === activeWorkspace.id)) {
    throw new Error("Active workspace is not customer-accessible");
  }

  const destinationRules = new Map();
  const deepLinkContract = raw.deep_link_contract;
  if (
    isRecord(deepLinkContract) &&
    deepLinkContract.version === "geovision.portal-destination.v1"
  ) {
    for (const rule of asArray(deepLinkContract.destinations)) {
      if (
        isRecord(rule) &&
        TARGET_TYPES.has(rule.target_type) &&
        KNOWN_CAPABILITIES.has(rule.capability) &&
        capabilities.has(rule.capability) &&
        featureFlags[rule.capability] === true
      ) {
        destinationRules.set(rule.target_type, {
          capability: rule.capability,
          routeTemplate: asString(rule.route_template),
        });
      }
    }
  }

  return {
    activeWorkspaceId: activeWorkspace.id,
    activeOrganizationId: activeWorkspace.organizationId,
    organizationName: asString(raw.organization_name, activeWorkspace.organizationName),
    activeWorkspace,
    permissions,
    capabilities,
    featureFlags,
    subscription: {
      plan: asString(raw.subscription.plan, "—"),
      tier: asString(raw.subscription.tier, "—"),
      status: raw.subscription.status,
      validUntil: raw.subscription.valid_until || null,
    },
    workspaces,
    navigation,
    assetTree: normalizeAssetTree(raw.asset_tree),
    destinationRules,
  };
}

function parseLocation(url = new URL(window.location.href)) {
  const params = url.searchParams;
  const requested = asString(params.get("view"), "overview").toLowerCase();
  let route = ROUTE_ALIASES[requested] || requested;
  let targetType = null;
  let targetId = null;

  const typedView = {
    asset: "ASSET",
    action: "ACTION",
    service: "SERVICE",
    "service-result": "SERVICE_RESULT",
    order: "ORDER",
    report: "REPORT",
  }[requested];
  if (typedView && safeId(params.get("target_id"))) {
    targetType = typedView;
    targetId = params.get("target_id");
  }

  const legacyTargets = [
    ["asset", "ASSET", "assets"],
    ["action", "ACTION", "actions"],
    ["service_result", "SERVICE_RESULT", "services"],
    ["request", "SERVICE_RESULT", "services"],
    ["service", "SERVICE", "services"],
    ["order", "ORDER", "orders"],
    ["report", "REPORT", "reports"],
  ];
  for (const [param, type, destinationRoute] of legacyTargets) {
    if (!targetId && safeId(params.get(param))) {
      targetType = type;
      targetId = params.get(param);
      route = destinationRoute;
      break;
    }
  }
  if (!ROUTES[route]) route = "overview";
  return {
    route,
    targetType,
    targetId,
    notificationId: safeId(params.get("notification")) ? params.get("notification") : null,
  };
}

function safePortalPath(path) {
  if (typeof path !== "string") return null;
  const matchers = [
    [/^\/assets\/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$/, "ASSET", "assets"],
    [/^\/actions\/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$/, "ACTION", "actions"],
    [/^\/services\/orders\/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$/, "ORDER", "orders"],
    [/^\/orders\/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$/, "ORDER", "orders"],
    [/^\/services\/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$/, "SERVICE", "services"],
    [/^\/work\/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$/, "SERVICE_RESULT", "services"],
    [/^\/reports\/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$/, "REPORT", "reports"],
  ];
  for (const [pattern, targetType, route] of matchers) {
    const match = path.match(pattern);
    if (match) return { targetType, targetId: match[1], route };
  }
  if (["/portal", "/home", "/dashboard.html"].includes(path)) {
    return { targetType: "WORKSPACE", targetId: null, route: "overview" };
  }
  return null;
}

function normalizeRoute(value) {
  const input = asString(value, "overview").toLowerCase();
  return ROUTE_ALIASES[input] || (ROUTES[input] ? input : "overview");
}

function requiredCapability(route) {
  return ROUTES[route]?.capability || "overview";
}

function setStatus(id, text, kind = "") {
  const element = document.getElementById(id);
  if (!element) return;
  element.className = `portal-view-status${kind ? ` portal-${kind}` : ""}`;
  element.textContent = text || "";
}

function emptyState(title, description, retry) {
  const box = node("div", { className: "portal-empty" });
  box.append(node("h2", { text: title }), node("p", { text: description }));
  if (retry) {
    const button = node("button", { className: "btn btn-primary", text: "Try again", attrs: { type: "button" } });
    button.addEventListener("click", retry);
    box.appendChild(button);
  }
  return box;
}

function errorState(title, description, retry) {
  const box = emptyState(title, description, retry);
  box.className = "portal-error";
  return box;
}

function kpiCard(kpi, context = "") {
  const status = asString(kpi?.status, "unknown").toLowerCase();
  const article = node("article", {
    className: "portal-decision-kpi",
    dataset: { status: ["critical", "warning", "attention"].includes(status) ? status : "normal" },
    attrs: { "aria-label": `${asString(kpi?.name, "Metric")}: ${asString(kpi?.display_value, "—")}` },
  });
  article.append(
    node("div", { className: "portal-kpi-label", text: asString(kpi?.name, "Metric") }),
    node("div", { className: "portal-kpi-value", text: asString(kpi?.display_value, "—") }),
  );
  const details = [context];
  if (Number.isFinite(Number(kpi?.confidence))) details.push(`${Math.round(Number(kpi.confidence) * 100)}% confidence`);
  if (Number.isFinite(Number(kpi?.change_percent))) details.push(`${Number(kpi.change_percent) > 0 ? "+" : ""}${Number(kpi.change_percent).toFixed(1)}%`);
  if (details.filter(Boolean).length) {
    article.appendChild(node("div", { className: "portal-kpi-context", text: details.filter(Boolean).join(" · ") }));
  }
  return article;
}

function countCard(label, value, context = "") {
  return kpiCard({ name: label, display_value: String(value ?? 0), status: "normal" }, context);
}

function normalizeSummary(raw, workspaceId) {
  if (!isRecord(raw) || raw.workspace_id !== workspaceId || !isRecord(raw.totals)) {
    throw new Error("Invalid workspace summary");
  }
  const items = asArray(raw.items).filter((item) => isRecord(item) && safeId(item.id));
  return { workspaceId, generatedAt: raw.generated_at, totals: raw.totals, items };
}

function primaryKpis(summary) {
  const result = [];
  for (const item of summary.items) {
    for (const kpi of asArray(item.primary_kpis)) {
      if (!isRecord(kpi)) continue;
      result.push({ ...kpi, assetName: asString(item.name, "Asset") });
      if (result.length >= 4) return result;
    }
  }
  return result;
}

function flattenTree(nodes, result = []) {
  for (const item of nodes) {
    result.push(item);
    flattenTree(item.children, result);
  }
  return result;
}

class CustomerPortal {
  constructor({ apiBase, workspaceStorageKey, legacyWorkspaceStorageKey }) {
    this.workspaceStorageKey = workspaceStorageKey || "gv_workspace_id";
    this.legacyWorkspaceStorageKey = legacyWorkspaceStorageKey || "gv_account_id";
    this.experience = null;
    this.workspaceId = null;
    this.currentRoute = "overview";
    this.currentTarget = null;
    this.summary = null;
    this.authorizedKeys = new Set();
    this.loadedWorkspace = new Map();
    this.map = null;
    this.mapLayers = new Map();
    this.api = new PortalApi(apiBase, () => this.workspaceId);
  }

  installBridge() {
    window.GeoVisionPortal = {
      ownsNavigation: true,
      navigate: (route) => this.navigate(normalizeRoute(route), { userInitiated: true }),
      selectWorkspace: (workspaceId) => this.selectWorkspace(workspaceId),
    };
  }

  async init() {
    this.installBridge();
    this.bindNavigation();
    this.bindWorkspaceSwitcher();
    this.bindNotifications();
    if (!localStorage.getItem("gv_token")) {
      const returnTo = rememberSafeReturn();
      window.location.replace(`login.html?return=${encodeURIComponent(returnTo)}`);
      return;
    }
    try {
      await this.loadInitialExperience();
      document.body.dataset.portalState = "ready";
      document.querySelector(".sidebar-nav")?.setAttribute("aria-busy", "false");
      document.getElementById("portal-shell-status")?.setAttribute("hidden", "");
      const destination = this.initialDestination();
      if (destination.notificationId) {
        await this.resolveNotification(destination.notificationId);
      } else {
        this.navigate(destination.route, {
          targetType: destination.targetType,
          targetId: destination.targetId,
          replace: true,
        });
      }
      this.refreshNotificationCount();
    } catch (error) {
      if (error instanceof PortalApiError && error.status === 401) return;
      this.renderFatal(error);
    }
  }

  initialDestination() {
    const current = parseLocation();
    const hasExplicitDestination = current.notificationId || current.targetId ||
      new URL(window.location.href).searchParams.has("view");
    const stored = sessionStorage.getItem("gv_portal_return");
    sessionStorage.removeItem("gv_portal_return");
    if (hasExplicitDestination || typeof stored !== "string" || !stored.startsWith("/dashboard.html")) {
      return current;
    }
    try {
      const candidate = new URL(stored, window.location.origin);
      if (candidate.origin !== window.location.origin || candidate.pathname !== "/dashboard.html") return current;
      return parseLocation(candidate);
    } catch (_) {
      return current;
    }
  }

  bindNavigation() {
    document.querySelectorAll(".sidebar-link[data-route]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        if (link.hidden) return;
        this.navigate(link.dataset.route, { userInitiated: true });
      });
    });
    window.addEventListener("popstate", () => {
      const destination = parseLocation();
      if (destination.notificationId) this.resolveNotification(destination.notificationId);
      else this.navigate(destination.route, {
        targetType: destination.targetType,
        targetId: destination.targetId,
        fromHistory: true,
      });
    });
  }

  bindWorkspaceSwitcher() {
    const select = document.getElementById("account-switcher");
    if (!select || select.dataset.portalBound) return;
    select.dataset.portalBound = "true";
    select.addEventListener("change", () => this.selectWorkspace(select.value));
  }

  bindNotifications() {
    const button = document.getElementById("btn-notifications");
    button?.addEventListener("click", () => this.openNotificationInbox());
  }

  async loadInitialExperience() {
    const requestedFromUrl = new URL(window.location.href).searchParams.get("workspace_id");
    const stored = (safeId(requestedFromUrl) ? requestedFromUrl : null) ||
      localStorage.getItem(this.workspaceStorageKey) ||
      localStorage.getItem(this.legacyWorkspaceStorageKey);
    try {
      const raw = await this.api.get("/portal/experience", {
        workspaceId: safeId(stored) ? stored : null,
      });
      this.applyExperience(normalizeExperience(raw));
    } catch (error) {
      if (safeId(stored) && error instanceof PortalApiError && [403, 404].includes(error.status)) {
        localStorage.removeItem(this.workspaceStorageKey);
        localStorage.removeItem(this.legacyWorkspaceStorageKey);
        const raw = await this.api.get("/portal/experience", { workspaceId: null });
        this.applyExperience(normalizeExperience(raw));
        return;
      }
      throw error;
    }
  }

  applyExperience(experience) {
    this.experience = experience;
    this.workspaceId = experience.activeWorkspaceId;
    localStorage.setItem(this.workspaceStorageKey, this.workspaceId);
    localStorage.setItem(this.legacyWorkspaceStorageKey, this.workspaceId);
    localStorage.setItem("gv_account_name", experience.activeWorkspace.name);
    this.authorizedKeys = new Set(
      experience.navigation.flatMap((group) => group.items.map((item) => item.key)),
    );
    this.renderNavigation();
    this.renderWorkspaceContext();
    this.loadedWorkspace.clear();
    this.summary = null;
    this.destroyMap();
  }

  hasPermission(required) {
    return !required || this.experience.permissions.has(required);
  }

  routeAllowed(route) {
    const capability = requiredCapability(route);
    return this.authorizedKeys.has(capability) &&
      this.experience.capabilities.has(capability) &&
      this.experience.featureFlags[capability] === true;
  }

  renderNavigation() {
    const nav = document.querySelector(".sidebar-nav");
    document.querySelectorAll("[data-portal-group]").forEach((group) => { group.hidden = true; });
    document.querySelectorAll("[data-portal-item]").forEach((item) => { item.hidden = true; });
    document.querySelectorAll("[data-capability]:not([data-portal-item])").forEach((item) => {
      item.hidden = true;
    });

    document.querySelectorAll("[data-portal-item]").forEach((item) => {
      item.querySelectorAll("i").forEach((icon) => icon.setAttribute("aria-hidden", "true"));
      const key = item.dataset.portalItem;
      const capability = item.dataset.capability || key;
      const anyPermissions = asString(item.dataset.permissionAny).split(/\s+/).filter(Boolean);
      const permissionAllowed = this.hasPermission(item.dataset.permission) &&
        (!anyPermissions.length || anyPermissions.some((permission) => this.hasPermission(permission)));
      const allowed = this.authorizedKeys.has(key) &&
        this.experience.capabilities.has(capability) &&
        this.experience.featureFlags[capability] === true &&
        permissionAllowed;
      item.hidden = !allowed;
    });

    document.querySelectorAll("[data-portal-group]").forEach((group) => {
      group.hidden = !group.querySelector("[data-portal-item]:not([hidden])");
    });
    document.querySelectorAll("[data-capability]:not([data-portal-item])").forEach((item) => {
      const capability = item.dataset.capability;
      item.hidden = !this.authorizedKeys.has(capability) ||
        !this.experience.capabilities.has(capability) ||
        this.experience.featureFlags[capability] !== true;
    });
    const status = document.getElementById("portal-nav-status");
    if (status) {
      status.textContent = this.authorizedKeys.size ? "" : "No portal areas are available for this workspace.";
      status.hidden = this.authorizedKeys.size > 0;
    }
    nav?.setAttribute("aria-busy", "false");
    const notificationButton = document.getElementById("btn-notifications");
    if (notificationButton) notificationButton.hidden = false;
  }

  renderWorkspaceContext() {
    const select = document.getElementById("account-switcher");
    if (select) {
      select.replaceChildren();
      this.experience.workspaces.forEach((workspace) => {
        const option = node("option", {
          text: `${workspace.name} · ${workspace.organizationName}`,
          attrs: { value: workspace.id },
        });
        option.selected = workspace.id === this.workspaceId;
        select.appendChild(option);
      });
      select.disabled = this.experience.workspaces.length < 2;
    }
    const meta = document.getElementById("portal-workspace-meta");
    if (meta) meta.textContent = `${this.experience.organizationName} · ${workspaceSectorLabel(this.experience.activeWorkspace)}`;
    const role = this.experience.activeWorkspace.role;
    const roleLabel = role.charAt(0).toUpperCase() + role.slice(1);
    ["user-role", "dash-user-info-role"].forEach((id) => {
      const element = document.getElementById(id);
      if (element) element.textContent = roleLabel;
    });
    const accountInput = document.getElementById("settings-account");
    if (accountInput) accountInput.value = this.experience.activeWorkspace.name;
    const roleInput = document.getElementById("settings-role");
    if (roleInput) roleInput.value = roleLabel;
  }

  async selectWorkspace(nextWorkspaceId) {
    if (!safeId(nextWorkspaceId) || nextWorkspaceId === this.workspaceId) return;
    if (!this.experience.workspaces.some((workspace) => workspace.id === nextWorkspaceId)) return;
    const previousWorkspaceId = this.workspaceId;
    const select = document.getElementById("account-switcher");
    if (select) select.disabled = true;
    const navStatus = document.getElementById("portal-nav-status");
    if (navStatus) {
      navStatus.hidden = false;
      navStatus.textContent = "Switching workspace…";
    }
    try {
      const raw = await this.api.get("/portal/experience", { workspaceId: nextWorkspaceId });
      const experience = normalizeExperience(raw);
      if (experience.activeWorkspaceId !== nextWorkspaceId) throw new Error("Workspace selection mismatch");
      this.applyExperience(experience);
      document.body.dataset.portalState = "ready";
      const nextRoute = this.routeAllowed(this.currentRoute) ? this.currentRoute : "overview";
      this.navigate(nextRoute, { replace: true });
      this.refreshNotificationCount();
    } catch (error) {
      this.workspaceId = previousWorkspaceId;
      if (select) {
        select.value = previousWorkspaceId;
        select.disabled = this.experience.workspaces.length < 2;
      }
      if (navStatus) {
        navStatus.hidden = false;
        navStatus.textContent = "Could not switch workspace. Your previous workspace is still active.";
      }
    }
  }

  historyUrl(route, targetType, targetId) {
    const url = new URL(window.location.href);
    url.search = "";
    if (route !== "overview") url.searchParams.set("view", route);
    if (targetId && safeId(targetId)) {
      let param = ROUTE_TARGET_PARAMS[route] || "target_id";
      if (targetType === "SERVICE_RESULT") param = "service_result";
      url.searchParams.set(param, targetId);
    }
    return `${url.pathname}${url.search}${url.hash}`;
  }

  navigate(route, options = {}) {
    route = normalizeRoute(route);
    if (!this.experience) return;
    if (!this.routeAllowed(route)) route = this.routeAllowed("overview") ? "overview" : null;
    if (!route) {
      this.renderFatal(new Error("No authorized customer portal destination"));
      return;
    }
    let targetType = TARGET_TYPES.has(options.targetType) ? options.targetType : null;
    let targetId = safeId(options.targetId) ? options.targetId : null;
    if (targetType && !this.targetAllowed(targetType)) {
      targetType = null;
      targetId = null;
      route = "overview";
    }
    this.currentRoute = route;
    this.currentTarget = targetId ? { type: targetType, id: targetId } : null;
    const panelId = `view-${ROUTES[route].panel}`;
    document.querySelectorAll(".view-panel").forEach((panel) => {
      const active = panel.id === panelId;
      panel.classList.toggle("active", active);
      panel.setAttribute("aria-hidden", String(!active));
    });
    document.querySelectorAll(".sidebar-link[data-route]").forEach((link) => {
      const active = link.dataset.route === route;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    const breadcrumb = document.getElementById("breadcrumb-current");
    if (breadcrumb) breadcrumb.textContent = ROUTES[route].label;
    const sidebar = document.getElementById("sidebar");
    const menuButton = document.getElementById("btn-menu-toggle");
    sidebar?.classList.remove("open");
    menuButton?.setAttribute("aria-expanded", "false");

    if (!options.fromHistory) {
      const method = options.replace ? "replaceState" : "pushState";
      window.history[method]({ route, targetType, targetId }, "", this.historyUrl(route, targetType, targetId));
    }
    this.loadRoute(route, targetType, targetId);
    if (options.userInitiated) {
      document.querySelector(`#${panelId} h1`)?.focus({ preventScroll: true });
    }
  }

  targetAllowed(targetType) {
    const rule = this.experience.destinationRules.get(targetType);
    if (!rule) return false;
    const expected = requiredCapability(TARGET_ROUTES[targetType]);
    return rule.capability === expected && this.authorizedKeys.has(expected);
  }

  loadRoute(route, targetType, targetId) {
    switch (route) {
      case "overview": this.renderOverview(); break;
      case "assets": this.renderAssets(targetId); break;
      case "actions": this.renderActions(targetId); break;
      case "monitoring": this.renderMonitoring(targetId); break;
      case "services": this.renderServices(targetId, targetType); break;
      case "map": this.renderMap(targetId); break;
      case "analytics": this.renderAnalytics(targetId); break;
      case "reports": this.renderReports(targetId); break;
      case "orders": this.renderOrders(targetId); break;
      case "billing": this.renderBilling(); break;
      case "team": this.renderTeam(); break;
      case "integrations": this.renderIntegrations(); break;
      case "settings": this.renderSettings(); break;
      default: break;
    }
  }

  async getSummary(assetId = null) {
    const path = `/portal/assets/summary${assetId ? `?asset_id=${encodeURIComponent(assetId)}` : ""}`;
    const raw = await this.api.get(path);
    return normalizeSummary(raw, this.workspaceId);
  }

  async renderOverview() {
    const panel = document.getElementById("view-dashboard");
    if (!panel) return;
    panel.replaceChildren();
    const header = node("div", { className: "page-header" }, [
      node("div", { className: "page-eyebrow", text: this.experience.organizationName }),
      node("h1", { className: "page-title", text: this.experience.activeWorkspace.name, id: "portal-overview-title", attrs: { tabindex: "-1" } }),
      node("p", { className: "page-subtitle", text: `${workspaceSectorLabel(this.experience.activeWorkspace)} · Updated decision view` }),
    ]);
    const decisionHeading = node("h2", { className: "card-title", text: "What needs a decision now" });
    const decisionGrid = node("div", { className: "portal-decision-grid", id: "portal-decision-kpis", attrs: { "aria-busy": "true" } });
    const lower = node("div", { className: "portal-overview-grid" });
    panel.append(header, decisionHeading, decisionGrid, lower);
    try {
      const summary = await this.getSummary();
      if (this.currentRoute !== "overview" || summary.workspaceId !== this.workspaceId) return;
      this.summary = summary;
      decisionGrid.replaceChildren();
      const decisions = primaryKpis(summary);
      if (decisions.length) {
        decisions.forEach((kpi) => decisionGrid.appendChild(kpiCard(kpi, kpi.assetName)));
      } else {
        decisionGrid.append(
          countCard("Assets needing attention", summary.totals.attention, "Portfolio"),
          countCard("Open actions", summary.totals.open_actions, "Workspace"),
          countCard("Offline devices", summary.totals.offline_devices, "Monitoring"),
          countCard("Published reports", summary.totals.published_reports, "Intelligence"),
        );
      }
      decisionGrid.setAttribute("aria-busy", "false");

      const portfolioCard = node("section", { className: "card", attrs: { "aria-labelledby": "portfolio-title" } });
      const portfolioBody = node("div", { className: "card-body" });
      portfolioCard.append(
        node("div", { className: "card-header" }, node("h2", { className: "card-title", id: "portfolio-title", text: "Portfolio at a glance" })),
        portfolioBody,
      );
      const totals = node("div", { className: "portal-metric-list" });
      [
        ["Assets", summary.totals.assets],
        ["Active", summary.totals.active],
        ["Attention", summary.totals.attention],
        ["Open actions", summary.totals.open_actions],
      ].forEach(([label, value]) => {
        const metric = node("dl", { className: "portal-technical-metric" });
        metric.append(node("dt", { text: label }), node("dd", { text: value ?? 0 }));
        totals.appendChild(metric);
      });
      portfolioBody.appendChild(totals);

      const nextCard = node("section", { className: "card", attrs: { "aria-labelledby": "next-title" } });
      const nextBody = node("div", { className: "card-body" });
      nextCard.append(
        node("div", { className: "card-header" }, node("h2", { className: "card-title", id: "next-title", text: "Contextual next steps" })),
        nextBody,
      );
      const links = [
        ["assets", "Explore asset hierarchy"],
        ["actions", "Review prioritized actions"],
        ["reports", "Open published reports"],
      ].filter(([route]) => this.routeAllowed(route));
      if (!links.length) nextBody.appendChild(node("p", { text: "No additional areas are enabled for this workspace." }));
      links.forEach(([route, label]) => {
        const button = node("button", { className: "btn btn-secondary", text: label, attrs: { type: "button" } });
        button.addEventListener("click", () => this.navigate(route, { userInitiated: true }));
        nextBody.appendChild(button);
      });
      lower.replaceChildren(portfolioCard, nextCard);
    } catch (_) {
      decisionGrid.replaceChildren(errorState("Overview unavailable", "We could not load this workspace summary.", () => this.renderOverview()));
      decisionGrid.setAttribute("aria-busy", "false");
    }
  }

  renderAssetTree(selectedId) {
    const container = document.getElementById("asset-tree");
    if (!container) return;
    container.replaceChildren();
    const renderLevel = (items, level) => {
      const list = node("ul", { attrs: { role: level === 1 ? "presentation" : "group" } });
      items.forEach((asset) => {
        const item = node("li", {
          attrs: {
            role: "treeitem",
            "aria-level": level,
            ...(asset.children.length ? { "aria-expanded": "true" } : {}),
          },
        });
        const button = node("button", {
          className: "portal-tree-button",
          attrs: { type: "button", "aria-selected": String(asset.id === selectedId) },
        });
        button.append(
          node("span", { text: asset.name }),
          node("span", { className: "portal-tree-meta", text: asset.assetType }),
        );
        button.addEventListener("click", () => this.selectAsset(asset.id));
        item.appendChild(button);
        if (asset.children.length) item.appendChild(renderLevel(asset.children, level + 1));
        list.appendChild(item);
      });
      return list;
    };
    container.appendChild(renderLevel(this.experience.assetTree, 1));
    const buttons = [...container.querySelectorAll(".portal-tree-button")];
    buttons.forEach((button, index) => {
      button.addEventListener("keydown", (event) => {
        let next = null;
        if (event.key === "ArrowDown") next = buttons[index + 1];
        if (event.key === "ArrowUp") next = buttons[index - 1];
        if (event.key === "Home") next = buttons[0];
        if (event.key === "End") next = buttons.at(-1);
        if (next) {
          event.preventDefault();
          next.focus();
        }
      });
    });
  }

  async renderAssets(assetId = null) {
    const status = document.getElementById("assets-status");
    const layout = document.getElementById("assets-layout");
    if (!status || !layout) return;
    const flat = flattenTree(this.experience.assetTree);
    const selected = safeId(assetId) && flat.some((asset) => asset.id === assetId)
      ? assetId
      : flat[0]?.id || null;
    this.renderAssetTree(selected);
    if (!flat.length) {
      layout.hidden = true;
      status.replaceChildren(emptyState("No assets yet", "This workspace has no customer assets."));
      return;
    }
    status.textContent = "Loading asset summary…";
    layout.hidden = false;
    try {
      const summary = await this.getSummary(selected);
      if (this.currentRoute !== "assets") return;
      const item = summary.items.find((row) => row.id === selected) || summary.items[0];
      if (!item) throw new Error("Asset summary missing");
      status.textContent = "";
      this.renderAssetSummary(item);
      this.renderAssetTree(item.id);
    } catch (_) {
      status.replaceChildren(errorState("Asset unavailable", "The selected asset could not be loaded in this workspace.", () => this.renderAssets(selected)));
    }
  }

  selectAsset(assetId) {
    if (!safeId(assetId)) return;
    this.currentTarget = { type: "ASSET", id: assetId };
    window.history.pushState(
      { route: "assets", targetType: "ASSET", targetId: assetId },
      "",
      this.historyUrl("assets", "ASSET", assetId),
    );
    this.renderAssets(assetId);
  }

  renderAssetSummary(item) {
    const container = document.getElementById("asset-summary");
    if (!container) return;
    container.replaceChildren();
    const header = node("div", { className: "portal-summary-header" });
    header.append(
      node("div", {}, [
        node("h3", { text: asString(item.name, "Asset"), attrs: { tabindex: "-1" } }),
        node("p", { text: `${asString(item.sector, "Sector")} · ${asString(item.asset_type, "Asset")} · ${asString(item.location_label, "No location label")}` }),
      ]),
      node("span", { className: "badge", text: asString(item.decision_status, "UNKNOWN") }),
    );
    container.appendChild(header);
    const heading = node("h4", { text: "Decision KPIs" });
    const primary = node("div", { className: "portal-decision-grid" });
    const kpis = asArray(item.primary_kpis).filter(isRecord);
    if (kpis.length) kpis.forEach((kpi) => primary.appendChild(kpiCard(kpi)));
    else primary.appendChild(countCard("Open actions", item.open_action_count || 0, "This asset"));
    container.append(heading, primary);

    const facts = node("div", { className: "portal-metric-list" });
    [
      ["Open actions", item.open_action_count],
      ["Critical observations", item.critical_observation_count],
      ["Warnings", item.warning_observation_count],
      ["Child assets", item.children_count],
    ].forEach(([label, value]) => {
      const dl = node("dl", { className: "portal-technical-metric" });
      dl.append(node("dt", { text: label }), node("dd", { text: value ?? 0 }));
      facts.appendChild(dl);
    });
    container.appendChild(facts);

    const details = node("details", { className: "portal-metric-details" });
    details.appendChild(node("summary", { text: `Technical drilldown (${Number(item.technical_metric_count || 0)} technical metrics)` }));
    const secondary = node("div", { className: "portal-metric-list" });
    asArray(item.secondary_kpis).filter(isRecord).forEach((kpi) => {
      const dl = node("dl", { className: "portal-technical-metric" });
      dl.append(node("dt", { text: asString(kpi.name, "Metric") }), node("dd", { text: asString(kpi.display_value, "—") }));
      secondary.appendChild(dl);
    });
    if (!secondary.children.length) secondary.appendChild(node("p", { text: "No secondary metrics are available." }));
    details.appendChild(secondary);
    container.appendChild(details);
  }

  bucketForAction(action) {
    if (action.status === "COMPLETED") return "completed";
    if (["CRITICAL", "URGENT"].includes(action.priority)) return "critical";
    if (action.due_date && new Date(action.due_date).getTime() > Date.now()) return "scheduled";
    return "attention";
  }

  async renderActions(focusId = null) {
    const status = document.getElementById("actions-status");
    const board = document.getElementById("actions-board");
    if (!status || !board) return;
    status.textContent = "Loading actions…";
    board.hidden = true;
    try {
      const raw = await this.api.get("/actions?limit=100");
      const items = asArray(raw?.items).filter((item) =>
        isRecord(item) && safeId(item.id) && item.workspace_id === this.workspaceId,
      );
      if (this.currentRoute !== "actions") return;
      board.replaceChildren();
      const grouped = Object.fromEntries(ACTION_BUCKETS.map(([key]) => [key, []]));
      items.forEach((item) => grouped[this.bucketForAction(item)].push(item));
      ACTION_BUCKETS.forEach(([key, label]) => {
        const column = node("section", { className: "portal-action-column", attrs: { "aria-labelledby": `action-bucket-${key}` } });
        column.appendChild(node("h2", { text: `${label} (${grouped[key].length})`, id: `action-bucket-${key}` }));
        if (!grouped[key].length) column.appendChild(node("p", { className: "portal-kpi-context", text: "No actions" }));
        grouped[key].forEach((action) => {
          const card = node("article", {
            className: "portal-item-card",
            dataset: { focused: action.id === focusId },
            attrs: { tabindex: action.id === focusId ? "-1" : undefined },
          });
          card.append(
            node("h3", { text: asString(action.title, "Action") }),
            node("p", { text: asString(action.description, "No description") }),
            node("p", { text: `${asString(action.priority, "NORMAL")} · ${action.due_date ? `Due ${formatDate(action.due_date)}` : "No due date"}` }),
          );
          column.appendChild(card);
        });
        board.appendChild(column);
      });
      status.textContent = items.length ? "" : "No actions in this workspace.";
      board.hidden = false;
      if (focusId && !items.some((item) => item.id === focusId)) {
        status.textContent = "The requested action is not available in this workspace.";
      }
      board.querySelector('[data-focused="true"]')?.focus();
    } catch (_) {
      status.replaceChildren(errorState("Actions unavailable", "We could not load the workspace action queue.", () => this.renderActions(focusId)));
    }
  }

  async renderMonitoring() {
    const view = document.getElementById("view-hardware");
    const tbody = document.getElementById("hardware-table-body");
    const empty = document.getElementById("hardware-empty");
    if (!view || !tbody) return;
    const title = view.querySelector("h1");
    if (title) title.textContent = "Monitoring";
    const subtitle = view.querySelector(".page-subtitle");
    if (subtitle) subtitle.textContent = "Workspace devices and data freshness.";
    const provision = document.getElementById("iot-kit-card");
    if (provision) provision.hidden = !this.hasPermission("workspace:operate");
    tbody.replaceChildren();
    if (empty) {
      empty.style.display = "";
      empty.querySelector("p").textContent = "Loading monitoring devices…";
    }
    try {
      const raw = await this.api.get("/mobile/devices");
      const devices = asArray(raw?.items);
      if (this.currentRoute !== "monitoring") return;
      tbody.replaceChildren();
      devices.forEach((device) => {
        if (!isRecord(device) || !safeId(device.id)) return;
        const row = node("tr");
        [
          asString(device.name || device.hardware_model, "Device"),
          asString(device.site_name || device.location_label, "—"),
          asString(device.status || device.connectivity_status, "unknown"),
          device.last_seen_at ? formatDate(device.last_seen_at) : "—",
        ].forEach((value) => row.appendChild(node("td", { text: value })));
        tbody.appendChild(row);
      });
      if (empty) {
        empty.style.display = devices.length ? "none" : "";
        empty.querySelector("p").textContent = "No monitoring devices in this workspace.";
      }
    } catch (_) {
      if (empty) {
        empty.style.display = "";
        empty.querySelector("p").textContent = "Monitoring is temporarily unavailable.";
      }
    }
  }

  async renderServices(focusId = null, targetType = null) {
    const status = document.getElementById("services-status");
    const list = document.getElementById("services-list");
    if (!status || !list) return;
    status.textContent = "Loading services…";
    list.hidden = true;
    try {
      const raw = focusId && targetType === "SERVICE_RESULT"
        ? [await this.api.get(`/mobile/service-requests/${encodeURIComponent(focusId)}`)]
        : await this.api.get("/mobile/service-requests");
      const items = asArray(raw).filter((item) => isRecord(item) && safeId(item.id));
      if (this.currentRoute !== "services") return;
      list.replaceChildren();
      items.forEach((service) => {
        const card = node("article", {
          className: "card portal-item-card",
          dataset: { focused: service.id === focusId },
          attrs: { tabindex: service.id === focusId ? "-1" : undefined },
        });
        card.append(
          node("h3", { text: asString(service.type, "GeoVision service") }),
          node("p", { text: `${asString(service.site_name, "Asset")} · ${asString(service.status, "unknown")}` }),
          node("p", { text: asString(service.description, "No description") }),
          node("p", { text: `Progress: ${Math.max(0, Math.min(100, Number(service.progress_percent) || 0))}%` }),
        );
        if (isRecord(service.result)) {
          const result = node("div", { className: "portal-metric-details" });
          result.append(
            node("strong", { text: asString(service.result.title, "Service result") }),
            node("p", { text: asString(service.result.summary, "Result available") }),
          );
          card.appendChild(result);
        }
        list.appendChild(card);
      });
      if (!items.length) list.appendChild(emptyState("No service requests", "Request a first-party GeoVision service from the catalogue."));
      status.textContent = "";
      list.hidden = false;
      list.querySelector('[data-focused="true"]')?.focus();
    } catch (_) {
      status.replaceChildren(errorState("Services unavailable", "The requested service is not available in this workspace.", () => this.renderServices(focusId, targetType)));
    }
  }

  async renderAnalytics(assetId = null) {
    const status = document.getElementById("analytics-status");
    const content = document.getElementById("analytics-content");
    if (!status || !content) return;
    status.textContent = "Loading analytics…";
    content.hidden = true;
    try {
      const summary = await this.getSummary(assetId);
      if (this.currentRoute !== "analytics") return;
      content.replaceChildren();
      const primaryHeading = node("h2", { className: "card-title", text: "Decision KPIs" });
      const grid = node("div", { className: "portal-decision-grid" });
      const decisions = primaryKpis(summary);
      decisions.forEach((kpi) => grid.appendChild(kpiCard(kpi, kpi.assetName)));
      if (!decisions.length) grid.appendChild(emptyState("No decision KPIs", "Validated intelligence has not produced primary KPIs yet."));
      content.append(primaryHeading, grid);
      const details = node("details", { className: "card portal-metric-details" });
      details.appendChild(node("summary", { text: "Technical drilldown" }));
      const metrics = node("div", { className: "portal-metric-list" });
      summary.items.forEach((item) => {
        asArray(item.secondary_kpis).filter(isRecord).forEach((kpi) => {
          const metric = node("dl", { className: "portal-technical-metric" });
          metric.append(
            node("dt", { text: `${asString(item.name, "Asset")} · ${asString(kpi.name, "Metric")}` }),
            node("dd", { text: asString(kpi.display_value, "—") }),
          );
          metrics.appendChild(metric);
        });
      });
      if (!metrics.children.length) metrics.appendChild(node("p", { text: "No secondary metrics are available." }));
      details.appendChild(metrics);
      content.appendChild(details);
      status.textContent = "";
      content.hidden = false;
    } catch (_) {
      status.replaceChildren(errorState("Analytics unavailable", "We could not load validated workspace analytics.", () => this.renderAnalytics(assetId)));
    }
  }

  geometryValid(geometry, allowedTypes) {
    if (!isRecord(geometry) || !SAFE_GEOMETRIES.has(geometry.type) || !allowedTypes.has(geometry.type)) return false;
    let coordinateCount = 0;
    const validCoordinates = (value, depth = 0) => {
      if (depth > 8 || coordinateCount > 200000 || !Array.isArray(value)) return false;
      if (value.length >= 2 && value.every((item) => typeof item === "number")) {
        coordinateCount += value.length;
        return value.every(Number.isFinite);
      }
      return value.length > 0 && value.every((child) => validCoordinates(child, depth + 1));
    };
    return validCoordinates(geometry.coordinates);
  }

  normalizeMapLayers(raw) {
    if (!isRecord(raw) || raw.workspace_id !== this.workspaceId) throw new Error("Invalid map workspace");
    const layers = [];
    for (const layer of asArray(raw.layers)) {
      if (!isRecord(layer) || !safeId(layer.id) || !["ASSET", "OBSERVATION", "DEVICE"].includes(layer.kind)) continue;
      const allowedTypes = new Set(asArray(layer.geometry_types).filter((type) => SAFE_GEOMETRIES.has(type)));
      const collection = layer.feature_collection;
      if (!isRecord(collection) || collection.type !== "FeatureCollection") continue;
      const features = asArray(collection.features).slice(0, 5000).filter((feature) =>
        isRecord(feature) && feature.type === "Feature" && safeId(feature.id) &&
        this.geometryValid(feature.geometry, allowedTypes) && isRecord(feature.properties),
      );
      layers.push({
        id: layer.id,
        label: asString(layer.label, layer.id),
        kind: layer.kind,
        defaultVisible: layer.default_visible === true,
        collection: { type: "FeatureCollection", features },
      });
    }
    const bounds = asArray(raw.bounds).map(Number);
    return { layers, bounds: bounds.length === 4 && bounds.every(Number.isFinite) ? bounds : null };
  }

  destroyMap() {
    if (this.map) {
      this.map.remove();
      this.map = null;
    }
    this.mapLayers.clear();
  }

  async estimateRoute(destination, label, output) {
    output.replaceChildren(node("p", { text: "Calculating driving route…" }));
    try {
      const origin = await currentBrowserPosition();
      const raw = await this.api.post("/location/routes:compute", {
        origin,
        destination,
        language_code: document.documentElement.lang || "pt",
      });
      const estimate = normalizeRouteEstimate(raw);
      if (!estimate) throw new Error("Invalid route response");
      const quality = estimate.simulated
        ? "Demonstration estimate — not live navigation"
        : estimate.trafficAware
          ? "Provider estimate with traffic"
          : "Provider estimate without live traffic";
      output.replaceChildren(
        node("strong", { text: `Route to ${label}` }),
        node("p", { text: `${routeDistance(estimate.distanceMeters)} · ${routeDuration(estimate.durationSeconds)}` }),
        node("small", { text: quality }),
      );
    } catch (_) {
      output.replaceChildren(node("p", { text: "The route estimate is unavailable. Check location permission and try again." }));
    }
  }

  async renderMap(assetId = null) {
    const view = document.getElementById("view-map");
    const controls = document.getElementById("geo-layers");
    const side = document.getElementById("geo-side");
    const mapElement = document.getElementById("iot-map");
    const empty = document.getElementById("iot-map-empty");
    const refresh = document.getElementById("geo-refresh");
    if (!view || !controls || !side || !mapElement) return;
    if (refresh) {
      refresh.setAttribute("aria-label", "Refresh map layers");
      refresh.onclick = () => this.renderMap(assetId);
    }
    view.querySelector("h1").textContent = "Map";
    view.querySelector(".page-subtitle").textContent = "Validated workspace layers supplied by GeoVision.";
    controls.replaceChildren(node("span", { text: "Loading map layers…" }));
    side.replaceChildren();
    try {
      const raw = await this.api.get(`/portal/map-layers${assetId ? `?asset_id=${encodeURIComponent(assetId)}` : ""}`);
      const projection = this.normalizeMapLayers(raw);
      if (this.currentRoute !== "map") return;
      this.destroyMap();
      controls.replaceChildren();
      if (!window.L) throw new Error("Map renderer unavailable");
      this.map = window.L.map(mapElement, { zoomControl: true, attributionControl: true }).setView([-12.5, 18.5], 5);
      const baseMap = normalizeBaseMap();
      if (!baseMap) throw new Error("Base map configuration unavailable");
      window.L.tileLayer(baseMap.urlTemplate, {
        attribution: baseMap.attribution,
        maxZoom: baseMap.maxZoom,
      }).addTo(this.map);
      const routeOutput = node("section", {
        className: "portal-map-route",
        attrs: { "aria-live": "polite", "aria-label": "Driving route estimate" },
      }, node("p", { text: "Select a map point to estimate a driving route from your current location." }));
      side.appendChild(routeOutput);
      const colors = { ASSET: "#22d3ee", OBSERVATION: "#f59e0b", DEVICE: "#34d399" };
      projection.layers.forEach((layer) => {
        const leafletLayer = window.L.geoJSON(layer.collection, {
          pointToLayer: (_, latlng) => window.L.circleMarker(latlng, {
            radius: 7,
            color: colors[layer.kind],
            fillColor: colors[layer.kind],
            fillOpacity: .72,
            weight: 2,
          }),
          style: { color: colors[layer.kind], weight: 3, fillOpacity: .16 },
          onEachFeature: (feature, rendered) => {
            const popup = node("div");
            const label = asString(feature.properties.name || feature.properties.observation_type, layer.label);
            popup.append(
              node("strong", { text: label }),
              node("p", { text: asString(feature.properties.status || feature.properties.severity, layer.kind) }),
            );
            const destination = pointCoordinate(feature);
            if (destination) {
              const actions = node("div", { className: "portal-map-popup-actions" });
              actions.appendChild(node("a", {
                text: "Open directions",
                attrs: {
                  href: googleDirectionsUrl(destination),
                  target: "_blank",
                  rel: "noopener noreferrer",
                },
              }));
              const estimate = node("button", {
                text: "Estimate route",
                attrs: { type: "button" },
              });
              estimate.addEventListener("click", () => this.estimateRoute(destination, label, routeOutput));
              actions.appendChild(estimate);
              popup.appendChild(actions);
            }
            rendered.bindPopup(popup);
          },
        });
        this.mapLayers.set(layer.id, leafletLayer);
        if (layer.defaultVisible) leafletLayer.addTo(this.map);
        const toggle = node("button", {
          className: "portal-layer-toggle",
          text: `${layer.label} (${layer.collection.features.length})`,
          attrs: { type: "button", "aria-pressed": String(layer.defaultVisible) },
        });
        toggle.addEventListener("click", () => {
          const visible = toggle.getAttribute("aria-pressed") !== "true";
          toggle.setAttribute("aria-pressed", String(visible));
          if (visible) leafletLayer.addTo(this.map);
          else leafletLayer.removeFrom(this.map);
        });
        controls.appendChild(toggle);
        const legend = node("div", { className: "portal-map-legend-item" });
        legend.append(node("strong", { text: layer.label }), node("span", { text: `${layer.kind} · validated features only` }));
        side.appendChild(legend);
      });
      if (projection.bounds) {
        this.map.fitBounds([
          [projection.bounds[1], projection.bounds[0]],
          [projection.bounds[3], projection.bounds[2]],
        ], { padding: [24, 24], maxZoom: 16 });
      } else {
        const featureBounds = [...this.mapLayers.values()]
          .map((layer) => layer.getBounds?.())
          .filter((bounds) => bounds?.isValid());
        if (featureBounds.length) this.map.fitBounds(featureBounds.reduce((all, bounds) => all.extend(bounds), featureBounds[0]), { padding: [24, 24] });
      }
      if (empty) {
        empty.style.display = projection.layers.some((layer) => layer.collection.features.length) ? "none" : "";
        empty.textContent = "No validated spatial data is available for this workspace.";
      }
      setTimeout(() => this.map?.invalidateSize(), 0);
    } catch (_) {
      controls.replaceChildren(errorState("Map unavailable", "Workspace layers could not be loaded.", () => this.renderMap(assetId)));
      if (empty) empty.style.display = "none";
    }
  }

  async renderReports(focusId = null) {
    const tbody = document.getElementById("reports-table-body");
    const empty = document.getElementById("reports-empty");
    if (!tbody || !empty) return;
    tbody.replaceChildren();
    empty.style.display = "";
    empty.querySelector("p").textContent = "Loading published reports…";
    try {
      const raw = await this.api.get("/reports?status=PUBLISHED&limit=100");
      const reports = asArray(raw?.items).filter((report) =>
        isRecord(report) && safeId(report.id) &&
        (report.workspace_id === this.workspaceId || report.workspace_id === null),
      );
      if (this.currentRoute !== "reports") return;
      tbody.replaceChildren();
      reports.forEach((report) => {
        const row = node("tr", {
          dataset: { focused: report.id === focusId },
          attrs: { tabindex: report.id === focusId ? "-1" : undefined },
        });
        row.append(
          node("td", {}, node("strong", { text: asString(report.title, "Report") })),
          node("td", { text: asString(report.report_type, "Report") }),
          node("td", { text: formatDate(report.published_at || report.created_at) }),
          node("td", { text: asString(report.status, "PUBLISHED") }),
        );
        const actionCell = node("td");
        const download = node("button", { className: "btn btn-sm btn-primary", text: "Download", attrs: { type: "button" } });
        download.addEventListener("click", () => this.downloadReport(report.id));
        actionCell.appendChild(download);
        row.appendChild(actionCell);
        tbody.appendChild(row);
      });
      empty.style.display = reports.length ? "none" : "";
      empty.querySelector("p").textContent = reports.length
        ? ""
        : "No published reports in this workspace.";
      if (focusId && !reports.some((report) => report.id === focusId)) {
        empty.style.display = "";
        empty.querySelector("p").textContent = "The requested report is not available in this workspace.";
      }
      tbody.querySelector('[data-focused="true"]')?.focus();
    } catch (_) {
      empty.style.display = "";
      empty.replaceChildren(errorState("Reports unavailable", "Published reports could not be loaded.", () => this.renderReports(focusId)));
    }
  }

  async downloadReport(reportId) {
    if (!safeId(reportId)) return;
    const token = localStorage.getItem("gv_token");
    const response = await fetch(`${this.api.apiBase}/reports/${encodeURIComponent(reportId)}/download`, {
      headers: { Authorization: `Bearer ${token}`, "X-Workspace-ID": this.workspaceId },
    });
    if (!response.ok) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = node("a", { attrs: { href: url, download: `report-${reportId}.pdf` } });
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async renderOrders(focusId = null) {
    const container = document.getElementById("orders-container");
    if (!container) return;
    container.replaceChildren(node("p", { className: "portal-view-status", text: "Loading orders…" }));
    try {
      const raw = await this.api.get("/orders?limit=100");
      const orders = asArray(raw).filter((order) => isRecord(order) && safeId(order.id));
      if (this.currentRoute !== "orders") return;
      container.replaceChildren();
      if (!orders.length) {
        container.appendChild(emptyState("No orders", "There are no orders in this selected workspace."));
        return;
      }
      const list = node("div", { className: "portal-card-list" });
      orders.forEach((order) => {
        const card = node("article", {
          className: "card portal-item-card",
          dataset: { focused: order.id === focusId },
          attrs: { tabindex: order.id === focusId ? "-1" : undefined },
        });
        card.append(
          node("h3", { text: asString(order.order_number, `Order ${order.id.slice(0, 8)}`) }),
          node("p", { text: `${asString(order.fulfilment_status || order.status, "pending")} · ${asString(order.payment_status, "pending")}` }),
          node("p", { text: `${Number(order.item_count) || 0} items · ${formatMoney(order.total, order.currency)}` }),
          node("time", { text: formatDate(order.created_at), attrs: { datetime: order.created_at || "" } }),
        );
        const button = node("button", { className: "btn btn-secondary", text: "View details", attrs: { type: "button" } });
        button.addEventListener("click", () => this.openOrder(order.id));
        card.appendChild(button);
        list.appendChild(card);
      });
      container.appendChild(list);
      if (focusId) this.openOrder(focusId);
    } catch (_) {
      container.replaceChildren(errorState("Orders unavailable", "Workspace orders could not be loaded.", () => this.renderOrders(focusId)));
    }
  }

  async openOrder(orderId) {
    if (!safeId(orderId)) return;
    const modal = document.getElementById("order-modal");
    const content = document.getElementById("order-modal-content");
    if (!modal || !content) return;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    content.textContent = "Loading order…";
    try {
      const order = await this.api.get(`/orders/${encodeURIComponent(orderId)}`);
      if (!isRecord(order) || order.id !== orderId ||
        (order.workspace_id !== this.workspaceId && order.workspace_id !== null)) {
        throw new Error("Order scope mismatch");
      }
      const title = document.getElementById("order-modal-title");
      if (title) title.textContent = asString(order.order_number, "Order details");
      content.replaceChildren();
      content.append(
        node("p", { text: `Fulfilment: ${asString(order.fulfilment_status, "pending")}` }),
        node("p", { text: `Payment: ${asString(order.payment_status, "pending")}` }),
        node("p", { text: `Total: ${formatMoney(order.total, order.currency)}` }),
      );
      asArray(order.items).filter(isRecord).forEach((item) => {
        content.appendChild(node("div", { className: "portal-item-card", text: `${Number(item.quantity) || 0}× ${asString(item.name, "Item")} · ${formatMoney(item.line_total, item.currency || order.currency)}` }));
      });
    } catch (_) {
      content.replaceChildren(errorState("Order unavailable", "This order is not available in the selected workspace."));
    }
  }

  renderBilling() {
    const status = document.getElementById("billing-status");
    const content = document.getElementById("billing-content");
    if (!status || !content) return;
    status.textContent = "";
    content.hidden = false;
    const body = content.querySelector(".card-body");
    body.replaceChildren();
    const subscription = this.experience.subscription;
    body.append(
      node("h2", { className: "card-title", text: subscription.plan }),
      node("p", { className: "portal-kpi-context", text: `Status: ${subscription.status} · Tier: ${subscription.tier}` }),
      node("p", { className: "portal-kpi-context", text: subscription.validUntil ? `Valid until ${formatDate(subscription.validUntil)}` : "No expiry date supplied" }),
    );
  }

  renderTeam() {
    const status = document.getElementById("team-status");
    const content = document.getElementById("team-content");
    if (!status || !content) return;
    status.textContent = "";
    content.hidden = false;
    const body = content.querySelector(".card-body");
    body.replaceChildren(
      node("h2", { className: "card-title", text: "Customer organization access" }),
      node("p", { className: "portal-kpi-context", text: `Your active workspace role is ${this.experience.activeWorkspace.role}. Team membership changes remain scoped to ${this.experience.organizationName}.` }),
    );
  }

  renderIntegrations() {
    const status = document.getElementById("integrations-status");
    const content = document.getElementById("integrations-content");
    if (!status || !content) return;
    status.textContent = "";
    content.hidden = false;
    const body = content.querySelector(".card-body");
    body.replaceChildren(
      node("h2", { className: "card-title", text: "Workspace integrations" }),
      node("p", { className: "portal-kpi-context", text: "Only customer-safe integrations enabled by your plan appear here. Provider credentials and internal operations connections are never exposed." }),
    );
  }

  renderSettings() {
    const account = document.getElementById("settings-account");
    const role = document.getElementById("settings-role");
    if (account) account.value = this.experience.activeWorkspace.name;
    if (role) role.value = this.experience.activeWorkspace.role;
  }

  async refreshNotificationCount() {
    try {
      const raw = await this.api.get(`/notifications/unread-count?workspace_id=${encodeURIComponent(this.workspaceId)}`);
      const count = Math.max(0, Number(raw?.unread) || 0);
      const element = document.getElementById("notification-count");
      if (element) element.textContent = count > 99 ? "99+" : String(count);
      document.getElementById("btn-notifications")?.setAttribute("aria-label", `Open notifications, ${count} unread`);
    } catch (_) {
      const element = document.getElementById("notification-count");
      if (element) element.textContent = "0";
    }
  }

  ensureNotificationDialog() {
    let dialog = document.getElementById("portal-notification-dialog");
    if (dialog) return dialog;
    dialog = node("dialog", { id: "portal-notification-dialog", className: "modal", attrs: { "aria-labelledby": "portal-notification-title" } });
    const header = node("div", { className: "modal-header" });
    header.append(
      node("h2", { className: "modal-title", id: "portal-notification-title", text: "Notifications" }),
    );
    const close = node("button", { className: "modal-close", text: "×", attrs: { type: "button", "aria-label": "Close notifications" } });
    close.addEventListener("click", () => dialog.close());
    header.appendChild(close);
    dialog.append(header, node("div", { className: "modal-body", id: "portal-notification-list", attrs: { "aria-live": "polite" } }));
    document.body.appendChild(dialog);
    return dialog;
  }

  async openNotificationInbox() {
    const dialog = this.ensureNotificationDialog();
    const list = document.getElementById("portal-notification-list");
    list.textContent = "Loading notifications…";
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    try {
      const raw = await this.api.get(`/notifications?workspace_id=${encodeURIComponent(this.workspaceId)}&limit=20`);
      const items = asArray(raw?.items).filter((item) =>
        isRecord(item) && safeId(item.id) && item.workspace_id === this.workspaceId,
      );
      list.replaceChildren();
      if (!items.length) list.appendChild(emptyState("All caught up", "There are no notifications in this workspace."));
      items.forEach((item) => {
        const button = node("button", { className: "portal-item-card", attrs: { type: "button" } });
        button.append(
          node("h3", { text: asString(item.title, "Notification") }),
          node("p", { text: asString(item.body, "") }),
          node("time", { text: formatDate(item.last_occurred_at || item.created_at) }),
        );
        button.addEventListener("click", async () => {
          dialog.close?.();
          await this.resolveNotification(item.id);
        });
        list.appendChild(button);
      });
      const count = document.getElementById("notification-count");
      if (count) count.textContent = String(Math.max(0, Number(raw?.unread) || 0));
    } catch (_) {
      list.replaceChildren(errorState("Notifications unavailable", "The inbox could not be loaded.", () => this.openNotificationInbox()));
    }
  }

  async resolveNotification(notificationId) {
    if (!safeId(notificationId)) {
      this.navigate("overview", { replace: true });
      return;
    }
    try {
      const target = await this.api.get(`/notifications/${encodeURIComponent(notificationId)}/target`);
      if (!isRecord(target) || target.notification_id !== notificationId ||
        !TARGET_TYPES.has(target.target_type) || !safeId(target.target_id)) {
        throw new Error("Invalid notification target");
      }
      const pathTarget = safePortalPath(target.portal_path);
      if (!pathTarget || pathTarget.targetType !== target.target_type ||
        pathTarget.route !== TARGET_ROUTES[target.target_type] ||
        (pathTarget.targetId && pathTarget.targetId !== target.target_id)) {
        throw new Error("Unsafe notification path");
      }
      if (target.workspace_id && target.workspace_id !== this.workspaceId) {
        if (!safeId(target.workspace_id) || !this.experience.workspaces.some((item) => item.id === target.workspace_id)) {
          throw new Error("Notification workspace unavailable");
        }
        const raw = await this.api.get("/portal/experience", { workspaceId: target.workspace_id });
        this.applyExperience(normalizeExperience(raw));
        document.body.dataset.portalState = "ready";
      }
      if (!this.targetAllowed(target.target_type)) throw new Error("Target capability unavailable");
      this.navigate(TARGET_ROUTES[target.target_type], {
        targetType: target.target_type,
        targetId: target.target_id,
        replace: true,
      });
      this.api.post(`/notifications/${encodeURIComponent(notificationId)}/read`, {}).catch(() => {});
    } catch (_) {
      this.navigate("overview", { replace: true });
      const panel = document.getElementById("view-dashboard");
      panel?.prepend(errorState("Destination unavailable", "This notification target is not available in the selected customer workspace."));
    }
  }

  renderFatal() {
    document.body.dataset.portalState = "error";
    document.querySelector(".sidebar-nav")?.setAttribute("aria-busy", "false");
    document.querySelectorAll("[data-portal-group], [data-capability]").forEach((item) => { item.hidden = true; });
    const shellStatus = document.getElementById("portal-shell-status");
    if (shellStatus) shellStatus.hidden = true;
    const panel = document.getElementById("view-dashboard");
    document.querySelectorAll(".view-panel").forEach((item) => item.classList.remove("active"));
    if (!panel) return;
    panel.classList.add("active");
    panel.replaceChildren(errorState(
      "Customer portal unavailable",
      "We could not validate your workspace access. No contextual modules have been shown.",
      () => window.location.reload(),
    ));
  }
}

export function initCustomerPortal(options) {
  const portal = new CustomerPortal(options || {});
  portal.init();
  return portal;
}
