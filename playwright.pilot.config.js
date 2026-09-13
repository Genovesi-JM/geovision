// Fully intercepted pilot fixtures: never start a backend or load its .env.
const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: 'tests',
  testMatch: ['pilot-login-layout.spec.js', 'pilot-operations.spec.js'],
  timeout: 30000,
  expect: { timeout: 5000 },
  workers: 1,
  use: { headless: true, browserName: 'chromium', viewport: { width: 1280, height: 844 }, trace: 'off' },
});
