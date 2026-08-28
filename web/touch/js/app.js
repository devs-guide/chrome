import { loadCatalog, testById } from "./catalog.js";
import { detectEnvironment } from "./detect.js";
import {
  exportReport,
  importReport,
  loadReport,
  progress,
  resetReport,
  saveReport,
  updateResult
} from "./report.js";
import { startRouter, testHref } from "./router.js";
import { setupPointerTest } from "./tests/pointer.js";
import { setupTouchTest } from "./tests/touch.js";

const view = document.querySelector("#app-view");
const secureStatus = document.querySelector("#secure-status");
const networkStatus = document.querySelector("#network-status");
const workerStatus = document.querySelector("#worker-status");
let catalog;
let environment;
let report;
let disposeRoute = () => {};

function escapeHtml(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function resultFor(id) {
  return report.results.find((result) => result.id === id);
}

function statusLabel(status) {
  return status.replace(/-/g, " ");
}

function statusClass(status) {
  if (status === "passed" || status === "expected-unavailable") return "pass";
  if (status === "failed" || status === "unexpected-unavailable") return "fail";
  return "warm";
}

function updateRuntimeStatus() {
  secureStatus.textContent = window.isSecureContext ? "Secure context" : "Not a secure context";
  secureStatus.className = `status-pill ${window.isSecureContext ? "pass" : "fail"}`;
  networkStatus.textContent = navigator.onLine ? "Network reachable" : "Offline mode";
  networkStatus.className = "status-pill pass";
}

async function registerWorker() {
  if (!("serviceWorker" in navigator)) {
    workerStatus.textContent = "Service worker unavailable";
    workerStatus.className = "status-pill fail";
    return;
  }
  try {
    await navigator.serviceWorker.register(new URL("../service-worker.js", import.meta.url), { scope: "./" });
    await navigator.serviceWorker.ready;
    workerStatus.textContent = navigator.serviceWorker.controller ? "Offline cache active" : "Offline cache installed · reload once";
    workerStatus.className = "status-pill pass";
  } catch (error) {
    workerStatus.textContent = `Offline cache failed: ${error.message}`;
    workerStatus.className = "status-pill fail";
  }
}

function setNavigation(route) {
  const name = route.name === "test" ? "tests" : route.name;
  document.querySelectorAll("[data-nav]").forEach((link) => {
    if (link.dataset.nav === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function renderRun() {
  const runProgress = progress(report);
  const next = catalog.tests.find((test) => {
    const status = resultFor(test.id).status;
    return status === "pending" || status === "not-exercised";
  });
  view.innerHTML = `
    <section class="hero hero-grid">
      <div>
        <p class="eyebrow">Guided mode · ${escapeHtml(catalog.suiteVersion)}</p>
        <h1>Observe the browser you actually have.</h1>
        <p class="lede">Exercise touch and pointer behavior, keep evidence on-device, and run the identical application from public Pages or an isolated trusted LAN.</p>
        <div class="button-row">
          ${next ? `<a class="button" href="${testHref(next.id)}">Continue with ${escapeHtml(next.name)}</a>` : '<a class="button" href="#/report">Review completed report</a>'}
          <a class="button secondary" href="#/tests">Select a test</a>
        </div>
      </div>
      <aside class="panel" aria-label="Run summary">
        <div class="metric"><strong>${runProgress.complete}/${runProgress.total}</strong><span>tests recorded</span></div>
        <div class="metric"><strong>${environment.platform.maxTouchPoints}</strong><span>browser-reported max touch points</span></div>
        <div class="metric"><strong>${window.isSecureContext ? "yes" : "no"}</strong><span>secure context</span></div>
        <div class="metric"><strong>${navigator.onLine ? "online" : "offline"}</strong><span>current connectivity signal</span></div>
      </aside>
    </section>
    <div class="section-head"><div><p class="eyebrow">Run order</p><h2>Initial diagnostic path</h2></div><span class="chip">catalog ${escapeHtml(catalog.catalogVersion)}</span></div>
    <section class="grid">${catalog.tests.map(testCard).join("")}</section>
  `;
}

function testCard(test) {
  const result = resultFor(test.id);
  return `
    <a class="test-card" href="${testHref(test.id)}">
      <div class="metadata"><span class="chip">${escapeHtml(test.category)}</span><span class="chip">${escapeHtml(test.automationLevel)}</span></div>
      <div><h3>${escapeHtml(test.name)}</h3><p>${escapeHtml(test.description)}</p></div>
      <div class="card-footer"><span class="chip ${statusClass(result.status)}">${escapeHtml(statusLabel(result.status))}</span><span aria-hidden="true">→</span></div>
    </a>
  `;
}

function renderTests() {
  view.innerHTML = `
    <div class="section-head">
      <div><p class="eyebrow">Direct selection</p><h1>Select a test</h1><p class="lede">Expected results provide context. Only runtime evidence changes an observed result.</p></div>
      <a class="button secondary" href="#/run">Guided mode</a>
    </div>
    <section class="grid">${catalog.tests.map(testCard).join("")}</section>
    <div class="section-head"><div><p class="eyebrow">Research boundary</p><h2>Primary references</h2></div></div>
    <section class="grid">${catalog.sources.map((source) => `
      <a class="test-card" href="${escapeHtml(source.url)}">
        <div><h3>${escapeHtml(source.title)}</h3><p>${escapeHtml(source.role)}</p></div>
        <div class="card-footer"><span class="chip">reviewed ${escapeHtml(source.lastReviewed)}</span><span aria-hidden="true">↗</span></div>
      </a>
    `).join("")}</section>
  `;
}

function metadata(test) {
  const values = [
    test.category,
    test.automationLevel,
    test.offlineCapable ? "offline-capable" : "network-dependent",
    test.requiresHardware ? "hardware" : "no special hardware",
    test.requiresSecureContext ? "secure context" : "ordinary origin"
  ];
  return values.map((value) => `<span class="chip">${escapeHtml(value)}</span>`).join("");
}

function resultControls(test) {
  return `
    <div class="button-row" data-result-controls>
      <button type="button" data-status="failed" class="danger">Record failure</button>
      <button type="button" data-status="skipped" class="secondary">Skip</button>
      <button type="button" data-status="pending" class="secondary">Reset result</button>
    </div>
    <label>Test notes
      <textarea id="test-notes" placeholder="Optional local operator notes">${escapeHtml(resultFor(test.id).notes.join("\n"))}</textarea>
    </label>
  `;
}

function environmentRows() {
  const values = {
    "Secure context": environment.origin.secureContext,
    Origin: environment.origin.origin,
    Platform: environment.platform.reportedPlatform,
    "Max touch points": environment.platform.maxTouchPoints,
    "Pointer Events": environment.input.pointerEvents,
    "Touch Events": environment.input.touchEvents,
    "Coarse pointer": environment.input.coarsePointer,
    Hover: environment.input.hover,
    Viewport: `${environment.viewport.width} × ${environment.viewport.height}`,
    DPR: environment.viewport.devicePixelRatio,
    Orientation: environment.viewport.orientation || "not exposed",
    VisualViewport: environment.viewport.visualViewport
  };
  return Object.entries(values).map(([name, value]) => `
    <div class="metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(name)}</span></div>
  `).join("");
}

function renderTest(id) {
  const test = testById(catalog, id);
  if (!test) {
    view.innerHTML = '<section class="panel error-card"><h1>Unknown test</h1><p>This stable test ID is not present in the bundled catalog.</p><a class="button" href="#/tests">Select a test</a></section>';
    return;
  }
  const result = resultFor(test.id);
  view.innerHTML = `
    <div class="section-head"><div><p class="eyebrow">${escapeHtml(test.id)}</p><h1>${escapeHtml(test.name)}</h1></div><span id="current-result" class="chip ${statusClass(result.status)}">${escapeHtml(statusLabel(result.status))}</span></div>
    <div class="detail-grid">
      <section class="panel">
        <div class="metadata">${metadata(test)}</div>
        <p class="lede">${escapeHtml(test.description)}</p>
        <p class="instructions"><strong>Procedure:</strong> ${escapeHtml(test.instructions)}</p>
        <p><strong>Catalog expectation:</strong> ${escapeHtml(test.expected)}</p>
        <div id="test-runtime"></div>
      </section>
      <aside class="panel">
        <p class="eyebrow">Evidence controls</p>
        <p>Nothing is uploaded. Failure and absence remain valid results.</p>
        ${resultControls(test)}
      </aside>
    </div>
  `;
  wireResultControls(test);
  if (test.id === "environment.baseline") renderEnvironmentTest(test);
  else if (test.id === "pointer.lifecycle") renderPointerTest(test);
  else if (test.id === "touch.lifecycle") renderTouchTest(test);
}

function updateResultBadge(status) {
  const badge = document.querySelector("#current-result");
  if (!badge) return;
  badge.className = `chip ${statusClass(status)}`;
  badge.textContent = statusLabel(status);
}

function wireResultControls(test) {
  document.querySelectorAll("[data-status]").forEach((button) => {
    button.addEventListener("click", () => {
      const status = button.dataset.status;
      updateResult(report, test.id, {
        status,
        observed: status === "pending" ? null : status,
        details: status === "pending" ? {} : resultFor(test.id).details
      });
      updateResultBadge(status);
    });
  });
  document.querySelector("#test-notes").addEventListener("change", (event) => {
    const notes = event.target.value.split("\n").map((note) => note.trim()).filter(Boolean);
    updateResult(report, test.id, { notes });
  });
}

function renderEnvironmentTest(test) {
  const runtime = document.querySelector("#test-runtime");
  runtime.innerHTML = `
    <div class="grid">${environmentRows()}</div>
    <div class="button-row"><button type="button" id="capture-environment">Save observed environment</button></div>
  `;
  document.querySelector("#capture-environment").addEventListener("click", () => {
    updateResult(report, test.id, {
      status: "passed",
      apiAvailable: true,
      observed: "browser-exposed environment captured",
      details: environment
    });
    updateResultBadge("passed");
  });
}

function interactiveMarkup(apiName, available) {
  return `
    <div class="live-stats">
      <span class="chip ${available ? "pass" : "fail"}">${escapeHtml(apiName)} ${available ? "exposed" : "not exposed"}</span>
      <span class="chip">active <strong id="active-count">0</strong></span>
      <span class="chip">high-water <strong id="high-water">0</strong></span>
    </div>
    <div id="contact-stage" class="contact-stage" aria-label="Interactive contact field">
      <p class="stage-copy">Use a finger, stylus, mouse, or trackpad here. Contact markers are transient and remain on this page.</p>
    </div>
    <p class="eyebrow">Recent event evidence</p>
    <pre id="event-log" class="event-log">No input observed yet.</pre>
  `;
}

function evidenceHandler(test, kind) {
  return (evidence) => {
    document.querySelector("#active-count").textContent = evidence.active;
    document.querySelector("#high-water").textContent = evidence.highWater;
    document.querySelector("#event-log").textContent = evidence.events
      .slice(-12)
      .map((entry) => JSON.stringify(entry))
      .join("\n");
    if (evidence.complete) {
      updateResult(report, test.id, {
        status: "passed",
        apiAvailable: true,
        observed: `${kind} lifecycle completed`,
        details: { highWater: evidence.highWater, events: evidence.events }
      });
      updateResultBadge("passed");
    }
  };
}

function renderPointerTest(test) {
  const available = "PointerEvent" in window;
  const runtime = document.querySelector("#test-runtime");
  runtime.innerHTML = interactiveMarkup("Pointer Events", available);
  if (!available) {
    updateResult(report, test.id, {
      status: "unexpected-unavailable",
      apiAvailable: false,
      observed: "PointerEvent is not exposed"
    });
    updateResultBadge("unexpected-unavailable");
    document.querySelector("#contact-stage").inert = true;
    return;
  }
  disposeRoute = setupPointerTest(
    document.querySelector("#contact-stage"),
    evidenceHandler(test, "pointer")
  );
}

function renderTouchTest(test) {
  const available = "TouchEvent" in window || "ontouchstart" in window;
  const runtime = document.querySelector("#test-runtime");
  runtime.innerHTML = interactiveMarkup("Touch Events", available);
  if (!available) {
    runtime.insertAdjacentHTML(
      "beforeend",
      '<div class="button-row"><button type="button" id="record-touch-absence">Record expected platform-dependent absence</button></div>'
    );
    document.querySelector("#contact-stage").inert = true;
    document.querySelector("#record-touch-absence").addEventListener("click", () => {
      updateResult(report, test.id, {
        status: "expected-unavailable",
        apiAvailable: false,
        observed: "Touch Events not exposed on this browser/device"
      });
      updateResultBadge("expected-unavailable");
    });
    return;
  }
  disposeRoute = setupTouchTest(
    document.querySelector("#contact-stage"),
    evidenceHandler(test, "touch")
  );
}

function renderReport() {
  const runProgress = progress(report);
  const rows = report.results.map((result) => {
    const test = testById(catalog, result.id);
    return `<tr><td><a href="${testHref(result.id)}">${escapeHtml(test.name)}</a><br><small>${escapeHtml(result.id)}</small></td><td><span class="chip ${statusClass(result.status)}">${escapeHtml(statusLabel(result.status))}</span></td><td>${escapeHtml(result.expected)}</td><td>${escapeHtml(result.observed || "—")}</td></tr>`;
  }).join("");
  view.innerHTML = `
    <div class="section-head"><div><p class="eyebrow">Local report · ${runProgress.complete}/${runProgress.total} recorded</p><h1>Device evidence</h1><p class="lede">Export is explicit. Print uses the browser's Print → PDF path.</p></div><span class="chip">run ${escapeHtml(report.runId)}</span></div>
    <section class="panel">
      <div class="button-row">
        <button type="button" id="export-report">Export JSON</button>
        <button type="button" id="import-report" class="secondary">Import JSON</button>
        <button type="button" id="print-report" class="secondary">Print / PDF</button>
        <button type="button" id="reset-report" class="danger">Start new local run</button>
        <input id="report-file" type="file" accept="application/json,.json" hidden>
      </div>
      <p><strong>Origin:</strong> ${escapeHtml(report.origin)} · <strong>secure:</strong> ${escapeHtml(report.secureContext)} · <strong>updated:</strong> ${escapeHtml(report.updatedAt)}</p>
      <div style="overflow-x:auto"><table class="report-table"><thead><tr><th>Test</th><th>Status</th><th>Expected</th><th>Observed</th></tr></thead><tbody>${rows}</tbody></table></div>
    </section>
    <section class="panel" style="margin-top:1rem">
      <label>Operator notes<textarea id="operator-notes" placeholder="Optional notes kept only in this local report">${escapeHtml(report.operatorNotes)}</textarea></label>
    </section>
  `;
  document.querySelector("#export-report").addEventListener("click", () => exportReport(report));
  document.querySelector("#print-report").addEventListener("click", () => window.print());
  document.querySelector("#import-report").addEventListener("click", () => document.querySelector("#report-file").click());
  document.querySelector("#report-file").addEventListener("change", async (event) => {
    const [file] = event.target.files;
    if (!file) return;
    try {
      report = await importReport(file, catalog);
      renderReport();
    } catch (error) {
      window.alert(`Report import failed: ${error.message}`);
    }
  });
  document.querySelector("#operator-notes").addEventListener("change", (event) => {
    report.operatorNotes = event.target.value;
    saveReport(report);
  });
  document.querySelector("#reset-report").addEventListener("click", () => {
    if (!window.confirm("Start a new local run? Export the current report first if it must be retained.")) return;
    report = resetReport(catalog, detectEnvironment());
    renderReport();
  });
}

function render(route) {
  disposeRoute();
  disposeRoute = () => {};
  environment = detectEnvironment();
  setNavigation(route);
  if (route.name === "tests") renderTests();
  else if (route.name === "test") renderTest(route.id);
  else if (route.name === "report") renderReport();
  else renderRun();
  view.focus({ preventScroll: true });
}

async function boot() {
  updateRuntimeStatus();
  window.addEventListener("online", updateRuntimeStatus);
  window.addEventListener("offline", updateRuntimeStatus);
  try {
    catalog = await loadCatalog();
    environment = detectEnvironment();
    report = loadReport(catalog, environment);
    startRouter(render);
    registerWorker();
  } catch (error) {
    view.innerHTML = `<section class="panel error-card"><p class="eyebrow">Startup failure</p><h1>The local suite could not start.</h1><p>${escapeHtml(error.message)}</p><p>Confirm that the generated artifact includes the bundled catalog and every JavaScript module.</p></section>`;
    workerStatus.textContent = "Application startup failed";
    workerStatus.className = "status-pill fail";
  }
}

boot();
