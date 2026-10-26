"""Public static website only; no API proxy, credentials or database access."""
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.datastructures import URL
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

PUBLIC = Path(__file__).resolve().parent / "public"


async def health(request):
    return JSONResponse({"status": "ok", "service": "geovision-public-web"})


class SiteHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def secured(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"strict-transport-security", b"max-age=31536000"),
                ])
                path = scope.get("path", "")
                if path == "/" or path.endswith((".html", ".js", ".mjs", ".css")):
                    headers.append((b"cache-control", b"no-cache"))
                message["headers"] = headers
            await send(message)
        if scope["type"] == "http":
            url = URL(scope=scope)
            if url.hostname == "www.geovisionops.com":
                # OAuth returns to the apex origin. Keep the browser nonce and
                # sign-in session on that same origin from the first page load.
                response = RedirectResponse(
                    str(url.replace(scheme="https", netloc="geovisionops.com")),
                    status_code=308,
                )
                await response(scope, receive, secured)
                return
        await self.app(scope, receive, secured)


app = SiteHeaders(Starlette(routes=[
    Route("/_site/health", health),
    Mount("/", app=StaticFiles(directory=PUBLIC, html=True, follow_symlink=False)),
]))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")),
                proxy_headers=False, access_log=False)
