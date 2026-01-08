#!/usr/bin/env python3
"""
Lightweight Playwright + axe-core smoke check (Python).

Runs headless Chromium, navigates to /login.html, submits demo creds,
waits for #success-box, injects axe-core from CDN and runs accessibility checks.

Run inside the project's backend venv: backend/.venv/bin/python backend/playwright_login_a11y.py
Make sure a static server is running that serves the repo root at http://127.0.0.1:8001
Example: (in another terminal)
  python3 -m http.server 8001 --bind 127.0.0.1

Exit code: 0 = success (no violations), 2 = axe violations found, 1 = other error.
"""
import sys
import json
import urllib.request
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.6.3/axe.min.js"
TARGET = "http://127.0.0.1:8001/login.html"


def run_check():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"Opening {TARGET}")
        page.goto(TARGET, wait_until="domcontentloaded")

        # Fill form and submit
        page.fill('#login-email', 'teste@admin.com')
        page.fill('#login-password', '123456')
        page.click('button[type=submit]')

        try:
            page.wait_for_selector('#success-box', timeout=7000)
            print('Success box appeared')
        except PlaywrightTimeout:
            print('Timed out waiting for success box', file=sys.stderr)
            browser.close()
            return 1

        # inject axe-core
        print('Downloading axe-core...')
        try:
            axe_js = urllib.request.urlopen(AXE_URL).read().decode('utf-8')
        except Exception as e:
            print('Failed to download axe-core:', e, file=sys.stderr)
            browser.close()
            return 1

        page.add_script_tag(content=axe_js)
        print('Running axe...')
        result = page.evaluate('''async () => {
            return await axe.run();
        }''')

        print(json.dumps(result, indent=2))
        violations = result.get('violations', [])
        browser.close()
        if violations:
            print(f"Found {len(violations)} accessibility violations", file=sys.stderr)
            return 2
        print('No accessibility violations found (axe).')
        return 0


if __name__ == '__main__':
    rc = run_check()
    sys.exit(rc)
