import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def _resolve_dist() -> Path | None:
    raw = os.environ.get("GIGABRAIN_FRONTEND_DIST")
    if raw:
        path = Path(raw)
    else:
        path = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return path if path.is_dir() and (path / "index.html").exists() else None


def build_frontend_router() -> APIRouter | None:
    dist = _resolve_dist()
    if not dist:
        return None

    router = APIRouter()

    assets = dist / "assets"
    if assets.is_dir():
        router.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @router.get("/", include_in_schema=False)
    @router.get("/inbox", include_in_schema=False)
    async def index():
        return FileResponse(dist / "index.html")

    return router
