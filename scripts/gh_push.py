#!/usr/bin/env python3
"""Push a local directory to a GitHub repo using the REST git-data API.

Why this exists: `git push` over HTTPS fails on this machine with
`fatal: unable to write flush packet: Broken pipe` at send-pack, for every
protocol version (0/1/2), both ssl backends (schannel/openssl), with and
without `Expect: 100-continue`, and with a correct fine-grained PAT that the
REST API accepts for writes. The REST git-data path works. So we use it.

Usage:
    python scripts/gh_push.py [--repo owner/name] [--branch main] [--dir .]
                              [--message "commit message"] [--dry-run]

Reads GITHUB_PAT from the environment (or a --token-file). Exits non-zero on
any API failure. Never prints the token.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
IGNORE_DIRS = {
    ".git", "node_modules", ".wrangler", ".venv", "__pycache__", "dist",
    "build", ".next", ".cache", ".idea", ".vscode",
}
IGNORE_FILES = {".env", ".DS_Store", "Thumbs.db"}
MAX_FILE_BYTES = 20 * 1024 * 1024


class GhError(RuntimeError):
    pass


def request(method: str, path: str, token: str, payload=None):
    url = f"{API}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hermes-gh-push",
    }
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise GhError(f"{method} {path} -> HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise GhError(f"{method} {path} -> network error: {exc.reason}") from None
    return json.loads(body) if body.strip() else {}


def collect_files(root: pathlib.Path):
    """Yield (relpath, abspath) for every file that should be tracked."""
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & IGNORE_DIRS:
            continue
        if path.name in IGNORE_FILES or path.name.endswith(".log"):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            print(f"  skip (too large): {path.relative_to(root)}")
            continue
        yield path.relative_to(root).as_posix(), path


def gitignore_filter(root: pathlib.Path, rel: str) -> bool:
    """Honour .gitignore patterns (simple glob semantics, no negations)."""
    gi = root / ".gitignore"
    if not gi.exists():
        return False
    patterns = []
    for line in gi.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line.rstrip("/"))
    import fnmatch
    parts = rel.split("/")
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat):
            return True
        if any(fnmatch.fnmatch(part, pat) for part in parts):
            return True
        if pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:]):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPO", "hemantsarthak/myhermesminmax"))
    ap.add_argument("--branch", default=os.environ.get("GITHUB_BRANCH", "main"))
    ap.add_argument("--dir", default=".")
    ap.add_argument("--message", default=None)
    ap.add_argument("--token-file", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_PAT", "")
    if args.token_file:
        token = pathlib.Path(args.token_file).read_text(encoding="utf-8").strip()
    if not token:
        print("ERROR: no token. Set GITHUB_PAT or pass --token-file", file=sys.stderr)
        return 2

    root = pathlib.Path(args.dir).resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 2

    files = [(rel, p) for rel, p in collect_files(root) if not gitignore_filter(root, rel)]
    print(f"repo={args.repo} branch={args.branch} files={len(files)}")

    # 1. Ensure repo exists
    try:
        repo = request("GET", f"/repos/{args.repo}", token)
    except GhError as exc:
        if "HTTP 404" in str(exc):
            print(f"creating repo {args.repo}")
            request("POST", "/user/repos", token,
                    {"name": args.repo.split("/")[1], "private": False, "auto_init": True})
            time.sleep(1.5)
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    # 2. Resolve base commit (or create the branch)
    base_sha = None
    repo_is_empty = False
    try:
        ref = request("GET", f"/repos/{args.repo}/git/ref/heads/{args.branch}", token)
        base_sha = ref["object"]["sha"]
    except GhError as exc:
        if "409" in str(exc) and "empty" in str(exc).lower():
            # Repo has no commits at all. Seed it with the first file via the
            # Contents API (the git-data blob API refuses on an empty repo),
            # then continue with the git-data path.
            repo_is_empty = True
            print(f"repo is empty; seeding {args.branch} with the first file")
            if not files:
                print("ERROR: nothing to push", file=sys.stderr)
                return 1
            seed_rel, seed_path = files[0]
            seed_b64 = base64.b64encode(seed_path.read_bytes()).decode()
            created = request(
                "PUT", f"/repos/{args.repo}/contents/{seed_rel}", token,
                {"message": f"chore: add {seed_rel}", "content": seed_b64,
                 "branch": args.branch})
            base_sha = created["commit"]["sha"]
            print(f"  seeded {seed_rel} -> {base_sha[:8]}")
        else:
            # branch missing — find the default branch and branch from it
            try:
                info = request("GET", f"/repos/{args.repo}", token)
                default = info.get("default_branch", "main")
                base_ref = request("GET", f"/repos/{args.repo}/git/ref/heads/{default}", token)
                base_sha = base_ref["object"]["sha"]
            except GhError as exc2:
                print(f"ERROR: no base branch: {exc2}", file=sys.stderr)
                return 1
            request("POST", f"/repos/{args.repo}/git/refs", token,
                    {"ref": f"refs/heads/{args.branch}", "sha": base_sha})
            print(f"created branch {args.branch} from {base_sha[:8]}")

    # The seeded file is already committed; don't upload it twice.
    if repo_is_empty:
        files = files[1:]

    # 3. Build the tree
    tree_entries = []
    for rel, abspath in files:
        raw = abspath.read_bytes()
        enc = "base64"
        content = base64.b64encode(raw).decode()
        mime = mimetypes.guess_type(rel)[0] or "application/octet-stream"
        if mime.startswith("text/") or rel.endswith((".md", ".js", ".json", ".html", ".css", ".txt", ".yml", ".yaml", ".sh", ".py")):
            enc = "utf-8"
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                enc = "base64"
                content = base64.b64encode(raw).decode()
        blob = request("POST", f"/repos/{args.repo}/git/blobs", token,
                       {"content": content, "encoding": enc})
        tree_entries.append({
            "path": rel,
            "mode": "100644",
            "type": "blob",
            "sha": blob["sha"],
        })
        print(f"  blob {rel}")

    if args.dry_run:
        print("dry-run: no commit created")
        return 0

    tree_payload = {"tree": tree_entries}
    if base_sha:
        tree_payload["base_tree"] = base_sha
    tree = request("POST", f"/repos/{args.repo}/git/trees", token, tree_payload)

    msg = args.message or f"sync: {len(tree_entries)} files"
    commit_payload = {"message": msg, "tree": tree["sha"]}
    if base_sha:
        commit_payload["parents"] = [base_sha]
    commit = request("POST", f"/repos/{args.repo}/git/commits", token, commit_payload)

    if repo_is_empty:
        # The seeded commit already created the branch; advance it.
        request("PATCH", f"/repos/{args.repo}/git/refs/heads/{args.branch}", token,
                {"sha": commit["sha"], "force": True})
        try:
            request("PATCH", f"/repos/{args.repo}", token,
                    {"default_branch": args.branch})
        except GhError as exc:
            print(f"note: could not set default branch: {exc}")
    else:
        request("PATCH", f"/repos/{args.repo}/git/refs/heads/{args.branch}", token,
                {"sha": commit["sha"], "force": False})

    print(f"OK {args.branch} -> {commit['sha']}")
    print(f"https://github.com/{args.repo}/tree/{args.branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
