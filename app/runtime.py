# from argparse import ArgumentParser
# from dataclasses import asdict, dataclass
# from datetime import datetime, timezone
# from pathlib import Path
# import json

# from .analysis import run_summary_draft
# from .config import load_settings
# from .discovery import run_discovery
# from .extract import run_extract
# from .fetch import run_fetch
# from .db import init_db


# @dataclass(frozen=True)
# class RuntimeStageSummary:
#     stage_name: str
#     source_key: str
#     crawl_run_id: int | None
#     status: str


# @dataclass(frozen=True)
# class RuntimeSourceSummary:
#     source_key: str
#     status: str
#     stages: tuple[RuntimeStageSummary, ...]


# @dataclass(frozen=True)
# class RuntimeRunResult:
#     status: str
#     source_count: int
#     failed_source_count: int
#     log_path: str
#     sources: tuple[RuntimeSourceSummary, ...]


# def _append_log(log_path: Path, payload: dict[str, str | int | None]) -> None:
#     log_path.parent.mkdir(parents=True, exist_ok=True)
#     with log_path.open("a", encoding="utf-8") as handle:
#         handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


# def _build_runtime_log_path(log_dir: Path) -> Path:
#     timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
#     return log_dir / f"runtime-run-{timestamp}.log"


# def run_pipeline_once(
#     *,
#     config_path: Path | None = None,
#     database_path: Path | None = None,
#     raw_dir: Path | None = None,
#     cleaned_dir: Path | None = None,
#     derived_dir: Path | None = None,
#     log_dir: Path | None = None,
#     prompt_path: Path | None = None,
#     model_name: str | None = None,
#     base_url: str | None = None,
#     timeout_seconds: int | None = None,
#     run_discovery_stage=run_discovery,
#     run_fetch_stage=run_fetch,
#     run_extract_stage=run_extract,
#     run_analysis_stage=run_summary_draft,
# ) -> RuntimeRunResult:
#     settings = load_settings()
#     db_path = init_db(database_path)
#     logs_root = Path(log_dir or settings.log_dir)
#     logs_root.mkdir(parents=True, exist_ok=True)
#     runtime_log_path = _build_runtime_log_path(logs_root)
#     stored_runtime_log_path = (Path("data") / "logs" / runtime_log_path.name).as_posix()

#     _append_log(
#         runtime_log_path,
#         {
#             "event": "runtime_started",
#             "database_path": str(db_path),
#             "config_path": str(Path(config_path)) if config_path is not None else None,
#         },
#     )

#     discovery_results = run_discovery_stage(config_path=config_path, database_path=db_path)
#     source_summaries: list[RuntimeSourceSummary] = []
#     failed_source_count = 0

#     for discovery_result in discovery_results:
#         source_key = discovery_result.source_key
#         stage_summaries: list[RuntimeStageSummary] = []
#         source_has_failure = False
#         _append_log(
#             runtime_log_path,
#             {
#                 "event": "source_started",
#                 "source_key": source_key,
#                 "discovery_run_id": discovery_result.crawl_run_id,
#                 "discovery_status": "success",
#             },
#         )

#         stage_specs = (
#             (
#                 "fetch",
#                 run_fetch_stage,
#                 {
#                     "source_key": source_key,
#                     "database_path": db_path,
#                     "raw_dir": raw_dir,
#                     "log_dir": log_dir,
#                 },
#             ),
#             (
#                 "extract",
#                 run_extract_stage,
#                 {
#                     "source_key": source_key,
#                     "database_path": db_path,
#                     "raw_dir": raw_dir,
#                     "cleaned_dir": cleaned_dir,
#                     "log_dir": log_dir,
#                 },
#             ),
#             (
#                 "summary_draft",
#                 run_analysis_stage,
#                 {
#                     "source_key": source_key,
#                     "database_path": db_path,
#                     "cleaned_dir": cleaned_dir,
#                     "derived_dir": derived_dir,
#                     "log_dir": log_dir,
#                     "prompt_path": prompt_path,
#                     "model_name": model_name,
#                     "base_url": base_url,
#                     "timeout_seconds": timeout_seconds,
#                 },
#             ),
#         )

#         for stage_name, stage_runner, stage_kwargs in stage_specs:
#             _append_log(
#                 runtime_log_path,
#                 {
#                     "event": "stage_started",
#                     "source_key": source_key,
#                     "stage_name": stage_name,
#                 },
#             )
#             try:
#                 stage_result = stage_runner(**stage_kwargs)
#             except Exception as exc:
#                 source_has_failure = True
#                 stage_summaries.append(
#                     RuntimeStageSummary(
#                         stage_name=stage_name,
#                         source_key=source_key,
#                         crawl_run_id=None,
#                         status="failed",
#                     )
#                 )
#                 _append_log(
#                     runtime_log_path,
#                     {
#                         "event": "stage_failed",
#                         "source_key": source_key,
#                         "stage_name": stage_name,
#                         "error": str(exc),
#                     },
#                 )
#                 break

#             stage_status = str(stage_result.status)
#             crawl_run_id = int(stage_result.crawl_run_id)
#             if stage_status != "success":
#                 source_has_failure = True
#             stage_summaries.append(
#                 RuntimeStageSummary(
#                     stage_name=stage_name,
#                     source_key=source_key,
#                     crawl_run_id=crawl_run_id,
#                     status=stage_status,
#                 )
#             )
#             _append_log(
#                 runtime_log_path,
#                 {
#                     "event": "stage_finished",
#                     "source_key": source_key,
#                     "stage_name": stage_name,
#                     "crawl_run_id": crawl_run_id,
#                     "status": stage_status,
#                     "log_path": getattr(stage_result, "log_path", None),
#                 },
#             )

#         source_status = "partial_failure" if source_has_failure else "success"
#         if source_has_failure:
#             failed_source_count += 1
#         source_summaries.append(
#             RuntimeSourceSummary(
#                 source_key=source_key,
#                 status=source_status,
#                 stages=tuple(stage_summaries),
#             )
#         )
#         _append_log(
#             runtime_log_path,
#             {
#                 "event": "source_finished",
#                 "source_key": source_key,
#                 "status": source_status,
#             },
#         )

#     overall_status = "partial_failure" if failed_source_count else "success"
#     _append_log(
#         runtime_log_path,
#         {
#             "event": "runtime_finished",
#             "status": overall_status,
#             "source_count": len(source_summaries),
#             "failed_source_count": failed_source_count,
#         },
#     )

#     return RuntimeRunResult(
#         status=overall_status,
#         source_count=len(source_summaries),
#         failed_source_count=failed_source_count,
#         log_path=stored_runtime_log_path,
#         sources=tuple(source_summaries),
#     )


# def _build_parser() -> ArgumentParser:
#     parser = ArgumentParser(description="Run the auto-scrapy pipeline once outside Flask.")
#     parser.add_argument("--config-path", type=Path, default=None)
#     parser.add_argument("--database-path", type=Path, default=None)
#     parser.add_argument("--raw-dir", type=Path, default=None)
#     parser.add_argument("--cleaned-dir", type=Path, default=None)
#     parser.add_argument("--derived-dir", type=Path, default=None)
#     parser.add_argument("--log-dir", type=Path, default=None)
#     parser.add_argument("--prompt-path", type=Path, default=None)
#     parser.add_argument("--model-name", default=None)
#     parser.add_argument("--base-url", default=None)
#     parser.add_argument("--timeout-seconds", type=int, default=None)
#     return parser


# def main() -> int:
#     parser = _build_parser()
#     args = parser.parse_args()
#     result = run_pipeline_once(
#         config_path=args.config_path,
#         database_path=args.database_path,
#         raw_dir=args.raw_dir,
#         cleaned_dir=args.cleaned_dir,
#         derived_dir=args.derived_dir,
#         log_dir=args.log_dir,
#         prompt_path=args.prompt_path,
#         model_name=args.model_name,
#         base_url=args.base_url,
#         timeout_seconds=args.timeout_seconds,
#     )
#     print(json.dumps(asdict(result), ensure_ascii=True))
#     return 0 if result.status == "success" else 1


# if __name__ == "__main__":
#     raise SystemExit(main())



























# claude version

from argparse import ArgumentParser
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import multiprocessing
import os
import sys

from .analysis import run_summary_draft
from .config import load_settings
from .discovery import run_discovery
from .extract import run_extract
from .fetch import FetchRunResult
from .db import init_db


@dataclass(frozen=True)
class RuntimeStageSummary:
    stage_name: str
    source_key: str
    crawl_run_id: int | None
    status: str


@dataclass(frozen=True)
class RuntimeSourceSummary:
    source_key: str
    status: str
    stages: tuple[RuntimeStageSummary, ...]


@dataclass(frozen=True)
class RuntimeRunResult:
    status: str
    source_count: int
    failed_source_count: int
    log_path: str
    sources: tuple[RuntimeSourceSummary, ...]
    discovered_new_count: int = 0
    rediscovered_existing_count: int = 0
    fetched_new_count: int = 0
    unchanged_count: int = 0
    extracted_count: int = 0
    summarized_count: int = 0
    skipped_summary_count: int = 0
    failed_count: int = 0


# ---------------------------------------------------------------------------
# Subprocess-isolated fetch
# ---------------------------------------------------------------------------
# run_fetch() internally starts a Twisted Reactor (process-level singleton).
# Once it stops, it cannot be restarted in the same process.
# Calling run_fetch() more than once per process raises ReactorNotRestartable
# (whose __str__ is empty → silent failure with crawl_run_id: null).
#
# Fix: each run_fetch() call runs in its own child process.
#   Windows → "spawn" (no fork available)
#   Linux / Ubuntu prod → "fork" (faster, skips re-import)
# ---------------------------------------------------------------------------
def _fetch_worker(
    source_key: str,
    database_path: str,
    raw_dir: str | None,
    log_dir: str | None,
    log_path: str | None,
    result_queue: "multiprocessing.Queue[tuple[str, object]]",
) -> None:
    """Runs inside the child process. Import of run_fetch is deferred here
    so Twisted globals are never initialised in the parent process."""
    try:
        from app.fetch import run_fetch  # deferred — keeps parent clean

        result = run_fetch(
            source_key=source_key,
            database_path=Path(database_path),
            raw_dir=Path(raw_dir) if raw_dir else None,
            log_dir=Path(log_dir) if log_dir else None,
            log_path=Path(log_path) if log_path else None,
        )
        result_queue.put((
            "ok",
            {
                "source_key": result.source_key,
                "crawl_run_id": result.crawl_run_id,
                "fetched_count": result.fetched_count,
                "failed_count": result.failed_count,
                "needs_browser_count": result.needs_browser_count,
                "browser_fetched_count": result.browser_fetched_count,
                "unchanged_count": result.unchanged_count,
                "log_path": result.log_path,
                "status": result.status,
            },
        ))
    except Exception as exc:
        result_queue.put(("err", f"[{type(exc).__name__}] {exc!r}"))


def _run_fetch_isolated(
    *,
    source_key: str,
    database_path: Path,
    raw_dir: Path | None = None,
    log_dir: Path | None = None,
    log_path: Path | None = None,
    timeout_seconds: int = 120,
) -> FetchRunResult:
    """
    Wraps run_fetch() in a fresh child process to avoid Twisted
    ReactorNotRestartable when multiple sources are processed in sequence.
    Returns a FetchRunResult identical to what run_fetch() would return.
    """
    ctx_name = "spawn" if sys.platform == "win32" else "fork"
    ctx = multiprocessing.get_context(ctx_name)
    queue: "multiprocessing.Queue[tuple[str, object]]" = ctx.Queue()

    process = ctx.Process(
        target=_fetch_worker,
        args=(
            source_key,
            str(database_path),
            str(raw_dir) if raw_dir else None,
            str(log_dir) if log_dir else None,
            str(log_path) if log_path else None,
            queue,
        ),
        daemon=True,
    )
    try:
        process.start()
        process.join(timeout=timeout_seconds)

        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            raise TimeoutError(
                f"run_fetch for '{source_key}' exceeded {timeout_seconds}s timeout"
            )

        if process.exitcode != 0:
            raise RuntimeError(
                f"fetch child process for '{source_key}' exited with code {process.exitcode}"
            )

        try:
            status, payload = queue.get_nowait()
        except Exception:
            raise RuntimeError(
                f"fetch child process for '{source_key}' produced no result (crashed silently)"
            )
    finally:
        queue.close()
        queue.join_thread()
        if hasattr(process, "close"):
            process.close()


    if status == "err":
        raise RuntimeError(payload)

    d = payload  # type: ignore[assignment]
    return FetchRunResult(
        source_key=str(d["source_key"]),
        crawl_run_id=int(d["crawl_run_id"]),
        fetched_count=int(d["fetched_count"]),
        failed_count=int(d["failed_count"]),
        needs_browser_count=int(d["needs_browser_count"]),
        browser_fetched_count=int(d["browser_fetched_count"]),
        unchanged_count=int(d["unchanged_count"]),
        log_path=str(d["log_path"]),
        status=str(d["status"]),
    )


def _open_fd_count() -> int | None:
    fd_root = Path("/proc/self/fd")
    if not fd_root.exists():
        return None
    try:
        return len(os.listdir(fd_root))
    except OSError:
        return None


@contextmanager
def _runtime_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"runtime lock already exists: {lock_path}") from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _prune_old_logs(
    log_dir: Path,
    *,
    max_age_days: int | None = None,
    max_files: int | None = None,
) -> int:
    max_age_days = int(
        os.getenv("AUTO_SCRAPY_LOG_RETENTION_DAYS", str(max_age_days or 14))
    )
    max_files = int(os.getenv("AUTO_SCRAPY_LOG_RETENTION_MAX_FILES", str(max_files or 500)))
    if max_age_days <= 0 and max_files <= 0:
        return 0

    log_files = sorted(
        [path for path in log_dir.glob("*.log") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    protected = set(log_files[:max_files]) if max_files > 0 else set()
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=max_age_days)
        if max_age_days > 0
        else None
    )
    removed_count = 0
    for log_file in log_files:
        if log_file in protected:
            continue
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime, tz=timezone.utc)
        if cutoff is None or mtime < cutoff:
            log_file.unlink()
            removed_count += 1
    return removed_count


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _append_log(log_path: Path, payload: dict[str, str | int | None]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _build_runtime_log_path(log_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return log_dir / f"runtime-run-{timestamp}.log"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline_once(
    *,
    config_path: Path | None = None,
    database_path: Path | None = None,
    raw_dir: Path | None = None,
    cleaned_dir: Path | None = None,
    derived_dir: Path | None = None,
    log_dir: Path | None = None,
    prompt_path: Path | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    timeout_seconds: int | None = None,
    run_analysis: bool = True,
    analysis_limit_per_source: int | None = None,
    source_keys: tuple[str, ...] | None = None,
    run_discovery_stage=run_discovery,
    run_fetch_stage=_run_fetch_isolated,   # ← was run_fetch (Reactor bug)
    run_extract_stage=run_extract,
    run_analysis_stage=run_summary_draft,
) -> RuntimeRunResult:
    settings = load_settings()
    db_path = init_db(database_path)
    logs_root = Path(log_dir or settings.log_dir)
    logs_root.mkdir(parents=True, exist_ok=True)
    runtime_log_path = _build_runtime_log_path(logs_root)
    stored_runtime_log_path = (Path("data") / "logs" / runtime_log_path.name).as_posix()
    lock_path = logs_root.parent / "runtime.lock"

    with _runtime_lock(lock_path):
        pruned_log_count = _prune_old_logs(logs_root)

        _append_log(
            runtime_log_path,
            {
                "event": "runtime_started",
                "database_path": str(db_path),
                "config_path": str(Path(config_path)) if config_path is not None else None,
                "open_fd_count": _open_fd_count(),
                "pruned_log_count": pruned_log_count,
            },
        )

        discovery_kwargs = {
            "config_path": config_path,
            "database_path": db_path,
            "source_keys": source_keys,
        }
        if settings.log_mode == "centralized":
            discovery_kwargs["log_path"] = runtime_log_path

        discovery_results = run_discovery_stage(**discovery_kwargs)
        source_summaries: list[RuntimeSourceSummary] = []
        failed_source_count = 0
        discovered_new_count = 0
        rediscovered_existing_count = 0
        fetched_new_count = 0
        unchanged_count = 0
        extracted_count = 0
        summarized_count = 0
        skipped_summary_count = 0
        failed_count = 0

        for discovery_result in discovery_results:
            source_key = discovery_result.source_key
            discovered_count = int(getattr(discovery_result, "discovered_count", 0))
            inserted_count = int(getattr(discovery_result, "inserted_count", 0))
            discovered_new_count += inserted_count
            rediscovered_existing_count += max(discovered_count - inserted_count, 0)
            stage_summaries: list[RuntimeStageSummary] = []
            source_has_failure = discovery_result.status != "success"
            _append_log(
                runtime_log_path,
                {
                    "event": "source_started",
                    "source_key": source_key,
                    "discovery_run_id": discovery_result.crawl_run_id,
                    "discovery_status": discovery_result.status,
                    "discovered_count": discovered_count,
                    "inserted_count": inserted_count,
                    "rediscovered_existing_count": max(discovered_count - inserted_count, 0),
                },
            )

            if discovery_result.status == "failed":
                failed_source_count += 1
                failed_count += 1
                source_summaries.append(
                    RuntimeSourceSummary(
                        source_key=source_key,
                        status="failed",
                        stages=tuple(),
                    )
                )
                _append_log(
                    runtime_log_path,
                    {
                        "event": "source_finished",
                        "source_key": source_key,
                        "status": "failed",
                    },
                )
                continue

            stage_specs = [
                (
                    "fetch",
                    run_fetch_stage,
                    {
                        "source_key": source_key,
                        "database_path": db_path,
                        "raw_dir": raw_dir,
                        "log_dir": log_dir,
                    },
                ),
                (
                    "extract",
                    run_extract_stage,
                    {
                        "source_key": source_key,
                        "database_path": db_path,
                        "raw_dir": raw_dir,
                        "cleaned_dir": cleaned_dir,
                        "log_dir": log_dir,
                    },
                ),
            ]
            if run_analysis:
                stage_specs.append(
                    (
                    "summary_draft",
                    run_analysis_stage,
                    {
                        "source_key": source_key,
                        "database_path": db_path,
                        "cleaned_dir": cleaned_dir,
                        "derived_dir": derived_dir,
                        "log_dir": log_dir,
                        "prompt_path": prompt_path,
                        "model_name": model_name,
                        "base_url": base_url,
                        "timeout_seconds": timeout_seconds,
                        "max_documents": analysis_limit_per_source,
                    },
                    )
                )

            if settings.log_mode == "centralized":
                for _, _, kwargs in stage_specs:
                    kwargs["log_path"] = runtime_log_path

            for stage_name, stage_runner, stage_kwargs in stage_specs:
                _append_log(
                    runtime_log_path,
                    {
                        "event": "stage_started",
                        "source_key": source_key,
                        "stage_name": stage_name,
                        "open_fd_count": _open_fd_count(),
                    },
                )
                try:
                    stage_result = stage_runner(**stage_kwargs)
                except Exception as exc:
                    source_has_failure = True
                    failed_count += 1
                    stage_summaries.append(
                        RuntimeStageSummary(
                            stage_name=stage_name,
                            source_key=source_key,
                            crawl_run_id=None,
                            status="failed",
                        )
                    )
                    _append_log(
                        runtime_log_path,
                        {
                            "event": "stage_failed",
                            "source_key": source_key,
                            "stage_name": stage_name,
                            "error": f"[{type(exc).__name__}] {exc!r}",
                            "open_fd_count": _open_fd_count(),
                        },
                    )
                    break

                stage_status = str(stage_result.status)
                crawl_run_id = int(stage_result.crawl_run_id)
                if stage_status != "success":
                    source_has_failure = True
                failed_count += int(getattr(stage_result, "failed_count", 0) or 0)
                if stage_name == "fetch":
                    fetched_new_count += int(getattr(stage_result, "fetched_count", 0) or 0)
                    unchanged_count += int(getattr(stage_result, "unchanged_count", 0) or 0)
                if stage_name == "extract":
                    extracted_count += int(getattr(stage_result, "extracted_count", 0) or 0)
                if stage_name == "summary_draft":
                    summarized_count += int(getattr(stage_result, "generated_count", 0) or 0)
                    skipped_summary_count += int(getattr(stage_result, "skipped_count", 0) or 0)
                stage_summaries.append(
                    RuntimeStageSummary(
                        stage_name=stage_name,
                        source_key=source_key,
                        crawl_run_id=crawl_run_id,
                        status=stage_status,
                    )
                )
                _append_log(
                    runtime_log_path,
                    {
                        "event": "stage_finished",
                        "source_key": source_key,
                        "stage_name": stage_name,
                        "crawl_run_id": crawl_run_id,
                        "status": stage_status,
                        "log_path": getattr(stage_result, "log_path", None),
                        "open_fd_count": _open_fd_count(),
                    },
                )

            source_status = "partial_failure" if source_has_failure else "success"
            if source_has_failure:
                failed_source_count += 1
            source_summaries.append(
                RuntimeSourceSummary(
                    source_key=source_key,
                    status=source_status,
                    stages=tuple(stage_summaries),
                )
            )
            _append_log(
                runtime_log_path,
                {
                    "event": "source_finished",
                    "source_key": source_key,
                    "status": source_status,
                },
            )

        overall_status = "partial_failure" if failed_source_count else "success"
        _append_log(
            runtime_log_path,
            {
                "event": "runtime_finished",
                "status": overall_status,
                "source_count": len(source_summaries),
                "failed_source_count": failed_source_count,
                "discovered_new_count": discovered_new_count,
                "rediscovered_existing_count": rediscovered_existing_count,
                "fetched_new_count": fetched_new_count,
                "unchanged_count": unchanged_count,
                "extracted_count": extracted_count,
                "summarized_count": summarized_count,
                "skipped_summary_count": skipped_summary_count,
                "failed_count": failed_count,
                "open_fd_count": _open_fd_count(),
            },
        )

        return RuntimeRunResult(
            status=overall_status,
            source_count=len(source_summaries),
            failed_source_count=failed_source_count,
            log_path=stored_runtime_log_path,
            sources=tuple(source_summaries),
            discovered_new_count=discovered_new_count,
            rediscovered_existing_count=rediscovered_existing_count,
            fetched_new_count=fetched_new_count,
            unchanged_count=unchanged_count,
            extracted_count=extracted_count,
            summarized_count=summarized_count,
            skipped_summary_count=skipped_summary_count,
            failed_count=failed_count,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Run the auto-scrapy pipeline once outside Flask.")
    parser.add_argument("--config-path", type=Path, default=None)
    parser.add_argument("--database-path", type=Path, default=None)
    parser.add_argument("--raw-dir", type=Path, default=None)
    parser.add_argument("--cleaned-dir", type=Path, default=None)
    parser.add_argument("--derived-dir", type=Path, default=None)
    parser.add_argument("--log-dir", type=Path, default=None)
    parser.add_argument("--prompt-path", type=Path, default=None)
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--analysis-limit-per-source", type=int, default=None)
    parser.add_argument("--source-key", action="append", default=None)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    result = run_pipeline_once(
        config_path=args.config_path,
        database_path=args.database_path,
        raw_dir=args.raw_dir,
        cleaned_dir=args.cleaned_dir,
        derived_dir=args.derived_dir,
        log_dir=args.log_dir,
        prompt_path=args.prompt_path,
        model_name=args.model_name,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        run_analysis=not args.skip_analysis,
        analysis_limit_per_source=args.analysis_limit_per_source,
        source_keys=tuple(args.source_key) if args.source_key else None,
    )
    print(json.dumps(asdict(result), ensure_ascii=True))
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
