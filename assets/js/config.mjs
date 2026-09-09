// assets/js/config.mjs
const LOCAL_DEFAULT = "http://127.0.0.1:8010";
// Stable production API origin shared by every supported client.
const PROD_DEFAULT = "https://api.geovisionops.com";

const isProduction =
	typeof window !== "undefined" &&
	window.location &&
	window.location.hostname &&
	(window.location.hostname.endsWith("github.io") ||
	 window.location.hostname.endsWith("geovisionops.com"));

export const API_BASE = isProduction ? PROD_DEFAULT : LOCAL_DEFAULT;
