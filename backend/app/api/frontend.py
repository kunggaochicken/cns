import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def _resolve_dist() -> Path | None:
    raw = os.environ.get("GIGABRAIN_FRONTEND_DIST")
    if raw:
        path = Path(raw)
    else:
        path = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return path if path.is_dir() and (path / "index.html").exists() else None


def mount_frontend(app: FastAPI) -> bool:
    dist = _resolve_dist()
    if not dist:
        return False

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    index_path = dist / "index.html"

    @app.get("/", include_in_schema=False)
    async def index_root():
        return FileResponse(index_path)

    @app.get("/inbox", include_in_schema=False)
    async def index_inbox():
        return FileResponse(index_path)

    return True
