const STORAGE_KEY = "chrome.web.touch.report.v1";
const VALID_STATES = new Set([
  "pending",
  "passed",
  "failed",
  "expected-unavailable",
  "unexpected-unavailable",
  "skipped",
  "not-exercised"
]);

function runId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const random = crypto.getRandomValues(new Uint32Array(4));
  return Array.from(random, (part) => part.toString(16).padStart(8, "0")).join("-");
}

function resultFor(test) {
  return {
    id: test.id,
    category: test.category,
    status: "pending",
    apiAvailable: null,
    expected: test.expected,
    observed: null,
    details: {},
    errors: [],
    notes: []
  };
}

export function createReport(catalog, environment) {
  const now = new Date().toISOString();
  return {
    schemaVersion: 1,
    suiteVersion: catalog.suiteVersion,
    catalogVersion: catalog.catalogVersion,
    runId: runId(),
    createdAt: now,
    updatedAt: now,
    origin: environment.origin.origin,
    secureContext: environment.origin.secureContext,
    browser: environment.browser,
    platform: { ...environment.platform, input: environment.input },
    viewport: environment.viewport,
    results: catalog.tests.map(resultFor),
    observations: [],
    operatorNotes: ""
  };
}

export function loadReport(catalog, environment) {
  try {
    const candidate = JSON.parse(localStorage.getItem(STORAGE_KEY));
    validateReport(candidate, catalog);
    candidate.secureContext = environment.origin.secureContext;
    candidate.origin = environment.origin.origin;
    candidate.browser = environment.browser;
    candidate.platform = { ...environment.platform, input: environment.input };
    candidate.viewport = environment.viewport;
    for (const test of catalog.tests) {
      if (!candidate.results.some((result) => result.id === test.id)) {
        candidate.results.push(resultFor(test));
      }
    }
    return candidate;
  } catch {
    return createReport(catalog, environment);
  }
}

export function validateReport(report, catalog) {
  if (!report || report.schemaVersion !== 1 || !report.runId || !Array.isArray(report.results)) {
    throw new Error("Unsupported report envelope");
  }
  if (report.suiteVersion !== catalog.suiteVersion || report.catalogVersion !== catalog.catalogVersion) {
    throw new Error("Report suite/catalog version does not match this application");
  }
  const known = new Set(catalog.tests.map((test) => test.id));
  for (const result of report.results) {
    if (!known.has(result.id) || !VALID_STATES.has(result.status)) {
      throw new Error(`Invalid report result: ${result.id}`);
    }
  }
  return report;
}

export function saveReport(report) {
  report.updatedAt = new Date().toISOString();
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(report));
    report.storageAvailable = true;
  } catch {
    report.storageAvailable = false;
  }
  return report;
}

export function updateResult(report, id, patch) {
  const result = report.results.find((item) => item.id === id);
  if (!result) throw new Error(`Unknown result: ${id}`);
  if (patch.status && !VALID_STATES.has(patch.status)) throw new Error(`Invalid status: ${patch.status}`);
  Object.assign(result, patch);
  saveReport(report);
  return result;
}

export function resetReport(catalog, environment) {
  const report = createReport(catalog, environment);
  saveReport(report);
  return report;
}

export function exportReport(report) {
  const blob = new Blob([`${JSON.stringify(report, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `chrome-touch-report-${report.runId}.json`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export async function importReport(file, catalog) {
  const report = JSON.parse(await file.text());
  validateReport(report, catalog);
  saveReport(report);
  return report;
}

export function progress(report) {
  const complete = report.results.filter((result) => !["pending", "not-exercised"].includes(result.status)).length;
  return { complete, total: report.results.length };
}
