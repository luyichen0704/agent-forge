"""S3 API-surface discovery — the framework's object-storage transport.

S3-compatible stores (AWS S3, MinIO, Ceph, Cloudflare R2, Wasabi…) expose no
OpenAPI/introspection, but the operation set is a FIXED, well-known protocol and
the real buckets are enumerable via a signed ListBuckets call. So discovery =
list the buckets + emit the standard bucket/object CRUD as ordinary REST
endpoints (method + path). They bind to the normal APIExecutor; the only S3-
specific machinery is SigV4 signing (targets.SigV4Auth, per-request) and XML→rows
parsing (targets.xml_to_rows) — both already wired into client_for/APIExecutor.

Gate: a source whose auth.kind == "sigv4". Zero per-system code.
"""
from __future__ import annotations

from . import targets

# the fixed S3 verb set, as REST endpoints (path params substituted by APIExecutor)
_BASE_OPS = [
    {"method": "GET", "path": "/", "summary": "列出所有存储桶 (S3 ListBuckets)", "params": {}},
    {"method": "GET", "path": "/{bucket}", "summary": "列出指定存储桶中的对象 (S3 ListObjects)",
     "params": {"bucket": {"in": "path", "required": True}}},
    {"method": "PUT", "path": "/{bucket}", "summary": "创建存储桶 (S3 CreateBucket)",
     "params": {"bucket": {"in": "path", "required": True}}},
    {"method": "DELETE", "path": "/{bucket}", "summary": "删除存储桶 (S3 DeleteBucket)",
     "params": {"bucket": {"in": "path", "required": True}}},
    {"method": "PUT", "path": "/{bucket}/{key}", "summary": "上传对象 (S3 PutObject)",
     "params": {"bucket": {"in": "path", "required": True}, "key": {"in": "path", "required": True}}},
    {"method": "DELETE", "path": "/{bucket}/{key}", "summary": "删除对象 (S3 DeleteObject)",
     "params": {"bucket": {"in": "path", "required": True}, "key": {"in": "path", "required": True}}},
    {"method": "HEAD", "path": "/{bucket}/{key}", "summary": "查看对象信息 (S3 HeadObject)",
     "params": {"bucket": {"in": "path", "required": True}, "key": {"in": "path", "required": True}}},
]


async def discover_s3(config: dict) -> list[dict]:
    """List real buckets (signed) and emit the fixed S3 CRUD endpoints plus a
    concrete list-objects op per real bucket. Returns [] if unreachable/unsigned."""
    if ((config or {}).get("auth") or {}).get("kind") != "sigv4":
        return []
    buckets: list[str] = []
    try:
        async with targets.client_for(config) as client:
            resp = await client.get("/")
        if resp.status_code < 300:
            rows = targets.xml_to_rows(resp.text) or []
            buckets = [r["Name"] for r in rows if isinstance(r, dict) and r.get("Name")]
    except Exception:  # noqa: BLE001 — unreachable/unauthorized → generic ops only
        return []

    eps = [dict(e) for e in _BASE_OPS]
    # a concrete, no-argument list op per real bucket → "列出 <bucket> 里的对象" just works
    seen = {(e["method"], e["path"]) for e in eps}
    for b in buckets[:50]:
        key = ("GET", f"/{b}")
        if key not in seen:
            seen.add(key)
            eps.append({"method": "GET", "path": f"/{b}",
                        "summary": f"列出存储桶「{b}」中的对象", "params": {}})
    return eps
