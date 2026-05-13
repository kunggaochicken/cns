from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_frontend_root_serves_index_when_built(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>GB</title>")
    monkeypatch.setenv("GIGABRAIN_FRONTEND_DIST", str(dist))

    from app.api.frontend import build_frontend_router

    test_app = FastAPI()
    router = build_frontend_router()
    assert router is not None
    test_app.include_router(router)

    client = TestClient(test_app)
    response = client.get("/")
    assert response.status_code == 200
    assert b"<title>GB</title>" in response.content


def test_frontend_skips_mount_when_dist_absent(tmp_path, monkeypatch):
    missing = tmp_path / "no-dist"
    monkeypatch.setenv("GIGABRAIN_FRONTEND_DIST", str(missing))

    from app.api.frontend import build_frontend_router

    router = build_frontend_router()
    assert router is None
