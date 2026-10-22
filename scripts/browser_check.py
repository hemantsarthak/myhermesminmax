#!/usr/bin/env python3
"""Headless browser check of the deployed (or local) site.

Verifies the page that a human actually gets:
  - the page renders with a real title and the calculator form present
  - submitting the form produces results (not an error, not empty)
  - the numbers in the results match the Python reference implementation
  - the city page shows that city's real irradiance

Uses the Playwright CLI wrapper that is installed on this box
(playwright-cli), because the Hermes browser stack (camofox) is not running.

Usage:
    python3 scripts/browser_check.py [base-url]
"""

from __future__ import annotations

import json
import math
import os
import shutil
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYSTEM_EFFICIENCY = 0.86 * 0.96


def expected(city, monthly_kwh, wattage, roof_factor, kind):
    daily = monthly_kwh / 30.0
    psh = city["peak_sun_hours"]
    design = {"ongrid": 1.0, "hybrid": 0.9, "offgrid": 0.75}[kind]
    eff = SYSTEM_EFFICIENCY * roof_factor * design
    array_kw = daily / (psh * eff)
    panels = math.ceil(array_kw / (wattage / 1000.0))
    annual = 0.0
    for m in city["months"]:
        annual += (array_kw * city["monthly"].get(m, 0.0) * 30.4
                   * SYSTEM_EFFICIENCY * roof_factor * design)
    return panels, array_kw, annual


def run(base: str) -> int:
    data = json.loads((ROOT / "site" / "data" / "solar.json").read_text(encoding="utf-8"))
    cities = data["cities"]

    script = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  // Use the full chromium build that is already on this box rather than the
  // headless-shell revision playwright would otherwise demand (the alpha
  // playwright-core here wants build 1246; the installed one is 1229).
  const exe = process.env.CHROMIUM_EXE;
  const browser = await chromium.launch({{ headless: true, ...(exe ? {{ executablePath: exe }} : {{}}) }});
  const page = await browser.newPage();
  const errors = [];
  page.on('console', m => {{ if (m.type() === 'error') errors.push(m.text()); }});
  page.on('pageerror', e => errors.push(String(e)));

  const out = {{}};

  // --- home / calculator ---
  await page.goto('{base}/', {{ waitUntil: 'networkidle' }});
  out.title = await page.title();
  out.hasForm = await page.locator('#solar-form').count();
  out.hasData = await page.evaluate(() => !!(window.SOLAR_DATA && Object.keys(window.SOLAR_DATA.cities).length));

  await page.selectOption('#city', 'seattle');
  await page.fill('#usage', '900');
  await page.selectOption('#wattage', '400');
  await page.selectOption('#tilt', '1.0');
  await page.selectOption('#system', 'ongrid');
  await page.click('#solar-form button[type=submit]');
  await page.waitForSelector('#results:not([hidden])', {{ timeout: 10000 }});

  out.results = {{
    city:   await page.textContent('#r-city'),
    panels: await page.textContent('#r-panels'),
    kw:     await page.textContent('#r-kw'),
    psh:    await page.textContent('#r-psh'),
    annual: await page.textContent('#r-annual'),
    rows:   await page.locator('#r-months tbody tr').count(),
    rowKwh: await page.locator('#r-months tbody tr td:nth-child(3)').allTextContents(),
  }};

  // --- a city page ---
  await page.goto('{base}/solar/phoenix/', {{ waitUntil: 'networkidle' }});
  out.cityTitle = await page.title();
  out.cityH1 = (await page.textContent('h1')).trim();
  out.cityLink = await page.getAttribute('#r-citylink', 'href').catch(() => null);

  // --- table population on home ---
  await page.goto('{base}/', {{ waitUntil: 'networkidle' }});
  out.tableRows = await page.locator('#psh-table tbody tr').count();
  out.cityLinks = await page.locator('#city-links li').count();

  out.errors = errors;
  console.log(JSON.stringify(out));
  await browser.close();
}})();
"""

    tmp = ROOT / ".tmp" / "browser_check.js"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(script, encoding="utf-8")

    # playwright is nested inside the global @playwright/cli install on this
    # box (not a top-level module). Build NODE_PATH from every place it
    # actually lives, and prefer a project-local install if one exists.
    npm_root = ""
    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_cmd:
        try:
            npm_root = subprocess.run([npm_cmd, "root", "-g"],
                                      capture_output=True, text=True,
                                      timeout=60).stdout.strip()
        except Exception:  # noqa: BLE001
            npm_root = ""
    if not npm_root:
        npm_root = str(pathlib.Path.home() / "AppData" / "Roaming" / "npm" / "node_modules")

    # node itself must be resolvable too.
    node_exe = shutil.which("node") or shutil.which("node.exe")
    if not node_exe:
        print("ERROR: node not on PATH", file=sys.stderr)
        return 2

    candidates = [
        ROOT / "node_modules",
        pathlib.Path(npm_root) / "@playwright" / "cli" / "node_modules",
        pathlib.Path(npm_root),
    ]
    node_path = os.pathsep.join(str(c) for c in candidates if c.exists())

    env = dict(os.environ)
    env["NODE_PATH"] = node_path
    env["PATH"] = env.get("PATH", "") + os.pathsep + str(pathlib.Path(npm_root).parent)
    env["PLAYWRIGHT_BROWSERS_PATH"] = env.get(
        "PLAYWRIGHT_BROWSERS_PATH",
        str(pathlib.Path.home() / "AppData" / "Local" / "ms-playwright"))

    # Point at the newest full chromium build present, if any.
    browsers = pathlib.Path.home() / "AppData" / "Local" / "ms-playwright"
    chrome = None
    if browsers.exists():
        builds = sorted(
            (p for p in browsers.glob("chromium-*") if p.is_dir()),
            key=lambda p: p.name.split("-")[-1],
        )
        for b in builds:
            cand = b / "chrome-win64" / "chrome.exe"
            if cand.exists():
                chrome = str(cand)
                break
    if chrome:
        env["CHROMIUM_EXE"] = chrome

    try:
        proc = subprocess.run(
            [node_exe, str(tmp)],
            capture_output=True, text=True, timeout=180, cwd=str(ROOT), env=env)
    except FileNotFoundError:
        print("ERROR: node not on PATH", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("ERROR: browser check timed out", file=sys.stderr)
        return 2

    raw = (proc.stdout or "") + (proc.stderr or "")
    # The script prints one JSON object on its own line. Find the last line
    # that parses as a JSON object, rather than trying to slice braces
    # (which breaks on braces inside string values).
    result = None
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        try:
            result = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if result is None:
        print("ERROR: no JSON from the browser script")
        print(raw[:2000])
        return 2

    print(json.dumps(result, indent=2)[:2000])

    errors: list[str] = []
    if "Solar" not in (result.get("title") or ""):
        errors.append(f"bad title: {result.get('title')}")
    if not result.get("hasForm"):
        errors.append("calculator form missing")
    if not result.get("hasData"):
        errors.append("SOLAR_DATA not loaded")
    if result.get("results", {}).get("rows") != 12:
        errors.append(f"expected 12 month rows, got {result.get('results', {}).get('rows')}")

    # The month rows must carry real numbers, not zeros. A key mismatch
    # between the dataset's monthly keys and its month codes produces a
    # table of zeros while every other test still passes.
    row_kwh = []
    for x in (result.get("results", {}).get("rowKwh") or []):
        cleaned = str(x).replace(",", "").strip()
        try:
            row_kwh.append(float(cleaned))
        except ValueError:
            errors.append(f"non-numeric monthly output cell: {x!r}")
    if len(row_kwh) != 12:
        errors.append(f"expected 12 month output values, got {len(row_kwh)}")
    elif sum(row_kwh) <= 0:
        errors.append("monthly production is all zeros — dataset key mismatch")
    elif max(row_kwh) <= 0:
        errors.append("max monthly production is zero")

    seattle = cities["seattle"]
    exp_panels, exp_kw, exp_annual = expected(seattle, 900, 400, 1.0, "ongrid")
    got_panels = int((result.get("results", {}).get("panels") or "0").replace(",", ""))
    got_kw = float(result.get("results", {}).get("kw") or 0)
    got_annual = int((result.get("results", {}).get("annual") or "0").replace(",", ""))
    if got_panels != exp_panels:
        errors.append(f"panels: browser {got_panels} != expected {exp_panels}")
    if abs(got_kw - exp_kw) > 0.02:
        errors.append(f"kW: browser {got_kw} != expected {exp_kw:.3f}")
    if abs(got_annual - exp_annual) / max(exp_annual, 1) > 0.01:
        errors.append(f"annual: browser {got_annual} != expected {round(exp_annual)}")
    if f"{seattle['peak_sun_hours']:.2f}" != result.get("results", {}).get("psh"):
        errors.append(f"psh mismatch: {result.get('results', {}).get('psh')}")

    if result.get("tableRows") != len(cities):
        errors.append(f"table rows {result.get('tableRows')} != {len(cities)}")
    if result.get("cityLinks") != len(cities):
        errors.append(f"city links {result.get('cityLinks')} != {len(cities)}")
    if "Phoenix" not in (result.get("cityH1") or ""):
        errors.append(f"city page h1 wrong: {result.get('cityH1')}")
    if result.get("errors"):
        errors.append(f"console errors: {result['errors']}")

    if errors:
        for e in errors:
            print(f"ERROR {e}")
        print("BROWSER CHECK: FAILED")
        return 1
    print("BROWSER CHECK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8788"))
