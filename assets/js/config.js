// assets/js/config.js

// This file is intentionally a plain script (not an ES module)
// so it can be included with a normal <script src="..."></script>
// in legacy pages. It exposes `window.API_BASE` for other scripts.

(function () {
	const LOCAL_DEFAULT = "http://127.0.0.1:8010";
	// Production backend URL (use direct Render URL until api.geovisionops.com SSL is ready)
	const PROD_DEFAULT = "https://geovisionops-sqknb.ondigitalocean.app";

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

	window.API_BASE =
		window.API_BASE ||
		(override && override.trim()) ||
		(isProduction ? PROD_DEFAULT : LOCAL_DEFAULT);
})();

