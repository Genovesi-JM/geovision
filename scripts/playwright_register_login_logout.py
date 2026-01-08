from playwright.sync_api import sync_playwright
import time, uuid

URL = "http://127.0.0.1:8001/login.html"


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        logs = []

        page.on("console", lambda msg: logs.append(("console", msg.type, msg.text)))
        page.on("pageerror", lambda err: logs.append(("pageerror", str(err))))
        page.on("request", lambda req: logs.append(("request", req.method, req.url)))
        page.on("response", lambda resp: logs.append(("response", resp.status, resp.url)))

        print(f"Opening {URL}")
        page.goto(URL)
        page.wait_for_timeout(800)

        # Create unique email
        unique = uuid.uuid4().hex[:8]
        email = f"test-{unique}@example.com"
        password = "Pwd12345!"

        # Open create form
        page.click('#show-create-btn')
        page.fill('#create-email', email)
        page.fill('#create-password', password)
        page.fill('#create-password-confirm', password)

        # Submit and wait for /auth/register
        try:
            with page.expect_response(lambda r: '/auth/register' in r.url, timeout=5000) as reg_info:
                page.click('#create-submit')
            reg_resp = reg_info.value
            try:
                reg_body = reg_resp.json()
            except Exception:
                reg_body = reg_resp.text()
            logs.append(('register-response', reg_resp.status, str(reg_body)[:200]))
        except Exception as e:
            logs.append(('register-error', str(e)))

        page.wait_for_timeout(600)

        # After register, navigate to login (in case redirected)
        page.goto(URL)
        page.wait_for_timeout(300)

        # Perform login with the created credentials
        page.fill('#login-email', email)
        page.fill('#login-password', password)
        try:
            with page.expect_response(lambda r: '/auth/login' in r.url, timeout=5000) as login_info:
                page.click('button[type=submit]')
            login_resp = login_info.value
            try:
                login_body = login_resp.json()
            except Exception:
                login_body = login_resp.text()
            logs.append(('login-response', login_resp.status, str(login_body)[:200]))
        except Exception as e:
            logs.append(('login-error', str(e)))

        page.wait_for_timeout(600)

        # Check localStorage for token
        try:
            token = page.evaluate("() => localStorage.getItem('gv_token')")
            user = page.evaluate("() => localStorage.getItem('gv_user')")
            logs.append(('localStorage', token is not None, token, user))
        except Exception as e:
            logs.append(('localStorage-error', str(e)))

        # Logout: clear localStorage and check
        page.evaluate("() => { localStorage.removeItem('gv_token'); localStorage.removeItem('gv_user'); }")
        page.wait_for_timeout(200)
        try:
            token_after = page.evaluate("() => localStorage.getItem('gv_token')")
            logs.append(('token-after-logout', token_after))
        except Exception as e:
            logs.append(('token-after-error', str(e)))

        print('\n=== Playwright register/login/logout logs ===')
        for item in logs:
            print(item)

        browser.close()


if __name__ == '__main__':
    run()
