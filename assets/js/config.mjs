// assets/js/config.mjs
const LOCAL_DEFAULT = "http://127.0.0.1:8010";
const PROD_DEFAULT = "https://geovision-backend-db2f.onrender.com";

const isGitHubPages =
	typeof window !== "undefined" &&
	window.location &&
	window.location.hostname &&
	window.location.hostname.endsWith("github.io");

let override = null;
try {
	override = localStorage.getItem("gv_api_base");
} catch (e) {}

export const API_BASE = (override && override.trim()) || (isGitHubPages ? PROD_DEFAULT : LOCAL_DEFAULT);
