const { chromium } = require('playwright');
(async () => {
  const exe = process.env.CHROMIUM_EXE;
  const browser = await chromium.launch({ headless: process.env.HEADED !== '1', ...(exe ? { executablePath: exe } : {}) });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'en-US', viewport: { width: 1366, height: 900 },
  });
  const page = await ctx.newPage();
  const out = { steps: [] };
  try {
    await page.goto('https://publishers.adsterra.com/signup', { waitUntil: 'domcontentloaded', timeout: 60000 });
    for (let i = 0; i < 12; i++) {
      await page.waitForTimeout(5000);
      const t = await page.title();
      const inputs = await page.evaluate(() => document.querySelectorAll('input').length);
      out.steps.push(`${i}: title="${t}" inputs=${inputs} url=${page.url()}`);
      if (inputs > 1) { out.passed = true; break; }
    }
    out.finalUrl = page.url();
    out.title = await page.title();
    out.inputs = await page.evaluate(() => Array.from(document.querySelectorAll('input')).map(i => ({ name: i.name||i.id, type: i.type, placeholder: i.placeholder||'' })));
  } catch (e) { out.error = String(e).slice(0,400); }
  console.log(JSON.stringify(out));
  await browser.close();
})();
