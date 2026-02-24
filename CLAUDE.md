# CLAUDE.md — system-dashboard

**ORGAN Meta** (Meta) · `meta-organvm/system-dashboard`
**Status:** ACTIVE · **Branch:** `main`

## What This Repo Is

Live system health dashboard — FastAPI + Jinja2 + HTMX with brutalist CMYK design. 6 pages: health overview, registry browser, dependency graph, soak test monitoring, essay feed, omega scorecard.

## Stack

**Languages:** Python, HTML
**Build:** Python (pip/setuptools)
**Testing:** pytest (likely)

## Directory Structure

```
📁 .github/
📁 src/
    dashboard
📁 tests/
    __init__.py
    test_app.py
  CHANGELOG.md
  README.md
  pyproject.toml
  seed.yaml
```

## Key Files

- `README.md` — Project documentation
- `pyproject.toml` — Python project config
- `seed.yaml` — ORGANVM orchestration metadata
- `src/` — Main source code
- `tests/` — Test suite

## Development

```bash
pip install -e .    # Install in development mode
pytest              # Run tests
```

## ORGANVM Context

This repository is part of the **ORGANVM** eight-organ creative-institutional system.
It belongs to **ORGAN Meta (Meta)** under the `meta-organvm` GitHub organization.

**Dependencies:**
- meta-organvm/organvm-engine
- meta-organvm/organvm-corpvs-testamentvm

**Registry:** [`registry-v2.json`](https://github.com/meta-organvm/organvm-corpvs-testamentvm/blob/main/registry-v2.json)
**Corpus:** [`organvm-corpvs-testamentvm`](https://github.com/meta-organvm/organvm-corpvs-testamentvm)

<!-- ORGANVM:AUTO:START -->
## System Context (auto-generated — do not edit)

**Organ:** META-ORGANVM (Meta) | **Tier:** standard | **Status:** CANDIDATE
**Org:** `unknown` | **Repo:** `system-dashboard`

### Edges
- **Produces** → `unknown`: unknown
- **Consumes** ← `organvm-corpvs-testamentvm`: unknown
- **Consumes** ← `organvm-corpvs-testamentvm`: unknown
- **Consumes** ← `organvm-corpvs-testamentvm`: unknown

### Siblings in Meta
`.github`, `organvm-corpvs-testamentvm`, `alchemia-ingestvm`, `schema-definitions`, `organvm-engine`, `organvm-mcp-server`

### Governance
- *Standard ORGANVM governance applies*

*Last synced: 2026-02-24T12:41:28Z*
<!-- ORGANVM:AUTO:END -->
