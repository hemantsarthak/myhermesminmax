#!/usr/bin/env python3
"""Sign up for an ad network as a publisher, using a mail.tm inbox.

HilltopAds is the primary target: its signup page is a plain form (no
Turnstile), it accepts publishers with no traffic minimum, it supports
crypto payouts (BTC/USDT) which suits an unregistered India-based
individual, and website verification is self-service via a meta tag or a
verification file we can serve.

The flow:
  1. create (or reuse) a throwaway inbox
  2. fill the signup form and submit
  3. poll the inbox for the verification email, print its link
  4. optionally follow the link

Usage:
    python3 scripts/ad_network_signup.py --network hilltop \
        --email <addr> --password <pw> --name "Display Name"
    python3 scripts/ad_network_signup.py --network hilltop --list-fields
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent

TARGETS = {
    "hilltop": {
        "url": "https://hilltopads.com/signup",
        "form": "https://hilltopads.com/signup",
    },
}


def node_env() -> tuple[str, dict]:
    npm_root = ""
    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_cmd:
        try:
            npm_root = subprocess.run([npm_cmd, "root", "-g"], capture_output=True,
                                      text=True, timeout=60).stdout.strip()
        except Exception:  # noqa: BLE001
            npm_root = ""
    if not npm_root:
        npm_root = str(pathlib.Path.home() / "AppData" / "Roaming" / "npm" / "node_modules")
    node_exe = shutil.which("node") or shutil.which("node.exe")
    if not node_exe:
        raise RuntimeError("node not on PATH")

    candidates = [
        ROOT / "node_modules",
        pathlib.Path(npm_root) / "@playwright" / "cli" / "node_modules",
        pathlib.Path(npm_root),
    ]
    node_path = os.pathsep.join(str(c) for c in candidates if c.exists())

    env = dict(os.environ)
    env["NODE_PATH"] = node_path
    env["PATH"] = env.get("PATH", "") + os.pathsep + str(pathlib.Path(npm_root).parent)
    browsers = pathlib.Path.home() / "AppData" / "Local" / "ms-playwright"
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    if browsers.exists():
        builds = sorted((p for p in browsers.glob("chromium-*") if p.is_dir()),
                        key=lambda p: p.name.split("-")[-1])
        for b in builds:
            cand = b / "chrome-win64" / "chrome.exe"
            if cand.exists():
                env["CHROMIUM_EXE"] = str(cand)
                break
    return node_exe, env


def run_js(script: str, timeout: int = 240) -> dict:
    node_exe, env = node_env()
    tmp = ROOT / ".tmp" / "_adnet.js"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(script, encoding="utf-8")
    try:
        proc = subprocess.run([node_exe, str(tmp)], capture_output=True, text=True,
                              timeout=timeout, cwd=str(ROOT), env=env)
    except subprocess.TimeoutExpired:
        return {"_error": "browser script timed out"}
    raw = (proc.stdout or "") + (proc.stderr or "")
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"_error": raw[-2500:]}


LIST_SCRIPT = """
const { chromium } = require('playwright');
(async () => {
  const exe = process.env.CHROMIUM_EXE;
  const browser = await chromium.launch({ headless: true, ...(exe ? { executablePath: exe } : {}) });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'en-US', viewport: { width: 1366, height: 900 },
  });
  const page = await ctx.newPage();
  const out = { url: __URL__, title: '', inputs: [], labels: [], text: '' };
  try {
    await page.goto(__URL__, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(5000);
    out.title = await page.title();
    out.inputs = await page.evaluate(() => Array.from(document.querySelectorAll('input')).map((i,idx) => ({
      idx, name: i.name || '', id: i.id || '', type: i.type || '',
      placeholder: (i.placeholder || '').slice(0, 40),
      visible: !!(i.offsetWidth || i.offsetHeight),
      value: i.type === 'password' ? '' : (i.value || '')
    })));
    out.labels = await page.evaluate(() => Array.from(document.querySelectorAll('label')).map(l => (l.innerText||'').trim().slice(0,60)).filter(Boolean).slice(0,30));
    out.text = (await page.evaluate(() => document.body.innerText)).slice(0, 1200);
  } catch (e) { out.error = String(e).slice(0, 400); }
  console.log(JSON.stringify(out));
  await browser.close();
})();
"""

SIGNUP_SCRIPT = """
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
    await page.goto(__URL__, { waitUntil: 'domcontentloaded', timeout: 60000 });
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
    await setField('input[name="name"]:visible', __NAME__);
    await setField('input[name="email"]:visible', __EMAIL__);
    await setField('input[name="password"]:visible', __PASSWORD__);
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
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", default="hilltop", choices=list(TARGETS))
    ap.add_argument("--list-fields", action="store_true")
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--name", default="")
    ap.add_argument("--messenger", default="Telegram")
    args = ap.parse_args()

    tgt = TARGETS[args.network]

    if args.list_fields:
        res = run_js(LIST_SCRIPT.replace("__URL__", json.dumps(tgt["url"])))
        print(json.dumps(res, indent=2)[:6000])
        return 0

    if not (args.email and args.password):
        print("ERROR: --email and --password required", file=sys.stderr)
        return 2

    script = SIGNUP_SCRIPT.replace("__NAME__", json.dumps(args.name or "Tekify Media")) \
                          .replace("__MESSENGER__", json.dumps(args.messenger or "Telegram")) \
                          .replace("__EMAIL__", json.dumps(args.email)) \
                          .replace("__PASSWORD__", json.dumps(args.password)) \
                          .replace("__URL__", json.dumps(tgt["url"]))
    res = run_js(script)
    print(json.dumps(res, indent=2)[:5000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
