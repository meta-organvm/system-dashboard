"""System pulse — mood, density, events, nerve wiring, flow."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/pulse", tags=["pulse"])


def _load_pulse_data(config) -> dict:
    """Compute all pulse data from organvm-engine.

    Returns a dict with mood, density, events, nerve, and cross-organ data.
    Falls back gracefully if the pulse module is not available.
    """
    from organvm_engine.pulse.affective import MoodFactors, compute_mood
    from organvm_engine.pulse.density import compute_density
    from organvm_engine.pulse.events import event_counts, recent
    from organvm_engine.pulse.nerve import resolve_subscriptions
    from organvm_engine.metrics.organism import get_organism
    from organvm_engine.seed.graph import build_seed_graph, validate_edge_resolution

    workspace = config.workspace_root()
    organism = get_organism(include_omega=False)

    # Seed graph + density
    graph = build_seed_graph(workspace)
    unresolved = validate_edge_resolution(graph)
    dp = compute_density(graph, organism, len(unresolved))

    # Mood factors from organism + density
    total = organism.total_repos or 1
    gate_stats = organism.gate_stats()
    avg_gate_rate = (
        sum(g.rate for g in gate_stats) / len(gate_stats) if gate_stats else 0.0
    )

    factors = MoodFactors(
        health_pct=organism.sys_pct,
        health_velocity=0.0,
        stale_ratio=organism.total_stale / total,
        stale_velocity=0.0,
        density_score=dp.interconnection_score,
        gate_pass_rate=avg_gate_rate,
        promo_ready_ratio=organism.total_promo_ready / total,
        session_frequency=0.0,
    )

    mood_result = compute_mood(factors)
    recent_events = recent(10)
    counts = event_counts()

    # Nerve subscriptions
    bundle = resolve_subscriptions(workspace)

    # Cross-organ edges from graph
    outbound_orgs: set[str] = set()
    inbound_orgs: set[str] = set()
    cross_count = 0
    for src, tgt, _ in graph.edges:
        src_org = src.split("/", maxsplit=1)[0] if "/" in src else src
        tgt_org = tgt.split("/", maxsplit=1)[0] if "/" in tgt else tgt
        if src_org != tgt_org:
            cross_count += 1
            outbound_orgs.add(src_org)
            inbound_orgs.add(tgt_org)

    return {
        "mood": mood_result,
        "density": dp,
        "events": recent_events,
        "event_counts": counts,
        "nerve": bundle,
        "cross_organ_edges": cross_count,
        "outbound_orgs": sorted(outbound_orgs),
        "inbound_orgs": sorted(inbound_orgs),
        "total_edges": len(graph.edges),
        "total_nodes": len(graph.nodes),
        "organism_sys_pct": organism.sys_pct,
        "organism_total_repos": organism.total_repos,
    }


def _fallback_data() -> dict:
    """Return empty/safe data when pulse module is unavailable."""
    return {
        "mood": None,
        "density": None,
        "events": [],
        "event_counts": {},
        "nerve": None,
        "cross_organ_edges": 0,
        "outbound_orgs": [],
        "inbound_orgs": [],
        "total_edges": 0,
        "total_nodes": 0,
        "organism_sys_pct": 0,
        "organism_total_repos": 0,
        "error": "Pulse module unavailable",
    }


@router.get("/", response_class=HTMLResponse)
async def pulse_page(request: Request):
    config = request.app.state.path_config

    try:
        data = _load_pulse_data(config)
    except Exception:
        data = _fallback_data()

    mood = data["mood"]
    density = data["density"]
    nerve = data["nerve"]

    # Build nerve summary for template
    nerve_summary: list[dict] = []
    if nerve is not None:
        for etype in sorted(nerve.by_event.keys()):
            subs = nerve.by_event[etype]
            subscribers = [
                {"name": s.subscriber, "action": s.action} for s in subs
            ]
            nerve_summary.append({
                "event_type": etype,
                "count": len(subs),
                "subscribers": subscribers,
            })

    # Build event rows
    event_rows: list[dict] = []
    for evt in data["events"]:
        ts = evt.timestamp[:19] if len(evt.timestamp) >= 19 else evt.timestamp
        event_rows.append({
            "timestamp": ts,
            "event_type": evt.event_type,
            "source": evt.source,
        })

    # Coverage bars from density
    coverage_bars: list[dict] = []
    if density is not None:
        total = density.total_repos or 1
        coverage_bars = [
            {
                "label": "Seeds",
                "count": density.repos_with_seeds,
                "total": density.total_repos,
                "pct": round(density.repos_with_seeds / total * 100, 1),
            },
            {
                "label": "CI",
                "count": density.repos_with_ci,
                "total": density.total_repos,
                "pct": round(density.repos_with_ci / total * 100, 1),
            },
            {
                "label": "Tests",
                "count": density.repos_with_tests,
                "total": density.total_repos,
                "pct": round(density.repos_with_tests / total * 100, 1),
            },
            {
                "label": "Docs",
                "count": density.repos_with_docs,
                "total": density.total_repos,
                "pct": round(density.repos_with_docs / total * 100, 1),
            },
        ]

    return request.app.state.templates.TemplateResponse(
        request,
        name="pulse.html",
        context={
            "page_title": "Pulse",
            "mood": mood,
            "density": density,
            "event_rows": event_rows,
            "nerve_summary": nerve_summary,
            "coverage_bars": coverage_bars,
            "cross_organ_edges": data["cross_organ_edges"],
            "outbound_orgs": data["outbound_orgs"],
            "inbound_orgs": data["inbound_orgs"],
            "total_edges": data["total_edges"],
            "total_nodes": data["total_nodes"],
            "event_counts": data["event_counts"],
            "error": data.get("error"),
        },
    )


@router.get("/api")
async def pulse_api(request: Request):
    """JSON endpoint returning all pulse data."""
    config = request.app.state.path_config

    try:
        data = _load_pulse_data(config)
    except Exception:
        data = _fallback_data()
        return data

    mood = data["mood"]
    density = data["density"]
    nerve = data["nerve"]

    return {
        "mood": mood.to_dict() if mood else None,
        "density": density.to_dict() if density else None,
        "events": [
            {
                "timestamp": e.timestamp,
                "event_type": e.event_type,
                "source": e.source,
            }
            for e in data["events"]
        ],
        "event_counts": data["event_counts"],
        "nerve_total": len(nerve.subscriptions) if nerve else 0,
        "nerve_event_types": len(nerve.by_event) if nerve else 0,
        "cross_organ_edges": data["cross_organ_edges"],
        "total_edges": data["total_edges"],
        "total_nodes": data["total_nodes"],
    }
