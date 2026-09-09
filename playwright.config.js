// playwright.config.js
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: 'tests',
  timeout: 30 * 1000,
  expect: { timeout: 5000 },
  reporter: [['list']],
  webServer: [
    {
      command: 'bash scripts/start_e2e_backend.sh',
      url: 'http://127.0.0.1:8010/health',
      reuseExistingServer: true,
      timeout: 60 * 1000,
    },
    {
      command: 'python3 -m http.server 8001 --bind 127.0.0.1',
      url: 'http://127.0.0.1:8001/index.html',
      reuseExistingServer: true,
      timeout: 30 * 1000,
    },
  ],
  use: {
    headless: true,
    viewport: { width: 1280, height: 800 },
    actionTimeout: 5000,
    ignoreHTTPSErrors: true,
    trace: 'off'
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
