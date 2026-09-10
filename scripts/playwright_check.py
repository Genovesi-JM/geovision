import os
import sys

URL = os.environ.get(
    "GEOVISION_SMOKE_URL",
    "http://127.0.0.1:8001/login.html",
).strip()


def run() -> int:
    email = os.environ.get("GEOVISION_SMOKE_EMAIL", "").strip()
    password = os.environ.get("GEOVISION_SMOKE_PASSWORD", "")
    if not email or not password:
        print(
            "GEOVISION_SMOKE_EMAIL and GEOVISION_SMOKE_PASSWORD are required.",
            file=sys.stderr,
        )
        return 2

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        logs = []

        def on_console(msg):
            try:
                logs.append(("console", msg.type, msg.text))
            except Exception:
                logs.append(("console", "unknown", str(msg)))

        def on_page_error(err):
            logs.append(("pageerror", str(err)))

        def on_request(req):
            logs.append(("request", req.method, req.url))

        def on_response(resp):
            try:
                logs.append(("response", resp.status, resp.url))
            except Exception:
                logs.append(("response", "err", str(resp)))

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("request", on_request)
        page.on("response", on_response)

        print(f"Opening {URL}")
        page.goto(URL)

        # wait briefly to let scripts run
        page.wait_for_timeout(1200)

        # check if login form has listener by dispatching submit and seeing console logs
        try:
            page.fill("#login-email", email)
            page.fill("#login-password", password)
            # wait for the auth POST response
            with page.expect_response(
                lambda r: "/auth/login" in r.url, timeout=5000
            ) as resp_info:
                page.click("button[type=submit]")
            resp = resp_info.value
            logs.append(("auth-response", resp.status, resp.url))
            page.wait_for_timeout(600)
        except Exception as e:
            logs.append(("error", f"interaction-failed: {e}"))
            browser.close()
            return 1

        # capture DOM state for feedback boxes (guard against navigation)
        try:
            success = page.query_selector("#success-box")
            error = page.query_selector("#error-box")
            s_text = success.inner_text() if success else ""
            e_text = error.inner_text() if error else ""
            nav_url = page.url
        except Exception as e:
            s_text = ""
            e_text = ""
            nav_url = page.url
            logs.append(("note", "navigation-detected-or-context-lost", str(e)))

        print("\n=== Console / Page Logs ===")
        for item in logs:
            print(item)

        print("\n=== Feedback boxes / navigation ===")
        print("page.url:", nav_url)
        print("success-box:", repr(s_text))
        print("error-box:", repr(e_text))

        browser.close()
        return 0 if resp.status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(run())
