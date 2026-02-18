"""Essay feed."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.data.loader import load_essays

router = APIRouter(prefix="/essays", tags=["essays"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def essays_page(request: Request):
    essays = load_essays()

    return templates.TemplateResponse("essays.html", {
        "request": request,
        "page_title": "Essays",
        "essays": essays,
        "total": len(essays),
    })
