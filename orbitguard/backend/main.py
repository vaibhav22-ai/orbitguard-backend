from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from orbitguard.backend.api.routes import router as api_router
from orbitguard.backend.config import get_settings

settings = get_settings()
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend intelligence layer for ORBITGUARD AI.",
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "ORBITGUARD AI Backend",
        "status": "ok",
    }


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
    }


@app.get("/app", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.include_router(api_router)
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
