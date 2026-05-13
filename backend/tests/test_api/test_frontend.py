from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_frontend_root_serves_index_when_built(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>GB</title>")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('hi');")
    monkeypatch.setenv("GIGABRAIN_FRONTEND_DIST", str(dist))

    from app.api.frontend import mount_frontend

    test_app = FastAPI()
    mounted = mount_frontend(test_app)
    assert mounted is True

    client = TestClient(test_app)
    response = client.get("/")
    assert response.status_code == 200
    assert b"<title>GB</title>" in response.content

    asset_response = client.get("/assets/app.js")
    assert asset_response.status_code == 200
    assert b"console.log" in asset_response.content


def test_frontend_skips_mount_when_dist_absent(tmp_path, monkeypatch):
    missing = tmp_path / "no-dist"
    monkeypatch.setenv("GIGABRAIN_FRONTEND_DIST", str(missing))

    from app.api.frontend import mount_frontend

    test_app = FastAPI()
    mounted = mount_frontend(test_app)
    assert mounted is False
