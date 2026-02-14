// assets/js/config.mjs
const LOCAL_DEFAULT = "http://127.0.0.1:8010";
// Production backend URL (use direct Render URL until api.geovisionops.com SSL is ready)
const PROD_DEFAULT = "https://geovision-backend-db2f.onrender.com";

const isProduction =
	typeof window !== "undefined" &&
	window.location &&
	window.location.hostname &&
	(window.location.hostname.endsWith("github.io") ||
	 window.location.hostname.endsWith("geovisionops.com"));

let override = null;
try {
	override = localStorage.getItem("gv_api_base");
} catch (e) {}

export const API_BASE = (override && override.trim()) || (isProduction ? PROD_DEFAULT : LOCAL_DEFAULT);
