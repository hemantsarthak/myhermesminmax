const { chromium } = require('playwright');
const URLS = [
  'https://hilltopads.com/signup',
  'https://monetag.com/publishers',
  'https://www.nitropay.com/publishers',
];
(async () => {
  const exe = process.env.CHROMIUM_EXE;
  const browser = await chromium.launch({ headless: true, ...(exe ? { executablePath: exe } : {}) });
  const out = [];
  for (const u of URLS) {
    const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', locale: 'en-US' });
    const page = await ctx.newPage();
    const rec = { url: u };
    try {
      await page.goto(u, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(6000);
      rec.title = await page.title();
      rec.finalUrl = page.url();
      rec.inputs = await page.evaluate(() => Array.from(document.querySelectorAll('input')).map(i => ({ name: i.name||i.id||'', type: i.type||'', placeholder: (i.placeholder||'').slice(0,30) })).slice(0,25));
      rec.forms = await page.evaluate(() => Array.from(document.querySelectorAll('form')).map(f => f.action||'(same-page)').slice(0,8));
    } catch (e) { rec.error = String(e).slice(0,200); }
    out.push(rec);
    await ctx.close();
  }
  console.log(JSON.stringify(out));
  await browser.close();
})();
