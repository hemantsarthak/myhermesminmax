const { chromium } = require('playwright');
(async () => {
  const exe = process.env.CHROMIUM_EXE;
  const browser = await chromium.launch({ headless: true, ...(exe ? { executablePath: exe } : {}) });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'en-US', viewport: { width: 1366, height: 900 },
  });
  const page = await ctx.newPage();
  const out = { steps: [], console: [], requests: [] };
  const log = (s) => out.steps.push(s);
  page.on('console', m => out.console.push(m.type() + ': ' + m.text().slice(0, 200)));
  page.on('pageerror', e => out.console.push('PAGEERROR: ' + String(e).slice(0, 200)));
  page.on('request', r => { if (r.method() !== 'GET') out.requests.push(r.method() + ' ' + r.url().slice(0, 200)); });
  page.on('response', async r => {
    if (r.request().method() !== 'GET') {
      let body = '';
      try { body = (await r.text()).slice(0, 600); } catch (e) { body = '<' + String(e).slice(0,80) + '>'; }
      out.requests.push('  RESP ' + r.status() + ' ' + r.url().slice(0, 160) + ' :: ' + body.replace(/\s+/g,' ').slice(0, 500));
    }
  });

  try {
    await page.goto('https://hilltopads.com/signup', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(6000);
    log('loaded ' + await page.title());

    // Dump the signup form HTML (the one with email input)
    const formHtml = await page.evaluate(() => {
      const f = Array.from(document.querySelectorAll('form')).find(x => x.querySelector('input[name="email"]'));
      if (!f) return 'NO FORM';
      return f.outerHTML.slice(0, 6000);
    });
    out.formHtml = formHtml;

    // All scripts on the page (to understand validation logic)
    out.scripts = await page.evaluate(() => Array.from(document.querySelectorAll('script[src]')).map(s => s.src).slice(0, 30));

    // Set role
    const roleSet = await page.evaluate(() => {
      const s = document.querySelector('select[name="who"]');
      if (!s) return 'no select';
      s.value = 'publisher';
      s.dispatchEvent(new Event('input', { bubbles: true }));
      s.dispatchEvent(new Event('change', { bubbles: true }));
      return 'who=' + s.value;
    });
    log('role: ' + roleSet);
    await page.waitForTimeout(2500);

    // dump form html again after role change
    out.formHtmlAfterRole = await page.evaluate(() => {
      const f = Array.from(document.querySelectorAll('form')).find(x => x.querySelector('input[name="email"]'));
      return f ? f.outerHTML.slice(0, 6000) : 'NO FORM';
    });

    console.log(JSON.stringify(out));
  } catch (e) { out.error = String(e).slice(0, 600); console.log(JSON.stringify(out)); }
  await browser.close();
})();
