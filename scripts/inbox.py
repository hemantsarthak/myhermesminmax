#!/usr/bin/env python3
"""Temporary inbox over the mail.tm API, for autonomous account signups.

Why: ad networks (Adsterra, Monetag) and analytics/payout providers need an
email address and send a verification link. The operator is asleep most of the
day and does not want to be the mailman for every signup. This creates a
throwaway address, polls for the verification mail, and prints the link.

Usage:
    python3 scripts/inbox.py new                 # create an address, print it
    python3 scripts/inbox.py new --label adsterra
    python3 scripts/inbox.py poll <address> [minutes]
    python3 scripts/inbox.py read <address> [message-id]
    python3 scripts/inbox.py wait <address> <substr> [minutes]
            # wait for a mail whose subject/body contains <substr>, print the
            # verification URL if there is one

Credentials live in .tmp/inbox.json (gitignored). Nothing is printed except
the inbox address and message content the caller asked for.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.mail.tm"
ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / ".tmp" / "inbox.json"


def api(method: str, path: str, payload=None, token: str | None = None):
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"{method} {path} -> network error: {e.reason}") from None
    return json.loads(body) if body.strip() else {}


def members_of(payload) -> list:
    """mail.tm returns either a hydra envelope or a plain list, depending on
    the endpoint and the client's Accept header. Handle both."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("hydra:member", "member", "data", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def load() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}


def save(data: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def new_address(label: str = "") -> tuple[str, str]:
    domains = api("GET", "/domains")
    members = members_of(domains)
    if not members:
        raise RuntimeError("no active mail.tm domain")
    domain = members[0]["domain"]
    password = "MoneymMax-" + str(int(time.time() * 1000))[-10:]
    # mail.tm rejects some words in usernames as reserved/blocked
    # (verified: "moneymmax..." -> 422 "username is not valid", while
    # "mmax..." -> 201). Try a list of prefixes and use the first that works.
    prefixes = ["mmax", "mmweb", "mmsite", "mmtools"]
    address = ""
    for pfx in prefixes:
        slug = re.sub(r"[^a-z0-9]", "", (label or "inbox").lower()) or "inbox"
        cand = f"{pfx}{slug}{int(time.time())}@{domain}"
        try:
            acct = api("POST", "/accounts", {"address": cand, "password": password})
            address = cand
            break
        except RuntimeError as exc:
            if "429" in str(exc):
                raise
            continue
    if not address:
        raise RuntimeError("could not create a mail.tm account with any prefix")
    # POST /accounts returns the account object but NOT a token. The token
    # comes from a separate POST /token with the address+password.
    tok = api("POST", "/token", {"address": address, "password": password})
    token = tok.get("token")
    if not token:
        raise RuntimeError("no token returned")
    data = load()
    data[address] = {"token": token, "password": password, "label": label,
                     "created": int(time.time())}
    save(data)
    return address, token


def list_messages(address: str, token: str) -> list[dict]:
    res = api("GET", "/messages", token=token)
    return members_of(res)


def get_message(address: str, token: str, msg_id: str) -> dict:
    return api("GET", f"/messages/{msg_id}", token=token)


def extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s<>\"')\]]+", text or "")
    out = []
    for u in urls:
        u = u.rstrip(".,);")
        if u not in out:
            out.append(u)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["new", "poll", "read", "wait"])
    ap.add_argument("arg", nargs="*")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    if args.action == "new":
        address, _ = new_address(args.label)
        print(address)
        return 0

    if not args.arg:
        print("ERROR: need an address", file=sys.stderr)
        return 2
    address = args.arg[0]
    data = load()
    if address not in data:
        print(f"ERROR: unknown inbox {address}", file=sys.stderr)
        return 2
    token = data[address]["token"]

    if args.action == "poll":
        msgs = list_messages(address, token)
        print(f"{len(msgs)} message(s)")
        for m in msgs:
            print(f"  [{m.get('id')}] {m.get('subject','')}  ({m.get('createdAt','')})")
        return 0

    if args.action == "read":
        if len(args.arg) < 2:
            print("ERROR: read needs a message id", file=sys.stderr)
            return 2
        msg = get_message(address, token, args.arg[1])
        print(f"Subject: {msg.get('subject','')}")
        print(f"From:    {msg.get('from',{}).get('address','')}")
        print(f"Date:    {msg.get('createdAt','')}")
        print("---")
        print((msg.get("text") or msg.get("html") or "")[:4000])
        return 0

    if args.action == "wait":
        if len(args.arg) < 2:
            print("ERROR: wait needs a substring to look for", file=sys.stderr)
            return 2
        needle = args.arg[1].lower()
        minutes = int(args.arg[2]) if len(args.arg) > 2 else 10
        deadline = time.time() + minutes * 60
        seen = set()
        while time.time() < deadline:
            for m in list_messages(address, token):
                mid = m.get("id")
                if mid in seen:
                    continue
                seen.add(mid)
                full = get_message(address, token, mid)
                haystack = f"{full.get('subject','')} {(full.get('text') or '')}".lower()
                if needle in haystack:
                    print(f"MATCH {mid}: {full.get('subject','')}")
                    body = full.get("text") or ""
                    urls = extract_urls(body)
                    if urls:
                        print("URLS:")
                        for u in urls:
                            print(f"  {u}")
                    else:
                        print(body[:2000])
                    return 0
            time.sleep(20)
        print(f"NO MATCH within {minutes} min")
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
