
const { chromium } = require('playwright');
(async () => {
  const exe = process.env.CHROMIUM_EXE;
  const browser = await chromium.launch({ headless: true, ...(exe ? { executablePath: exe } : {}) });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'en-US',
  });
  const page = await ctx.newPage();
  const out = { url: '', title: '', fields: [], selects: [], buttons: [], text: '' };
  try {
    await page.goto('https://publishers.adsterra.com/signup', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(4000);
    out.url = page.url();
    out.title = await page.title();
    out.fields = await page.evaluate(() => Array.from(document.querySelectorAll('input')).map(i => ({
      name: i.name || i.id || '', type: i.type || '', placeholder: i.placeholder || '',
      required: i.required, value: i.type === 'password' ? '' : (i.value || '')
    })));
    out.selects = await page.evaluate(() => Array.from(document.querySelectorAll('select')).map(s => ({
      name: s.name || s.id || '',
      options: Array.from(s.options).map(o => ({ v: o.value, t: (o.textContent||'').trim() })).slice(0, 60)
    })));
    out.buttons = await page.evaluate(() => Array.from(document.querySelectorAll('button, input[type=submit]')).map(b => ({
      tag: b.tagName, text: (b.textContent||b.value||'').trim().slice(0,60), type: b.type||''
    })));
    out.text = (await page.evaluate(() => document.body.innerText)).slice(0, 1500);
  } catch (e) {
    out.error = String(e).slice(0, 500);
  }
  console.log(JSON.stringify(out));
  await browser.close();
})();
