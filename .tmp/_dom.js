const { chromium } = require('playwright');
(async () => {
  const exe = process.env.CHROMIUM_EXE;
  const browser = await chromium.launch({ headless: true, ...(exe ? { executablePath: exe } : {}) });
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36', viewport:{width:1366,height:900} });
  const page = await ctx.newPage();
  await page.goto('https://hilltopads.com/signup', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(6000);
  const out = await page.evaluate(() => {
    const res = { selects: [], checkboxes: [], comboboxes: [] };
    res.selects = Array.from(document.querySelectorAll('select')).map(s => ({
      name: s.name||s.id, visible: !!(s.offsetWidth||s.offsetHeight),
      opts: Array.from(s.options).map(o=>o.value+'|'+o.textContent.trim()).slice(0,20)
    }));
    res.checkboxes = Array.from(document.querySelectorAll('input[type=checkbox]')).map(c => ({
      name: c.name||c.id, visible: !!(c.offsetWidth||c.offsetHeight),
      outer: c.outerHTML.slice(0,200),
      labelText: (c.closest('label')?.innerText||'').trim().slice(0,60)
    }));
    // look for custom dropdowns
    res.comboboxes = Array.from(document.querySelectorAll('[role=combobox], [role=listbox], .select, [class*=select], [class*=dropdown]'))
      .slice(0,12).map(e => ({ tag: e.tagName, cls: (e.className||'').toString().slice(0,70), role: e.getAttribute('role'), text: (e.innerText||'').trim().slice(0,40) }));
    return res;
  });
  console.log(JSON.stringify(out));
  await browser.close();
})();
