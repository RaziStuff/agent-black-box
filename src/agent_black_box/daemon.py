from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse
import zipfile

from .agent_kit import create_agent_kit
from .api_manifest import api_manifest, openapi_spec
from .diff import compare_runs
from .handoff import format_handoff_briefing
from .proxy import proxy_openai_request
from .storage import ABBStore, format_compare_briefing, format_compare_export


HTML_APP = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agent Black Box</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --panel-soft: #fbfcfd;
      --ink: #202124;
      --muted: #667085;
      --line: #d6dae1;
      --accent: #0f766e;
      --accent-soft: #e6f5f2;
      --bad: #b42318;
      --bad-soft: #fff0ed;
      --ok: #207a3c;
      --ok-soft: #edf8ef;
      --warn: #a15c07;
      --warn-soft: #fff5e5;
      --code-bg: #f0f2f5;
      --code: #1f2937;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #121416;
        --panel: #1a1d20;
        --panel-soft: #202327;
        --ink: #edf0f2;
        --muted: #a7adb4;
        --line: #32373d;
        --accent: #4fd1c5;
        --accent-soft: #12332f;
        --bad: #ff9b91;
        --bad-soft: #3a1915;
        --ok: #86efac;
        --ok-soft: #17351f;
        --warn: #f7c873;
        --warn-soft: #382710;
        --code-bg: #111315;
        --code: #f6f8fa;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    header {
      min-height: 58px;
      border-bottom: 1px solid var(--line);
      display: flex;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      padding: 10px 16px;
      background: var(--panel);
    }
    h1, h2, h3 {
      margin: 0;
      letter-spacing: 0;
    }
    h1 { font-size: 17px; }
    h2 { font-size: 18px; }
    h3 { font-size: 14px; }
    button, select, input, textarea {
      font: inherit;
      color: var(--ink);
    }
    button {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 6px;
      min-height: 34px;
      padding: 7px 10px;
      cursor: pointer;
    }
    button:hover { border-color: var(--accent); }
    button.active {
      border-color: var(--accent);
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 650;
    }
    select, input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      min-height: 34px;
      padding: 7px 9px;
    }
    textarea {
      min-height: 78px;
      resize: vertical;
    }
    [hidden] {
      display: none !important;
    }
    main {
      display: grid;
      grid-template-columns: minmax(300px, 31vw) 1fr;
      min-height: calc(100vh - 58px);
    }
    aside {
      border-right: 1px solid var(--line);
      padding: 12px;
      overflow: auto;
    }
    section {
      padding: 14px;
      overflow: auto;
    }
    .toolbar, .tabs, .actions, .split, .metrics, .form-grid {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .tabs { flex-wrap: wrap; }
    .actions { justify-content: flex-end; flex-wrap: wrap; }
    .split { justify-content: space-between; align-items: flex-start; gap: 12px; }
    .form-grid {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) minmax(180px, 1fr) auto;
      align-items: end;
      margin-bottom: 12px;
    }
    .list {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }
    .row {
      width: 100%;
      text-align: left;
      display: block;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 10px;
    }
    .row strong {
      display: block;
      font-size: 14px;
      margin-bottom: 4px;
      overflow-wrap: anywhere;
    }
    .meta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      overflow-wrap: anywhere;
    }
    .provenance {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
      max-width: min(860px, 100%);
    }
    .provenance .meta { line-height: 1.6; }
    .status-ok { color: var(--ok); }
    .status-error { color: var(--bad); }
    .status-running { color: var(--warn); }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 23px;
      border-radius: 999px;
      padding: 2px 8px;
      background: var(--panel-soft);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      white-space: nowrap;
    }
    .pill.ok { background: var(--ok-soft); color: var(--ok); border-color: transparent; }
    .pill.error { background: var(--bad-soft); color: var(--bad); border-color: transparent; }
    .pill.running { background: var(--warn-soft); color: var(--warn); border-color: transparent; }
    .usage-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }
    .ref-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }
    .ref-button {
      min-height: 28px;
      padding: 5px 8px;
      font-size: 12px;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
      margin: 14px 0;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px;
      min-height: 64px;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }
    .metric strong { font-size: 20px; }
    .content-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(260px, 0.65fr);
      gap: 12px;
      align-items: start;
    }
    .side-stack {
      display: grid;
      gap: 12px;
    }
    .compare-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
    }
    .compare-status {
      flex-basis: 100%;
      min-height: 18px;
    }
    .compare-export-text {
      flex-basis: 100%;
      min-height: 160px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
    }
    .compare-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .compare-pane {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px;
    }
    .compare-pane pre {
      max-height: 300px;
    }
    .filters {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 10px;
    }
    .filters input {
      grid-column: 1 / -1;
    }
    .import-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px;
      margin-top: 10px;
      display: grid;
      gap: 8px;
    }
    .import-panel .form-grid {
      grid-template-columns: 1fr auto;
      margin-bottom: 0;
    }
    .import-panel label input[type="checkbox"] {
      width: auto;
      min-height: 0;
      margin-right: 6px;
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }
    .panel-head {
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .panel-body {
      padding: 12px;
      display: grid;
      gap: 8px;
    }
    .item {
      border: 1px solid var(--line);
      background: var(--panel-soft);
      border-radius: 8px;
      padding: 10px;
    }
    .item.active {
      border-color: var(--accent);
      background: var(--accent-soft);
    }
    .item.debug-critical { border-color: rgba(185, 28, 28, 0.35); background: var(--bad-soft); }
    .item.debug-warning { border-color: rgba(161, 98, 7, 0.35); background: var(--warn-soft); }
    .item-title {
      display: flex;
      gap: 8px;
      align-items: baseline;
      justify-content: space-between;
    }
    pre {
      margin: 8px 0 0;
      overflow: auto;
      color: var(--code);
      background: var(--code-bg);
      white-space: pre-wrap;
      font-size: 12px;
      line-height: 1.45;
      padding: 10px;
      border-radius: 6px;
      max-height: 360px;
    }
    .empty {
      color: var(--muted);
      padding: 18px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: var(--panel-soft);
    }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); max-height: 42vh; }
      .content-grid, .form-grid, .filters { grid-template-columns: 1fr; }
      .compare-grid { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(2, minmax(90px, 1fr)); }
      header { align-items: stretch; flex-direction: column; }
      .actions { justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <header>
    <div class="toolbar">
      <h1>Agent Black Box</h1>
      <span id="storeStatus" class="pill">local</span>
    </div>
    <div class="tabs" role="tablist">
      <button id="tab-runs" class="active" onclick="setMode('runs')">Runs</button>
      <button id="tab-fixtures" onclick="setMode('fixtures')">Fixtures</button>
      <button id="tab-diff" onclick="setMode('diff')">Diff</button>
      <button onclick="refreshAll()">Refresh</button>
    </div>
  </header>
  <main>
    <aside>
      <div id="sidebar"></div>
    </aside>
    <section>
      <div id="detail" class="empty"></div>
    </section>
  </main>
  <script>
    const state = {
      mode: "runs",
      runs: [],
      fixtures: [],
      selectedRunId: null,
      selectedFixtureId: null,
      selectedArtifactId: null,
      selectedSpanId: null,
      selectedCompareKey: "",
      artifactIndex: {},
      artifactTextCache: {},
      spanGroups: [],
      spanGroupIndex: {},
      filters: { query: "", status: "all", source: "all" },
      searchRunIds: null,
      searchSeq: 0,
      importMessage: "",
      handoffMessage: "",
      compareMessage: "",
      agentKitMessage: "",
      agentKit: null,
    };

    function statusClass(status) {
      if (status === "ok") return "ok";
      if (status === "error") return "error";
      if (status === "running") return "running";
      return "";
    }

    function provenanceLabel(run) {
      const metadata = run.metadata || {};
      if (metadata.remapped_from_run_id) return "Remapped import";
      if (metadata.imported_from_bundle) return "Imported bundle";
      return "";
    }

    function provenanceBadge(run) {
      const label = provenanceLabel(run);
      return label ? `<br /><span class="pill">${escapeHtml(label)}</span>` : "";
    }

    function provenanceBlock(run) {
      const metadata = run.metadata || {};
      const label = provenanceLabel(run);
      if (!label) return "";
      const lines = [];
      if (metadata.remapped_from_run_id) {
        lines.push(`Original run ${metadata.remapped_from_run_id}`);
      }
      if (metadata.imported_from_bundle) {
        lines.push(`Bundle ${metadata.imported_from_bundle}`);
      }
      return `
        <div class="provenance">
          <span class="pill">${escapeHtml(label)}</span>
          <span class="meta">${lines.map(escapeHtml).join(" · ")}</span>
        </div>
      `;
    }

    function setMode(mode) {
      state.mode = mode;
      for (const name of ["runs", "fixtures", "diff"]) {
        document.getElementById(`tab-${name}`).classList.toggle("active", name === mode);
      }
      renderSidebar();
      if (mode === "runs") {
        if (state.selectedRunId) loadRun(state.selectedRunId);
        else renderEmpty("runs");
      } else if (mode === "fixtures") {
        if (state.selectedFixtureId) loadFixture(state.selectedFixtureId);
        else renderFixturesHome();
      } else {
        renderDiff();
      }
    }

    async function refreshAll() {
      const health = await fetchJson("/health");
      document.getElementById("storeStatus").textContent = health.ok ? "local" : "offline";
      state.runs = await fetchJson("/v1/runs?limit=100");
      state.fixtures = await fetchJson("/v1/fixtures?limit=100");
      if (!state.selectedRunId && state.runs.length) state.selectedRunId = state.runs[0].run_id;
      if (!state.selectedFixtureId && state.fixtures.length) state.selectedFixtureId = state.fixtures[0].fixture_id;
      renderSidebar();
      setMode(state.mode);
    }

    function renderSidebar() {
      const sidebar = document.getElementById("sidebar");
      if (state.mode === "runs" || state.mode === "diff") {
        const runs = filteredRuns();
        sidebar.innerHTML = `
          <div class="split">
            <h3>Runs</h3>
            <span id="runCount" class="pill">${runs.length}/${state.runs.length}</span>
          </div>
          <div class="filters">
            <input id="runSearch" value="${escapeHtml(state.filters.query)}" oninput="updateFilter('query', this.value)" placeholder="Search runs" />
            <select id="statusFilter" onchange="updateFilter('status', this.value)">
              ${option("all", "All statuses", state.filters.status)}
              ${uniqueValues(state.runs.map(run => run.status)).map(value => option(value, value, state.filters.status)).join("")}
            </select>
            <select id="sourceFilter" onchange="updateFilter('source', this.value)">
              ${option("all", "All sources", state.filters.source)}
              ${uniqueValues(state.runs.map(run => run.source)).map(value => option(value, value, state.filters.source)).join("")}
            </select>
          </div>
          <div class="import-panel">
            <div class="split">
              <h3>Agent Kit</h3>
              <span class="pill">onboard</span>
            </div>
            <input id="agentKitOutput" data-testid="agent-kit-output" placeholder="Output directory (optional)" />
            <input id="agentKitZipOutput" data-testid="agent-kit-zip-output" placeholder="Zip output path (optional)" />
            <div class="form-grid">
              <label class="meta"><input id="agentKitZip" type="checkbox" checked /> create zip archive</label>
              <label class="meta"><input id="agentKitForce" type="checkbox" /> overwrite existing kit</label>
              <button data-testid="agent-kit-button" onclick="createAgentKit()">Create Kit</button>
            </div>
            <div id="agentKitStatus" data-testid="agent-kit-status" class="meta">${escapeHtml(state.agentKitMessage)}</div>
            ${state.agentKit ? agentKitSummary(state.agentKit) : ""}
          </div>
          <div class="import-panel">
            <div class="split">
              <h3>Import ABB</h3>
              <select id="importConflict">
                ${option("fail", "Fail", "fail")}
                ${option("skip", "Skip", "fail")}
                ${option("remap", "Remap", "fail")}
              </select>
            </div>
            <div class="form-grid">
              <input id="importPath" placeholder="Path to .abb bundle" />
              <button onclick="importBundle()">Import</button>
            </div>
            <div id="importStatus" class="meta">${escapeHtml(state.importMessage)}</div>
          </div>
          <div class="import-panel">
            <div class="split">
              <h3>Ingest Handoff</h3>
              <span class="pill">investigate</span>
            </div>
            <input id="handoffPath" placeholder="Path to .handoff.json packet" />
            <div class="form-grid">
              <input id="handoffName" placeholder="Investigation name (optional)" />
              <button onclick="ingestHandoff()">Ingest</button>
            </div>
            <div id="handoffStatus" class="meta">${escapeHtml(state.handoffMessage)}</div>
          </div>
          <div class="import-panel">
            <div class="split">
              <h3>Ingest Compare</h3>
              <span class="pill">evidence</span>
            </div>
            <input id="comparePath" data-testid="compare-ingest-path" placeholder="Path to .compare.json packet" />
            <div class="form-grid">
              <input id="compareName" data-testid="compare-ingest-name" placeholder="Investigation name (optional)" />
              <button data-testid="compare-ingest-button" onclick="ingestCompare()">Ingest</button>
            </div>
            <div id="compareStatus" data-testid="compare-ingest-status" class="meta">${escapeHtml(state.compareMessage)}</div>
          </div>
          <div id="runList" class="list" data-testid="run-list">${runs.map(runButton).join("") || '<div class="empty">No matching runs.</div>'}</div>
        `;
        return;
      }
      sidebar.innerHTML = `
        <div class="split">
          <h3>Fixtures</h3>
          <span class="pill">${state.fixtures.length}</span>
        </div>
        <div class="list">${state.fixtures.map(fixtureButton).join("") || '<div class="empty">No fixtures yet.</div>'}</div>
      `;
    }

    function agentKitSummary(kit) {
      const files = kit.files || {};
      const directory = files.manifest ? files.manifest.split(/[\\\\/]/).slice(0, -1).join("/") : "";
      return `
        <div class="item" data-testid="agent-kit-summary">
          <strong>Agent kit ready</strong>
          <div class="meta">${escapeHtml(directory)}</div>
          ${kit.archive ? `<div class="meta" data-testid="agent-kit-zip">Zip: ${escapeHtml(kit.archive.path)}<br />SHA-256: ${escapeHtml(kit.archive.sha256)}</div>` : ""}
          <div class="ref-buttons" data-testid="agent-kit-files">
            ${["guide", "openapi", "endpoints", "python_client", "node_client", "env", "smoke", "manifest"].map(key => {
              const value = files[key];
              return value ? `<span class="pill">${escapeHtml(key)}: ${escapeHtml(value.split(/[\\\\/]/).pop())}</span>` : "";
            }).join("")}
          </div>
          <pre>abb agent-kit --zip
sh ${escapeHtml(directory ? directory + "/smoke.sh" : ".abb/agent-kit/smoke.sh")}
abb start</pre>
        </div>
      `;
    }

    function runButton(run) {
      const active = run.run_id === state.selectedRunId ? "active" : "";
      return `
        <button class="row ${active}" data-testid="run-row" data-run-id="${escapeHtml(run.run_id)}" onclick="selectRun('${run.run_id}')">
          <strong>${escapeHtml(run.name)}</strong>
          <span class="meta">
            <span class="pill ${statusClass(run.status)}">${escapeHtml(run.status)}</span>
            ${escapeHtml(run.source)}<br />
            ${escapeHtml(run.created_at)}<br />
            ${escapeHtml(run.run_id)}
            ${provenanceBadge(run)}
          </span>
        </button>
      `;
    }

    function fixtureButton(fixture) {
      const active = fixture.fixture_id === state.selectedFixtureId ? "active" : "";
      return `
        <button class="row ${active}" onclick="loadFixture('${fixture.fixture_id}')">
          <strong>${escapeHtml(fixture.name)}</strong>
          <span class="meta">
            ${escapeHtml(fixture.created_at)}<br />
            ${escapeHtml(fixture.fixture_id)}<br />
            ${escapeHtml(fixture.run_id)}
          </span>
        </button>
      `;
    }

    function selectRun(runId) {
      state.selectedRunId = runId;
      if (state.mode === "diff") renderDiff();
      else loadRun(runId);
      renderSidebar();
    }

    async function updateFilter(key, value) {
      state.filters[key] = value;
      if (key === "query") {
        const query = value.trim();
        const seq = ++state.searchSeq;
        if (query) {
          const matches = await fetchJson(`/v1/search?q=${encodeURIComponent(query)}`);
          if (seq === state.searchSeq) {
            state.searchRunIds = new Set(matches.map(run => run.run_id));
          }
        } else {
          state.searchRunIds = null;
        }
      }
      renderRunList();
    }

    function renderRunList() {
      const runs = filteredRuns();
      const count = document.getElementById("runCount");
      const list = document.getElementById("runList");
      if (count) count.textContent = `${runs.length}/${state.runs.length}`;
      if (list) list.innerHTML = runs.map(runButton).join("") || '<div class="empty">No matching runs.</div>';
    }

    function filteredRuns() {
      const query = state.filters.query.trim().toLowerCase();
      return state.runs.filter(run => {
        if (state.filters.status !== "all" && run.status !== state.filters.status) return false;
        if (state.filters.source !== "all" && run.source !== state.filters.source) return false;
        if (state.searchRunIds && !state.searchRunIds.has(run.run_id)) return false;
        if (!query) return true;
        if (state.searchRunIds) return true;
        const haystack = [
          run.run_id,
          run.name,
          run.status,
          run.source,
          JSON.stringify(run.tags || []),
          JSON.stringify(run.metadata || {})
        ].join(" ").toLowerCase();
        return haystack.includes(query);
      });
    }

    function uniqueValues(values) {
      return Array.from(new Set(values.filter(Boolean))).sort();
    }

    function option(value, label, selected) {
      return `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
    }

    async function loadRun(runId) {
      state.mode = "runs";
      state.selectedRunId = runId;
      setActiveTabOnly("runs");
      const detail = document.getElementById("detail");
      detail.className = "empty";
      detail.innerHTML = "Loading...";
      const timeline = await fetchJson(`/v1/runs/${runId}/timeline`);
      const links = await fetchJson(`/v1/runs/${runId}/links`);
      const run = timeline.run;
      const summary = timeline.summary || {};
      state.artifactIndex = Object.fromEntries((timeline.artifacts || []).map(artifact => [artifact.artifact_id, artifact]));
      state.artifactTextCache = {};
      state.spanGroups = timeline.artifact_groups || [];
      state.spanGroupIndex = Object.fromEntries(state.spanGroups.filter(group => group.span_id).map(group => [group.span_id, group]));
      state.selectedSpanId = state.selectedSpanId && state.spanGroupIndex[state.selectedSpanId]
        ? state.selectedSpanId
        : (state.spanGroups[0] && state.spanGroups[0].span_id) || null;
      ensureSelectedComparePair();
      detail.className = "";
      detail.innerHTML = `
        <div class="split" data-testid="run-detail" data-run-id="${escapeHtml(run.run_id)}">
          <div>
            <h2>${escapeHtml(run.name)}</h2>
            <div class="meta">${escapeHtml(run.run_id)} · <span class="status-${escapeHtml(run.status)}">${escapeHtml(run.status)}</span> · ${escapeHtml(run.created_at)}</div>
            ${provenanceBlock(run)}
          </div>
          <div class="actions">
            <button onclick="createFixture('${run.run_id}')">Create Fixture</button>
            <button onclick="exportRun('${run.run_id}', 'bundle')">Export ABB</button>
            <button onclick="exportRun('${run.run_id}', 'handoff')">Export Handoff</button>
            <button onclick="exportRun('${run.run_id}', 'markdown')">Export MD</button>
            <button onclick="exportRun('${run.run_id}', 'jsonl')">Export JSONL</button>
            <button data-testid="delete-run-button" onclick="deleteRun('${run.run_id}')">Delete Run</button>
          </div>
        </div>
        <div class="metrics">
          ${metric("Spans", timeline.spans.length)}
          ${metric("Events", timeline.events.length)}
          ${metric("Artifacts", timeline.artifacts.length)}
          ${metric("Annotations", timeline.annotations.length)}
        </div>
        <div class="metrics">
          ${metric("Model Calls", summary.model_calls || 0)}
          ${metric("Graph Nodes", summary.graph_nodes || 0)}
          ${metric("Tokens", summary.usage && summary.usage.total_tokens !== undefined ? summary.usage.total_tokens : 0)}
          ${metric("Warnings", summary.warnings || 0)}
          ${metric("Errors", summary.errors || 0)}
        </div>
        ${compareInvestigationPanel(run, timeline)}
        ${summaryPanel(summary)}
        ${debugPathPanel(timeline.debug_path || [])}
        <div class="content-grid">
          <div class="panel" data-testid="timeline-panel">
            <div class="panel-head"><h3>Timeline</h3><span class="pill">${timeline.items.length}</span></div>
            <div class="panel-body">${timeline.items.map(timelineItem).join("") || '<div class="empty">No timeline items.</div>'}</div>
          </div>
          <div class="side-stack">
            <div id="spanInspector">${spanInspectorPanel()}</div>
            ${linkedRunsPanel(links)}
            <div id="artifactGroups">${artifactGroupsPanel(state.spanGroups)}</div>
            <div class="panel">
              <div class="panel-head"><h3>Annotations</h3><span class="pill">${timeline.annotations.length}</span></div>
              <div class="panel-body">
                <textarea id="annotationInput" placeholder="Add a debugging note"></textarea>
                <button onclick="addAnnotation('${run.run_id}')">Add Annotation</button>
                <div id="annotationsList">${timeline.annotations.map(annotationItem).join("") || '<div class="empty">No annotations yet.</div>'}</div>
              </div>
            </div>
            <div class="panel" data-testid="artifacts-panel">
              <div class="panel-head"><h3>Artifacts</h3><span class="pill">${timeline.artifacts.length}</span></div>
              <div class="panel-body">
                ${timeline.artifacts.map(artifactItem).join("") || '<div class="empty">No artifacts.</div>'}
                <div id="artifactPreview"></div>
              </div>
            </div>
          </div>
        </div>
      `;
      renderSidebar();
      loadSelectedSpanCompare();
    }

    function summaryPanel(summary) {
      if (!summary || !summary.first_failure) return "";
      const failure = summary.first_failure;
      return `
        <div class="panel" data-testid="run-summary-panel">
          <div class="panel-head"><h3>Run Summary</h3><span class="pill">first failure</span></div>
          <div class="panel-body">
            <div class="item">
              <strong>${escapeHtml(failure.title || failure.id || "Failure")}</strong>
              <div class="meta">${escapeHtml(failure.ts || "")} · ${escapeHtml(failure.type || failure.kind || "")}</div>
            </div>
          </div>
        </div>
      `;
    }

    function compareInvestigationPanel(run, timeline) {
      const metadata = run.metadata || {};
      const sourceRunId = metadata.source_compare_run_id || "";
      if (run.source !== "compare-ingest" && !sourceRunId) return "";
      const artifacts = timeline.artifacts || [];
      const artifactByKind = Object.fromEntries(artifacts.map(artifact => [artifact.kind, artifact]));
      const evidenceButtons = [
        compareEvidenceButton("Packet", artifactByKind["compare.packet"], "compare-evidence-packet"),
        compareEvidenceButton("Briefing", artifactByKind["compare.briefing"], "compare-evidence-briefing"),
        compareEvidenceButton("Left Body", artifactByKind["compare.left"], "compare-evidence-left"),
        compareEvidenceButton("Right Body", artifactByKind["compare.right"], "compare-evidence-right"),
      ].filter(Boolean).join("");
      const sourceButton = sourceRunId
        ? `<button class="ref-button" data-testid="compare-source-run-button" onclick="selectRun('${sourceRunId}')">Open Source Trace</button>`
        : "";
      const pairLabel = metadata.source_compare_pair_label || metadata.source_compare_pair_type || "Compare Pair";
      const spanName = metadata.source_compare_span_name || metadata.source_compare_span_id || "";
      return `
        <div class="panel" data-testid="compare-investigation-panel">
          <div class="panel-head">
            <h3>Compare Investigation</h3>
            <span class="pill">${escapeHtml(metadata.source_compare_pair_type || "compare")}</span>
          </div>
          <div class="panel-body">
            <div class="item">
              <div class="item-title">
                <strong>${escapeHtml(pairLabel)}</strong>
                <span class="pill">${escapeHtml(run.source || "investigation")}</span>
              </div>
              <div class="meta">
                Source run: ${escapeHtml(sourceRunId || "unknown")}<br />
                Source span: ${escapeHtml(spanName || "unknown")}<br />
                Source span ID: ${escapeHtml(metadata.source_compare_span_id || "")}
              </div>
              <div class="ref-buttons" data-testid="compare-evidence-buttons">
                ${sourceButton}
                ${evidenceButtons}
              </div>
            </div>
          </div>
        </div>
      `;
    }

    function compareEvidenceButton(label, artifact, testId) {
      if (!artifact) return "";
      return `
        <button class="ref-button" data-testid="${testId}" onclick="loadArtifact('${artifact.artifact_id}')">
          ${escapeHtml(label)}
        </button>
      `;
    }

    function debugPathPanel(path) {
      if (!path || !path.length) return "";
      return `
        <div class="panel" data-testid="debug-path-panel">
          <div class="panel-head"><h3>Debug Path</h3><span class="pill">${path.length}</span></div>
          <div class="panel-body">${path.map(debugPathItem).join("")}</div>
        </div>
      `;
    }

    function debugPathItem(item) {
      const refs = item.refs && Object.keys(item.refs).length
        ? `<div class="meta">refs: ${Object.keys(item.refs).sort().map(key => `${escapeHtml(key)}=${escapeHtml(String(item.refs[key]))}`).join(" · ")}</div>`
        : "";
      const artifactRefs = artifactRefButtons(item.artifact_refs || []);
      const priorityClass = item.priority === "critical" ? "error" : item.priority === "warning" ? "running" : "";
      const itemClass = item.priority === "critical" ? "debug-critical" : item.priority === "warning" ? "debug-warning" : "";
      return `
        <div class="item ${itemClass}">
          <div class="item-title">
            <strong>${escapeHtml(item.step || "?")}. ${escapeHtml(item.label || item.kind || "Inspect")}</strong>
            <span class="pill ${priorityClass}">${escapeHtml(item.priority || "note")}</span>
          </div>
          <div class="meta">${escapeHtml(item.title || item.id || "")}<br />${escapeHtml(item.ts || "")} · ${escapeHtml(item.type || item.kind || "")}</div>
          <div class="meta"><strong>Why:</strong> ${escapeHtml(item.reason || "")}</div>
          <div class="meta"><strong>Next:</strong> ${escapeHtml(item.suggested_action || "")}</div>
          ${artifactRefs}
          ${refs}
        </div>
      `;
    }

    function artifactRefButtons(refs) {
      if (!refs || !refs.length) return "";
      return `
        <div class="ref-buttons">
          ${refs.map(ref => `
            <button class="ref-button" onclick="loadArtifact('${ref.artifact_id}')">
              ${escapeHtml(ref.ref || "artifact")}: ${escapeHtml(ref.kind || ref.artifact_id)}
            </button>
          `).join("")}
        </div>
      `;
    }

    function artifactGroupsPanel(groups) {
      if (!groups || !groups.length) return "";
      return `
        <div class="panel" data-testid="artifact-groups-panel">
          <div class="panel-head"><h3>Artifact Groups</h3><span class="pill">${groups.length}</span></div>
          <div class="panel-body">${groups.map(artifactGroupItem).join("")}</div>
        </div>
      `;
    }

    function artifactGroupItem(group) {
      const active = group.span_id === state.selectedSpanId ? "active" : "";
      return `
        <div class="item ${active}" data-testid="artifact-group" data-span-id="${escapeHtml(group.span_id || "")}">
          <div class="item-title">
            <strong>${escapeHtml(group.name || group.span_id || "Span")}</strong>
            <span class="pill ${statusClass(group.status)}">${escapeHtml(group.type || "span")}</span>
          </div>
          <div class="meta">${escapeHtml(group.span_id || "")}<br />${escapeHtml(group.ts || "")}</div>
          <div class="ref-buttons">
            <button class="ref-button" onclick="selectSpanGroup('${group.span_id}')">Inspect Span</button>
            ${(group.artifacts || []).map(artifact => `
              <button class="ref-button" onclick="loadArtifact('${artifact.artifact_id}')">
                ${escapeHtml(artifact.role || artifact.ref || "artifact")}: ${escapeHtml(artifact.kind || artifact.artifact_id)}
              </button>
            `).join("")}
          </div>
        </div>
      `;
    }

    function selectSpanGroup(spanId) {
      state.selectedSpanId = spanId;
      ensureSelectedComparePair();
      renderSpanInspector();
      renderArtifactGroups();
      loadSelectedSpanCompare();
    }

    function selectComparePair(key) {
      state.selectedCompareKey = key;
      renderSpanInspector();
      loadSelectedSpanCompare();
    }

    function renderSpanInspector() {
      const target = document.getElementById("spanInspector");
      if (target) target.innerHTML = spanInspectorPanel();
    }

    function renderArtifactGroups() {
      const target = document.getElementById("artifactGroups");
      if (target) target.innerHTML = artifactGroupsPanel(state.spanGroups);
    }

    function spanInspectorPanel() {
      if (!state.spanGroups || !state.spanGroups.length) return "";
      const group = selectedSpanGroup();
      if (!group) return "";
      const artifacts = group.artifacts || [];
      const firstArtifact = artifacts[0];
      const pairs = comparePairsForGroup(group);
      return `
        <div class="panel" data-testid="span-inspector" data-span-id="${escapeHtml(group.span_id || "")}">
          <div class="panel-head">
            <h3>Span Inspector</h3>
            <span class="pill ${statusClass(group.status)}">${escapeHtml(group.status || "span")}</span>
          </div>
          <div class="panel-body">
            <div class="item active">
              <div class="item-title">
                <strong>${escapeHtml(group.name || group.span_id || "Span")}</strong>
                <span class="pill">${escapeHtml(group.type || "span")}</span>
              </div>
              <div class="meta">
                ${escapeHtml(group.span_id || "")}<br />
                ${escapeHtml(group.ts || "")} · ${artifacts.length} artifacts
              </div>
              <div class="ref-buttons">
                ${firstArtifact ? `<button class="ref-button" onclick="loadArtifact('${firstArtifact.artifact_id}')">Open Primary Artifact</button>` : ""}
              </div>
            </div>
            ${spanCompareControls(pairs)}
            ${pairs.length ? '<div id="spanArtifactCompare" class="item" data-testid="artifact-compare">Loading comparison...</div>' : ""}
            ${artifacts.map(spanInspectorArtifact).join("") || '<div class="empty">No artifacts for this span.</div>'}
          </div>
        </div>
      `;
    }

    function spanInspectorArtifact(artifact) {
      const role = artifact.role || artifact.ref || "artifact";
      const source = artifact.source ? ` · ${artifact.source}` : "";
      const redacted = artifact.redacted ? " · redacted" : "";
      return `
        <button class="row" data-testid="span-artifact-row" data-artifact-id="${escapeHtml(artifact.artifact_id)}" onclick="loadArtifact('${artifact.artifact_id}')">
          <strong>${escapeHtml(role)}: ${escapeHtml(artifact.kind || artifact.artifact_id)}</strong>
          <span class="meta">
            ${escapeHtml(artifact.artifact_id)}<br />
            ${escapeHtml(artifact.media_type || "application/octet-stream")} · ${artifact.size !== undefined ? artifact.size : "?"} bytes${escapeHtml(source)}${redacted}
          </span>
        </button>
      `;
    }

    function selectedSpanGroup() {
      return state.spanGroupIndex[state.selectedSpanId] || state.spanGroups[0] || null;
    }

    function ensureSelectedComparePair() {
      const group = selectedSpanGroup();
      const pairs = comparePairsForGroup(group);
      if (!pairs.length) {
        state.selectedCompareKey = "";
        return;
      }
      if (!pairs.some(pair => comparePairKey(pair) === state.selectedCompareKey)) {
        state.selectedCompareKey = comparePairKey(pairs[0]);
      }
    }

    function comparePairsForGroup(group) {
      if (!group || !group.artifacts) return [];
      const byRole = {};
      for (const artifact of group.artifacts) {
        const role = artifact.role || artifact.ref || "";
        if (role && !byRole[role]) byRole[role] = artifact;
      }
      const pairs = [];
      const seen = new Set();
      const addRolePair = (pairType, label, leftRole, rightRole, testId) => {
        const left = byRole[leftRole];
        const right = byRole[rightRole];
        if (!left || !right || left.artifact_id === right.artifact_id) return;
        const key = `${left.artifact_id}::${right.artifact_id}`;
        if (seen.has(key)) return;
        seen.add(key);
        pairs.push({type: pairType, label, left, right, testId});
      };
      addRolePair("request-response", "Request vs Response", "request", "response", "compare-pair-request-response");
      addRolePair("input-output", "Input vs Output", "input", "output", "compare-pair-input-output");
      addRolePair("schema-input", "Schema vs Input", "schema", "input", "compare-pair-schema-input");
      addRolePair("schema-output", "Schema vs Output", "schema", "output", "compare-pair-schema-output");
      return pairs;
    }

    function spanCompareControls(pairs) {
      if (!pairs.length) return "";
      return `
        <div class="compare-toolbar">
          <span class="meta">Compare</span>
          ${pairs.map(pair => {
            const key = comparePairKey(pair);
            const active = key === state.selectedCompareKey ? "active" : "";
            return `<button class="ref-button ${active}" data-testid="${escapeHtml(pair.testId)}" onclick="selectComparePair('${key}')">${escapeHtml(pair.label)}</button>`;
          }).join("")}
          <button class="ref-button" data-testid="compare-copy-markdown" onclick="copySelectedCompare('markdown')">Copy MD</button>
          <button class="ref-button" data-testid="compare-copy-json" onclick="copySelectedCompare('json')">Copy JSON</button>
          <button class="ref-button" data-testid="compare-download-markdown" onclick="downloadSelectedCompare('markdown')">Download MD</button>
          <button class="ref-button" data-testid="compare-download-json" onclick="downloadSelectedCompare('json')">Download JSON</button>
          <span id="compareExportStatus" class="meta compare-status" data-testid="compare-export-status"></span>
          <textarea id="compareExportText" class="compare-export-text" data-testid="compare-export-text" readonly hidden></textarea>
        </div>
      `;
    }

    function comparePairKey(pair) {
      return `${pair.left.artifact_id}::${pair.right.artifact_id}`;
    }

    function selectedComparePair() {
      const pairs = comparePairsForGroup(selectedSpanGroup());
      if (!pairs.length) return null;
      return pairs.find(pair => comparePairKey(pair) === state.selectedCompareKey) || pairs[0];
    }

    async function loadSelectedSpanCompare() {
      const target = document.getElementById("spanArtifactCompare");
      if (!target) return;
      const pair = selectedComparePair();
      if (!pair) {
        target.innerHTML = "";
        return;
      }
      const pairKey = comparePairKey(pair);
      target.innerHTML = '<div class="empty">Loading comparison...</div>';
      try {
        const texts = await Promise.all([
          loadArtifactText(pair.left.artifact_id),
          loadArtifactText(pair.right.artifact_id),
        ]);
        if (state.selectedCompareKey !== pairKey) return;
        target.className = "item";
        target.innerHTML = spanCompareBody(pair, texts[0], texts[1]);
      } catch (error) {
        target.className = "empty";
        target.textContent = `Could not load comparison: ${error.message}`;
      }
    }

    async function loadArtifactText(artifactId) {
      if (state.artifactTextCache[artifactId] !== undefined) return state.artifactTextCache[artifactId];
      const response = await fetch(`/v1/artifacts/${artifactId}`);
      if (!response.ok) throw new Error(`artifact ${artifactId} returned ${response.status}`);
      const text = await response.text();
      state.artifactTextCache[artifactId] = text;
      return text;
    }

    function spanCompareBody(pair, leftText, rightText) {
      return `
        <div class="item-title">
          <strong>${escapeHtml(pair.label)}</strong>
          <span class="pill">Artifact Compare</span>
        </div>
        <div class="compare-grid">
          ${spanComparePane(pair.left, leftText)}
          ${spanComparePane(pair.right, rightText)}
        </div>
      `;
    }

    async function copySelectedCompare(format) {
      const label = format === "json" ? "JSON" : "Markdown";
      setCompareExportStatus(`Preparing ${label}...`);
      try {
        const exportData = await fetchCompareExport(format);
        await writeTextToClipboard(exportData.text);
        hideCompareExportText();
        setCompareExportStatus(`Copied ${label} compare.`);
      } catch (error) {
        if (error.exportText) {
          showCompareExportText(error.exportText);
          setCompareExportStatus(`Clipboard unavailable; ${label} export text is selected below.`);
        } else {
          setCompareExportStatus(`Copy failed: ${error.message}`, true);
        }
      }
    }

    async function downloadSelectedCompare(format) {
      const label = format === "json" ? "JSON" : "Markdown";
      setCompareExportStatus(`Preparing ${label}...`);
      try {
        const exportData = await fetchCompareExport(format);
        const extension = format === "json" ? "json" : "md";
        const mediaType = format === "json" ? "application/json" : "text/markdown";
        const filename = safeFileToken([
          "abb-compare",
          exportData.payload.run_id,
          exportData.payload.span.span_id,
          exportData.payload.pair.type || exportData.payload.pair.label,
        ].filter(Boolean).join("-")) + `.${extension}`;
        downloadText(filename, exportData.text, mediaType);
        hideCompareExportText();
        setCompareExportStatus(`Downloaded ${label} compare.`);
      } catch (error) {
        setCompareExportStatus(`Download failed: ${error.message}`, true);
      }
    }

    async function fetchCompareExport(format) {
      const group = selectedSpanGroup();
      const pair = selectedComparePair();
      if (!group || !pair) throw new Error("no selected compare pair");
      const normalizedFormat = format === "json" ? "json" : "markdown";
      const params = new URLSearchParams({
        span: group.span_id || "",
        pair: pair.type || "auto",
        format: normalizedFormat,
      });
      const response = await fetch(`/v1/runs/${encodeURIComponent(state.selectedRunId)}/compare-export?${params.toString()}`);
      if (!response.ok) {
        let message = `compare export returned ${response.status}`;
        try {
          const error = await response.json();
          message = error.message || error.error || message;
        } catch (parseError) {
        }
        throw new Error(message);
      }
      if (normalizedFormat === "json") {
        const payload = await response.json();
        return {payload, text: JSON.stringify(payload, null, 2)};
      }
      const text = await response.text();
      return {
        payload: {
          run_id: state.selectedRunId,
          span: {span_id: group.span_id || ""},
          pair: {type: pair.type || "", label: pair.label || ""},
        },
        text,
      };
    }

    async function writeTextToClipboard(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(text);
          return;
        } catch (error) {
          // Fall back when the browser denies async clipboard writes for focus.
        }
      }
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      textarea.style.top = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      if (!copied) {
        const error = new Error("clipboard unavailable");
        error.exportText = text;
        throw error;
      }
    }

    function showCompareExportText(text) {
      const output = document.getElementById("compareExportText");
      if (!output) return;
      output.hidden = false;
      output.value = text;
      output.focus();
      output.select();
    }

    function hideCompareExportText() {
      const output = document.getElementById("compareExportText");
      if (!output) return;
      output.hidden = true;
      output.value = "";
    }

    function downloadText(filename, text, mediaType) {
      const blob = new Blob([text], {type: `${mediaType}; charset=utf-8`});
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    }

    function setCompareExportStatus(message, isError = false) {
      const status = document.getElementById("compareExportStatus");
      if (!status) return;
      status.textContent = message;
      status.className = `meta compare-status ${isError ? "status-error" : "status-ok"}`;
    }

    function safeFileToken(value) {
      const token = String(value || "compare")
        .replace(/[^a-zA-Z0-9._-]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 120);
      return token || "compare";
    }

    function spanComparePane(artifact, text) {
      const role = artifact.role || artifact.ref || "artifact";
      return `
        <div class="compare-pane" data-testid="compare-pane" data-artifact-role="${escapeHtml(role)}">
          <div class="item-title">
            <strong>${escapeHtml(role)}</strong>
            <span class="pill">${escapeHtml(artifact.kind || "artifact")}</span>
          </div>
          <div class="meta">
            ${escapeHtml(artifact.artifact_id)}<br />
            ${escapeHtml(artifact.media_type || "application/octet-stream")} · ${artifact.size !== undefined ? artifact.size : text.length} bytes${artifact.redacted ? " · redacted" : ""}
          </div>
          ${artifactPreviewBody(artifact, text)}
        </div>
      `;
    }

    function linkedRunsPanel(links) {
      if (!links || (!links.source && !(links.investigations || []).length)) return "";
      const source = links.source
        ? `<button class="row" onclick="selectRun('${links.source.run_id}')">
             <strong>${escapeHtml(links.source.name)}</strong>
             <span class="meta">${escapeHtml(links.source.run_id)}<br />${escapeHtml(links.source.status)} · ${escapeHtml(links.source.created_at)}</span>
           </button>`
        : "";
      const investigations = (links.investigations || []).map(run => `
        <button class="row" onclick="selectRun('${run.run_id}')">
          <strong>${escapeHtml(run.name)}</strong>
          <span class="meta">${escapeHtml(run.run_id)}<br />${escapeHtml(run.status)} · ${escapeHtml(run.created_at)}</span>
        </button>
      `).join("");
      return `
        <div class="panel">
          <div class="panel-head"><h3>Linked Runs</h3><span class="pill">${(links.investigations || []).length + (links.source ? 1 : 0)}</span></div>
          <div class="panel-body">
            ${links.source ? '<div class="meta">Source trace</div>' + source : ""}
            ${(links.investigations || []).length ? '<div class="meta">Investigations</div>' + investigations : ""}
          </div>
        </div>
      `;
    }

    function timelineItem(item) {
      const title = item.name || item.message || item.type || "Untitled";
      const usage = usagePills(item.attributes && item.attributes.usage);
      const inspect = item.kind === "span" && item.span_id && state.spanGroupIndex[item.span_id]
        ? `<div class="ref-buttons"><button class="ref-button" onclick="selectSpanGroup('${item.span_id}')">Inspect Span</button></div>`
        : "";
      const attrs = item.attributes && Object.keys(item.attributes).length
        ? `<pre>${escapeHtml(JSON.stringify(item.attributes, null, 2))}</pre>`
        : "";
      return `
        <div class="item">
          <div class="item-title">
            <strong>${escapeHtml(title)}</strong>
            <span class="pill ${statusClass(item.status)}">${escapeHtml(item.type || item.kind)}</span>
          </div>
          <div class="meta">${escapeHtml(item.ts || item.started_at || "")} · ${escapeHtml(item.status || item.kind || "")}</div>
          ${usage}
          ${inspect}
          ${attrs}
        </div>
      `;
    }

    function usagePills(usage) {
      if (!usage || typeof usage !== "object") return "";
      const parts = [
        usage.input_tokens !== undefined ? `input ${usage.input_tokens}` : "",
        usage.output_tokens !== undefined ? `output ${usage.output_tokens}` : "",
        usage.total_tokens !== undefined ? `total ${usage.total_tokens}` : ""
      ].filter(Boolean);
      if (!parts.length) return "";
      return `<div class="usage-row">${parts.map(part => `<span class="pill">tokens ${escapeHtml(part)}</span>`).join("")}</div>`;
    }

    function annotationItem(annotation) {
      const target = annotation.span_id ? ` · ${annotation.span_id}` : "";
      return `
        <div class="item">
          <strong>${escapeHtml(annotation.message)}</strong>
          <div class="meta">${escapeHtml(annotation.created_at)}${escapeHtml(target)}</div>
        </div>
      `;
    }

    async function addAnnotation(runId) {
      const input = document.getElementById("annotationInput");
      const message = input.value.trim();
      if (!message) return;
      await fetch("/v1/annotations", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({run_id: runId, message})
      });
      input.value = "";
      await loadRun(runId);
    }

    function artifactItem(artifact) {
      return `
        <button class="row" data-testid="artifact-row" data-artifact-id="${escapeHtml(artifact.artifact_id)}" onclick="loadArtifact('${artifact.artifact_id}')">
          <strong>${escapeHtml(artifact.kind)}</strong>
          <span class="meta">
            ${escapeHtml(artifact.artifact_id)}<br />
            ${escapeHtml(artifact.media_type)} · ${artifact.size} bytes
          </span>
        </button>
      `;
    }

    async function loadArtifact(artifactId) {
      state.selectedArtifactId = artifactId;
      const preview = document.getElementById("artifactPreview");
      if (!preview) return;
      preview.innerHTML = '<div class="empty">Loading...</div>';
      const response = await fetch(`/v1/artifacts/${artifactId}`);
      const text = await response.text();
      const artifact = state.artifactIndex[artifactId] || {artifact_id: artifactId};
      preview.innerHTML = `
        <div class="item" data-testid="artifact-preview">
          <div class="item-title"><strong>${escapeHtml(artifact.kind || artifactId)}</strong><span class="pill">artifact</span></div>
          <div class="meta">
            ${escapeHtml(artifactId)}<br />
            ${escapeHtml(artifact.media_type || "application/octet-stream")} · ${artifact.size !== undefined ? artifact.size : text.length} bytes${artifact.redacted ? " · redacted" : ""}
          </div>
          ${artifactPreviewBody(artifact, text)}
        </div>
      `;
      preview.scrollIntoView({block: "nearest"});
    }

    function artifactPreviewBody(artifact, text) {
      const mediaType = artifact.media_type || "";
      if (mediaType.includes("json") || /^[\s]*[\[{]/.test(text)) {
        try {
          return `<pre>${escapeHtml(JSON.stringify(JSON.parse(text), null, 2))}</pre>`;
        } catch (error) {
          return `<pre>${escapeHtml(text)}</pre>`;
        }
      }
      return `<pre>${escapeHtml(text)}</pre>`;
    }

    async function createFixture(runId) {
      const response = await fetch(`/v1/runs/${runId}/fixture`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name: `${runId} fixture`})
      });
      const fixture = await response.json();
      state.selectedFixtureId = fixture.fixture_id;
      await refreshAll();
      setMode("fixtures");
      await loadFixture(fixture.fixture_id);
    }

    async function exportRun(runId, format) {
      const response = await fetch(`/v1/runs/${runId}/export`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({format})
      });
      const result = await response.json();
      const detail = document.getElementById("detail");
      detail.insertAdjacentHTML("afterbegin", `<div class="item"><strong>Exported</strong><div class="meta">${escapeHtml(result.path)}</div></div>`);
    }

    async function deleteRun(runId) {
      const run = state.runs.find(candidate => candidate.run_id === runId);
      const label = run ? `${run.name} (${run.run_id})` : runId;
      if (!confirm(`Delete ${label}? This removes the local trace, artifacts, fixtures, and default exports for this run.`)) {
        return;
      }
      const response = await fetch(`/v1/runs/${encodeURIComponent(runId)}`, {method: "DELETE"});
      const result = await response.json();
      if (!response.ok) {
        alert(result.message || result.error || "Delete failed");
        return;
      }
      state.selectedRunId = null;
      state.selectedArtifactId = null;
      state.selectedSpanId = null;
      state.artifactIndex = {};
      state.artifactTextCache = {};
      state.runs = await fetchJson("/v1/runs?limit=100");
      state.fixtures = await fetchJson("/v1/fixtures?limit=100");
      renderSidebar();
      const detail = document.getElementById("detail");
      detail.className = "";
      detail.innerHTML = `
        <div class="item" data-testid="delete-run-result">
          <strong>Deleted ${escapeHtml(result.run_id)}</strong>
          <div class="meta">
            ${escapeHtml(result.counts.artifacts || 0)} artifacts ·
            ${escapeHtml(result.counts.artifact_objects || 0)} object files ·
            ${escapeHtml(result.counts.export_files || 0)} export files
          </div>
        </div>
      `;
    }

    async function importBundle() {
      const pathInput = document.getElementById("importPath");
      const conflictInput = document.getElementById("importConflict");
      const status = document.getElementById("importStatus");
      const path = pathInput ? pathInput.value.trim() : "";
      const onConflict = conflictInput ? conflictInput.value : "fail";
      if (!path) {
        state.importMessage = "Choose a bundle path.";
        if (status) status.textContent = state.importMessage;
        return;
      }
      if (status) status.textContent = "Importing...";
      const response = await fetch("/v1/bundles/import", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({path, on_conflict: onConflict})
      });
      const result = await response.json();
      if (!response.ok) {
        state.importMessage = result.message || result.error || "Import failed";
        if (status) status.textContent = state.importMessage;
        return;
      }
      state.importMessage = result.skipped
        ? `Skipped ${result.run_id}`
        : `Imported ${result.run_id}`;
      state.selectedRunId = result.run_id;
      await refreshAll();
      if (!result.skipped) await loadRun(result.run_id);
    }

    async function createAgentKit() {
      const outputInput = document.getElementById("agentKitOutput");
      const zipOutputInput = document.getElementById("agentKitZipOutput");
      const zipInput = document.getElementById("agentKitZip");
      const forceInput = document.getElementById("agentKitForce");
      const status = document.getElementById("agentKitStatus");
      const output = outputInput ? outputInput.value.trim() : "";
      const zip_output = zipOutputInput ? zipOutputInput.value.trim() : "";
      const zip = zipInput ? zipInput.checked : false;
      const force = forceInput ? forceInput.checked : false;
      if (status) status.textContent = "Creating agent kit...";
      const response = await fetch("/v1/agent-kit", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({output, force, zip, zip_output})
      });
      const result = await response.json();
      if (!response.ok) {
        state.agentKitMessage = result.message || result.error || "Agent kit failed";
        state.agentKit = null;
        renderSidebar();
        return;
      }
      state.agentKit = result;
      const files = result.files || {};
      state.agentKitMessage = `Agent kit ready: ${files.manifest || result.kit_id}`;
      renderSidebar();
    }

    async function ingestHandoff() {
      const pathInput = document.getElementById("handoffPath");
      const nameInput = document.getElementById("handoffName");
      const status = document.getElementById("handoffStatus");
      const path = pathInput ? pathInput.value.trim() : "";
      const name = nameInput ? nameInput.value.trim() : "";
      if (!path) {
        state.handoffMessage = "Choose a handoff packet path.";
        if (status) status.textContent = state.handoffMessage;
        return;
      }
      if (status) status.textContent = "Creating investigation...";
      const response = await fetch("/v1/handoffs/ingest", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({path, name})
      });
      const result = await response.json();
      if (!response.ok) {
        state.handoffMessage = result.message || result.error || "Handoff ingest failed";
        if (status) status.textContent = state.handoffMessage;
        return;
      }
      const runId = result.run && result.run.run_id;
      state.handoffMessage = `Created ${runId}`;
      state.selectedRunId = runId;
      await refreshAll();
      if (runId) await loadRun(runId);
    }

    async function ingestCompare() {
      const pathInput = document.getElementById("comparePath");
      const nameInput = document.getElementById("compareName");
      const status = document.getElementById("compareStatus");
      const path = pathInput ? pathInput.value.trim() : "";
      const name = nameInput ? nameInput.value.trim() : "";
      if (!path) {
        state.compareMessage = "Choose a compare packet path.";
        if (status) status.textContent = state.compareMessage;
        return;
      }
      if (status) status.textContent = "Creating compare investigation...";
      const response = await fetch("/v1/compare/ingest", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({path, name})
      });
      const result = await response.json();
      if (!response.ok) {
        state.compareMessage = result.message || result.error || "Compare ingest failed";
        if (status) status.textContent = state.compareMessage;
        return;
      }
      const runId = result.run && result.run.run_id;
      state.compareMessage = `Created ${runId}`;
      state.selectedRunId = runId;
      await refreshAll();
      if (runId) await loadRun(runId);
    }

    async function loadFixture(fixtureId) {
      state.mode = "fixtures";
      state.selectedFixtureId = fixtureId;
      setActiveTabOnly("fixtures");
      const fixture = await fetchJson(`/v1/fixtures/${fixtureId}`);
      const body = fixture.fixture || {};
      const expected = body.expected || {};
      document.getElementById("detail").className = "";
      document.getElementById("detail").innerHTML = `
        <div class="split">
          <div>
            <h2>${escapeHtml(fixture.name)}</h2>
            <div class="meta">${escapeHtml(fixture.fixture_id)} · ${escapeHtml(fixture.run_id)} · ${escapeHtml(fixture.created_at)}</div>
          </div>
          <div class="actions">
            <button onclick="selectRun('${fixture.run_id}')">Open Run</button>
          </div>
        </div>
        <div class="metrics">
          ${metric("Status", expected.status || "n/a")}
          ${metric("Spans", expected.span_count || 0)}
          ${metric("Events", expected.event_count || 0)}
          ${metric("Artifacts", expected.artifact_count || 0)}
        </div>
        <div class="panel">
          <div class="panel-head"><h3>Replay</h3><span class="pill">${(body.timeline || []).length}</span></div>
          <div class="panel-body">${(body.timeline || []).map(replayItem).join("") || '<div class="empty">No replay items.</div>'}</div>
        </div>
      `;
      renderSidebar();
    }

    function replayItem(item, index) {
      const title = item.name || item.message || item.type || "Untitled";
      return `
        <div class="item">
          <div class="item-title">
            <strong>${String(index + 1).padStart(3, "0")}. ${escapeHtml(title)}</strong>
            <span class="pill ${statusClass(item.status)}">${escapeHtml(item.type || item.kind || "event")}</span>
          </div>
          <div class="meta">${escapeHtml(item.status || "recorded")}</div>
        </div>
      `;
    }

    function renderFixturesHome() {
      document.getElementById("detail").className = state.fixtures.length ? "" : "empty";
      if (!state.fixtures.length) {
        document.getElementById("detail").innerHTML = "No fixtures.";
        return;
      }
      loadFixture(state.fixtures[0].fixture_id);
    }

    function renderDiff() {
      setActiveTabOnly("diff");
      const first = state.selectedRunId || (state.runs[0] && state.runs[0].run_id) || "";
      const second = nextRunId(first);
      document.getElementById("detail").className = "";
      document.getElementById("detail").innerHTML = `
        <h2>Run Diff</h2>
        <div class="form-grid">
          <label><span class="meta">Run A</span>${runSelect("diffA", first)}</label>
          <label><span class="meta">Run B</span>${runSelect("diffB", second)}</label>
          <button onclick="loadDiff()">Compare</button>
        </div>
        <div id="diffResult" class="empty">Choose two runs.</div>
      `;
      renderSidebar();
    }

    async function loadDiff() {
      const runA = document.getElementById("diffA").value;
      const runB = document.getElementById("diffB").value;
      const target = document.getElementById("diffResult");
      if (!runA || !runB) {
        target.className = "empty";
        target.innerHTML = "Choose two runs.";
        return;
      }
      const diff = await fetchJson(`/v1/diff?run_a=${encodeURIComponent(runA)}&run_b=${encodeURIComponent(runB)}`);
      target.className = "panel";
      const divergence = diff.first_divergence;
      target.innerHTML = `
        <div class="panel-head"><h3>${escapeHtml(diff.run_a.name)} -> ${escapeHtml(diff.run_b.name)}</h3><span class="pill">diff</span></div>
        <div class="panel-body">
          <div class="metrics">
            ${metric("Spans", `${diff.counts.spans.a} -> ${diff.counts.spans.b}`)}
            ${metric("Events", `${diff.counts.events.a} -> ${diff.counts.events.b}`)}
            ${metric("Artifacts", `${diff.counts.artifacts.a} -> ${diff.counts.artifacts.b}`)}
            ${metric("First", divergence ? `#${divergence.index}` : "none")}
          </div>
          <div class="content-grid">
            <div class="item"><strong>Span Types</strong>${typeDelta(diff.span_types)}</div>
            <div class="item"><strong>Event Types</strong>${typeDelta(diff.event_types)}</div>
          </div>
          ${divergence ? `<div class="item"><strong>First Divergence</strong><pre>${escapeHtml(JSON.stringify(divergence, null, 2))}</pre></div>` : '<div class="empty">No normalized timeline divergence.</div>'}
        </div>
      `;
    }

    function runSelect(id, selected) {
      return `
        <select id="${id}">
          ${state.runs.map(run => `<option value="${escapeHtml(run.run_id)}" ${run.run_id === selected ? "selected" : ""}>${escapeHtml(run.name)} · ${escapeHtml(run.status)}</option>`).join("")}
        </select>
      `;
    }

    function nextRunId(current) {
      const other = state.runs.find(run => run.run_id !== current);
      return other ? other.run_id : current;
    }

    function typeDelta(delta) {
      const rows = Object.entries(delta || {}).map(([name, counts]) => `<div class="meta">${escapeHtml(name)}: ${counts.a} -> ${counts.b}</div>`);
      return rows.join("") || '<div class="meta">none</div>';
    }

    function metric(label, value) {
      return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
    }

    function renderEmpty(mode) {
      document.getElementById("detail").className = "empty";
      document.getElementById("detail").innerHTML = mode === "runs" ? "No runs." : "No data.";
    }

    function setActiveTabOnly(mode) {
      state.mode = mode;
      for (const name of ["runs", "fixtures", "diff"]) {
        document.getElementById(`tab-${name}`).classList.toggle("active", name === mode);
      }
    }

    async function fetchJson(path) {
      const response = await fetch(path);
      return response.json();
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    refreshAll();
  </script>
</body>
</html>
"""


class ABBRequestHandler(BaseHTTPRequestHandler):
    store: ABBStore
    auth_token: Optional[str] = None

    server_version = "AgentBlackBox/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if getattr(self.server, "quiet", False):
            return
        super().log_message(fmt, *args)

    def do_GET(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == "/":
                self._send(200, HTML_APP.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/health":
                self._json(200, {"ok": True, "data_dir": str(self.store.root), "service": "agent-black-box"})
                return
            if path == "/v1/endpoints":
                host = self.headers.get("Host", "127.0.0.1:43188")
                self._json(200, api_manifest(f"http://{host}"))
                return
            if path == "/v1/openapi.json":
                host = self.headers.get("Host", "127.0.0.1:43188")
                self._json(200, openapi_spec(f"http://{host}"))
                return
            if path == "/v1/runs":
                limit = int(query.get("limit", ["50"])[0])
                self._json(200, self.store.list_runs(limit=limit))
                return
            if path.startswith("/v1/runs/") and path.endswith("/timeline"):
                run_id = path.split("/")[3]
                self._json(200, self.store.get_timeline(run_id))
                return
            if path.startswith("/v1/runs/") and path.endswith("/links"):
                run_id = path.split("/")[3]
                self._json(200, self.store.get_run_links(run_id))
                return
            if path.startswith("/v1/runs/") and path.endswith("/compare-export"):
                run_id = path.split("/")[3]
                span_id = (query.get("span_id") or query.get("span") or [None])[0] or None
                pair = query.get("pair", ["auto"])[0]
                fmt = query.get("format", ["json"])[0]
                if fmt not in {"json", "markdown", "md"}:
                    self._json(400, {"error": "bad_request", "message": "format must be one of: json, markdown, md"})
                    return
                payload = self.store.build_compare_export(run_id, span_id=span_id, pair=pair)
                if fmt == "json":
                    self._json(200, payload)
                    return
                if fmt in {"markdown", "md"}:
                    self._send(
                        200,
                        format_compare_export(payload, fmt).encode("utf-8"),
                        "text/markdown; charset=utf-8",
                    )
                    return
            if path.startswith("/v1/runs/") and path.endswith("/compare-evidence"):
                run_id = path.split("/")[3]
                part = (query.get("part") or [None])[0] or None
                fmt = query.get("format", ["json"])[0]
                raw = (query.get("raw", ["0"])[0] or "").lower() in {"1", "true", "yes", "on"}
                if not part:
                    if fmt != "json":
                        self._json(400, {"error": "bad_request", "message": "part is required when format is not json"})
                        return
                    self._json(200, self.store.compare_evidence_summary(run_id))
                    return
                result = self.store.get_compare_evidence(run_id, part, raw=raw)
                if fmt == "json":
                    self._json(200, result)
                    return
                if fmt in {"text", "txt"}:
                    self._send(200, result["content"].encode("utf-8"), "text/plain; charset=utf-8")
                    return
                self._json(400, {"error": "bad_request", "message": "format must be one of: json, text, txt"})
                return
            if path.startswith("/v1/runs/") and path.endswith("/artifacts"):
                run_id = path.split("/")[3]
                self._json(200, self.store.list_artifacts(run_id))
                return
            if path.startswith("/v1/runs/") and path.endswith("/annotations"):
                run_id = path.split("/")[3]
                self._json(200, self.store.list_annotations(run_id))
                return
            if path.startswith("/v1/runs/"):
                run_id = path.split("/")[3]
                run = self.store.get_run(run_id)
                if not run:
                    self._json(404, {"error": "run_not_found"})
                    return
                self._json(200, run)
                return
            if path == "/v1/search":
                q = query.get("q", [""])[0]
                self._json(200, self.store.search(q) if q else [])
                return
            if path == "/v1/diff":
                run_a = query.get("run_a", [""])[0]
                run_b = query.get("run_b", [""])[0]
                if not run_a or not run_b:
                    self._json(400, {"error": "missing_run_ids"})
                    return
                self._json(200, compare_runs(self.store, run_a, run_b))
                return
            if path == "/v1/fixtures":
                limit = int(query.get("limit", ["50"])[0])
                self._json(200, self.store.list_fixtures(limit=limit))
                return
            if path.startswith("/v1/fixtures/"):
                fixture_id = path.split("/")[3]
                fixture = self.store.get_fixture(fixture_id)
                if not fixture:
                    self._json(404, {"error": "fixture_not_found"})
                    return
                self._json(200, fixture)
                return
            if path.startswith("/v1/artifacts/"):
                artifact_id = path.split("/")[3]
                content = self.store.read_artifact(artifact_id)
                if content is None:
                    self._json(404, {"error": "artifact_not_found"})
                    return
                self._send(200, content, "application/octet-stream")
                return
            self._json(404, {"error": "not_found"})
        except KeyError:
            self._json(404, {"error": "not_found"})
        except ValueError as exc:
            self._json(400, {"error": "bad_request", "message": str(exc)})
        except Exception as exc:
            self._json(500, {"error": "internal_error", "message": str(exc)})

    def do_POST(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/proxy/openai/"):
            self._handle_openai_proxy(path, parsed.query)
            return
        payload = self._read_json()

        try:
            if path == "/v1/runs":
                self._json(201, self.store.create_run(payload))
                return
            if path.startswith("/v1/runs/") and path.endswith("/end"):
                run_id = path.split("/")[3]
                self._json(200, self.store.end_run(run_id, payload.get("status", "ok")))
                return
            if path.startswith("/v1/runs/") and path.endswith("/fixture"):
                run_id = path.split("/")[3]
                self._json(201, self.store.create_fixture(run_id, name=payload.get("name")))
                return
            if path == "/v1/spans":
                self._json(201, self.store.start_span(payload))
                return
            if path.startswith("/v1/spans/") and path.endswith("/end"):
                span_id = path.split("/")[3]
                self._json(
                    200,
                    self.store.end_span(
                        span_id,
                        payload.get("status", "ok"),
                        attributes=payload.get("attributes"),
                        output_ref=payload.get("output_ref"),
                    ),
                )
                return
            if path == "/v1/events":
                self._json(201, self.store.add_event(payload))
                return
            if path == "/v1/annotations":
                self._json(
                    201,
                    self.store.add_annotation(
                        payload["run_id"],
                        payload["message"],
                        span_id=payload.get("span_id"),
                    ),
                )
                return
            if path == "/v1/artifacts":
                content = payload.get("content", "")
                self._json(
                    201,
                    self.store.add_artifact(
                        payload.get("run_id"),
                        payload.get("span_id"),
                        payload.get("kind", "artifact"),
                        content,
                        media_type=payload.get("media_type", "text/plain"),
                    ),
                )
                return
            if path == "/v1/batch":
                result: Dict[str, Any] = {"runs": [], "spans": [], "events": [], "annotations": []}
                for run in payload.get("runs", []):
                    result["runs"].append(self.store.create_run(run))
                for span in payload.get("spans", []):
                    result["spans"].append(self.store.start_span(span))
                for event in payload.get("events", []):
                    result["events"].append(self.store.add_event(event))
                for annotation in payload.get("annotations", []):
                    result["annotations"].append(
                        self.store.add_annotation(
                            annotation["run_id"],
                            annotation["message"],
                            span_id=annotation.get("span_id"),
                        )
                    )
                self._json(200, result)
                return
            if path == "/v1/agent-kit":
                host = self.headers.get("Host", "127.0.0.1:43188")
                daemon_url = (payload.get("url") or f"http://{host}").rstrip("/")
                try:
                    result = create_agent_kit(
                        self.store,
                        daemon_url=daemon_url,
                        output=payload.get("output") or None,
                        force=bool(payload.get("force")),
                        zip_archive=bool(payload.get("zip")),
                        zip_output=payload.get("zip_output") or None,
                    )
                except (OSError, ValueError) as exc:
                    self._json(400, {"error": "agent_kit_failed", "message": str(exc)})
                    return
                self._json(201, result)
                return
            if path == "/v1/bundles/import":
                bundle_path = payload.get("path")
                if not bundle_path:
                    self._json(400, {"error": "missing_field", "field": "path"})
                    return
                try:
                    result = self.store.import_bundle(
                        bundle_path,
                        on_conflict=payload.get("on_conflict", "fail"),
                    )
                except (ValueError, json.JSONDecodeError, OSError, zipfile.BadZipFile) as exc:
                    self._json(400, {"error": "bundle_import_failed", "message": str(exc)})
                    return
                self._json(200 if result.get("skipped") else 201, result)
                return
            if path == "/v1/handoffs/ingest":
                handoff_path = payload.get("path")
                if not handoff_path:
                    self._json(400, {"error": "missing_field", "field": "path"})
                    return
                try:
                    packet = json.loads(Path(handoff_path).read_text(encoding="utf-8"))
                    if not isinstance(packet, dict):
                        raise ValueError("handoff packet must be a JSON object")
                    briefing = format_handoff_briefing(packet)
                    result = self.store.ingest_handoff_packet(
                        packet,
                        briefing,
                        name=payload.get("name") or None,
                    )
                except (ValueError, json.JSONDecodeError, OSError) as exc:
                    self._json(400, {"error": "handoff_ingest_failed", "message": str(exc)})
                    return
                self._json(201, result)
                return
            if path == "/v1/compare/ingest":
                compare_path = payload.get("path")
                if not compare_path:
                    self._json(400, {"error": "missing_field", "field": "path"})
                    return
                try:
                    packet = json.loads(Path(compare_path).read_text(encoding="utf-8"))
                    if not isinstance(packet, dict):
                        raise ValueError("compare packet must be a JSON object")
                    briefing = format_compare_briefing(packet)
                    result = self.store.ingest_compare_packet(
                        packet,
                        name=payload.get("name") or None,
                        briefing=briefing,
                    )
                except (ValueError, json.JSONDecodeError, OSError) as exc:
                    self._json(400, {"error": "compare_ingest_failed", "message": str(exc)})
                    return
                self._json(201, result)
                return
            if path.startswith("/v1/runs/") and path.endswith("/export"):
                run_id = path.split("/")[3]
                fmt = payload.get("format", "jsonl")
                if fmt in {"abb", "bundle"}:
                    output = self.store.export_bundle(run_id)
                else:
                    output = self.store.export_run(run_id, fmt=fmt)
                self._json(201, {"path": str(output), "format": fmt})
                return
            self._json(404, {"error": "not_found"})
        except KeyError as exc:
            self._json(400, {"error": "missing_field", "field": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": "bad_request", "message": str(exc)})
        except Exception as exc:
            self._json(500, {"error": "internal_error", "message": str(exc)})

    def do_DELETE(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "v1" and parts[1] == "runs":
                run_id = parts[2]
                keep_exports = (query.get("keep_exports", ["false"])[0] or "").lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                self._json(200, self.store.delete_run(run_id, include_exports=not keep_exports))
                return
            self._json(404, {"error": "not_found"})
        except KeyError:
            self._json(404, {"error": "run_not_found"})
        except Exception as exc:
            self._json(500, {"error": "internal_error", "message": str(exc)})

    def _authorized(self) -> bool:
        if not self.auth_token:
            return True
        header = self.headers.get("Authorization", "")
        if header == f"Bearer {self.auth_token}":
            return True
        self._json(401, {"error": "unauthorized"})
        return False

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _handle_openai_proxy(self, path: str, query: str) -> None:
        body = self._read_body()
        headers = {key: value for key, value in self.headers.items()}
        try:
            status, response_headers, response_body = proxy_openai_request(
                self.store,
                self.command,
                path,
                query,
                headers,
                body,
            )
            self._send_with_headers(status, response_body, response_headers)
        except Exception as exc:
            self._json(500, {"error": "proxy_error", "message": str(exc)})

    def _json(self, status: int, payload: Any) -> None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        self._send(status, data, "application/json; charset=utf-8")

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "http://localhost")
        self.end_headers()
        self.wfile.write(data)

    def _send_with_headers(self, status: int, data: bytes, headers: Dict[str, str]) -> None:
        self.send_response(status)
        sent_content_type = False
        for key, value in headers.items():
            if key.lower() == "content-length":
                continue
            if key.lower() == "content-type":
                sent_content_type = True
            self.send_header(key, value)
        if not sent_content_type:
            self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_handler(store: ABBStore, auth_token: Optional[str] = None):
    class Handler(ABBRequestHandler):
        pass

    Handler.store = store
    Handler.auth_token = auth_token
    return Handler


def build_server(
    store: ABBStore,
    host: str = "127.0.0.1",
    port: int = 43188,
    auth_token: Optional[str] = None,
    quiet: bool = False,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(store, auth_token))
    server.quiet = quiet
    return server


def serve(
    data_dir: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 43188,
    auth_token: Optional[str] = None,
    quiet: bool = False,
) -> None:
    store = ABBStore(data_dir)
    server = build_server(store, host=host, port=port, auth_token=auth_token, quiet=quiet)
    print(f"Agent Black Box daemon listening on http://{host}:{server.server_port}")
    print(f"Data directory: {store.root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Agent Black Box daemon")
    finally:
        server.server_close()
        store.close()


def serve_in_thread(
    store: ABBStore,
    host: str = "127.0.0.1",
    port: int = 0,
    auth_token: Optional[str] = None,
) -> Tuple[ThreadingHTTPServer, threading.Thread]:
    server = build_server(store, host=host, port=port, auth_token=auth_token, quiet=True)
    thread = threading.Thread(target=server.serve_forever, name="abb-daemon", daemon=True)
    thread.start()
    return server, thread
