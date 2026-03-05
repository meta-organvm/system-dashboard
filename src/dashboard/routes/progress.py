"""Per-project alpha-to-omega progress — contextually-aware gate evaluation.

Routes:
    /progress/           — main overview (organ cards with repo tables)
    /progress/repo/NAME  — single repo detail view
    /progress/gate-stats — gate pass-rate heatmap
    /progress/blockers   — promotion blockers
    /progress/stale      — staleness report
    /progress/api        — full JSON API
    /progress/api/repo/N — single repo JSON
    /progress/api/gates  — gate stats JSON
"""

import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from dashboard.data.loader import load_registry
from organvm_engine.paths import registry_path as _registry_path

router = APIRouter(prefix="/progress", tags=["progress"])

WORKSPACE = Path.home() / "Workspace"
_PROGRESS_CACHE_TTL_SECONDS = int(os.environ.get("DASHBOARD_PROGRESS_CACHE_TTL_SECONDS", "30"))
_PROGRESS_CACHE: dict[str, object] = {
    "projects": None,
    "loaded_at": 0.0,
    "registry_mtime": None,
}
_PROGRESS_CACHE_LOCK = Lock()

# ---------------------------------------------------------------------------
# Inline evaluator (mirrors orchestration-start-here/scripts/lib/progress.py)
# ---------------------------------------------------------------------------

_IMPL_ORDER = {"ARCHIVED": 0, "DESIGN_ONLY": 1, "SKELETON": 2, "PROTOTYPE": 3, "ACTIVE": 4, "PRODUCTION": 4}
_PROMO_ORDER = {"ARCHIVED": -1, "LOCAL": 0, "CANDIDATE": 1, "PUBLIC_PROCESS": 2, "GRADUATED": 3}
_STALE_WARN = 30
_STALE_CRIT = 90
_DOCS_THRESHOLD = {"flagship": 1000, "standard": 500, "infrastructure": 100, "stub": 50, "archive": 0}

ORG_TO_ORGAN = {
    "ivviiviivvi": "ORGAN-I", "organvm-i-theoria": "ORGAN-I",
    "omni-dromenon-machina": "ORGAN-II", "organvm-ii-poiesis": "ORGAN-II",
    "labores-profani-crux": "ORGAN-III", "organvm-iii-ergon": "ORGAN-III",
    "organvm-iv-taxis": "ORGAN-IV", "organvm-v-logos": "ORGAN-V",
    "organvm-vi-koinonia": "ORGAN-VI", "organvm-vii-kerygma": "ORGAN-VII",
    "meta-organvm": "META-ORGANVM", "4444j99": "PERSONAL",
}
ORGAN_DIRS = {
    "ORGAN-I": ["organvm-i-theoria"], "ORGAN-II": ["organvm-ii-poiesis"],
    "ORGAN-III": ["organvm-iii-ergon"], "ORGAN-IV": ["organvm-iv-taxis"],
    "ORGAN-V": ["organvm-v-logos"], "ORGAN-VI": ["organvm-vi-koinonia"],
    "ORGAN-VII": ["organvm-vii-kerygma"], "META-ORGANVM": ["meta-organvm"],
    "PERSONAL": ["4444J99"],
}
PROFILES = {
    "code-full": set(),
    "documentation": {"TESTS", "DEPLOY"},
    "infrastructure": {"TESTS", "DOCS", "PROTO", "DEPLOY", "GRAD", "OMEGA"},
    "governance": {"TESTS", "PROTO", "DEPLOY"},
    "stub": {"TESTS", "DOCS", "PROTO", "DEPLOY", "GRAD", "OMEGA"},
    "archived": {"OMEGA"},
}
GATE_ORDER = ["SEED", "SCAFFOLD", "CI", "TESTS", "DOCS", "PROTO", "CAND", "DEPLOY", "GRAD", "OMEGA"]
LANG_EXTS = {".py": "Python", ".ts": "TypeScript", ".js": "JavaScript", ".rs": "Rust", ".go": "Go"}


def _has_code(path: Path) -> bool:
    exts = {".py", ".ts", ".js", ".rs", ".go", ".java"}
    dirs = {"src", "lib", "titan", "agents", "hive", "adapters", "runtime", "pkg", "cmd"}
    for d in dirs:
        if (path / d).is_dir():
            return True
    for item in path.iterdir():
        if item.is_file() and item.suffix in exts:
            return True
        if item.is_dir() and not item.name.startswith("."):
            try:
                if any(s.suffix in exts for s in item.iterdir() if s.is_file()):
                    return True
            except PermissionError:
                continue
    return False


def _detect_profile(entry: dict, local: Path | None) -> str:
    tier = entry.get("tier", "standard")
    impl = entry.get("implementation_status", "ACTIVE")
    promo = entry.get("promotion_status", "LOCAL")
    doc = entry.get("documentation_status", "")
    name = entry.get("name", "")
    if promo == "ARCHIVED" or tier == "archive":
        return "archived"
    if tier == "stub":
        return "stub"
    if tier == "infrastructure" or doc == "INFRASTRUCTURE":
        return "infrastructure"
    if impl == "DESIGN_ONLY":
        return "documentation"
    gov_kw = {"petasum", "governance", "commandments", "policy", "constitution"}
    if any(kw in name.lower() for kw in gov_kw):
        if local and _has_code(local):
            return "code-full"
        return "governance"
    if local and not _has_code(local):
        return "documentation"
    return "code-full"


def _find_local(entry: dict, organ_id: str) -> Path | None:
    if not WORKSPACE.is_dir():
        return None
    org = entry.get("org", "")
    name = entry.get("name", "")
    if not name:
        return None
    for key, dirs in ORGAN_DIRS.items():
        if organ_id == key or org in dirs:
            for d in dirs:
                c = WORKSPACE / d / name
                if c.is_dir():
                    return c
    if org:
        c = WORKSPACE / org / name
        if c.is_dir():
            return c
    return None


def _detect_langs(local: Path | None) -> dict:
    if not local:
        return {}
    counts: dict[str, int] = defaultdict(int)
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".build"}
    def walk(p: Path, d: int = 0) -> None:
        if d > 3:
            return
        try:
            for item in p.iterdir():
                if item.name in skip:
                    continue
                if item.is_file():
                    lang = LANG_EXTS.get(item.suffix)
                    if lang:
                        counts[lang] += 1
                elif item.is_dir() and not item.name.startswith("."):
                    walk(item, d + 1)
        except PermissionError:
            pass
    walk(local)
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def _stale_days(entry: dict) -> int:
    import datetime
    lv = entry.get("last_validated", "")
    if not lv:
        return -1
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(str(lv))).days
    except (ValueError, TypeError):
        return -1


def _scaffold_info(local: Path | None) -> dict:
    if not local:
        return {}
    readme = local / "README.md"
    wc = len(readme.read_text(errors="replace").split()) if readme.is_file() else 0
    return {
        "readme_words": wc,
        "has_readme": readme.is_file(),
        "has_gitignore": (local / ".gitignore").is_file(),
        "has_license": any((local / f).is_file() for f in ("LICENSE", "LICENSE.md", "LICENSE.txt")),
        "has_changelog": (local / "CHANGELOG.md").is_file(),
        "has_claude_md": (local / "CLAUDE.md").is_file(),
        "has_contributing": any((local / f).is_file() for f in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md")),
    }


def _next_action(gate: str, passed: bool, entry: dict, tier: str) -> str:
    if passed:
        return ""
    actions = {
        "SEED": "Create seed.yaml with schema_version, organ, repo",
        "SCAFFOLD": "Add README.md and .gitignore",
        "CI": "Add .github/workflows/ci.yml",
        "TESTS": "Create tests/ with initial test file" if tier != "flagship" else "Add >=10 test files (flagship)",
        "DOCS": f"Expand README to >={_DOCS_THRESHOLD.get(tier, 500)} words + add CHANGELOG.md",
        "PROTO": f"Advance implementation from {entry.get('implementation_status', '?')} to PROTOTYPE+",
        "CAND": f"Promote from {entry.get('promotion_status', '?')} to CANDIDATE",
        "DEPLOY": "Deploy and set deployment_url in registry",
        "GRAD": f"Promote from {entry.get('promotion_status', '?')} to GRADUATED",
        "OMEGA": "Clear all gates + set platinum_status=true",
    }
    return actions.get(gate, "")


def _eval_gate(gate: str, entry: dict, local: Path | None, tier: str, scaf: dict) -> dict:
    if gate == "SEED":
        if local:
            sp = local / "seed.yaml"
            if sp.is_file():
                return {"name": "SEED", "passed": True, "detail": "seed.yaml present"}
            return {"name": "SEED", "passed": False, "detail": "seed.yaml missing"}
        return {"name": "SEED", "passed": True, "detail": "in registry"}

    if gate == "SCAFFOLD":
        if local:
            ok = scaf.get("has_readme", False) and scaf.get("has_gitignore", False)
            parts = []
            if scaf.get("has_readme"):
                parts.append(f"README({scaf.get('readme_words', 0)}w)")
            if scaf.get("has_gitignore"):
                parts.append(".gitignore")
            if scaf.get("has_license"):
                parts.append("LICENSE")
            if scaf.get("has_claude_md"):
                parts.append("CLAUDE.md")
            return {"name": "SCAFFOLD", "passed": ok, "detail": ", ".join(parts) or "missing"}
        doc = entry.get("documentation_status", "")
        return {"name": "SCAFFOLD", "passed": bool(doc) and doc not in ("", "NONE"), "detail": f"doc={doc}"}

    if gate == "CI":
        reg_ci = entry.get("ci_workflow")
        if local:
            wf = local / ".github" / "workflows"
            local_ok = wf.is_dir() and any(wf.glob("*.yml"))
            passed = bool(reg_ci) and local_ok
            disc = "registry/local mismatch" if bool(reg_ci) != local_ok else ""
            return {"name": "CI", "passed": passed, "detail": reg_ci or "none", "discrepancy": disc}
        return {"name": "CI", "passed": bool(reg_ci), "detail": reg_ci or "none"}

    if gate == "TESTS":
        min_t = 10 if tier == "flagship" else 1
        if local:
            count = 0
            for td in ("tests", "__tests__", "test", "spec"):
                d = local / td
                if d.is_dir():
                    count += sum(1 for _ in d.rglob("*.py")) + sum(1 for _ in d.rglob("*.ts")) + sum(1 for _ in d.rglob("*.js"))
            detail = f"{count} files" + (f" (need {min_t})" if count < min_t else "")
            return {"name": "TESTS", "passed": count >= min_t, "detail": detail}
        return {"name": "TESTS", "passed": False, "detail": "no local"}

    if gate == "DOCS":
        doc = entry.get("documentation_status", "")
        reg_ok = doc in ("DEPLOYED", "FLAGSHIP README DEPLOYED")
        thresh = _DOCS_THRESHOLD.get(tier, 500)
        if local:
            wc = scaf.get("readme_words", 0)
            cl = scaf.get("has_changelog", False)
            local_ok = wc >= thresh and cl
            return {"name": "DOCS", "passed": reg_ok or local_ok, "detail": f"{wc}w/{thresh} {'+ CL' if cl else ''}"}
        return {"name": "DOCS", "passed": reg_ok, "detail": doc}

    if gate == "PROTO":
        impl = entry.get("implementation_status", "SKELETON")
        return {"name": "PROTO", "passed": _IMPL_ORDER.get(impl, 0) >= _IMPL_ORDER["PROTOTYPE"], "detail": impl}

    if gate == "CAND":
        promo = entry.get("promotion_status", "LOCAL")
        return {"name": "CAND", "passed": _PROMO_ORDER.get(promo, 0) >= 1, "detail": promo}

    if gate == "DEPLOY":
        url = entry.get("deployment_url", "")
        platform = entry.get("deployment_platform", "")
        detail = url or "none"
        if platform:
            detail += f" ({platform})"
        return {"name": "DEPLOY", "passed": bool(url), "detail": detail}

    if gate == "GRAD":
        promo = entry.get("promotion_status", "LOCAL")
        return {"name": "GRAD", "passed": _PROMO_ORDER.get(promo, 0) >= 3, "detail": promo}

    if gate == "OMEGA":
        plat = entry.get("platinum_status", False)
        return {"name": "OMEGA", "passed": plat, "detail": "platinum" if plat else "not platinum"}

    return {"name": gate, "passed": False, "detail": "unknown"}


def _promo_ready(gates: list[dict], promo: str) -> bool:
    current = _PROMO_ORDER.get(promo, 0)
    app = {g["name"]: g for g in gates if g.get("applicable")}
    if current == 0:
        return all(app.get(g, {}).get("passed", False) for g in ("SEED", "SCAFFOLD", "CI") if g in app)
    if current == 1:
        return all(app.get(g, {}).get("passed", False) for g in ("SEED", "SCAFFOLD", "CI", "TESTS", "DOCS", "PROTO") if g in app)
    if current == 2:
        return all(g["passed"] for g in gates if g.get("applicable") and g["name"] != "OMEGA")
    return False


def _next_promo(promo: str) -> str:
    _rev = {v: k for k, v in _PROMO_ORDER.items() if v >= 0}
    return _rev.get(_PROMO_ORDER.get(promo, 0) + 1, "GRADUATED")


def evaluate_all_for_dashboard(registry: dict) -> list[dict]:
    results = []
    for organ_id, organ_data in registry.get("organs", {}).items():
        organ_name = organ_data.get("name", organ_id)
        for entry in organ_data.get("repositories", []):
            local = _find_local(entry, organ_id)
            profile = _detect_profile(entry, local)
            skip = PROFILES[profile]
            tier = entry.get("tier", "standard")
            promo = entry.get("promotion_status", "LOCAL")
            scaf = _scaffold_info(local)
            langs = _detect_langs(local)
            stale = _stale_days(entry)

            gates = []
            for g in GATE_ORDER:
                if g in skip:
                    gates.append({"name": g, "passed": False, "applicable": False, "detail": "N/A", "next_action": ""})
                else:
                    ev = _eval_gate(g, entry, local, tier, scaf)
                    ev["applicable"] = True
                    ev["next_action"] = _next_action(g, ev["passed"], entry, tier)
                    gates.append(ev)

            # OMEGA: require all prior applicable gates
            applicable_prior = [x for x in gates[:-1] if x["applicable"]]
            if gates[-1]["applicable"]:
                all_ok = all(x["passed"] for x in applicable_prior) and gates[-1]["passed"]
                gates[-1]["passed"] = all_ok
                if not all_ok:
                    failed = [x["name"] for x in applicable_prior if not x["passed"]]
                    gates[-1]["next_action"] = f"Clear: {', '.join(failed)}" if failed else "Set platinum_status"

            score = sum(1 for x in gates if x["applicable"] and x["passed"])
            total = sum(1 for x in gates if x["applicable"])
            ready = _promo_ready(gates, promo)

            # Collect discrepancies
            discs = [g for g in gates if g.get("discrepancy")]

            results.append({
                "repo": entry.get("name", "?"),
                "organ": organ_id,
                "organ_name": organ_name,
                "tier": tier,
                "profile": profile,
                "promo": promo,
                "impl": entry.get("implementation_status", "?"),
                "description": entry.get("description", ""),
                "deployment_url": entry.get("deployment_url", ""),
                "platinum": entry.get("platinum_status", False),
                "revenue_model": entry.get("revenue_model", ""),
                "revenue_status": entry.get("revenue_status", ""),
                "gates": gates,
                "score": score,
                "total": total,
                "pct": int(score / total * 100) if total else 0,
                "languages": langs,
                "primary_lang": max((k for k in langs if k not in ("Markdown", "YAML", "JSON")), key=lambda k: langs[k], default="none") if langs else "none",
                "stale_days": stale,
                "is_stale": stale > _STALE_CRIT,
                "is_warn_stale": _STALE_WARN < stale <= _STALE_CRIT,
                "scaffold": scaf,
                "promo_ready": ready,
                "next_promo": _next_promo(promo),
                "discrepancies": discs,
                "blockers": [f"{g['name']}: {g['detail']}" for g in gates if g["applicable"] and not g["passed"]],
                "next_actions": [g["next_action"] for g in gates if g["applicable"] and not g["passed"] and g.get("next_action")],
            })
    return results


# ---------------------------------------------------------------------------
# Cached project evaluation
# ---------------------------------------------------------------------------

def _get_registry_mtime() -> float | None:
    path = _registry_path()
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def clear_progress_cache() -> None:
    with _PROGRESS_CACHE_LOCK:
        _PROGRESS_CACHE["projects"] = None
        _PROGRESS_CACHE["loaded_at"] = 0.0
        _PROGRESS_CACHE["registry_mtime"] = None


def get_progress_projects() -> list[dict]:
    now = time.monotonic()
    current_mtime = _get_registry_mtime()

    with _PROGRESS_CACHE_LOCK:
        cached_projects = _PROGRESS_CACHE["projects"]
        loaded_at = float(_PROGRESS_CACHE["loaded_at"])
        cached_mtime = _PROGRESS_CACHE["registry_mtime"]
        if (
            isinstance(cached_projects, list)
            and now - loaded_at < _PROGRESS_CACHE_TTL_SECONDS
            and cached_mtime == current_mtime
        ):
            return cached_projects

    registry = load_registry()
    projects = evaluate_all_for_dashboard(registry)

    with _PROGRESS_CACHE_LOCK:
        _PROGRESS_CACHE["projects"] = projects
        _PROGRESS_CACHE["loaded_at"] = now
        _PROGRESS_CACHE["registry_mtime"] = current_mtime

    return projects


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def progress_page(request: Request):
    projects = get_progress_projects()

    organs: dict[str, list[dict]] = defaultdict(list)
    for p in projects:
        organs[p["organ"]].append(p)

    organ_order = [
        "ORGAN-I", "ORGAN-II", "ORGAN-III", "ORGAN-IV",
        "ORGAN-V", "ORGAN-VI", "ORGAN-VII", "META-ORGANVM",
    ]
    organ_summaries = []
    for oid in organ_order:
        projs = organs.get(oid, [])
        if not projs:
            continue
        avg_pct = sum(p["pct"] for p in projs) / len(projs)
        ready = sum(1 for p in projs if p["promo_ready"])
        stale = sum(1 for p in projs if p["is_stale"])
        organ_summaries.append({
            "id": oid,
            "name": projs[0]["organ_name"],
            "repos": sorted(projs, key=lambda x: (-x["pct"], -x["score"], x["repo"])),
            "count": len(projs),
            "avg_pct": int(avg_pct),
            "promo_ready": ready,
            "stale": stale,
        })

    total = len(projects)
    sys_pct = int(sum(p["pct"] for p in projects) / total) if total else 0
    profile_counts = dict(Counter(p["profile"] for p in projects).most_common())
    promo_counts = dict(Counter(p["promo"] for p in projects).most_common())
    lang_counts = dict(Counter(p["primary_lang"] for p in projects if p["primary_lang"] != "none").most_common(6))
    total_discs = sum(len(p["discrepancies"]) for p in projects)
    total_stale = sum(1 for p in projects if p["is_stale"])
    total_ready = sum(1 for p in projects if p["promo_ready"])

    # Gate pass rates
    gate_stats = []
    for g in GATE_ORDER:
        applicable = [p for p in projects if any(x["name"] == g and x["applicable"] for x in p["gates"])]
        passed = [p for p in applicable if any(x["name"] == g and x["passed"] for x in p["gates"])]
        rate = int(len(passed) / len(applicable) * 100) if applicable else 0
        gate_stats.append({"name": g, "applicable": len(applicable), "passed": len(passed),
                           "failed": len(applicable) - len(passed), "rate": rate})

    return request.app.state.templates.TemplateResponse(
        request,
        name="progress.html",
        context={
            "page_title": "Progress",
            "organs": organ_summaries,
            "total_repos": total,
            "sys_pct": sys_pct,
            "profile_counts": profile_counts,
            "promo_counts": promo_counts,
            "lang_counts": lang_counts,
            "gate_stats": gate_stats,
            "gate_names": GATE_ORDER,
            "total_discs": total_discs,
            "total_stale": total_stale,
            "total_ready": total_ready,
        },
    )


@router.get("/repo/{repo_name}", response_class=HTMLResponse)
async def progress_repo_detail(request: Request, repo_name: str):
    projects = get_progress_projects()
    matches = [p for p in projects if p["repo"] == repo_name]
    if not matches:
        matches = [p for p in projects if repo_name.lower() in p["repo"].lower()]
    if not matches:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(f"Repo '{repo_name}' not found", status_code=404)

    p = matches[0]
    return request.app.state.templates.TemplateResponse(
        request,
        name="progress_detail.html",
        context={"page_title": f"Progress: {p['repo']}", "project": p, "gate_names": GATE_ORDER},
    )


@router.get("/api")
async def progress_api():
    projects = get_progress_projects()
    return {
        "total": len(projects),
        "sys_pct": int(sum(p["pct"] for p in projects) / len(projects)) if projects else 0,
        "profiles": dict(Counter(p["profile"] for p in projects).most_common()),
        "projects": projects,
    }


@router.get("/api/repo/{repo_name}")
async def progress_api_repo(repo_name: str):
    projects = get_progress_projects()
    matches = [p for p in projects if p["repo"] == repo_name]
    if not matches:
        matches = [p for p in projects if repo_name.lower() in p["repo"].lower()]
    if not matches:
        return {"error": f"Repo '{repo_name}' not found"}
    return matches[0]


@router.get("/api/gates")
async def progress_api_gates():
    projects = get_progress_projects()
    stats = []
    for g in GATE_ORDER:
        applicable = [p for p in projects if any(x["name"] == g and x["applicable"] for x in p["gates"])]
        passed = [p for p in applicable if any(x["name"] == g and x["passed"] for x in p["gates"])]
        failed_repos = [p["repo"] for p in applicable if not any(x["name"] == g and x["passed"] for x in p["gates"])]
        stats.append({
            "name": g, "applicable": len(applicable), "passed": len(passed),
            "failed": len(applicable) - len(passed),
            "rate": int(len(passed) / len(applicable) * 100) if applicable else 0,
            "failing_repos": failed_repos,
        })
    return {"gates": stats}


@router.get("/api/blockers")
async def progress_api_blockers():
    projects = get_progress_projects()
    return {
        "ready": [{"repo": p["repo"], "organ": p["organ"], "promo": p["promo"], "next": p["next_promo"]}
                  for p in projects if p["promo_ready"] and p["promo"] != "GRADUATED"],
        "blocked": [{"repo": p["repo"], "organ": p["organ"], "promo": p["promo"],
                      "blockers": p["blockers"], "next_actions": p["next_actions"]}
                    for p in projects if not p["promo_ready"] and p["promo"] not in ("GRADUATED", "ARCHIVED")],
    }
