# auto-scrapy

`4-auto-scrapy/` is the formal implementation directory for the local-first
CS/AI web knowledge harvester.

The runtime is a Python pipeline. OpenClaw is optional as a natural-language
control layer, but it is not the main crawler runtime.

## 1. Current Status

Current implementation status:

- M1-M10 implementation work is present in this directory.
- The development laptop has code, tests, source configs, Flask UI, runtime
  entrypoints, and systemd unit templates.
- The target 1080 Ti machine has now reached the point where the
  `auto-scrapy-runtime.service` and `auto-scrapy-runtime.timer` setup worked.
- Long-running target-machine stability is not yet complete. The next work is
  controlled target observation, source tuning, extraction quality tuning, and
  safe capped analysis.

Important interpretation:

```text
systemd worked on the target machine
does not yet mean
the whole 24/7 production system has been long-run validated
```

The project should currently be understood as:

```text
A functioning local-first CS/AI collection pipeline with target-machine
systemd scheduling proven at the basic service/timer level, but still needing
longer target observation and source/extraction quality refinement.
```

## 2. Fixed Architecture

The project architecture is fixed unless explicitly changed by a later
decision:

```text
source config
-> discovery
-> documents table
-> fetch
-> data/raw/
-> extract
-> data/cleaned/
-> optional analysis
-> data/derived/
-> Flask browse / runtime observe
```

Hard boundaries:

- Discovery is not fetch.
- Fetch is not extract.
- Extract is not analysis.
- Flask is not the scheduler.
- OpenClaw is not the main crawler loop.
- SQLite stores metadata and paths, not large article bodies.
- Raw, cleaned, derived, and logs stay separated on disk.
- Scrapy is the primary fetch path.
- Playwright is an escalation path only when necessary.
- systemd provides persistence and scheduling outside Flask.

## 3. What Has Been Done

The current project contains these completed implementation areas:

| Area | Status |
|---|---|
| Project scaffold | Python package, `pyproject.toml`, app modules, tests, config, scripts |
| Config loading | `app/config.py` loads paths, source config, Ollama settings, and storage locations |
| SQLite metadata index | `app/db.py` creates and updates core metadata tables |
| Discovery | RSS, sitemap, seed URL expansion, `llms.txt`, source allow/deny patterns |
| Fetch | Scrapy-first raw fetch, retry settings, conditional headers, raw artifact storage |
| Extract | Trafilatura-first HTML extraction plus fallback and textlike extraction |
| Versioning | Derived artifact version storage through `document_versions` |
| Analysis | Local Ollama `summary_draft` generation with repeat-run skip behavior |
| Flask UI | Local browsing for documents, sources, runs, artifacts, and versions |
| Runtime | Bounded `app.runtime` pipeline outside Flask |
| Runtime lock | `data/runtime.lock` prevents overlapping runtime jobs |
| Regression script | `scripts/run_regression.py` runs the stable smoke-test sequence |
| systemd | `auto-scrapy-runtime.service` and `.timer` exist and have worked on the target machine |

## 4. Important Current Files

```text
4-auto-scrapy/
  app/
    __init__.py
    config.py
    db.py
    discovery.py
    fetch.py
    extract.py
    versioning.py
    analysis.py
    routes.py
    runtime.py
    templates/
  config/
    sources/
      target_smoke_sources.toml
      demo_sources.toml
      api_candidates.toml
    prompts/
      summary_draft_v1.txt
  scripts/
    run_regression.py
  systemd/
    auto-scrapy-runtime.service
    auto-scrapy-runtime.timer
  tests/
    test_db_smoke.py
    test_discovery_smoke.py
    test_fetch_smoke.py
    test_extract_smoke.py
    test_versioning_smoke.py
    test_ui_smoke.py
    test_analysis_smoke.py
    test_runtime_smoke.py
    test_target_smoke_live_connectivity.py
  DEPLOY_TARGET.md
  project-agent-rules.md
  pyproject.toml
  README.md
```

Generated or local runtime areas also exist, but should not be treated as code:

```text
data/
instance/
.venv/
.pytest_cache/
__pycache__/
```

## 5. Module Responsibilities

| Module | Responsibility |
|---|---|
| `app/config.py` | Load settings and resolve storage/config paths |
| `app/db.py` | SQLite schema, connections, source/document/run/version helpers |
| `app/discovery.py` | Load source definitions and discover candidate document URLs |
| `app/fetch.py` | Fetch discovered documents and persist raw artifacts |
| `app/extract.py` | Extract cleaned text/markdown from raw artifacts |
| `app/versioning.py` | Store derived artifacts and connect them to document versions |
| `app/analysis.py` | Generate local Ollama `summary_draft` artifacts |
| `app/routes.py` | Flask browser routes for local inspection |
| `app/runtime.py` | Run the bounded pipeline outside Flask |

Main runtime chain:

```text
run_discovery()
-> run_fetch()
-> run_extract()
-> run_summary_draft() unless --skip-analysis is used
```

## 6. Data Model

SQLite core tables:

| Table | Purpose |
|---|---|
| `sources` | Source definitions and config provenance |
| `documents` | Canonical URL index, current raw/cleaned pointers, statuses |
| `document_versions` | Derived artifact records such as `summary_draft` |
| `crawl_runs` | Discovery/fetch/extract/analysis/runtime run records and errors |
| `tags` | Lightweight tag table reserved for later use |

Storage layout:

```text
data/raw/      raw fetched payloads
data/cleaned/  cleaned markdown/text
data/derived/  AI or later-stage derived artifacts
data/logs/     runtime and stage logs
```

Large article bodies belong on disk, not inside SQLite.

## 7. Source Configs

The production source pool is:

```text
config/sources/target_smoke_sources.toml
```

The word `smoke` in that filename is historical. It is currently the formal
target source pool.

The fixture/regression source config is:

```text
config/sources/demo_sources.toml
```

Source config resolution order:

1. `--config-path`
2. `AUTO_SCRAPY_SOURCES_CONFIG_PATH`
3. `config/sources/target_smoke_sources.toml`
4. `config/sources/demo_sources.toml` only if the target config is absent

Current source pool includes arXiv RSS feeds, AI/ML blogs, docs indexes, and
seed sources such as OpenAI, Anthropic, Hugging Face, PyTorch, Google Research,
DeepMind, GitHub, Distill, Colah, Lilian Weng, Jay Alammar, MCP docs,
LangChain, LangGraph, and LlamaIndex.

## 8. Common Development Commands

Run from `4-auto-scrapy/`.

Install/update dependencies:

```powershell
uv sync
```

Create/check the Flask app:

```powershell
uv run python -c "from app import create_app; app = create_app(); print(app.import_name)"
```

Initialize SQLite metadata:

```powershell
uv run python -c "from app.db import init_db; print(init_db())"
```

Run Flask UI:

```powershell
uv run flask --app app run
```

Run bounded runtime once:

```powershell
uv run python -m app.runtime
```

Run collection only, without Ollama analysis:

```powershell
uv run python -m app.runtime --skip-analysis
```

Run capped analysis:

```powershell
uv run python -m app.runtime --analysis-limit-per-source 5
```

Run one or more selected sources:

```powershell
uv run python -m app.runtime --source-key openai-news --skip-analysis
uv run python -m app.runtime --source-key openai-news --source-key pytorch-blog --skip-analysis
```

Show runtime CLI help:

```powershell
uv run python -m app.runtime --help
```

Run the stable smoke-test sequence:

```powershell
uv run python scripts/run_regression.py
```

## 9. Tests

Current smoke tests:

| Test file | Coverage |
|---|---|
| `tests/test_db_smoke.py` | SQLite schema and minimal metadata behavior |
| `tests/test_discovery_smoke.py` | Source loading, RSS/sitemap/seed discovery, filters, failure handling |
| `tests/test_fetch_smoke.py` | Raw fetch, Scrapy settings, retries, conditional fetch |
| `tests/test_extract_smoke.py` | Cleaned artifact extraction and low-quality rejection |
| `tests/test_versioning_smoke.py` | Derived artifact version storage |
| `tests/test_ui_smoke.py` | Flask browsing and artifact path safety |
| `tests/test_analysis_smoke.py` | Ollama summary draft flow and unchanged-content skip |
| `tests/test_runtime_smoke.py` | Pipeline orchestration, source subsets, runtime lock |
| `tests/test_target_smoke_live_connectivity.py` | Live connectivity-oriented target source checks |

Recommended normal development check:

```powershell
uv run python scripts/run_regression.py
```

Use `tests/test_target_smoke_live_connectivity.py` carefully because it is
network-facing and depends on live target source behavior.

## 10. Runtime And Logs

Runtime behavior:

```text
app.runtime starts
-> creates/uses data/runtime.lock
-> runs configured stages
-> writes stage/runtime logs
-> releases lock when finished
```

`data/runtime.lock` is not a schedule. It is an overlap guard:

```text
runtime.lock prevents two runtime jobs from entering the main pipeline together
```

It does not prevent frequent logs if the timer is configured to run too often.
Timer cadence is controlled by the `.timer` file.

Useful local log/status locations:

```text
data/logs/
SQLite crawl_runs table
Flask /runs and /runs/<id>
```

## 11. systemd Current Status

Target-machine status reported by the operator:

```text
auto-scrapy-runtime.service and auto-scrapy-runtime.timer worked on the target machine.
```

Current checked-in systemd files:

```text
systemd/auto-scrapy-runtime.service
systemd/auto-scrapy-runtime.timer
```

Current service role:

```text
Run the bounded auto-scrapy runtime command from /opt/247-data-collector.
```

Current timer role:

```text
Trigger auto-scrapy-runtime.service on a configured schedule.
```

Human-readable timer rule summary:

```text
OnActiveSec      = after manually starting the timer, wait this long before the first run
OnUnitActiveSec  = after the service has been activated, wait this long before the next run
OnBootSec        = after boot / user systemd start, wait this long before a run
```

Operational warning:

```text
OnUnitActiveSec=1m is only for short tests.
It can produce many repeated runs and many logs.
For normal operation, use a longer interval such as 2h or 3h.
```

Useful target-machine checks:

```bash
systemctl --user daemon-reload
systemctl --user restart auto-scrapy-runtime.timer
systemctl --user list-timers auto-scrapy-runtime.timer
systemctl --user status auto-scrapy-runtime.timer
systemctl --user status auto-scrapy-runtime.service
journalctl --user -u auto-scrapy-runtime.service -n 100 --no-pager
```

For live logs:

```bash
journalctl --user -u auto-scrapy-runtime.service -f
```

Stop live log following with `Ctrl+C`.

## 12. Development Laptop vs Target Machine

Development laptop:

- Used for Codex work, editing, smoke tests, source tuning, and documentation.
- May run authoring-level checks.
- Should not be described as proof of target deployment stability.

Target 1080 Ti machine:

- Used for real runtime execution, real dependency install, systemd behavior,
  long-running collection, Ollama behavior, and GPU observation.
- Does not assume Codex is available.
- Has now shown that the systemd service/timer path can work.
- Still needs controlled long-run observation and capped analysis validation.

## 13. Further Improvement

The next improvements should stay inside the existing architecture.

| Area | Improvement | Reason |
|---|---|---|
| systemd observation | Watch several target timer cycles with a safe interval | Confirm repeated target operation without excessive logs |
| Timer cadence | Avoid 1-minute schedules except for brief tests | Prevent repeated arXiv/source logs |
| Source configs | Tune allow/deny patterns from real collected URLs | Improve dataset quality without code changes |
| Extraction quality | Inspect repeated `partial_failure` sources before adding narrow fallbacks | Avoid weakening global extraction rules |
| Analysis | Run capped analysis manually before any analysis timer | Protect 1080 Ti thermals and avoid uncapped GPU work |
| Logs | Review `data/logs/` and `crawl_runs` after each target run | Make failures visible and actionable |
| README/DEPLOY_TARGET consistency | Keep README as current project overview and DEPLOY_TARGET as target deployment detail | Prevent status drift |

## 14. Next Move

Recommended next development move after the current systemd success:

1. On the target machine, run the timer with a safe interval such as `2h` or
   `3h`, not `1m`.
2. Observe at least a few service activations:

   ```bash
   systemctl --user list-timers auto-scrapy-runtime.timer
   journalctl --user -u auto-scrapy-runtime.service -n 100 --no-pager
   ```

3. Confirm that new artifacts appear under:

   ```text
   data/raw/
   data/cleaned/
   data/logs/
   instance/auto_scrapy.sqlite3
   ```

4. Review which sources produce useful cleaned artifacts and which sources
   produce low-quality or repeated failures.
5. Tune `config/sources/target_smoke_sources.toml` allow/deny patterns before
   changing extractor code.
6. Only after collection is stable, run capped analysis manually:

   ```bash
   uv run python -m app.runtime --source-key openai-news --analysis-limit-per-source 2
   ```

7. Decide whether the next milestone is source-quality tuning, extraction
   fallback tuning, or target-machine analysis validation.

Do not schedule uncapped analysis automatically on the 1080 Ti machine yet.

## 15. Related Documents

- `AGENTS.md`: coding-agent discipline for this implementation directory.
- `project-agent-rules.md`: auto-scrapy-specific architecture and command rules.
- `DEPLOY_TARGET.md`: target Ubuntu/1080 Ti deployment guide.
- `user-systemd.md`: user-level systemd notes from prior deployment work.

