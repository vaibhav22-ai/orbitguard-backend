from fastapi import FastAPI

from orbitguard.backend.api.routes import router as api_router
from orbitguard.backend.config import get_settings

settings = get_settings()

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


app.include_router(api_router)
