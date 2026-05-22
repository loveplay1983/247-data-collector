from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import threading
import pytest

from app.config import load_settings
from app.runtime import run_pipeline_once


class _FetchFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            body = b'<html><body><a href="/article">Fixture Article</a></body></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/article":
            body = (
                b"<html><head><title>Fixture Article</title></head>"
                b"<body><article><h1>Fixture Article</h1><p>"
                b"runtime smoke body with enough article detail to pass the quality gate. "
                b"This fixture includes meaningful technical context, more than a landing page, "
                b"and enough prose for extraction and downstream summary generation."
                b"</p></article></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        return


class _OllamaFixtureHandler(BaseHTTPRequestHandler):
    request_payloads: list[dict[str, object]] = []

    def do_POST(self) -> None:
        if self.path != "/api/generate":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        self.__class__.request_payloads.append(payload)

        response_body = json.dumps({"response": "summary draft from fixture"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format: str, *args) -> None:
        return


def test_centralized_logging_and_summary_level(monkeypatch, tmp_path: Path) -> None:
    # 1. Enforce centralized log mode and summary log level
    monkeypatch.setenv("AUTO_SCRAPY_LOG_MODE", "centralized")
    monkeypatch.setenv("AUTO_SCRAPY_LOG_LEVEL", "summary")

    # Load settings to verify monkeypatch takes effect
    settings = load_settings()
    assert settings.log_mode == "centralized"
    assert settings.log_level == "summary"

    database_path = tmp_path / "runtime.sqlite3"
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    cleaned_dir = data_dir / "cleaned"
    derived_dir = data_dir / "derived"
    log_dir = data_dir / "logs"
    config_dir = tmp_path / "config"
    sources_dir = config_dir / "sources"
    prompts_dir = config_dir / "prompts"
    sources_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    fetch_server = ThreadingHTTPServer(("127.0.0.1", 0), _FetchFixtureHandler)
    fetch_thread = threading.Thread(target=fetch_server.serve_forever, daemon=True)
    fetch_thread.start()

    ollama_server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaFixtureHandler)
    ollama_thread = threading.Thread(target=ollama_server.serve_forever, daemon=True)
    ollama_thread.start()
    _OllamaFixtureHandler.request_payloads.clear()

    try:
        base_fetch_url = f"http://127.0.0.1:{fetch_server.server_port}"
        config_path = sources_dir / "runtime_sources.toml"
        config_path.write_text(
            "\n".join(
                [
                    "[[sources]]",
                    'source_key = "runtime-seed"',
                    'source_type = "seed"',
                    'title = "Runtime Seed"',
                    "enabled = true",
                    f'seeds = ["{base_fetch_url}/"]',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        prompt_path = prompts_dir / "summary_draft_runtime.txt"
        prompt_path.write_text(
            "Create a short summary.\n\n{{ cleaned_content }}\n",
            encoding="utf-8",
        )

        result = run_pipeline_once(
            config_path=config_path,
            database_path=database_path,
            raw_dir=raw_dir,
            cleaned_dir=cleaned_dir,
            derived_dir=derived_dir,
            log_dir=log_dir,
            prompt_path=prompt_path,
            model_name="fixture-model",
            base_url=f"http://127.0.0.1:{ollama_server.server_port}",
            timeout_seconds=5,
        )

        assert result.status == "success"

        # Verify unified log is used
        unified_log_file = log_dir / Path(result.log_path).name
        assert unified_log_file.exists()

        log_content = unified_log_file.read_text(encoding="utf-8")
        assert '"event": "runtime_started"' in log_content
        assert '"event": "run_started"' in log_content
        assert '"event": "stage_started"' in log_content
        assert '"event": "run_finished"' in log_content
        assert '"event": "runtime_finished"' in log_content

        # Since log_level is summary, document-level success messages should NOT be logged
        assert '"status": "fetched"' not in log_content
        assert '"status": "extracted"' not in log_content
        assert '"status": "generated"' not in log_content

        # Verify no other log files were generated in the logs directory
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) == 1
        assert log_files[0].name == Path(result.log_path).name

    finally:
        fetch_server.shutdown()
        ollama_server.shutdown()


def test_centralized_logging_detailed_level(monkeypatch, tmp_path: Path) -> None:
    # 1. Enforce centralized log mode and detailed log level
    monkeypatch.setenv("AUTO_SCRAPY_LOG_MODE", "centralized")
    monkeypatch.setenv("AUTO_SCRAPY_LOG_LEVEL", "detailed")

    settings = load_settings()
    assert settings.log_mode == "centralized"
    assert settings.log_level == "detailed"

    database_path = tmp_path / "runtime.sqlite3"
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    cleaned_dir = data_dir / "cleaned"
    derived_dir = data_dir / "derived"
    log_dir = data_dir / "logs"
    config_dir = tmp_path / "config"
    sources_dir = config_dir / "sources"
    prompts_dir = config_dir / "prompts"
    sources_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    fetch_server = ThreadingHTTPServer(("127.0.0.1", 0), _FetchFixtureHandler)
    fetch_thread = threading.Thread(target=fetch_server.serve_forever, daemon=True)
    fetch_thread.start()

    ollama_server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaFixtureHandler)
    ollama_thread = threading.Thread(target=ollama_server.serve_forever, daemon=True)
    ollama_thread.start()
    _OllamaFixtureHandler.request_payloads.clear()

    try:
        base_fetch_url = f"http://127.0.0.1:{fetch_server.server_port}"
        config_path = sources_dir / "runtime_sources.toml"
        config_path.write_text(
            "\n".join(
                [
                    "[[sources]]",
                    'source_key = "runtime-seed"',
                    'source_type = "seed"',
                    'title = "Runtime Seed"',
                    "enabled = true",
                    f'seeds = ["{base_fetch_url}/"]',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        prompt_path = prompts_dir / "summary_draft_runtime.txt"
        prompt_path.write_text(
            "Create a short summary.\n\n{{ cleaned_content }}\n",
            encoding="utf-8",
        )

        result = run_pipeline_once(
            config_path=config_path,
            database_path=database_path,
            raw_dir=raw_dir,
            cleaned_dir=cleaned_dir,
            derived_dir=derived_dir,
            log_dir=log_dir,
            prompt_path=prompt_path,
            model_name="fixture-model",
            base_url=f"http://127.0.0.1:{ollama_server.server_port}",
            timeout_seconds=5,
        )

        assert result.status == "success"

        unified_log_file = log_dir / Path(result.log_path).name
        assert unified_log_file.exists()

        log_content = unified_log_file.read_text(encoding="utf-8")
        assert '"event": "runtime_started"' in log_content

        # Since log_level is detailed, document-level success messages MUST be logged
        assert '"status": "fetched"' in log_content
        assert '"status": "extracted"' in log_content
        assert '"status": "generated"' in log_content

    finally:
        fetch_server.shutdown()
        ollama_server.shutdown()
