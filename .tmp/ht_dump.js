const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const exe = process.env.CHROMIUM_EXE;
  const browser = await chromium.launch({ headless: true, ...(exe ? { executablePath: exe } : {}) });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'en-US', viewport: { width: 1366, height: 900 },
  });
  const page = await ctx.newPage();
  const out = { steps: [] };
  const log = (s) => out.steps.push(s);
  try {
    await page.goto('https://hilltopads.com/signup', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(6000);

    // Full form HTML -> file
    const formHtml = await page.evaluate(() => {
      const f = Array.from(document.querySelectorAll('form')).find(x => x.querySelector('input[name="email"]'));
      return f ? f.outerHTML : 'NO FORM';
    });
    fs.writeFileSync('.tmp/ht_form.html', formHtml);
    log('form html saved len=' + formHtml.length);

    // Grab the app JS for validation rules
    const jsUrls = await page.evaluate(() => Array.from(document.querySelectorAll('script[src]')).map(s => s.src).filter(u => u.includes('static.hilltopads.com')));
    for (const u of jsUrls) {
      try {
        const r = await ctx.request.get(u);
        const t = await r.text();
        fs.writeFileSync('.tmp/ht_main.js', t);
        log('main.js saved len=' + t.length + ' from ' + u);
      } catch (e) { log('js fetch fail ' + u + ' ' + String(e).slice(0,120)); }
    }
    console.log(JSON.stringify(out));
  } catch (e) { out.error = String(e).slice(0, 600); console.log(JSON.stringify(out)); }
  await browser.close();
})();
