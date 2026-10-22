
const { chromium } = require('playwright');
(async () => {
  // Use the full chromium build that is already on this box rather than the
  // headless-shell revision playwright would otherwise demand (the alpha
  // playwright-core here wants build 1246; the installed one is 1229).
  const exe = process.env.CHROMIUM_EXE;
  const browser = await chromium.launch({ headless: true, ...(exe ? { executablePath: exe } : {}) });
  const page = await browser.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));

  const out = {};

  // --- home / calculator ---
  await page.goto('https://solar.tekify.xyz/', { waitUntil: 'networkidle' });
  out.title = await page.title();
  out.hasForm = await page.locator('#solar-form').count();
  out.hasData = await page.evaluate(() => !!(window.SOLAR_DATA && Object.keys(window.SOLAR_DATA.cities).length));

  await page.selectOption('#city', 'seattle');
  await page.fill('#usage', '900');
  await page.selectOption('#wattage', '400');
  await page.selectOption('#tilt', '1.0');
  await page.selectOption('#system', 'ongrid');
  await page.click('#solar-form button[type=submit]');
  await page.waitForSelector('#results:not([hidden])', { timeout: 10000 });

  out.results = {
    city:   await page.textContent('#r-city'),
    panels: await page.textContent('#r-panels'),
    kw:     await page.textContent('#r-kw'),
    psh:    await page.textContent('#r-psh'),
    annual: await page.textContent('#r-annual'),
    rows:   await page.locator('#r-months tbody tr').count(),
    rowKwh: await page.locator('#r-months tbody tr td:nth-child(3)').allTextContents(),
  };

  // --- a city page ---
  await page.goto('https://solar.tekify.xyz/solar/phoenix/', { waitUntil: 'networkidle' });
  out.cityTitle = await page.title();
  out.cityH1 = (await page.textContent('h1')).trim();
  out.cityLink = await page.getAttribute('#r-citylink', 'href').catch(() => null);

  // --- table population on home ---
  await page.goto('https://solar.tekify.xyz/', { waitUntil: 'networkidle' });
  out.tableRows = await page.locator('#psh-table tbody tr').count();
  out.cityLinks = await page.locator('#city-links li').count();

  out.errors = errors;
  console.log(JSON.stringify(out));
  await browser.close();
})();
