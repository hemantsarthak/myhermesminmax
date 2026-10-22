#!/usr/bin/env python3
"""Drive an Adsterra publisher signup with Playwright and a mail.tm inbox.

Why: Adsterra's signup page is a JS app that 403s plain HTTP clients, so
the form has to be driven by a real browser. The verification email goes to
a throwaway inbox we control (scripts/inbox.py), so no human is needed to
complete the loop.

Steps:
  1. open the publisher signup page and report the form fields actually present
  2. fill them from config (email from a mail.tm inbox, login, password, country)
  3. submit, then poll the inbox for the verification link and open it
  4. print whether the account is live

Usage:
    python3 scripts/adsterra_signup.py --email <addr> --password <pw> --login <name>
    python3 scripts/adsterra_signup.py --dry-run     # just dump the form fields
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SIGNUP_URL = "https://publishers.adsterra.com/signup"


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
    if not env.get("PLAYWRIGHT_BROWSERS_PATH"):
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    if browsers.exists():
        builds = sorted((p for p in browsers.glob("chromium-*") if p.is_dir()),
                        key=lambda p: p.name.split("-")[-1])
        for b in builds:
            cand = b / "chrome-win64" / "chrome.exe"
            if cand.exists():
                env["CHROMIUM_EXE"] = str(cand)
                break
    return node_exe, env


def run_js(script: str, timeout: int = 240) -> str:
    node_exe, env = node_env()
    tmp = ROOT / ".tmp" / "_adsterra.js"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(script, encoding="utf-8")
    proc = subprocess.run([node_exe, str(tmp)], capture_output=True, text=True,
                          timeout=timeout, cwd=str(ROOT), env=env)
    raw = (proc.stdout or "") + (proc.stderr or "")
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.dumps(json.loads(line))
            except json.JSONDecodeError:
                continue
    return json.dumps({"_raw": raw[-3000:]})

FIELDS_SCRIPT = """
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
    await page.goto('%(url)s', { waitUntil: 'domcontentloaded', timeout: 60000 });
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
""" % {"url": SIGNUP_URL}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--login")
    ap.add_argument("--country", default="India")
    ap.add_argument("--full-name", default="")
    args = ap.parse_args()

    if args.dry_run:
        raw = run_js(FIELDS_SCRIPT)
        data = json.loads(raw)
        print(json.dumps(data, indent=2)[:6000])
        return 0

    if not (args.email and args.password and args.login):
        print("ERROR: --email, --password and --login are required", file=sys.stderr)
        return 2

    print(json.dumps({"_note": "fill script not yet implemented - run --dry-run first"},
                     file=sys.stderr))
    return 2


if __name__ == "__main__":
    sys.exit(main())
