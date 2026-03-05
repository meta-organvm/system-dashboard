"""Tests for progress route cache behavior."""

from dashboard.routes import progress


def test_progress_cache_hit_within_ttl(monkeypatch):
    progress.clear_progress_cache()
    calls = {"count": 0}
    clock = {"value": 100.0}

    def fake_eval(registry):
        calls["count"] += 1
        return [{"repo": "alpha", "registry": registry.get("marker")}]

    monkeypatch.setattr(progress, "_PROGRESS_CACHE_TTL_SECONDS", 30)
    monkeypatch.setattr(progress, "_get_registry_mtime", lambda: 123.0)
    monkeypatch.setattr(progress, "load_registry", lambda: {"marker": "r1"})
    monkeypatch.setattr(progress, "evaluate_all_for_dashboard", fake_eval)
    monkeypatch.setattr(progress.time, "monotonic", lambda: clock["value"])

    first = progress.get_progress_projects()
    clock["value"] = 110.0
    second = progress.get_progress_projects()

    assert first == second
    assert calls["count"] == 1


def test_progress_cache_expires_by_ttl(monkeypatch):
    progress.clear_progress_cache()
    calls = {"count": 0}
    clock = {"value": 10.0}

    def fake_eval(_registry):
        calls["count"] += 1
        return [{"repo": f"pass-{calls['count']}"}]

    monkeypatch.setattr(progress, "_PROGRESS_CACHE_TTL_SECONDS", 5)
    monkeypatch.setattr(progress, "_get_registry_mtime", lambda: 456.0)
    monkeypatch.setattr(progress, "load_registry", lambda: {})
    monkeypatch.setattr(progress, "evaluate_all_for_dashboard", fake_eval)
    monkeypatch.setattr(progress.time, "monotonic", lambda: clock["value"])

    first = progress.get_progress_projects()
    clock["value"] = 20.0
    second = progress.get_progress_projects()

    assert first != second
    assert calls["count"] == 2


def test_progress_cache_invalidates_on_registry_mtime_change(monkeypatch):
    progress.clear_progress_cache()
    calls = {"count": 0}
    clock = {"value": 200.0}
    mtimes = [100.0, 100.0, 200.0]

    def fake_mtime():
        return mtimes.pop(0)

    def fake_eval(_registry):
        calls["count"] += 1
        return [{"repo": f"snapshot-{calls['count']}"}]

    monkeypatch.setattr(progress, "_PROGRESS_CACHE_TTL_SECONDS", 60)
    monkeypatch.setattr(progress, "_get_registry_mtime", fake_mtime)
    monkeypatch.setattr(progress, "load_registry", lambda: {})
    monkeypatch.setattr(progress, "evaluate_all_for_dashboard", fake_eval)
    monkeypatch.setattr(progress.time, "monotonic", lambda: clock["value"])

    first = progress.get_progress_projects()
    second = progress.get_progress_projects()
    clock["value"] = 205.0
    third = progress.get_progress_projects()

    assert first == second
    assert third != second
    assert calls["count"] == 2
