const CATALOG_URL = new URL("../data/catalog.json", import.meta.url);
const STATES = new Set([
  "pending",
  "passed",
  "failed",
  "expected-unavailable",
  "unexpected-unavailable",
  "skipped",
  "not-exercised"
]);

export async function loadCatalog() {
  const response = await fetch(CATALOG_URL, { cache: "no-cache" });
  if (!response.ok) throw new Error(`Catalog request failed with HTTP ${response.status}`);
  const catalog = await response.json();
  validateCatalog(catalog);
  return catalog;
}

export function validateCatalog(catalog) {
  if (!catalog || catalog.schemaVersion !== 1 || !catalog.catalogVersion || !catalog.suiteVersion) {
    throw new Error("Unsupported touch catalog envelope");
  }
  if (!Array.isArray(catalog.tests) || catalog.tests.length === 0) {
    throw new Error("Touch catalog has no tests");
  }
  if (!Array.isArray(catalog.resultStates) || catalog.resultStates.some((state) => !STATES.has(state))) {
    throw new Error("Touch catalog contains unsupported result states");
  }
  const ids = new Set();
  for (const test of catalog.tests) {
    if (!/^[a-z0-9]+(?:[.-][a-z0-9]+)*$/.test(test.id || "") || ids.has(test.id)) {
      throw new Error(`Invalid or duplicate stable test ID: ${test.id}`);
    }
    ids.add(test.id);
  }
  return catalog;
}

export function testById(catalog, id) {
  return catalog.tests.find((test) => test.id === id);
}
