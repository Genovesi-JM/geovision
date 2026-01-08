// assets/js/config.js

// This file is intentionally a plain script (not an ES module)
// so it can be included with a normal <script src="..."></script>
// in legacy pages. It exposes `window.API_BASE` for other scripts.

(function () {
	const LOCAL_DEFAULT = "http://127.0.0.1:8010";
	// Set your deployed backend URL here (must be HTTPS for GitHub Pages)
	const PROD_DEFAULT = "https://geovision-backend.onrender.com";

	const isGitHubPages =
		typeof window !== "undefined" &&
		window.location &&
		window.location.hostname &&
		window.location.hostname.endsWith("github.io");

	let override = null;
	try {
		override = localStorage.getItem("gv_api_base");
	} catch (e) {}

	window.API_BASE =
		window.API_BASE ||
		(override && override.trim()) ||
		(isGitHubPages ? PROD_DEFAULT : LOCAL_DEFAULT);
})();

