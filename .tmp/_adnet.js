
const { chromium } = require('playwright');
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
    await page.goto("https://hilltopads.com/signup", { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(5000);
    log('loaded ' + await page.title());

    // The form's real controls are hidden and styled: <select name="who">,
    // <select name="im[key]">, <input type=checkbox name="legal">. The page
    // has JS validators that read them, so set the value and dispatch the
    // events those validators listen for. Clicking the styled dropdown does
    // not work because the native select is display:none.
    const roleSet = await page.evaluate(() => {
      const s = document.querySelector('select[name="who"]');
      if (!s) return 'no select';
      s.value = 'publisher';
      s.dispatchEvent(new Event('input', { bubbles: true }));
      s.dispatchEvent(new Event('change', { bubbles: true }));
      return 'who=' + s.value;
    });
    log('role: ' + roleSet);
    await page.waitForTimeout(2000);

    const imSet = await page.evaluate(() => {
      const s = document.querySelector('select[name="im[key]"]');
      if (!s) return 'no im select';
      s.value = 'telegraph';
      s.dispatchEvent(new Event('input', { bubbles: true }));
      s.dispatchEvent(new Event('change', { bubbles: true }));
      const t = document.querySelector('input[name="im[value]"]');
      if (t) {
        t.value = 'tekify.media';
        t.dispatchEvent(new Event('input', { bubbles: true }));
        t.dispatchEvent(new Event('change', { bubbles: true }));
      }
      return 'im=' + s.value;
    });
    log('messenger: ' + imSet);

    // Fill the visible fields of the main signup form.
    const filled = [];
    async function setField(selector, value) {
      const el = page.locator(selector).first();
      if (await el.count() === 0) return false;
      try {
        await el.fill(value, { timeout: 8000 });
        filled.push(selector);
        return true;
      } catch (e) { return false; }
    }
    await setField('input[name="name"]:visible', "Tekify Media");
    await setField('input[name="email"]:visible', "mmaxadsterra1792657770@maxxspace.com");
    await setField('input[name="password"]:visible', "Ht58450zQ9");
    log('filled: ' + filled.join(', '));

    // Tick the legal checkbox through its styled label (the input is hidden).
    const legalSet = await page.evaluate(() => {
      const c = document.querySelector('input[name="legal"]');
      if (!c) return 'no legal input';
      if (!c.checked) {
        c.checked = true;
        c.dispatchEvent(new Event('input', { bubbles: true }));
        c.dispatchEvent(new Event('change', { bubbles: true }));
      }
      return 'legal=' + c.checked;
    });
    log('legal: ' + legalSet);
    await page.waitForTimeout(600);

    // Submit the form that contains the email field. Must click the real
    // submit control, not call form.submit() directly — the CSRF token is
    // bound by JS and a direct submit() posts a stale token ("Invalid CSRF
    // protection token").
    const res = await page.evaluate(() => {
      const f = Array.from(document.querySelectorAll('form'))
        .find(x => x.querySelector('input[name="email"]'));
      if (!f) return 'no form found';
      const btn = Array.from(f.querySelectorAll('button[type="submit"], input[type="submit"], button'))
        .find(x => (x.offsetWidth || x.offsetHeight) && !(x.type === 'button'));
      if (btn) { btn.click(); return 'clicked: ' + (btn.innerText || btn.value || btn.type); }
      return 'no submit button';
    });
    log('submitted via ' + res);
    await page.waitForTimeout(10000);
    out.url = page.url();
    out.title = await page.title();
    out.bodyText = (await page.evaluate(() => document.body.innerText)).slice(0, 1800);
  } catch (e) { out.error = String(e).slice(0, 600); }
  console.log(JSON.stringify(out));
  await browser.close();
})();
