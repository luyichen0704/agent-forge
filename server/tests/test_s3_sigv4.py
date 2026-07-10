"""Unit tests for the S3/SigV4 transport (targets.SigV4Auth + xml_to_rows).

Signature correctness is proven live against MinIO (E2E); these lock in the
structure, determinism, and XML row-shaping.
"""
import httpx

from app.services import targets
from app.services.targets import SigV4Auth, build_sigv4_auth, xml_to_rows


# ---------- XML → rows ----------

def test_xml_to_rows_list_buckets():
    xml = ("<ListAllMyBucketsResult><Owner><ID>x</ID></Owner>"
           "<Buckets><Bucket><Name>a</Name><CreationDate>t1</CreationDate></Bucket>"
           "<Bucket><Name>b</Name><CreationDate>t2</CreationDate></Bucket></Buckets>"
           "</ListAllMyBucketsResult>")
    rows = xml_to_rows(xml)
    names = [r.get("Name") for r in rows if r.get("Name")]
    assert names == ["a", "b"]


def test_xml_to_rows_list_objects():
    xml = ("<ListBucketResult><Name>bkt</Name>"
           "<Contents><Key>k1</Key><Size>10</Size></Contents>"
           "<Contents><Key>k2</Key><Size>20</Size></Contents></ListBucketResult>")
    rows = xml_to_rows(xml)
    assert [r["Key"] for r in rows] == ["k1", "k2"]
    assert rows[0]["Size"] == "10"


def test_xml_to_rows_malformed_returns_none():
    assert xml_to_rows("not xml <<<") is None


# ---------- SigV4 signing ----------

def test_signing_key_deterministic_32_bytes():
    a = SigV4Auth("AK", "SK", "us-east-1", "s3")
    k1 = a._signing_key("20260709")
    k2 = a._signing_key("20260709")
    assert k1 == k2 and len(k1) == 32
    assert a._signing_key("20260710") != k1        # date-scoped


def test_auth_flow_adds_sigv4_headers():
    a = SigV4Auth("AKIDEXAMPLE", "SECRET", "us-east-1", "s3")
    req = httpx.Request("GET", "http://127.0.0.1:9000/bucket?b=2&a=1")
    next(a.auth_flow(req))                          # run the (single-yield) flow
    auth = req.headers["authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
    assert "/us-east-1/s3/aws4_request" in auth
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in auth
    assert len(auth.split("Signature=")[1]) == 64  # hex sha256
    assert req.headers["x-amz-date"].endswith("Z")
    # empty-body payload hash is the sha256 of ""
    assert req.headers["x-amz-content-sha256"] == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_auth_flow_signs_body_hash():
    a = SigV4Auth("AK", "SK")
    req = httpx.Request("PUT", "http://h:9000/b/k", content=b"hello")
    next(a.auth_flow(req))
    import hashlib
    assert req.headers["x-amz-content-sha256"] == hashlib.sha256(b"hello").hexdigest()


def test_build_sigv4_auth_gating(monkeypatch):
    assert build_sigv4_auth({"auth": {"kind": "bearer"}}) is None
    monkeypatch.setenv("AK_ENV", "ak")
    monkeypatch.setenv("SK_ENV", "sk")
    a = build_sigv4_auth({"auth": {"kind": "sigv4", "access_key_env": "AK_ENV",
                                   "secret_key_env": "SK_ENV", "region": "eu-1"}})
    assert isinstance(a, SigV4Auth) and a.region == "eu-1"


def test_client_for_uses_sigv4_auth(monkeypatch):
    monkeypatch.setenv("AK_ENV", "ak")
    monkeypatch.setenv("SK_ENV", "sk")
    c = targets.client_for({"base_url": "http://x", "auth": {
        "kind": "sigv4", "access_key_env": "AK_ENV", "secret_key_env": "SK_ENV"}})
    assert isinstance(c.auth, SigV4Auth)
