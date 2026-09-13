const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: '.', testMatch: ['pilot-login-layout.spec.js', 'pilot-operations.spec.js'], timeout: 20000,
  workers: 1, reporter: [['list']],
  use: { headless: true, browserName: 'chromium', trace: 'off', actionTimeout: 5000 },
});
