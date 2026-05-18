from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

from app.db import (
    connect_db,
    init_db,
    record_discovered_documents,
    update_document_fetch_state,
    upsert_source,
)
from app.fetch import RawFetchSpider, run_fetch
from app.runtime import _run_fetch_isolated


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/static":
            body = b"<html><body><article>static page</article></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/needs-browser":
            body = (
                b'<html><head><meta name="auto-scrapy-requires-browser" content="1"></head>'
                b"<body><div id='app'></div>"
                b"<script>"
                b"window.addEventListener('DOMContentLoaded', function () {"
                b"document.getElementById('app').innerHTML = \"<article id='hydrated'>browser page</article>\";"
                b"});"
                b"</script></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/broken":
            body = b"server error"
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        return


class _ConditionalFixtureHandler(BaseHTTPRequestHandler):
    body = b"<html><body><article>conditional page content</article></body></html>"

    def do_GET(self) -> None:
        if self.headers.get("If-None-Match") == '"fixture-etag"':
            self.send_response(304)
            self.send_header("ETag", '"fixture-etag"')
            self.send_header("Last-Modified", "Mon, 01 Jan 2024 00:00:00 GMT")
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.body)))
        self.send_header("ETag", '"fixture-etag"')
        self.send_header("Last-Modified", "Mon, 01 Jan 2024 00:00:00 GMT")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args) -> None:
        return


def test_raw_fetch_spider_uses_modest_timeout_and_transient_retries() -> None:
    assert RawFetchSpider.custom_settings["DOWNLOAD_TIMEOUT"] == 30
    assert RawFetchSpider.custom_settings["RETRY_ENABLED"] is True
    assert RawFetchSpider.custom_settings["RETRY_TIMES"] == 1
    assert RawFetchSpider.custom_settings["RETRY_HTTP_CODES"] == [
        408,
        429,
        500,
        502,
        503,
        504,
    ]


def test_run_fetch_persists_raw_updates_fetch_status_and_marks_browser_escalation(tmp_path: Path) -> None:
    database_path = tmp_path / "fetch.sqlite3"
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    log_dir = data_dir / "logs"

    init_db(database_path)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_port}"

        with connect_db(database_path) as connection:
            source_id = upsert_source(
                connection,
                source_key="fixture-fetch",
                source_type="seed",
                title="Fixture Fetch Source",
                config_path="tests/fixture-fetch",
            )
            inserted = record_discovered_documents(
                connection,
                source_id=source_id,
                canonical_urls=[
                    f"{base_url}/static",
                    f"{base_url}/needs-browser",
                    f"{base_url}/broken",
                ],
            )
            assert inserted == 3

        result = run_fetch(
            source_key="fixture-fetch",
            database_path=database_path,
            raw_dir=raw_dir,
            log_dir=log_dir,
        )

        assert result.source_key == "fixture-fetch"
        assert result.fetched_count == 2
        assert result.needs_browser_count == 1
        assert result.browser_fetched_count == 1
        assert result.failed_count == 1
        assert result.status == "partial_failure"
        assert result.log_path == "data/logs/fetch-run-1.log"

        with connect_db(database_path) as connection:
            document_rows = connection.execute(
                """
                SELECT canonical_url, fetch_status, current_raw_path
                FROM documents
                ORDER BY canonical_url
                """
            ).fetchall()
            fetch_map = {row["canonical_url"]: row for row in document_rows}

            assert fetch_map[f"{base_url}/static"]["fetch_status"] == "fetched"
            assert fetch_map[f"{base_url}/needs-browser"]["fetch_status"] == "fetched"
            assert fetch_map[f"{base_url}/broken"]["fetch_status"] == "fetch_failed"

            static_raw = fetch_map[f"{base_url}/static"]["current_raw_path"]
            browser_raw = fetch_map[f"{base_url}/needs-browser"]["current_raw_path"]
            failed_raw = fetch_map[f"{base_url}/broken"]["current_raw_path"]

            assert static_raw is not None
            assert browser_raw is not None
            assert failed_raw is None

            static_raw_path = tmp_path / Path(static_raw)
            browser_raw_path = tmp_path / Path(browser_raw)
            assert static_raw_path.exists()
            assert browser_raw_path.exists()
            assert static_raw_path.read_text(encoding="utf-8") == "<html><body><article>static page</article></body></html>"
            browser_raw_text = browser_raw_path.read_text(encoding="utf-8")
            assert "browser page" in browser_raw_text
            assert 'id="hydrated"' in browser_raw_text

            crawl_run = connection.execute(
                """
                SELECT run_kind, status, fetched_count, error_message, log_path
                FROM crawl_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            assert crawl_run is not None
            assert crawl_run["run_kind"] == "fetch:http"
            assert crawl_run["status"] == "partial_failure"
            assert crawl_run["fetched_count"] == 2
            assert crawl_run["log_path"] == "data/logs/fetch-run-1.log"
            assert "/broken" in crawl_run["error_message"]

        log_path = log_dir / "fetch-run-1.log"
        assert log_path.exists()
        log_text = log_path.read_text(encoding="utf-8")
        assert '"event": "run_started"' in log_text
        assert '"status": "fetched"' in log_text
        assert '"status": "needs_browser"' in log_text
        assert '"status": "fetch_failed"' in log_text
        assert '"event": "run_finished"' in log_text
        assert '"fetch_method": "http"' in log_text
        assert '"fetch_method": "browser"' in log_text
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_run_fetch_uses_conditional_headers_and_marks_304_unchanged(tmp_path: Path) -> None:
    database_path = tmp_path / "fetch-304.sqlite3"
    raw_dir = tmp_path / "data" / "raw"
    log_dir = tmp_path / "data" / "logs"
    init_db(database_path)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _ConditionalFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        url = f"http://127.0.0.1:{server.server_port}/conditional"
        with connect_db(database_path) as connection:
            source_id = upsert_source(
                connection,
                source_key="conditional-fetch",
                source_type="seed",
                title="Conditional Fetch",
                config_path="tests/conditional-fetch",
            )
            record_discovered_documents(
                connection,
                source_id=source_id,
                canonical_urls=[url],
            )

        first = _run_fetch_isolated(
            source_key="conditional-fetch",
            database_path=database_path,
            raw_dir=raw_dir,
            log_dir=log_dir,
        )
        assert first.fetched_count == 1
        assert first.unchanged_count == 0

        with connect_db(database_path) as connection:
            row = connection.execute(
                "SELECT id, raw_content_hash, http_etag FROM documents WHERE canonical_url = ?",
                (url,),
            ).fetchone()
            assert row is not None
            assert row["http_etag"] == '"fixture-etag"'
            update_document_fetch_state(
                connection,
                document_id=int(row["id"]),
                fetch_status="discovered",
            )

        second = _run_fetch_isolated(
            source_key="conditional-fetch",
            database_path=database_path,
            raw_dir=raw_dir,
            log_dir=log_dir,
        )

        assert second.fetched_count == 0
        assert second.unchanged_count == 1
        with connect_db(database_path) as connection:
            row = connection.execute(
                "SELECT fetch_status, extract_status, current_raw_path FROM documents WHERE canonical_url = ?",
                (url,),
            ).fetchone()
            assert row["fetch_status"] == "fetched"
            assert row["extract_status"] == "pending"
            assert row["current_raw_path"] is not None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
