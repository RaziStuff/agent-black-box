#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_black_box.daemon import serve_in_thread
from agent_black_box.storage import ABBStore


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a rendered browser smoke test for the Agent Black Box dashboard.")
    parser.add_argument("--data-dir", help="Data directory to use for the smoke store.")
    parser.add_argument("--keep-data", action="store_true", help="Keep the generated smoke store.")
    parser.add_argument(
        "--required",
        action="store_true",
        default=os.environ.get("ABB_BROWSER_SMOKE_REQUIRED") == "1",
        help="Fail instead of skipping when Playwright or a browser engine is unavailable.",
    )
    parser.add_argument("--timeout-ms", type=int, default=10000, help="Browser wait timeout in milliseconds.")
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _skip_or_fail(args.required, "Playwright is not installed. Install `playwright` and a browser engine to run rendered UI smoke.")

    store_dir = Path(args.data_dir) if args.data_dir else Path(tempfile.mkdtemp(prefix="abb-browser-smoke-"))
    store_dir.mkdir(parents=True, exist_ok=True)
    store = ABBStore(store_dir)
    server = None
    thread = None
    try:
        run = _create_browser_smoke_run(store)
        compare_path = store.export_compare_pair(run["run_id"], fmt="json")
        server, thread = serve_in_thread(store, host="127.0.0.1", port=0)
        url = f"http://127.0.0.1:{server.server_port}"
        _verify_dashboard(
            sync_playwright,
            PlaywrightError,
            PlaywrightTimeoutError,
            url,
            run["run_id"],
            compare_path,
            args.timeout_ms,
        )
        print(f"Browser UI smoke passed: {url} run={run['run_id']}")
        return 0
    except RuntimeError as exc:
        return _skip_or_fail(args.required, str(exc))
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)
        store.close()
        if not args.keep_data and not args.data_dir:
            shutil.rmtree(store_dir, ignore_errors=True)


def _create_browser_smoke_run(store: ABBStore) -> Dict[str, Any]:
    run = store.create_run({"name": "browser smoke compare", "source": "browser-smoke", "tags": ["browser-smoke"]})
    span = store.start_span(
        {
            "run_id": run["run_id"],
            "type": "model.call",
            "name": "Browser smoke model call",
            "attributes": {"model": "demo-model", "resource": "chat.completions"},
        }
    )
    request_artifact = store.add_artifact(
        run["run_id"],
        span["span_id"],
        "model.request",
        json.dumps(
            {
                "model": "demo-model",
                "messages": [{"role": "user", "content": "Explain the trace in one line"}],
            },
            indent=2,
        ),
        media_type="application/json",
    )
    response_artifact = store.add_artifact(
        run["run_id"],
        span["span_id"],
        "model.response",
        json.dumps(
            {
                "id": "chatcmpl_browser_smoke",
                "choices": [{"message": {"role": "assistant", "content": "Trace captured and grouped."}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
            },
            indent=2,
        ),
        media_type="application/json",
    )
    store.add_event(
        {
            "run_id": run["run_id"],
            "span_id": span["span_id"],
            "type": "model.completed",
            "message": "Browser smoke model completed",
            "attributes": {
                "request_ref": request_artifact["artifact_id"],
                "response_ref": response_artifact["artifact_id"],
                "usage": {"input_tokens": 12, "output_tokens": 6, "total_tokens": 18},
            },
        }
    )
    store.end_span(
        span["span_id"],
        output_ref=response_artifact["artifact_id"],
        attributes={"usage": {"input_tokens": 12, "output_tokens": 6, "total_tokens": 18}},
    )
    return store.end_run(run["run_id"]) or run


def _verify_dashboard(
    sync_playwright: Any,
    playwright_error: Any,
    timeout_error: Any,
    url: str,
    run_id: str,
    compare_path: Path,
    timeout_ms: int,
) -> None:
    console_errors: list[str] = []
    page_errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except playwright_error as exc:
                raise RuntimeError(f"Playwright could not launch Chromium: {exc}") from exc
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                page.wait_for_selector(f'[data-testid="run-detail"][data-run-id="{run_id}"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="span-inspector"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="artifact-compare"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-pair-request-response"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-copy-markdown"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-copy-json"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-download-markdown"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-download-json"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-export-status"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-export-text"]', state="attached", timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-ingest-path"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-ingest-name"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-ingest-button"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-ingest-status"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="agent-kit-button"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="agent-kit-status"]', timeout=timeout_ms)
                page.click('[data-testid="agent-kit-button"]')
                page.wait_for_selector('[data-testid="agent-kit-summary"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="agent-kit-zip"] >> text=SHA-256', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="agent-kit-files"] >> text=openapi', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="artifact-compare"] >> text=Trace captured and grouped.', timeout=timeout_ms)
                page.click('[data-testid="compare-copy-markdown"]')
                page.wait_for_function(
                    """
                    () => {
                      const status = document.querySelector('[data-testid="compare-export-status"]')?.textContent || '';
                      const fallback = document.querySelector('[data-testid="compare-export-text"]');
                      return status.includes('Copied Markdown compare.')
                        || (
                          status.includes('Clipboard unavailable')
                          && fallback
                          && fallback.value.includes('# Agent Black Box Compare Export')
                          && fallback.value.includes('Trace captured and grouped.')
                        );
                    }
                    """,
                    timeout=timeout_ms,
                )
                pane_count = page.locator('[data-testid="compare-pane"]').count()
                if pane_count < 2:
                    raise RuntimeError(f"Expected at least two compare panes, found {pane_count}")
                page.fill('[data-testid="compare-ingest-path"]', str(compare_path))
                page.fill('[data-testid="compare-ingest-name"]', "Browser smoke compare investigation")
                page.click('[data-testid="compare-ingest-button"]')
                page.wait_for_function(
                    """
                    () => {
                      const status = document.querySelector('[data-testid="compare-ingest-status"]')?.textContent || '';
                      return status.includes('Created run_');
                    }
                    """,
                    timeout=timeout_ms,
                )
                page.wait_for_selector('[data-testid="run-detail"] >> text=compare-ingest', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="run-detail"] >> text=Source trace', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-investigation-panel"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-source-run-button"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-evidence-packet"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-evidence-briefing"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-evidence-left"]', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="compare-evidence-right"]', timeout=timeout_ms)
                page.click('[data-testid="compare-evidence-left"]')
                page.wait_for_selector('[data-testid="artifact-preview"] >> text=compare.left', timeout=timeout_ms)
                page.wait_for_selector('[data-testid="artifact-preview"] >> text=Explain the trace in one line', timeout=timeout_ms)
                page.click('[data-testid="compare-source-run-button"]')
                page.wait_for_selector(f'[data-testid="run-detail"][data-run-id="{run_id}"]', timeout=timeout_ms)
                if page_errors:
                    raise RuntimeError("Browser page errors: " + "; ".join(page_errors))
                if console_errors:
                    raise RuntimeError("Browser console errors: " + "; ".join(console_errors))
            finally:
                browser.close()
    except timeout_error as exc:
        raise RuntimeError(f"Dashboard smoke timed out while waiting for rendered UI: {exc}") from exc


def _skip_or_fail(required: bool, message: str) -> int:
    prefix = "FAIL" if required else "SKIP"
    print(f"{prefix} browser UI smoke: {message}")
    return 1 if required else 0


if __name__ == "__main__":
    raise SystemExit(main())
