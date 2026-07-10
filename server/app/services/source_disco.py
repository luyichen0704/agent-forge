"""Source-code endpoint discovery — read the target system's OWN route definitions.

Our targets are popular open-source enterprise systems, so their route code is the
GROUND TRUTH for the API surface — more complete than probing (finds writes/admin
routes probing can't safely hit) and more accurate than proposing from the product
name (no hallucination). This module ACQUIRES the source and LOCATES the route-
definition files; the LLM extraction (EXTRACT_ROUTES) runs in the explorer, and the
extracted endpoints are still probe-verified to catch source/instance version drift.

Acquisition (config.source):
  • {"path": "/abs/dir"}                     — C: use a local checkout as-is
  • {"repo": "https://…", "ref": "v1.2.3"}   — B: shallow clone (cached by url+ref)
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
from pathlib import Path

# directories with no route definitions — skip to keep the scan fast + focused
_SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", "__pycache__",
    ".venv", "venv", "env", "target", "bin", "obj", "coverage", "docs", "doc",
    "test", "tests", "spec", "specs", "__tests__", "e2e", "fixtures", "examples",
    "example", "migrations", "seeders", "seeds", ".github", "public", "static",
    "assets", "storage", "cache", "tmp", "locale", "locales", "i18n", "translations",
}
_SRC_EXT = {".go", ".js", ".ts", ".mjs", ".cjs", ".php", ".py", ".rb", ".java", ".kt", ".cs", ".rs"}

# route-registration idioms across common web frameworks
_ROUTE_PAT = re.compile(
    r"\.(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|Handle|HandleFunc|Group|Any)\s*\("      # Go: gin/echo/chi/gorilla
    r"|\b(?:app|router|route|api|r|e|g|v1|group|srv|mux)\.(?:get|post|put|delete|patch|use|route|group|all|register)\s*\("  # node/js
    r"|Route::(?:get|post|put|delete|patch|resource|apiResource|group|match|any|prefix)"  # laravel
    r"|@(?:app|router|blueprint|bp|api_router)\.(?:get|post|put|delete|patch|route)"      # fastapi/flask
    r"|\b(?:path|re_path|url)\s*\(|urlpatterns"                                            # django
    r"|@(?:Get|Post|Put|Delete|Patch|Request)Mapping"                                     # spring
    r"|\bresources?\b|\bnamespace\b",                                                      # rails routes.rb
    re.IGNORECASE)
_ROUTE_FILE_HINT = re.compile(r"rout|url|api|web\.php|endpoint|controller|handler|server", re.IGNORECASE)


def _score(path: str, text: str) -> int:
    n = len(_ROUTE_PAT.findall(text))
    if n == 0:
        return 0
    return n + (8 if _ROUTE_FILE_HINT.search(os.path.basename(path)) else 0)


def find_route_files(root: str, *, max_files: int = 25, max_total: int = 90_000) -> list[tuple[str, str]]:
    """Walk the tree and return the highest route-density files as (relpath, text),
    capped by count and total size so the LLM extraction stays within budget."""
    scored: list[tuple[int, str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if Path(fn).suffix.lower() not in _SRC_EXT:
                continue
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > 400_000:
                    continue
                text = Path(p).read_text(errors="ignore")
            except OSError:
                continue
            s = _score(p, text)
            if s > 0:
                scored.append((s, os.path.relpath(p, root), text))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[tuple[str, str]] = []
    total = 0
    for _s, rel, text in scored:
        if len(out) >= max_files or total >= max_total:
            break
        out.append((rel, text))
        total += len(text)
    return out


def route_bundle(files: list[tuple[str, str]], *, max_chars: int = 24_000) -> list[str]:
    """Pack (relpath, text) files into <=max_chars chunks, each file prefixed by a
    path header so the model can trace cross-file router mounts within a chunk."""
    chunks: list[str] = []
    cur, cur_len = [], 0
    for rel, text in files:
        block = f"// ===== FILE: {rel} =====\n{text}\n"
        if cur and cur_len + len(block) > max_chars:
            chunks.append("".join(cur))
            cur, cur_len = [], 0
        cur.append(block)
        cur_len += len(block)
    if cur:
        chunks.append("".join(cur))
    return chunks


async def acquire_source(src: dict, *, cache_dir: str | None = None) -> str | None:
    """Return a local directory holding the target's source, or None. A local
    `path` is used as-is (C); a `repo`+`ref` is shallow-cloned and cached (B)."""
    if not src:
        return None
    if src.get("path"):
        p = os.path.expanduser(src["path"])
        return p if os.path.isdir(p) else None
    url = src.get("repo")
    if not url or not re.match(r"^(https?://|git@|ssh://)", url):
        return None
    ref = src.get("ref")
    cache_dir = cache_dir or os.environ.get("AGENTFORGE_SRC_CACHE") \
        or os.path.join(tempfile.gettempdir(), "agentforge-src")
    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, hashlib.sha256(f"{url}|{ref}".encode()).hexdigest()[:16])
    if os.path.isdir(os.path.join(dest, ".git")):
        return dest                                   # cached clone
    base = ["git", "clone", "--depth", "1", "--single-branch"]
    args = base + (["--branch", ref] if ref else []) + [url, dest]
    if await _run_git(args):
        return dest
    # ref may be a commit SHA (can't --branch a SHA) → clone default branch instead
    if ref and await _run_git(base + [url, dest]):
        return dest
    return None


async def _run_git(args: list[str], *, timeout: float = 180.0) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode == 0
    except (asyncio.TimeoutError, OSError, ValueError):
        return False
