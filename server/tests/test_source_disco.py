"""Unit tests for source-code endpoint discovery (services/source_disco).

The LLM extraction is exercised live/E2E; these lock in source acquisition, route-
file location, and bundling — the deterministic parts.
"""
import os

import pytest

from app.services import source_disco as s


def _write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


def test_find_route_files_picks_route_density(tmp_path):
    root = str(tmp_path)
    _write(root, "internal/router/api.go",
           'r := gin.Group("/api/v1")\nr.GET("/users/:id", h)\nr.POST("/tokens", c)\nr.DELETE("/x", d)')
    _write(root, "internal/model/user.go", "type User struct { Name string }")   # no routes
    _write(root, "node_modules/express/lib/x.js", "app.get('/a', h); app.post('/b', h)")  # skipped dir
    files = s.find_route_files(root)
    rels = [rel for rel, _ in files]
    assert "internal/router/api.go" in rels
    assert "internal/model/user.go" not in rels           # zero route score
    assert not any("node_modules" in r for r in rels)      # skipped


def test_route_file_name_hint_boosts_score(tmp_path):
    root = str(tmp_path)
    _write(root, "routes.php", "Route::get('/a', 'C@a');")            # 1 route + filename bonus
    _write(root, "helper.php", "function get(){} function post(){}")  # no Route:: pattern
    files = s.find_route_files(root)
    assert files and files[0][0] == "routes.php"


def test_route_bundle_chunks_by_size(tmp_path):
    files = [("a.go", "x" * 20), ("b.go", "y" * 20), ("c.go", "z" * 20)]
    chunks = s.route_bundle(files, max_chars=60)
    assert len(chunks) >= 2                                 # 3 files w/ headers exceed 60 chars
    assert "FILE: a.go" in chunks[0]


@pytest.mark.asyncio
async def test_acquire_source_local_path(tmp_path):
    assert await s.acquire_source({"path": str(tmp_path)}) == str(tmp_path)
    assert await s.acquire_source({"path": str(tmp_path / "nope")}) is None
    assert await s.acquire_source({}) is None


@pytest.mark.asyncio
async def test_acquire_source_rejects_bad_repo_url():
    assert await s.acquire_source({"repo": "ftp://evil/x"}) is None
    assert await s.acquire_source({"repo": "not a url"}) is None


@pytest.mark.asyncio
async def test_acquire_source_clone_cached(tmp_path, monkeypatch):
    calls = {"n": 0}

    async def fake_git(args, **kw):
        calls["n"] += 1
        dest = args[-1]
        os.makedirs(os.path.join(dest, ".git"), exist_ok=True)   # simulate a clone
        return True

    monkeypatch.setattr(s, "_run_git", fake_git)
    cache = str(tmp_path / "cache")
    cfg = {"repo": "https://github.com/x/y", "ref": "v1"}
    d1 = await s.acquire_source(cfg, cache_dir=cache)
    d2 = await s.acquire_source(cfg, cache_dir=cache)          # 2nd call hits cache, no re-clone
    assert d1 == d2 and calls["n"] == 1
