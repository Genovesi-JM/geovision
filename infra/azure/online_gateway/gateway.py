"""Restricted pilot gateway; deploy only behind verified Azure Easy Auth.

Identity headers are trustworthy only at that platform boundary. This process
does not verify Entra tokens and must never have a direct public TCP ingress.
It has no backend settings, service tokens, database access, or Azure SDK calls.
"""
import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import stat
import time
from collections import deque
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


EXPECTED_ORIGIN = "https://geovision-pilot-web-hcwka3w.nicepebble-b3698140.spaincentral.azurecontainerapps.io"
EXPECTED_OID = "883982a0-4de1-4549-be63-f9f5ded611dd"
EXPECTED_TENANT = "69f1c4f2-ab5f-4267-b68b-10c033e56613"
API_ORIGIN = "https://geovision-pilot-hcwka3w-api.internal.nicepebble-b3698140.spaincentral.azurecontainerapps.io"
API_PREFIX = "/_pilot/api"
MAX_BODY = 2 * 1024 * 1024
MAX_RESPONSE = 8 * 1024 * 1024
MAX_STATIC = 64 * 1024 * 1024
MAX_MANIFEST = 4 * 1024 * 1024
FORWARDED_HEADERS = {
    "accept", "content-type", "x-workspace-id", "x-account-id",
    "x-geovision-client", "idempotency-key",
}
GET_ROUTES = (
    r"/(health|ready|me)", r"/auth/me", r"/accounts/?",
    r"/organizations(?:/[A-Za-z0-9-]+(?:/workspaces)?)?/?",
    r"/admin/(health|companies)",
    r"/operations/(experience|dashboard|queues|jobs|contractors)",
    r"/(orders|missions)/internal", r"/internal/economics/location-usage/summary",
    r"/assets(?:/[A-Za-z0-9-]+(?:/(agriculture/(capabilities|summary)|reports))?)?/?",
    r"/datasets(?:/[A-Za-z0-9-]+)?/?", r"/reports(?:/[A-Za-z0-9-]+(?:/download)?)?/?",
)
POST_ROUTES = (
    r"/_access-check", r"/auth/(login|logout)", r"/organizations/?", r"/assets/?", r"/datasets/?",
    r"/datasets/[A-Za-z0-9-]+/(upload|finalize)",
    r"/assets/[A-Za-z0-9-]+/agriculture/evaluate",
    r"/assets/[A-Za-z0-9-]+/reports/?",
)
PUT_ROUTES = (r"/integration-connections/feature-flags/geovision\.sectors\.[a-z_]+",)
STATIC_EXTENSIONS = {
    ".html", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp",
    ".gif", ".ico", ".avif", ".woff", ".woff2", ".ttf", ".otf",
    ".json", ".webmanifest", ".mp4", ".webm",
}
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
}


class Denied(Exception):
    def __init__(self, status=403):
        self.status = status


def require(condition, status=403):
    if not condition:
        raise Denied(status)


def safe_path(path):
    return (
        isinstance(path, str) and path.startswith("/") and len(path) <= 4096
        and not any(ord(char) < 32 or ord(char) == 127 for char in path)
        and not any(char in path for char in ("%", "\\", "?", "#"))
        and "//" not in path
        and all(part not in (".", "..") for part in path.split("/"))
    )


def permitted(method, target):
    try:
        parsed = urlsplit(target)
    except ValueError:
        return False
    if (parsed.scheme or parsed.netloc or parsed.fragment or len(target) > 4096
            or not safe_path(parsed.path)
            or any(ord(char) < 32 or ord(char) == 127 for char in target)
            or "\\" in target):
        return False
    patterns = GET_ROUTES if method == "GET" else POST_ROUTES if method == "POST" else PUT_ROUTES if method == "PUT" else ()
    return any(re.fullmatch(pattern, parsed.path) for pattern in patterns)


def static_name(name):
    parts = name.split("/") if isinstance(name, str) else []
    return (
        bool(parts) and not name.startswith("/")
        and all(part and not part.startswith(".") and not any(char in part for char in ("\\", "?", "#", "%"))
                and not any(ord(char) < 32 or ord(char) == 127 for char in part) for part in parts)
        and Path(name).suffix.lower() in STATIC_EXTENSIONS
        and ((len(parts) == 1 and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.html", name))
             or (len(parts) > 1 and parts[0] == "assets"))
    )


def read_regular(root, name, limit):
    """Open each component without following symlinks, including after startup."""
    parts = name.split("/")
    require(all(part and part not in (".", "..") for part in parts), 404)
    directory = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    leaf = None
    try:
        for part in parts[:-1]:
            next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(leaf)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, 404)
        chunks, count = [], 0
        while True:
            chunk = os.read(leaf, min(65536, limit + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            require(count <= limit, 404)
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        if leaf is not None:
            os.close(leaf)
        os.close(directory)


def content_security_policy(body=b"", html=False):
    # Existing local inline scripts are authorized by their exact bytes, not by
    # unsafe-inline. Event-handler attributes and external code remain blocked.
    hashes = []
    if html:
        for match in re.finditer(rb"<script\b[^>]*>(.*?)</script\s*>", body, re.I | re.S):
            if match.group(1).strip():
                digest = base64.b64encode(hashlib.sha256(match.group(1)).digest()).decode("ascii")
                hashes.append("'sha256-" + digest + "'")
    return (
        "default-src 'none'; script-src 'self' " + " ".join(sorted(set(hashes))) + "; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
        "connect-src 'self'; media-src 'self' blob:; worker-src 'none'; frame-src 'none'; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )


def secured(response, html=False):
    response.headers.update(SECURITY_HEADERS)
    response.headers["Content-Security-Policy"] = content_security_policy(response.body, html)
    return response


def error_response(status):
    detail = "Servicio temporalmente no disponible. Inténtalo de nuevo más tarde." if status >= 500 else (
        "Demasiados intentos. Espera un minuto antes de intentarlo de nuevo." if status == 429
        else "Solicitud no permitida."
    )
    response = secured(JSONResponse({"detail": detail}, status_code=status))
    if status == 429:
        response.headers["Retry-After"] = "60"
    return response


def principal_id(headers):
    encoded = headers.get("x-ms-client-principal", "")
    require(0 < len(encoded) <= 32768, 401)
    try:
        principal = json.loads(base64.b64decode(encoded, validate=True))
    except (ValueError, TypeError, UnicodeError):
        raise Denied(401) from None
    require(isinstance(principal, dict) and principal.get("auth_typ") == "aad", 401)
    claims = principal.get("claims")
    require(isinstance(claims, list) and len(claims) <= 200, 401)
    require(all(isinstance(item, dict) and isinstance(item.get("typ"), str) and isinstance(item.get("val"), str) for item in claims), 401)
    oid_types = {"oid", "http://schemas.microsoft.com/identity/claims/objectidentifier"}
    tid_types = {"tid", "http://schemas.microsoft.com/identity/claims/tenantid"}
    oids = [item["val"] for item in claims if item["typ"] in oid_types]
    tenants = [item["val"] for item in claims if item["typ"] in tid_types]
    require(bool(oids) and all(value == EXPECTED_OID for value in oids), 403)
    require(bool(tenants) and all(value == EXPECTED_TENANT for value in tenants), 403)
    require(headers.get("x-ms-client-principal-id", EXPECTED_OID) == EXPECTED_OID, 403)
    require(headers.get("x-ms-client-principal-idp", "aad") == "aad", 403)
    return EXPECTED_OID


def runtime_script():
    return r"""/* Protected GeoVision pilot: no credentials are embedded here. */
(function () {
  'use strict';
  const origin = window.location.origin;
  const prefix = '/_pilot/api';
  window.GV_RUNTIME = Object.freeze({mode: 'pilot', locale: 'es', country: 'ES'});
  window.API_BASE = origin + prefix;
  document.documentElement.dataset.pilot = 'true';
  document.documentElement.lang = 'es';
  const nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    let url;
    try { url = new URL(input instanceof Request ? input.url : String(input), window.location.href); }
    catch (_) { return nativeFetch(input, init); }
    if (url.origin !== origin || !(url.pathname === prefix || url.pathname.startsWith(prefix + '/'))) {
      return nativeFetch(input, init);
    }
    const options = Object.assign({}, init || {});
    const headers = new Headers(options.headers !== undefined ? options.headers : (input instanceof Request ? input.headers : undefined));
    if (headers.has('Authorization') && headers.has('X-GeoVision-Authorization')) {
      return Promise.reject(new TypeError('Conflicting authentication headers.'));
    }
    if (headers.has('Authorization')) {
      headers.set('X-GeoVision-Authorization', headers.get('Authorization'));
      headers.delete('Authorization');
    }
    options.headers = headers;
    options.credentials = 'same-origin';
    options.redirect = 'error';
    options.cache = 'no-store';
    // Preserve origin-only Referer for cookie-authenticated POST compatibility.
    // Send only our origin on these same-origin API calls, never a page path
    // or query. Keep the document's no-referrer policy for all other requests.
    options.referrerPolicy = 'strict-origin';
    return nativeFetch(input, options);
  };
}());
"""


class Gateway:
    def __init__(self, public_dir, manifest_path, environ, transport=None, clock=time.monotonic):
        self.public_dir = Path(public_dir)
        self.transport = transport
        self.clock = clock
        # Only this exact user is authorized, so one bounded deque is also the
        # per-principal limiter. No user-controlled identifiers grow a map.
        self.auth_attempts = deque(maxlen=5)
        self.files = {}
        self.configured = (
            environ.get("PUBLIC_ORIGIN") == EXPECTED_ORIGIN
            and environ.get("ALLOWED_ENTRA_OID") == EXPECTED_OID
            and environ.get("ALLOWED_ENTRA_TENANT") == EXPECTED_TENANT
        )
        try:
            path = Path(manifest_path)
            manifest = json.loads(read_regular(path.parent, path.name, MAX_MANIFEST))
            require(isinstance(manifest, dict) and set(manifest) == {"files"})
            files = manifest["files"]
            require(isinstance(files, dict) and 0 < len(files) <= 10000)
            require(all(static_name(name) and isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest) for name, digest in files.items()))
            self.files = files
        except Exception:
            self.configured = False

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        try:
            response, html = await self.handle(Request(scope, receive))
            response = secured(response, html)
        except Denied as denied:
            response = error_response(denied.status)
        except asyncio.TimeoutError:
            response = error_response(504)
        except Exception:
            # Do not expose exception details or log paths, cookies or bodies.
            response = error_response(503)
        await response(scope, receive, send)

    async def handle(self, request):
        raw_path = request.scope.get("raw_path", b"").decode("ascii", errors="strict")
        if raw_path == "/_gateway/health" and not request.scope.get("query_string"):
            require(request.method == "GET", 405)
            require(self.configured, 503)
            return JSONResponse({"status": "alive"}), False
        require(self.configured, 503)
        require(len(raw_path) <= 4096 and not re.search(r"%(?:2f|5c)", raw_path, re.I), 400)
        path = unquote(raw_path, encoding="utf-8", errors="strict")
        require(safe_path(path), 400)
        require(request.scope.get("path") == path, 400)
        raw_headers = request.scope.get("headers", [])
        require(len(raw_headers) <= 100 and sum(len(k) + len(v) for k, v in raw_headers) <= 65536, 400)
        keys = [key.lower() for key, _ in raw_headers]
        require(len(keys) == len(set(keys)), 400)
        require(all(len(value) <= (32768 if key.lower() == b"x-ms-client-principal" else 12000)
                    and b"\r" not in value and b"\n" not in value and b"\x00" not in value for key, value in raw_headers), 400)
        require(request.headers.get("host") == urlsplit(EXPECTED_ORIGIN).netloc, 403)
        require("transfer-encoding" not in request.headers, 400)
        principal_id(request.headers)
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site")
        is_api = path == API_PREFIX or path.startswith(API_PREFIX + "/")
        # External links may navigate to a protected HTML document; this never
        # relaxes API/config/subresource CSRF checks or the Entra identity gate.
        top_navigation = (
            not is_api and request.method == "GET" and (path.endswith(".html") or path == "/")
            and request.headers.get("sec-fetch-mode") == "navigate"
            and request.headers.get("sec-fetch-dest") == "document"
        )
        require(top_navigation or origin in (None, EXPECTED_ORIGIN), 403)
        require(top_navigation or fetch_site in (None, "none", "same-origin"), 403)
        if is_api:
            require(raw_path == path and "%" not in raw_path, 400)
            query = request.scope.get("query_string", b"").decode("ascii", errors="strict")
            target = raw_path[len(API_PREFIX):] + ("?" + query if query else "")
            require(permitted(request.method, target), 403)
            require("authorization" not in request.headers, 400)
            headers = {key: request.headers[key] for key in FORWARDED_HEADERS if key in request.headers}
            app_auth = request.headers.get("x-geovision-authorization")
            if app_auth is not None:
                require(bool(re.fullmatch(r"Bearer [A-Za-z0-9._~+/-]+={0,2}", app_auth)), 400)
                headers["authorization"] = app_auth
            if request.method != "GET":
                require(origin == EXPECTED_ORIGIN and fetch_site in (None, "same-origin"), 403)
                media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
                require(media_type in ("application/json", "multipart/form-data"), 415)
            api_path = urlsplit(target).path
            if api_path == "/_access-check":
                # Exercise the real Microsoft/browser POST boundary before
                # credentials are submitted. No upstream call or login attempt.
                require(not query and app_auth is None, 400)
                require(headers.get("x-geovision-client") == "web", 403)
                body = await asyncio.wait_for(self.read_body(request), timeout=15)
                require(body == b"{}", 400)
                return JSONResponse({"status": "accepted"}), False
            if api_path == "/auth/login":
                require(headers.get("x-geovision-client") == "web", 403)
            if request.method == "POST" and api_path in ("/auth/login", "/auth/logout"):
                now = self.clock()
                while self.auth_attempts and now - self.auth_attempts[0] >= 60:
                    self.auth_attempts.popleft()
                require(len(self.auth_attempts) < 5, 429)
                self.auth_attempts.append(now)
            body = await asyncio.wait_for(self.read_body(request), timeout=15)
            require(request.method != "GET" or not body, 400)
            # One attempt only. A readiness GET may wait through scale-to-zero
            # startup; neither a failed GET nor a mutation is retried here.
            return await asyncio.wait_for(self.forward(request.method, target, headers, body), timeout=105), False
        require(request.method == "GET", 405)
        require(not request.headers.get("content-length") or request.headers["content-length"] == "0", 400)
        if path == "/_gateway/config.js":
            require(raw_path == path, 400)
            return Response(runtime_script(), media_type="application/javascript"), False
        name = "login.html" if path == "/" else path[1:]
        require(name in self.files and static_name(name), 404)
        try:
            body = read_regular(self.public_dir, name, MAX_STATIC)
        except (OSError, Denied):
            raise Denied(404) from None
        require(hashlib.sha256(body).hexdigest() == self.files[name], 503)
        media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return Response(body, media_type=media_type), name.endswith(".html")

    async def read_body(self, request):
        length = request.headers.get("content-length")
        if length is not None:
            require(bool(re.fullmatch(r"[0-9]{1,10}", length)) and int(length) <= MAX_BODY, 413)
        chunks, count = [], 0
        async for chunk in request.stream():
            count += len(chunk)
            require(count <= MAX_BODY, 413)
            chunks.append(chunk)
        if length is not None:
            require(count == int(length), 400)
        return b"".join(chunks)

    async def forward(self, method, target, headers, body):
        async with httpx.AsyncClient(
            transport=self.transport, trust_env=False, follow_redirects=False,
            timeout=httpx.Timeout(100.0, connect=10.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=0),
        ) as client:
            # Do not let a compressed stream allocate an unbounded decompressed
            # chunk before the response-size guard. The browser cannot override
            # this header because it is not in FORWARDED_HEADERS.
            outbound_headers = dict(headers, **{"accept-encoding": "identity"})
            async with client.stream(method, API_ORIGIN + target, headers=outbound_headers, content=body) as upstream:
                require(not 300 <= upstream.status_code < 400, 502)
                require(upstream.status_code < 500, 503)
                require(upstream.headers.get("content-encoding", "identity").strip().lower() == "identity", 502)
                chunks, count = [], 0
                async for chunk in upstream.aiter_bytes():
                    count += len(chunk)
                    require(count <= MAX_RESPONSE, 502)
                    chunks.append(chunk)
                selected = {key: upstream.headers[key] for key in ("content-type", "content-disposition") if key in upstream.headers}
                require(all(len(value) < 1000 and not any(c in value for c in ("\r", "\n", "\x00")) for value in selected.values()), 502)
                return Response(b"".join(chunks), status_code=upstream.status_code, headers=selected)


def create_app(public_dir=Path("/gateway/public"), manifest_path=Path("/gateway/manifest.json"), environ=None, transport=None, clock=time.monotonic):
    return Gateway(public_dir, manifest_path, os.environ if environ is None else environ, transport, clock)


app = create_app()


if __name__ == "__main__":
    import uvicorn
    logging.disable(logging.CRITICAL)
    uvicorn.run(app, host="0.0.0.0", port=8080, access_log=False, proxy_headers=False,
                server_header=False, date_header=False, log_level="critical")
