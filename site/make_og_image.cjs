// Renders site/og-card.html to site/public/og-image.png (1200 x 630). Maintenance command, not part of the build.
const { chromium } = require('@playwright/test');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.resolve(__dirname, 'og-card.html'));
  await page.screenshot({ path: path.resolve(__dirname, 'public/og-image.png'), type: 'png' });
  await browser.close();
})();
