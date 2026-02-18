"""FastAPI application — system dashboard for the eight-organ system."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.routes import health, registry, graph, soak, essays, omega

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(
    title="organvm system dashboard",
    description="Live health dashboard for the eight-organ system",
    version="0.1.0",
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Register routers
app.include_router(health.router)
app.include_router(registry.router)
app.include_router(graph.router)
app.include_router(soak.router)
app.include_router(essays.router)
app.include_router(omega.router)


@app.get("/")
async def index():
    """Root redirect to health dashboard."""
    return RedirectResponse(url="/health/")


def main():
    """CLI entry point."""
    import uvicorn
    uvicorn.run("dashboard.app:app", host="0.0.0.0", port=8000, reload=True)
