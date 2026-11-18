"""Open profile check routes. Plain asserts, no pytest. Forces the in-memory fallback, so it never touches Redis / Blob even if .env has them.
Run from wrapper/backend:  .venv/bin/python3 tests/test_open_profile.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("VERCEL", None)
os.environ.pop("APP_USERS", None)  # local-dev: auth lets everyone through as "local-dev"

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config, redis_cache, vercel_blob

# This machine's .env may point at the real Upstash Redis / Blob. Tests must never touch them:
# force the in-memory fallback before anything runs (audit.log also checks redis_cache.is_configured).
redis_cache.is_configured = lambda: False
vercel_blob.is_configured = lambda: False

from app.routes import open_profile as op

config.OPEN_PROFILE_WORKER_TOKEN = "t0k"
app = FastAPI()
app.include_router(op.router)
app.include_router(op.worker_router)
C = TestClient(app)
W = {"X-Worker-Token": "t0k"}
GOOD = "https://www.linkedin.com/sales/search/people?query=(recentSearchParam:(id:1),filters:List((type:REGION)))&sessionId=abc"
P = "/api/open-profile"
PW = "/api/open-profile-worker"


def url(n):
    return GOOD.replace("id:1", f"id:{n}")


def reset():
    op._Memory.kv.clear()
    op._Memory.files.clear()


def make(u=GOOD, name=None):
    return C.post(f"{P}/jobs", json={"url": u, "name": name})


def upload(jid, kind, data, parts=1, part=0):
    r = C.put(f"{PW}/jobs/{jid}/files/{kind}?part={part}&parts={parts}", content=data, headers=W)
    assert r.status_code == 200, r.text


CSV = "firstName,lastName,occupation,location,linkedinUrl,premium\n" + "".join(
    f"A{i},B{i},HR Director,Austin,https://www.linkedin.com/in/x{i},Yes\n" for i in range(5)
)


def finish(jid):
    for kind in ("open-profile", "not-open", "master"):
        upload(jid, kind, CSV.encode())
    upload(jid, "summary", b"# summary")
    return C.post(f"{PW}/jobs/{jid}/complete", headers=W, json={
        "unique_leads": 5, "open_count": 2, "not_open_count": 3, "expected_total": 10, "captured_total": 5})


def test_url_validation():
    reset()
    for bad in ["hello", "https://example.com/sales/search/people?query=1",
                "https://www.linkedin.com/sales/lists/people/123", "https://www.linkedin.com/in/someone",
                "https://www.linkedin.com/sales/search/people"]:
        r = make(bad)
        assert r.status_code == 422 and r.json()["detail"], bad


def test_create_stamps_signed_in_user_strips_tracking_and_dedupes():
    reset()
    a = make().json()
    assert a["duplicate"] is False and a["job"]["requester"] == "local-dev"
    assert "sessionId" not in a["job"]["url"]
    b = make().json()
    assert b["duplicate"] is True and b["job"]["id"] == a["job"]["id"]


def test_worker_auth_fails_closed():
    reset()
    assert C.post(f"{PW}/claim").status_code == 401
    assert C.post(f"{PW}/claim", headers={"X-Worker-Token": "nope"}).status_code == 401
    config.OPEN_PROFILE_WORKER_TOKEN = ""
    assert C.post(f"{PW}/claim", headers={"X-Worker-Token": ""}).status_code == 401
    config.OPEN_PROFILE_WORKER_TOKEN = "t0k"


def test_queue_is_serial_and_ordered():
    reset()
    first = make(url(11)).json()["job"]
    second = make(url(12)).json()["job"]
    c1 = C.post(f"{PW}/claim", headers=W).json()
    assert c1["job"]["id"] == first["id"] and c1["resumed"] is False
    c2 = C.post(f"{PW}/claim", headers=W).json()
    assert c2["job"]["id"] == first["id"] and c2["resumed"] is True
    jobs = {j["id"]: j for j in C.get(f"{P}/jobs").json()["jobs"]}
    assert jobs[second["id"]]["queue_ahead"] == 1 and jobs[first["id"]]["queue_ahead"] == 0


def test_full_lifecycle_parts_stitch_back_exactly():
    reset()
    jid = make(name="US HR leaders").json()["job"]["id"]
    C.post(f"{PW}/claim", headers=W)
    r = C.post(f"{PW}/jobs/{jid}/progress", headers=W, json={
        "stage": "importing", "percent": 40, "message": "Checking batch 2 of 5", "eta_minutes": 120})
    assert r.json() == {"cancel": False}
    j = C.get(f"{P}/jobs/{jid}").json()["job"]
    assert j["stage"] == "importing" and j["events"][-1]["message"] == "Checking batch 2 of 5"
    # a file bigger than one part, uploaded in 3 parts
    big = (CSV * 4).encode()
    cut = [big[:100], big[100:300], big[300:]]
    for i, chunk in enumerate(cut):
        upload(jid, "master", chunk, parts=3, part=i)
    upload(jid, "open-profile", CSV.encode())
    upload(jid, "not-open", CSV.encode())
    upload(jid, "summary", b"# s")
    done = C.post(f"{PW}/jobs/{jid}/complete", headers=W, json={
        "unique_leads": 5, "open_count": 2, "not_open_count": 3, "expected_total": 10, "captured_total": 5}).json()["job"]
    assert (done["status"], done["open_count"], done["unique_leads"]) == ("done", 2, 5)
    assert set(done["files"]) == {"open-profile", "not-open", "master", "summary"}
    got = b""
    for i in range(3):
        r = C.get(f"{P}/jobs/{jid}/files/master/{i}")
        assert r.status_code == 200 and r.headers["x-parts"] == "3" and r.headers["x-total-bytes"] == str(len(big))
        got += r.content
    assert got == big and r.headers["x-filename"] == "us-hr-leaders-all-leads.csv"
    assert C.get(f"{P}/jobs/{jid}/files/master/3").status_code == 404
    p = C.get(f"{P}/jobs/{jid}/preview/open-profile?n=2").json()
    assert p["columns"] == ["Name", "Title", "Location", "Profile"] and p["rows"][0]["Name"] == "A0 B0" and len(p["rows"]) == 2
    assert kv_free(op, "opc:running")


def kv_free(op_, key):
    return op_.kv_get(key) is None


def test_complete_requires_all_parts():
    reset()
    jid = make().json()["job"]["id"]
    C.post(f"{PW}/claim", headers=W)
    body = {"unique_leads": 1, "open_count": 1, "not_open_count": 0}
    assert C.post(f"{PW}/jobs/{jid}/complete", headers=W, json=body).status_code == 422
    upload(jid, "open-profile", b"x")
    upload(jid, "not-open", b"x")
    upload(jid, "master", b"a", parts=2, part=0)  # part 1 never arrives
    assert C.post(f"{PW}/jobs/{jid}/complete", headers=W, json=body).status_code == 422


def test_downloads_blocked_until_done_and_part_size_capped():
    reset()
    jid = make().json()["job"]["id"]
    assert C.get(f"{P}/jobs/{jid}/files/master/0").status_code == 404
    C.post(f"{PW}/claim", headers=W)
    r = C.put(f"{PW}/jobs/{jid}/files/master?part=0&parts=1", content=b"x" * (op.PART_BYTES + 5000), headers=W)
    assert r.status_code == 413


def test_cancel_queued_and_running():
    reset()
    a = make(url(21)).json()["job"]["id"]
    b = make(url(22)).json()["job"]["id"]
    assert C.post(f"{P}/jobs/{b}/cancel").json()["job"]["status"] == "cancelled"
    claimed = C.post(f"{PW}/claim", headers=W).json()["job"]["id"]
    assert claimed == a  # cancelled job is skipped
    assert C.post(f"{P}/jobs/{a}/cancel").json()["job"]["cancelling"] is True
    assert C.post(f"{PW}/jobs/{a}/progress", headers=W, json={"stage": "sizing", "percent": 5}).json()["cancel"] is True
    assert C.post(f"{PW}/jobs/{a}/fail", headers=W, json={"cancelled": True}).json()["job"]["status"] == "cancelled"
    assert C.post(f"{P}/jobs/{a}/cancel").status_code == 409


def test_cancelled_queued_job_is_never_claimed():
    reset()
    a = make(url(31)).json()["job"]["id"]
    kv = op._Memory.kv
    kv[f"opc:cancel:{a}"] = "someone"  # cancel flag landed but status write did not (race)
    assert C.post(f"{PW}/claim", headers=W).json()["job"] is None
    assert C.get(f"{P}/jobs/{a}").json()["job"]["status"] == "cancelled"


def test_failure_is_reported_and_unblocks_queue():
    reset()
    a = make(url(41)).json()["job"]["id"]
    b = make(url(42)).json()["job"]["id"]
    C.post(f"{PW}/claim", headers=W)
    j = C.post(f"{PW}/jobs/{a}/fail", headers=W, json={"message": "Waalaxy is logged out"}).json()["job"]
    assert j["status"] == "failed" and j["error"] == "Waalaxy is logged out"
    assert C.post(f"{PW}/claim", headers=W).json()["job"]["id"] == b
    assert C.get(f"{P}/jobs/{a}/files/master/0").status_code == 404


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"{len(tests)} passed")
