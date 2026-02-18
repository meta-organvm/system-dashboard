"""Load system data from the corpus repo and organvm-engine."""

import json
import os
from pathlib import Path

CORPUS_DIR = Path(os.environ.get(
    "ORGANVM_CORPUS_DIR",
    str(Path.home() / "Workspace" / "meta-organvm" / "organvm-corpvs-testamentvm"),
))


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning empty dict on failure."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def load_registry() -> dict:
    """Load registry-v2.json."""
    return _load_json(CORPUS_DIR / "registry-v2.json")


def load_metrics() -> dict:
    """Load system-metrics.json."""
    return _load_json(CORPUS_DIR / "system-metrics.json")


def load_governance_rules() -> dict:
    """Load governance-rules.json."""
    return _load_json(CORPUS_DIR / "governance-rules.json")


def load_soak_snapshots() -> list[dict]:
    """Load all soak test snapshots sorted by date."""
    soak_dir = CORPUS_DIR / "data" / "soak-test"
    if not soak_dir.is_dir():
        return []
    snapshots = []
    for path in sorted(soak_dir.glob("daily-*.json")):
        snapshots.append(_load_json(path))
    return snapshots


def load_essays() -> list[dict]:
    """List essay files from the corpus."""
    essays_dir = CORPUS_DIR / "essays"
    if not essays_dir.is_dir():
        # Try _posts for Jekyll
        essays_dir = CORPUS_DIR / "_posts"
    if not essays_dir.is_dir():
        return []

    essays = []
    for md in sorted(essays_dir.rglob("*.md")):
        title = md.stem.replace("-", " ").title()
        essays.append({
            "file": md.name,
            "title": title,
            "path": str(md.relative_to(CORPUS_DIR)),
        })
    return essays


def organ_summary(registry: dict) -> list[dict]:
    """Build per-organ summary for display."""
    organs = registry.get("organs", {})
    result = []
    for key, data in organs.items():
        repos = data.get("repositories", [])
        active = sum(1 for r in repos if r.get("implementation_status") != "ARCHIVED")
        flagships = sum(1 for r in repos if r.get("tier") == "flagship")
        result.append({
            "key": key,
            "name": data.get("name", key),
            "status": data.get("launch_status", "UNKNOWN"),
            "total": len(repos),
            "active": active,
            "flagships": flagships,
        })
    return result
