#!/usr/bin/env python3
"""Verify a built static site before deploy.

Checks the things that actually break a Pages deploy:
  - every .html file parses as HTML (well-formed enough for a browser)
  - no internal link points at a missing file or directory
  - no absolute links to localhost or example.com placeholders
  - sitemap.xml URLs all exist on disk
  - robots.txt exists and references the sitemap
  - every page has a non-empty <title> and a meta description
  - total file count is under the Cloudflare Pages free-tier cap (20,000)
  - no file exceeds 25 MiB

Usage:
    python3 scripts/verify_site.py [site-dir]     # default: ./site
Exit code 0 = clean, 1 = errors found.
"""

from __future__ import annotations

import pathlib
import re
import sys
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES_FILE_CAP = 20_000
MAX_FILE_BYTES = 25 * 1024 * 1024

SKIP_DIRS = {".git", "node_modules", ".wrangler", "__pycache__", ".tmp"}


class TitleDescParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = ""
        self.description = ""
        self._in_desc = False
        self.links: list[str] = []
        self.has_viewport = False
        self.lang = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            if d.get("name", "").lower() == "description":
                self._in_desc = True
                self.description = d.get("content", "")
            if d.get("name", "").lower() == "viewport":
                self.has_viewport = True
        elif tag == "html":
            self.lang = d.get("lang", "")
        elif tag in ("a", "link", "img", "script", "source"):
            for key in ("href", "src"):
                if key in d and d[key]:
                    self.links.append(d[key])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "meta":
            self._in_desc = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def main() -> int:
    site = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site"
    if not site.is_dir():
        print(f"ERROR: {site} does not exist", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    html_files = sorted(
        p for p in site.rglob("*.html")
        if not (set(p.relative_to(site).parts) & SKIP_DIRS)
    )
    all_files = [p for p in site.rglob("*") if p.is_file() and not (set(p.relative_to(site).parts) & SKIP_DIRS)]

    if not html_files:
        errors.append("no .html files found")
    if len(all_files) > PAGES_FILE_CAP:
        errors.append(f"{len(all_files)} files exceeds the Pages free-tier cap of {PAGES_FILE_CAP}")
    for p in all_files:
        if p.stat().st_size > MAX_FILE_BYTES:
            errors.append(f"file exceeds 25 MiB: {p.relative_to(site)}")

    # Pass 1: parse pages, collect titles/descriptions and links.
    parsed: dict[pathlib.Path, TitleDescParser] = {}
    for p in html_files:
        parser = TitleDescParser()
        try:
            parser.feed(p.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 - report, do not crash the gate
            errors.append(f"HTML parse error in {p.relative_to(site)}: {exc}")
            continue
        parsed[p] = parser
        rel = p.relative_to(site).as_posix()
        if not parser.title.strip():
            errors.append(f"missing <title> in {rel}")
        if not parser.description.strip():
            warnings.append(f"missing meta description in {rel}")
        if not parser.has_viewport:
            warnings.append(f"missing viewport meta in {rel}")
        if not parser.lang:
            warnings.append(f"missing lang attribute in {rel}")

    # Pass 2: link targets.
    def target_exists(base: pathlib.Path, link: str) -> bool:
        """Resolve an internal link to a path on disk. True if it exists."""
        clean = link.split("#")[0].split("?")[0]
        if not clean:
            return True  # pure fragment
        clean = clean.replace("%20", " ")
        if clean.endswith("/"):
            clean += "index.html"
        cand = (site / clean.lstrip("/")) if not clean.startswith("/") else (site / clean.lstrip("/"))
        if cand.is_file():
            return True
        # directory-style URL
        if (cand / "index.html").is_file():
            return True
        # extensionless URL -> try .html
        if cand.suffix == "" and (cand.with_suffix(".html")).is_file():
            return True
        return False

    for p, parser in parsed.items():
        rel = p.relative_to(site).as_posix()
        for link in parser.links:
            if link.startswith(("http://", "https://", "//", "mailto:", "tel:", "data:", "javascript:", "#")):
                if "localhost" in link or "127.0.0.1" in link:
                    errors.append(f"localhost link in {rel}: {link}")
                if "example.com" in link:
                    warnings.append(f"placeholder example.com link in {rel}: {link}")
                continue
            if not target_exists(p, link):
                errors.append(f"broken internal link in {rel}: {link}")

    # sitemap
    sitemap = site / "sitemap.xml"
    if not sitemap.exists():
        errors.append("sitemap.xml is missing")
    else:
        text = sitemap.read_text(encoding="utf-8", errors="replace")
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
        if not locs:
            errors.append("sitemap.xml contains no <loc> entries")
        for loc in locs:
            path_part = re.sub(r"^https?://[^/]+", "", loc).split("#")[0]
            if not path_part:
                continue
            if path_part.endswith("/"):
                path_part += "index.html"
            if not (site / path_part.lstrip("/")).is_file():
                errors.append(f"sitemap URL has no file on disk: {loc}")

    # robots
    robots = site / "robots.txt"
    if not robots.exists():
        errors.append("robots.txt is missing")
    elif "sitemap" not in robots.read_text(encoding="utf-8", errors="replace").lower():
        warnings.append("robots.txt does not reference a sitemap")

    print(f"site: {site}")
    print(f"html pages: {len(html_files)}   total files: {len(all_files)}")
    for w in warnings[:25]:
        print(f"WARN  {w}")
    if len(warnings) > 25:
        print(f"WARN  ... and {len(warnings) - 25} more")
    for e in errors[:40]:
        print(f"ERROR {e}")
    if len(errors) > 40:
        print(f"ERROR ... and {len(errors) - 40} more")

    if errors:
        print(f"VERIFY: FAILED ({len(errors)} errors, {len(warnings)} warnings)")
        return 1
    print(f"VERIFY: clean ({len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
