#!/usr/bin/env python3
"""Indexing toolkit: sitemap pinging, IndexNow, and search-console setup help.

Search Console API needs an OAuth token tied to a Google account, which the
operator must do once in a browser. Until then, the sitemap ping plus IndexNow
(Bing/Google/Yandex) still gets pages crawled.

IndexNow requires a key file served from the site root:
    <key>.txt containing the key string
Bing's implementation accepts a key that is also a file at /<key>.txt.

Usage:
    python3 scripts/index_now.py --key <32-hex>            # upload the key file + submit urls
    python3 scripts/index_now.py --key <32-hex> --submit    # just submit
    python3 scripts/index_now.py --ping                     # classic sitemap pings
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
BASE = "https://solar.tekify.xyz"
UA = "moneymmax-indexnow/1.0 (+https://solar.tekify.xyz)"


def site_urls() -> list[str]:
    """Every URL in the sitemap, plus the city pages."""
    urls: list[str] = []
    sm = SITE / "sitemap.xml"
    if sm.exists():
        text = sm.read_text(encoding="utf-8")
        import re
        for m in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text):
            urls.append(m)
    if not urls:
        urls = [BASE + "/"]
    return urls


def write_key_file(key: str) -> pathlib.Path:
    """Bing requires the key to be served at /<key>.txt with the key as body."""
    p = SITE / f"{key}.txt"
    p.write_text(key, encoding="utf-8")
    return p


def submit_indexnow(key: str, urls: list[str]) -> bool:
    payload = {
        "host": "solar.tekify.xyz",
        "key": key,
        "keyLocation": f"{BASE}/{key}.txt",
        "urlList": urls,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.indexnow.org/indexnow",
        data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            code = r.status
            print(f"IndexNow -> HTTP {code} ({len(urls)} urls)")
            return 200 <= code < 300
    except urllib.error.HTTPError as e:
        print(f"IndexNow -> HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}")
        return False
    except urllib.error.URLError as e:
        print(f"IndexNow -> network error: {e.reason}")
        return False


def ping_sitemaps() -> None:
    """Classic sitemap pings. Google deprecated the endpoint but Bing and
    others still accept it, and it costs nothing."""
    targets = [
        f"{BASE}/sitemap.xml",
    ]
    for engine in [
        "https://www.bing.com/ping?sitemap={}",
        "https://www.google.com/ping?sitemap={}",
    ]:
        for sm in targets:
            url = engine.format(urllib.parse.quote(sm, safe=""))
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    print(f"ping {url.split('/')[2]} -> HTTP {r.status}")
            except urllib.error.HTTPError as e:
                print(f"ping {url.split('/')[2]} -> HTTP {e.code}")
            except urllib.error.URLError as e:
                print(f"ping {url.split('/')[2]} -> network error: {e.reason}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", help="IndexNow key (a 32-hex string)")
    ap.add_argument("--submit", action="store_true", help="submit without writing the key file")
    ap.add_argument("--ping", action="store_true", help="ping search engines with the sitemap")
    args = ap.parse_args()

    if args.ping:
        ping_sitemaps()
        return 0

    if not args.key:
        ap.print_help()
        return 2

    if not args.submit:
        p = write_key_file(args.key)
        print(f"key file written: {p.relative_to(ROOT)}")
        print("  -> serves at https://solar.tekify.xyz/" + args.key + ".txt")

    urls = site_urls()
    ok = submit_indexnow(args.key, urls)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
