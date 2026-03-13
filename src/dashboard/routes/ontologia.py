"""Ontologia entity browser — UID-based identity registry dashboard."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

try:
    from ontologia.entity.identity import EntityType, LifecycleStatus
    from ontologia.registry.store import open_store

    HAS_ONTOLOGIA = True
except ImportError:
    HAS_ONTOLOGIA = False

router = APIRouter(prefix="/ontologia", tags=["ontologia"])


def _load_store():
    """Open the ontologia store, returning None if unavailable."""
    if not HAS_ONTOLOGIA:
        return None
    try:
        return open_store()
    except Exception:
        return None


def _build_entity_rows(store) -> list[dict]:
    """Build entity list with resolved display names."""
    rows: list[dict] = []
    for entity in store.list_entities():
        name_rec = store.current_name(entity.uid)
        display_name = name_rec.display_name if name_rec else "(unnamed)"
        rows.append({
            "uid": entity.uid,
            "name": display_name,
            "entity_type": entity.entity_type.value,
            "lifecycle_status": entity.lifecycle_status.value,
            "created_at": entity.created_at[:19] if len(entity.created_at) >= 19 else entity.created_at,
        })
    return rows


def _count_by_type(store) -> dict[str, int]:
    """Count entities grouped by EntityType."""
    counts: dict[str, int] = Counter()
    for entity in store.list_entities():
        counts[entity.entity_type.value] += 1
    return dict(sorted(counts.items()))


def _count_by_status(store) -> dict[str, int]:
    """Count entities grouped by LifecycleStatus."""
    counts: dict[str, int] = Counter()
    for entity in store.list_entities():
        counts[entity.lifecycle_status.value] += 1
    return dict(sorted(counts.items()))


@router.get("/", response_class=HTMLResponse)
async def ontologia_page(request: Request):
    """Entity browser: counts, entity list, and recent events."""
    store = _load_store()

    if store is None:
        return request.app.state.templates.TemplateResponse(
            request,
            name="ontologia.html",
            context={
                "page_title": "Ontologia",
                "available": False,
                "entity_count": 0,
                "counts_by_type": {},
                "counts_by_status": {},
                "entities": [],
                "events": [],
                "detail": None,
            },
        )

    entities = _build_entity_rows(store)
    events_raw = store.events(limit=50)
    event_rows = [
        {
            "timestamp": e.timestamp[:19] if len(e.timestamp) >= 19 else e.timestamp,
            "event_type": e.event_type,
            "source": e.source,
            "subject_entity": e.subject_entity or "",
        }
        for e in reversed(events_raw)
    ]

    return request.app.state.templates.TemplateResponse(
        request,
        name="ontologia.html",
        context={
            "page_title": "Ontologia",
            "available": True,
            "entity_count": store.entity_count,
            "counts_by_type": _count_by_type(store),
            "counts_by_status": _count_by_status(store),
            "entities": entities,
            "events": event_rows[:20],
            "detail": None,
        },
    )


@router.get("/events/", response_class=HTMLResponse)
async def ontologia_events(request: Request):
    """Recent event feed — full event log view."""
    store = _load_store()

    if store is None:
        return request.app.state.templates.TemplateResponse(
            request,
            name="ontologia.html",
            context={
                "page_title": "Ontologia — Events",
                "available": False,
                "entity_count": 0,
                "counts_by_type": {},
                "counts_by_status": {},
                "entities": [],
                "events": [],
                "detail": None,
            },
        )

    events_raw = store.events(limit=200)
    event_rows = [
        {
            "timestamp": e.timestamp[:19] if len(e.timestamp) >= 19 else e.timestamp,
            "event_type": e.event_type,
            "source": e.source,
            "subject_entity": e.subject_entity or "",
            "changed_property": e.changed_property or "",
            "previous_value": str(e.previous_value) if e.previous_value is not None else "",
            "new_value": str(e.new_value) if e.new_value is not None else "",
        }
        for e in reversed(events_raw)
    ]

    return request.app.state.templates.TemplateResponse(
        request,
        name="ontologia.html",
        context={
            "page_title": "Ontologia — Events",
            "available": True,
            "entity_count": store.entity_count,
            "counts_by_type": _count_by_type(store),
            "counts_by_status": _count_by_status(store),
            "entities": [],
            "events": event_rows,
            "detail": None,
        },
    )


@router.get("/{uid}", response_class=HTMLResponse)
async def ontologia_detail(request: Request, uid: str):
    """Entity detail view with name history."""
    store = _load_store()

    if store is None:
        return request.app.state.templates.TemplateResponse(
            request,
            name="ontologia.html",
            context={
                "page_title": "Ontologia — Entity",
                "available": False,
                "entity_count": 0,
                "counts_by_type": {},
                "counts_by_status": {},
                "entities": [],
                "events": [],
                "detail": None,
            },
        )

    entity = store.get_entity(uid)
    if entity is None:
        return request.app.state.templates.TemplateResponse(
            request,
            name="ontologia.html",
            context={
                "page_title": "Ontologia — Not Found",
                "available": True,
                "entity_count": store.entity_count,
                "counts_by_type": _count_by_type(store),
                "counts_by_status": _count_by_status(store),
                "entities": [],
                "events": [],
                "detail": {"not_found": True, "uid": uid},
            },
        )

    name_rec = store.current_name(uid)
    name_history = store.name_history(uid)
    entity_events = store.events(subject_entity=uid, limit=50)

    detail = {
        "not_found": False,
        "uid": entity.uid,
        "entity_type": entity.entity_type.value,
        "lifecycle_status": entity.lifecycle_status.value,
        "created_at": entity.created_at[:19] if len(entity.created_at) >= 19 else entity.created_at,
        "created_by": entity.created_by,
        "metadata": entity.metadata,
        "current_name": name_rec.display_name if name_rec else "(unnamed)",
        "name_history": [
            {
                "display_name": nr.display_name,
                "is_primary": nr.is_primary,
                "recorded_at": nr.recorded_at[:19] if len(nr.recorded_at) >= 19 else nr.recorded_at,
                "source": nr.source,
                "retired_at": nr.retired_at[:19] if nr.retired_at and len(nr.retired_at) >= 19 else nr.retired_at,
            }
            for nr in name_history
        ],
        "events": [
            {
                "timestamp": e.timestamp[:19] if len(e.timestamp) >= 19 else e.timestamp,
                "event_type": e.event_type,
                "source": e.source,
                "changed_property": e.changed_property or "",
                "previous_value": str(e.previous_value) if e.previous_value is not None else "",
                "new_value": str(e.new_value) if e.new_value is not None else "",
            }
            for e in reversed(entity_events)
        ],
    }

    return request.app.state.templates.TemplateResponse(
        request,
        name="ontologia.html",
        context={
            "page_title": f"Ontologia — {detail['current_name']}",
            "available": True,
            "entity_count": store.entity_count,
            "counts_by_type": _count_by_type(store),
            "counts_by_status": _count_by_status(store),
            "entities": [],
            "events": [],
            "detail": detail,
        },
    )
