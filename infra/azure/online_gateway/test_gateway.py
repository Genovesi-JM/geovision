"""Offline ASGI tests. Every upstream is mocked; files are synthetic temporary data."""
import asyncio
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import httpx


SPEC = importlib.util.spec_from_file_location("pilot_gateway", Path(__file__).with_name("gateway.py"))
gateway = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gateway)


def identity(oid=gateway.EXPECTED_OID, tenant=gateway.EXPECTED_TENANT, provider="aad", mapped=False):
    oid_name = "http://schemas.microsoft.com/identity/claims/objectidentifier" if mapped else "oid"
    tid_name = "http://schemas.microsoft.com/identity/claims/tenantid" if mapped else "tid"
    principal = {"auth_typ": provider, "claims": [{"typ": oid_name, "val": oid}, {"typ": tid_name, "val": tenant}]}
    return base64.b64encode(json.dumps(principal).encode()).decode()


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_only_public_provider_checks_are_routed(self):
        self.assertTrue(gateway.permitted("GET", "/operations/providers"))
        for provider in ("miteco", "copernicus"):
            self.assertTrue(gateway.permitted("POST", f"/operations/providers/{provider}/check"))
            self.assertFalse(gateway.permitted("GET", f"/operations/providers/{provider}/check"))
        for provider in ("stripe", "smtp", "azure_iot_hub", "../miteco", "%6diteco"):
            self.assertFalse(gateway.permitted("POST", f"/operations/providers/{provider}/check"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gv-gateway-offline-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.public = self.root / "public"
        (self.public / "assets/js").mkdir(parents=True)
        self.html = b"<!doctype html><html><head><script>window.synthetic=true;</script></head><body>synthetic</body></html>"
        (self.public / "login.html").write_bytes(self.html)
        (self.public / "assets/js/local.js").write_bytes(b"window.synthetic=true;")
        self.manifest = self.root / "manifest.json"
        self.write_manifest({
            "login.html": hashlib.sha256(self.html).hexdigest(),
            "assets/js/local.js": hashlib.sha256(b"window.synthetic=true;").hexdigest(),
        })
        self.environ = {
            "PUBLIC_ORIGIN": gateway.EXPECTED_ORIGIN,
            "ALLOWED_ENTRA_OID": gateway.EXPECTED_OID,
            "ALLOWED_ENTRA_TENANT": gateway.EXPECTED_TENANT,
        }
        self.now = 100.0
        self.calls = []
        self.upstream = lambda request: httpx.Response(200, json={"synthetic": True})

        def handler(request):
            self.calls.append(request)
            return self.upstream(request)

        self.transport = httpx.MockTransport(handler)
        self.app = self.make_app()

    def write_manifest(self, files):
        self.manifest.write_text(json.dumps({"files": files}))

    def make_app(self, **kwargs):
        return gateway.create_app(self.public, self.manifest, kwargs.get("environ", self.environ),
                                  self.transport, clock=lambda: self.now)

    async def request(self, path="/login.html", method="GET", headers=None, authenticated=True, app=None, **kwargs):
        default = {"x-ms-client-principal": identity()} if authenticated else {}
        default.update(headers or {})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app or self.app),
                                    base_url=gateway.EXPECTED_ORIGIN, follow_redirects=False) as client:
            return await client.request(method, path, headers=default, **kwargs)

    async def post(self, path="/auth/login", **kwargs):
        headers = {"origin": gateway.EXPECTED_ORIGIN, "content-type": "application/json", "x-geovision-client": "web"}
        headers.update(kwargs.pop("headers", {}))
        return await self.request(gateway.API_PREFIX + path, method="POST", headers=headers, content=kwargs.pop("content", b"{}"), **kwargs)

    async def test_health_only_anonymous_exception(self):
        response = await self.request("/_gateway/health", authenticated=False)
        self.assertEqual((response.status_code, response.json()), (200, {"status": "alive"}))
        for path in ("/", "/login.html", "/assets/js/local.js", "/_gateway/config.js", gateway.API_PREFIX + "/ready"):
            with self.subTest(path=path):
                self.assertEqual((await self.request(path, authenticated=False)).status_code, 401)
        self.assertEqual(self.calls, [])

    async def test_missing_config_fails_closed_including_probe(self):
        for name in self.environ:
            env = dict(self.environ)
            env.pop(name)
            app = self.make_app(environ=env)
            self.assertEqual((await self.request(app=app)).status_code, 503)
            self.assertEqual((await self.request("/_gateway/health", app=app, authenticated=False)).status_code, 503)

    async def test_mismatched_config_fails_closed(self):
        for name in self.environ:
            env = dict(self.environ, **{name: "different"})
            self.assertEqual((await self.request(app=self.make_app(environ=env))).status_code, 503)

    async def test_mapped_claims_accepted_without_email_authority(self):
        response = await self.request(headers={"x-ms-client-principal": identity(mapped=True), "x-ms-client-principal-name": "not-used@example.invalid"})
        self.assertEqual(response.status_code, 200)

    async def test_wrong_or_malformed_principal_denied(self):
        for encoded, status in ((identity(oid="other"), 403), (identity(tenant="other"), 403),
                                (identity(provider="google"), 401), ("invalid%%%", 401),
                                (base64.b64encode(b"[]").decode(), 401),
                                (base64.b64encode(b'{"auth_typ":"aad","claims":[]}').decode(), 403)):
            with self.subTest(status=status):
                self.assertEqual((await self.request(headers={"x-ms-client-principal": encoded})).status_code, status)
        self.assertEqual(self.calls, [])

    async def test_conflicting_principal_fields_denied(self):
        data = json.loads(base64.b64decode(identity()))
        data["claims"].append({"typ": "http://schemas.microsoft.com/identity/claims/objectidentifier", "val": "other"})
        conflict = base64.b64encode(json.dumps(data).encode()).decode()
        for headers in ({"x-ms-client-principal": conflict}, {"x-ms-client-principal-id": "other"}, {"x-ms-client-principal-idp": "google"}):
            self.assertEqual((await self.request(headers=headers)).status_code, 403)

    async def test_host_origin_and_fetch_site_guard(self):
        for headers in ({"host": "evil.invalid"}, {"origin": "https://evil.invalid"},
                        {"origin": "null"}, {"sec-fetch-site": "same-site"}, {"sec-fetch-site": "cross-site"}):
            self.assertEqual((await self.request(headers=headers)).status_code, 403)

    async def test_external_top_level_html_navigation_allowed_not_subresources_or_api(self):
        headers = {"origin": "https://external.invalid", "sec-fetch-site": "cross-site",
                   "sec-fetch-mode": "navigate", "sec-fetch-dest": "document"}
        self.assertEqual((await self.request("/login.html?return=/admin.html", headers=headers)).status_code, 200)
        for path in ("/assets/js/local.js", "/_gateway/config.js", gateway.API_PREFIX + "/ready"):
            self.assertEqual((await self.request(path, headers=headers)).status_code, 403)
        headers["sec-fetch-dest"] = "iframe"
        self.assertEqual((await self.request(headers=headers)).status_code, 403)

    async def test_static_allowlist_excludes_unlisted_and_dotfiles(self):
        (self.public / "unlisted.html").write_bytes(b"synthetic unlisted")
        (self.public / ".env").write_bytes(b"synthetic denied")
        for path in ("/unlisted.html", "/.env", "/assets/.env", "/manifest.json", "/gateway.py"):
            self.assertEqual((await self.request(path)).status_code, 404)

    async def test_manifest_path_escape_and_unknown_extensions_fail_closed(self):
        for name in ("../outside.html", "/login.html", "assets/.env", "assets/../login.html", "assets/code.py", "nested/page.html"):
            self.write_manifest({name: "0" * 64})
            self.assertEqual((await self.request(app=self.make_app())).status_code, 503)

    async def test_invalid_manifest_fails_closed(self):
        for data in (b"not-json", b"[]", b'{"files":{}}', b'{"files":{"login.html":"invalid"}}'):
            self.manifest.write_bytes(data)
            self.assertEqual((await self.request(app=self.make_app())).status_code, 503)

    async def test_static_integrity_rechecked_for_every_read(self):
        self.assertEqual((await self.request()).status_code, 200)
        (self.public / "login.html").write_bytes(b"changed after manifest")
        self.assertEqual((await self.request()).status_code, 503)

    async def test_unicode_and_space_asset_names_match_manifest_without_escape(self):
        name = "assets/js/Agro (São).js"
        payload = b"/* synthetic unicode named asset */"
        (self.public / name).write_bytes(payload)
        files = json.loads(self.manifest.read_text())["files"]
        files[name] = hashlib.sha256(payload).hexdigest()
        self.write_manifest(files)
        app = self.make_app()
        response = await self.request("/assets/js/Agro%20(S%C3%A3o).js", app=app)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, payload)
        self.assertEqual((await self.request("/assets%2Fjs/local.js", app=app)).status_code, 400)

    async def test_static_leaf_symlink_rejected(self):
        (self.root / "outside.html").write_bytes(self.html)
        (self.public / "login.html").unlink()
        (self.public / "login.html").symlink_to(self.root / "outside.html")
        self.assertEqual((await self.request()).status_code, 404)

    async def test_static_parent_symlink_rejected(self):
        (self.public / "assets/js/local.js").unlink()
        (self.public / "assets/js").rmdir()
        (self.root / "other").mkdir()
        (self.root / "other/local.js").write_bytes(b"window.synthetic=true;")
        (self.public / "assets/js").symlink_to(self.root / "other", target_is_directory=True)
        self.assertEqual((await self.request("/assets/js/local.js")).status_code, 404)

    async def test_manifest_symlink_rejected(self):
        data = self.manifest.read_bytes()
        self.manifest.unlink()
        (self.root / "other.json").write_bytes(data)
        self.manifest.symlink_to(self.root / "other.json")
        self.assertEqual((await self.request(app=self.make_app())).status_code, 503)

    async def test_security_headers_and_hashed_inline_scripts(self):
        response = await self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.html)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        policy = response.headers["content-security-policy"]
        digest = base64.b64encode(hashlib.sha256(b"window.synthetic=true;").digest()).decode()
        self.assertIn("'sha256-" + digest + "'", policy)
        self.assertIn("connect-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", policy)
        self.assertNotIn("https:", policy)

    async def test_runtime_config_protected_same_origin_and_no_credentials(self):
        response = await self.request("/_gateway/config.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/javascript", response.headers["content-type"])
        self.assertIn("credentials = 'same-origin'", response.text)
        self.assertIn("options.redirect = 'error'", response.text)
        self.assertNotIn(gateway.EXPECTED_OID, response.text)
        self.assertNotIn(gateway.API_ORIGIN, response.text)

    async def test_proxy_fixed_origin_and_only_application_authorization(self):
        response = await self.request(gateway.API_PREFIX + "/auth/me", headers={
            "x-geovision-authorization": "Bearer synthetic.jwt.token", "cookie": "edge_session=synthetic",
            "x-ms-token-aad-access-token": "synthetic-edge-token", "x-ms-client-principal-name": "person@example.invalid",
            "x-workspace-id": "workspace", "x-account-id": "account", "idempotency-key": "synthetic-id",
            "x-forwarded-host": "evil.invalid", "x-unapproved": "denied",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.calls), 1)
        upstream = self.calls[0]
        self.assertEqual(str(upstream.url), gateway.API_ORIGIN + "/auth/me")
        self.assertEqual(upstream.headers["authorization"], "Bearer synthetic.jwt.token")
        self.assertEqual(upstream.headers["x-workspace-id"], "workspace")
        for name in ("cookie", "x-ms-client-principal", "x-ms-token-aad-access-token", "x-geovision-authorization", "x-forwarded-host", "x-unapproved"):
            self.assertNotIn(name, upstream.headers)

    async def test_original_authorization_and_conflict_denied(self):
        for headers in ({"authorization": "Bearer synthetic"},
                        {"authorization": "Bearer edge", "x-geovision-authorization": "Bearer app"}):
            self.assertEqual((await self.request(gateway.API_PREFIX + "/me", headers=headers)).status_code, 400)
        self.assertEqual(self.calls, [])

    async def test_malformed_application_token_denied(self):
        for value in ("Basic synthetic", "Bearer", "Bearer has spaces", "Bearer one, Bearer two"):
            self.assertEqual((await self.request(gateway.API_PREFIX + "/me", headers={"x-geovision-authorization": value})).status_code, 400)

    async def test_readiness_warms_with_single_get_no_application_token(self):
        response = await self.request(gateway.API_PREFIX + "/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0].method, "GET")
        self.assertNotIn("authorization", self.calls[0].headers)
        self.assertEqual(self.calls[0].extensions["timeout"]["read"], 100.0)

    async def test_proxy_route_and_method_allowlist(self):
        for method, path in (("GET", "/admin/users"), ("POST", "/auth/register"), ("POST", "/auth/refresh"),
                             ("POST", "/auth/forgot-password"), ("DELETE", "/assets/abc"),
                             ("GET", "/auth/google"), ("PATCH", "/assets/abc"), ("OPTIONS", "/me"),
                             ("HEAD", "/health"), ("GET", "/contacts")):
            with self.subTest(method=method, path=path):
                self.assertEqual((await self.request(gateway.API_PREFIX + path, method=method)).status_code, 403)
        self.assertEqual(self.calls, [])

    async def test_unsafe_raw_paths_denied(self):
        for path in ("/_pilot/api/%61uth/me", "/_pilot/api/assets//abc", "/assets/%2e%2e/login.html"):
            self.assertEqual((await self.request(path)).status_code, 400)
        self.assertEqual(self.calls, [])

    async def test_post_requires_same_origin(self):
        for origin in (None, "https://evil.invalid", "null"):
            headers = {"content-type": "application/json", "x-geovision-client": "web"}
            if origin is not None:
                headers["origin"] = origin
            self.assertEqual((await self.request(gateway.API_PREFIX + "/auth/login", method="POST", headers=headers, content=b"{}")).status_code, 403)
        self.assertEqual(self.calls, [])

    async def test_login_web_client_required_even_with_query(self):
        for path in ("/auth/login", "/auth/login?example=1"):
            self.assertEqual((await self.post(path, headers={"x-geovision-client": "mobile"})).status_code, 403)
        self.assertEqual(self.calls, [])

    async def test_access_check_needs_identity_origin_and_empty_body_without_upstream(self):
        response = await self.post('/_access-check')
        self.assertEqual((response.status_code, response.json()), (200, {"status": "accepted"}))
        self.assertEqual(list(self.app.auth_attempts), [])
        self.assertEqual(self.calls, [])
        self.assertEqual((await self.post('/_access-check', authenticated=False)).status_code, 401)
        for origin in ('null', 'https://evil.invalid'):
            self.assertEqual((await self.post('/_access-check', headers={'origin': origin})).status_code, 403)
        self.assertEqual((await self.post('/_access-check', headers={'x-ms-client-principal': identity(oid='other')})).status_code, 403)
        self.assertEqual((await self.post('/_access-check', headers={'x-geovision-client': 'mobile'})).status_code, 403)
        self.assertEqual((await self.post('/_access-check', headers={'x-geovision-authorization': 'Bearer synthetic'})).status_code, 400)
        self.assertEqual((await self.post('/_access-check?unexpected=1')).status_code, 400)
        self.assertEqual((await self.post('/_access-check', content=b'{"password":"synthetic"}')).status_code, 400)
        self.assertEqual((await self.request(gateway.API_PREFIX + '/_access-check')).status_code, 403)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.app.auth_attempts), [])

    async def test_login_body_forwarded_once_without_credentials_in_logs(self):
        payload = b'{"email":"synthetic@example.invalid","password":"SYNTHETIC_NOT_REAL"}'
        with mock.patch("logging.Logger._log") as emitted:
            response = await self.post(content=payload)
        self.assertEqual([call for call in emitted.call_args_list if call[0][0] >= 30], [])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0].content, payload)

    async def test_post_media_type_strict(self):
        for value in ("text/plain", "application/json-malicious", "application/x-www-form-urlencoded"):
            self.assertEqual((await self.post(headers={"content-type": value})).status_code, 415)

    async def test_get_body_denied(self):
        self.assertEqual((await self.request(gateway.API_PREFIX + "/ready", content=b"body")).status_code, 400)
        self.assertEqual(self.calls, [])

    async def test_oversize_body_denied_before_upstream(self):
        self.assertEqual((await self.post(content=b"x" * (gateway.MAX_BODY + 1))).status_code, 413)
        self.assertEqual(self.calls, [])

    async def test_transfer_encoding_and_declared_length_mismatch_denied(self):
        self.assertEqual((await self.post(headers={"transfer-encoding": "chunked"})).status_code, 400)
        self.assertEqual((await self.post(headers={"content-length": "1"}, content=b"{}" )).status_code, 400)
        self.assertEqual(self.calls, [])

    async def test_duplicate_security_headers_denied(self):
        headers = [("x-ms-client-principal", identity()), ("x-ms-client-principal", identity())]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=gateway.EXPECTED_ORIGIN) as client:
            response = await client.get("/login.html", headers=headers)
        self.assertEqual(response.status_code, 400)

    async def test_auth_rate_limit_five_per_minute_and_bounded_state(self):
        for _ in range(5):
            self.assertEqual((await self.post()).status_code, 200)
        response = await self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(len(self.app.auth_attempts), 5)
        self.now += 61
        self.assertEqual((await self.post()).status_code, 200)
        self.assertEqual(len(self.app.auth_attempts), 1)

    async def test_invalid_identity_cannot_exhaust_authorized_rate_limit(self):
        for _ in range(6):
            self.assertEqual((await self.post(headers={"x-ms-client-principal": identity(oid="other")})).status_code, 403)
        self.assertEqual(len(self.app.auth_attempts), 0)
        self.assertEqual((await self.post()).status_code, 200)

    async def test_upstream_cookies_and_arbitrary_headers_not_forwarded(self):
        self.upstream = lambda request: httpx.Response(200, content=b"synthetic report", headers={
            "content-type": "application/pdf", "content-disposition": 'attachment; filename="synthetic.pdf"',
            "set-cookie": "backend=synthetic", "x-private": "synthetic", "access-control-allow-origin": "*",
        })
        response = await self.request(gateway.API_PREFIX + "/reports/abc/download")
        self.assertEqual(response.status_code, 200)
        self.assertIn("synthetic.pdf", response.headers["content-disposition"])
        for name in ("set-cookie", "x-private", "access-control-allow-origin"):
            self.assertNotIn(name, response.headers)

    async def test_redirects_denied_without_retry(self):
        self.upstream = lambda request: httpx.Response(302, headers={"location": "https://evil.invalid"})
        response = await self.post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("location", response.headers)

    async def test_upstream_errors_generic_no_retry(self):
        for status in (500, 502, 503):
            self.calls.clear()
            self.upstream = lambda request, status=status: httpx.Response(status, content=b"SYNTHETIC_PRIVATE_EXCEPTION")
            response = await self.post()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("SYNTHETIC_PRIVATE_EXCEPTION", response.text)
            self.assertEqual(len(self.calls), 1)

    async def test_network_failure_generic_no_retry(self):
        def fail(request):
            raise httpx.ConnectError("SYNTHETIC_PRIVATE_EXCEPTION", request=request)
        self.upstream = fail
        with mock.patch("logging.Logger._log") as emitted:
            response = await self.post()
        self.assertEqual([call for call in emitted.call_args_list if call[0][0] >= 30], [])
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("SYNTHETIC_PRIVATE_EXCEPTION", response.text)
        self.assertEqual(len(self.calls), 1)

    async def test_oversize_upstream_denied(self):
        self.upstream = lambda request: httpx.Response(200, content=b"x" * (gateway.MAX_RESPONSE + 1))
        response = await self.request(gateway.API_PREFIX + "/reports/abc/download")
        self.assertEqual(response.status_code, 502)
        self.assertLess(len(response.content), 200)

    async def test_upstream_requests_identity_encoding_not_browser_preference(self):
        response = await self.request(gateway.API_PREFIX + "/ready", headers={"accept-encoding": "gzip, br"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls[0].headers["accept-encoding"], "identity")

    async def test_unexpected_upstream_compression_rejected_before_reading(self):
        reads = []

        class UnreadStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                reads.append(True)
                yield b"must never be read or decoded"

        for encoding in ("gzip", "br", "deflate", "identity, gzip"):
            self.upstream = lambda request, encoding=encoding: httpx.Response(200, stream=UnreadStream(), headers={"content-encoding": encoding})
            response = await self.request(gateway.API_PREFIX + "/ready")
            self.assertEqual(response.status_code, 502)
        self.assertEqual(reads, [])

    async def test_authentication_rejection_preserved(self):
        self.upstream = lambda request: httpx.Response(401, json={"detail": "Synthetic invalid app session"})
        response = await self.request(gateway.API_PREFIX + "/auth/me", headers={"x-geovision-authorization": "Bearer invalid"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(len(self.calls), 1)

    async def test_write_route_payload_and_idempotency_preserved(self):
        path = "/assets/synthetic-asset/reports"
        response = await self.post(path, headers={"idempotency-key": "synthetic-request-id"}, content=b'{"synthetic":true}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls[0].headers["idempotency-key"], "synthetic-request-id")
        self.assertEqual(self.calls[0].content, b'{"synthetic":true}')


class PolicyTests(unittest.TestCase):
    def test_policy_rejects_destinations_and_traversal(self):
        for path in ("https://evil.invalid/me", "//evil.invalid/me", "/auth/%6de", "/assets/../me", "/assets//abc", "/me#fragment", "/me\r\nX: y"):
            self.assertFalse(gateway.permitted("GET", path))

    def test_positive_bounded_routes(self):
        for method, path in (("GET", "/auth/me"), ("GET", "/ready"), ("GET", "/admin/health"),
                             ("GET", "/assets/synthetic/agriculture/summary"),
                             ("POST", "/datasets/synthetic/upload"),
                             ("PUT", "/integration-connections/feature-flags/geovision.sectors.agriculture")):
            self.assertTrue(gateway.permitted(method, path))

    @unittest.skipUnless(shutil.which("node"), "Node optional; parent runs generated runtime JS separately")
    def test_actual_runtime_javascript_fetch_contract(self):
        # JavaScript is sent over stdin; no browser, filesystem or network calls.
        harness = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const script = JSON.parse(process.argv[1]);
const calls = [];
const origin = 'https://pilot.example.invalid';
const window = {location: {origin, href: origin + '/login.html'}, fetch: async (...args) => { calls.push(args); return {}; }};
const document = {documentElement: {dataset: {}}};
vm.runInNewContext(script, {window, document, Request, Headers, URL, Promise, TypeError, Object, String});
(async () => {
  await window.fetch(origin + '/_pilot/api/auth/me', {headers: {Authorization: 'Bearer synthetic'}, credentials: 'omit'});
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1].headers.get('Authorization'), null);
  assert.equal(calls[0][1].headers.get('X-GeoVision-Authorization'), 'Bearer synthetic');
  assert.equal(calls[0][1].credentials, 'same-origin');
  assert.equal(calls[0][1].redirect, 'error');
  assert.equal(calls[0][1].referrerPolicy, 'strict-origin');
  const req = new Request(origin + '/_pilot/api/assets', {method:'POST', headers:{Authorization:'Bearer request'}, body:'{}', credentials:'omit'});
  await window.fetch(req);
  assert.equal(calls[1][0], req);
  assert.equal(calls[1][1].headers.get('X-GeoVision-Authorization'), 'Bearer request');
  assert.equal(calls[1][1].credentials, 'same-origin');
  assert.equal(calls[1][1].referrerPolicy, 'strict-origin');
  const external = {headers:{Authorization:'Bearer external'}, credentials:'omit'};
  await window.fetch('https://other.invalid/_pilot/api/me', external);
  assert.equal(calls[2][1], external);
  assert.equal(calls[2][1].referrerPolicy, undefined);
  const nonApi = {credentials:'omit'};
  await window.fetch(origin + '/_pilot/api-malicious/me', nonApi);
  assert.equal(calls[3][1], nonApi);
  assert.equal(calls[3][1].referrerPolicy, undefined);
  await assert.rejects(window.fetch(origin + '/_pilot/api/me', {headers:{Authorization:'Bearer one','X-GeoVision-Authorization':'Bearer two'}}));
  assert.equal(calls.length, 4);
  assert.equal(window.API_BASE, origin + '/_pilot/api');
  assert.equal(window.GV_RUNTIME.mode, 'pilot');
  assert.equal(window.GV_RUNTIME.locale, 'es');
  assert.equal(document.documentElement.dataset.pilot, 'true');
  assert.equal(document.documentElement.lang, 'es');
  process.stdout.write('runtime fetch contract passed\n');
})().catch(() => {process.stderr.write('runtime contract failed\n');process.exit(1);});
"""
        result = subprocess.run([shutil.which("node"), "-e", harness, json.dumps(gateway.runtime_script())], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("runtime fetch contract passed", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
