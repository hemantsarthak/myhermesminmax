#!/usr/bin/env python3
"""Google autocomplete as a demand probe, plus long-tail expansion.

Autocomplete is a direct read of what people actually type. Counting the
suggestions for "<seed> a" ... "<seed> z" gives a long-tail size estimate,
and the suggestions themselves are real queries.

Usage:
    python3 scripts/demand.py "deck joist span calculator"
    python3 scripts/demand.py "pipe sizing calculator" --expand
    python3 scripts/demand.py "generator size calculator" --expand --json
"""

from __future__ import annotations

import argparse
import json
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def suggestions(query: str, client: str = "firefox") -> list[str]:
    """client='firefox' returns the JSON endpoint; 'gws' returns the web one."""
    if client == "firefox":
        url = ("https://suggestqueries.google.com/complete/search?client=firefox&hl=en"
               f"&q={urllib.parse.quote(query)}")
    else:
        url = ("https://www.google.com/complete/search?client=gws-wiz&hl=en"
               f"&q={urllib.parse.quote(query)}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
        return [str(s) for s in data[1]]
    return []


def expand(seed: str) -> list[str]:
    """Collect distinct suggestions for seed + ' a' .. ' z' plus bare seed."""
    out: list[str] = []
    seen: set[str] = set()
    queries = [seed] + [f"{seed} {c}" for c in string.ascii_lowercase]
    for q in queries:
        for s in suggestions(q):
            k = s.strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(s)
        time.sleep(0.25)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("seed")
    ap.add_argument("--expand", action="store_true", help="a-z long-tail expansion")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    if args.expand:
        items = expand(args.seed)
    else:
        items = suggestions(args.seed)

    if args.json:
        print(json.dumps({"seed": args.seed, "count": len(items), "suggestions": items},
                         indent=2))
        return 0

    print(f"### {args.seed}  -> {len(items)} suggestion(s)")
    for s in items[: args.top]:
        print(f"  - {s}")
    if len(items) > args.top:
        print(f"  ... and {len(items) - args.top} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
