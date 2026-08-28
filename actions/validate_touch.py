#!/usr/bin/env python3
"""Validate the static touch catalog, report, manifest, modules, and offline cache contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
TOUCH = ROOT / "web" / "touch"
AUTOMATION = {"AUTO", "SEMI-AUTO", "HUMAN", "EXTERNAL-HARDWARE", "SERVER-DEPENDENT"}
STATES = {
    "pending",
    "passed",
    "failed",
    "expected-unavailable",
    "unexpected-unavailable",
    "skipped",
    "not-exercised",
}
BOOLEAN_FIELDS = {
    "requiresSecureContext",
    "requiresPermission",
    "requiresUserGesture",
    "requiresHardware",
    "requiresInternet",
    "requiresSpecialServer",
    "requiresMultipleOrigins",
    "offlineCapable",
}
REQUIRED_TESTS = {"environment.baseline", "pointer.lifecycle", "touch.lifecycle"}
CRITICAL_CACHE = {
    "./",
    "./index.html",
    "./manifest.webmanifest",
    "./icons/app.svg",
    "./css/app.css",
    "./js/app.js",
    "./js/catalog.js",
    "./js/detect.js",
    "./js/report.js",
    "./js/router.js",
    "./js/tests/pointer.js",
    "./js/tests/touch.js",
    "./data/catalog.json",
    "./schema/catalog.schema.json",
    "./schema/report.schema.json",
}


def document(relative: str) -> dict:
    return json.loads((TOUCH / relative).read_text(encoding="utf-8"))


def validate_catalog(catalog: dict) -> list[str]:
    failures: list[str] = []
    if catalog.get("schemaVersion") != 1:
        failures.append("catalog schemaVersion must be 1")
    if not catalog.get("catalogVersion") or not catalog.get("suiteVersion"):
        failures.append("catalog and suite versions are required")
    states = catalog.get("resultStates")
    if not isinstance(states, list) or set(states) != STATES or len(states) != len(STATES):
        failures.append("catalog resultStates differ from the standard state set")
    tests = catalog.get("tests")
    if not isinstance(tests, list) or not tests:
        return failures + ["catalog tests must be a non-empty array"]

    ids: list[str] = []
    for index, test in enumerate(tests):
        id_ = test.get("id")
        if not isinstance(id_, str) or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", id_):
            failures.append(f"test {index} has an invalid stable ID")
            continue
        ids.append(id_)
        for field in ("name", "category", "description", "instructions", "expected", "destructivePotential", "privacySensitivity"):
            if not isinstance(test.get(field), str) or not test[field].strip():
                failures.append(f"{id_} has an invalid {field}")
        for field in BOOLEAN_FIELDS:
            if not isinstance(test.get(field), bool):
                failures.append(f"{id_} has a non-boolean {field}")
        if test.get("automationLevel") not in AUTOMATION:
            failures.append(f"{id_} has an invalid automationLevel")
    if len(ids) != len(set(ids)):
        failures.append("catalog has duplicate stable test IDs")
    missing = REQUIRED_TESTS - set(ids)
    if missing:
        failures.append(f"catalog lacks baseline tests: {', '.join(sorted(missing))}")

    profiles = catalog.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        failures.append("catalog must provide at least one expectation profile")
    sources = catalog.get("sources")
    if not isinstance(sources, list) or not sources:
        failures.append("catalog must provide reviewed primary sources")
    else:
        source_hosts = {urlsplit(source.get("url", "")).hostname for source in sources}
        required_hosts = {"developer.chrome.com", "developer.mozilla.org", "issues.chromium.org"}
        if not required_hosts.issubset(source_hosts):
            failures.append("catalog sources omit a required Chrome/MDN/Chromium authority")
    return failures


def validate_report_schema(schema: dict, catalog: dict) -> list[str]:
    failures: list[str] = []
    try:
        states = set(
            schema["properties"]["results"]["items"]["properties"]["status"]["enum"]
        )
    except (KeyError, TypeError):
        return ["report schema has no result status enum"]
    if states != set(catalog["resultStates"]):
        failures.append("report schema result statuses differ from catalog states")
    required = set(schema.get("required", []))
    expected = {
        "schemaVersion", "suiteVersion", "catalogVersion", "runId", "createdAt",
        "updatedAt", "origin", "secureContext", "results",
    }
    if not expected.issubset(required):
        failures.append("report schema omits required envelope fields")
    return failures


def local_reference(relative: str) -> bool:
    parsed = urlsplit(relative)
    return not parsed.scheme and not parsed.netloc and relative.startswith("./") and ".." not in relative


def validate_manifest(manifest: dict) -> list[str]:
    failures: list[str] = []
    for field in ("start_url", "scope"):
        value = manifest.get(field)
        if not isinstance(value, str) or not local_reference(value):
            failures.append(f"manifest {field} must be a local ./ reference")
    icons = manifest.get("icons")
    if not isinstance(icons, list) or not icons:
        failures.append("manifest has no local icon")
    else:
        for icon in icons:
            source = icon.get("src", "")
            if not local_reference(source) or not (TOUCH / source[2:]).is_file():
                failures.append(f"manifest icon is missing or non-local: {source}")
    return failures


def validate_cache() -> list[str]:
    source = (TOUCH / "service-worker.js").read_text(encoding="utf-8")
    cached = set(re.findall(r'^\s*"(\./[^"\r\n]*)",?\s*$', source, re.MULTILINE))
    missing = CRITICAL_CACHE - cached
    extra_missing = {
        relative for relative in cached
        if relative != "./" and not (TOUCH / relative[2:].split("#", 1)[0]).is_file()
    }
    failures: list[str] = []
    if missing:
        failures.append(f"service worker omits critical files: {', '.join(sorted(missing))}")
    if extra_missing:
        failures.append(f"service worker caches missing files: {', '.join(sorted(extra_missing))}")
    if "http://" in source or "https://" in source:
        failures.append("service worker contains an external runtime URL")
    return failures


def validate_modules() -> list[str]:
    failures: list[str] = []
    for module in sorted((TOUCH / "js").rglob("*.js")):
        source = module.read_text(encoding="utf-8")
        if re.search(r"\b(?:from|import)\s*\(?\s*['\"]https?://", source):
            failures.append(f"module imports an external runtime dependency: {module.relative_to(ROOT)}")
        for reference in re.findall(r"\bfrom\s+['\"]([^'\"]+)['\"]", source):
            if not reference.startswith("."):
                failures.append(f"module has a non-relative import: {module.relative_to(ROOT)} -> {reference}")
    return failures


def validate() -> list[str]:
    failures: list[str] = []
    required_files = {relative[2:] for relative in CRITICAL_CACHE if relative != "./"}
    for relative in sorted(required_files):
        if not (TOUCH / relative).is_file():
            failures.append(f"required touch file is missing: {relative}")
    if failures:
        return failures
    catalog = document("data/catalog.json")
    failures.extend(validate_catalog(catalog))
    failures.extend(validate_report_schema(document("schema/report.schema.json"), catalog))
    failures.extend(validate_manifest(document("manifest.webmanifest")))
    failures.extend(validate_cache())
    failures.extend(validate_modules())
    return failures


def main() -> int:
    failures = validate()
    if failures:
        for failure in failures:
            print(f"[validate.touch][FAIL] {failure}")
        return 1
    catalog = document("data/catalog.json")
    print(
        f"[validate.touch][PASS] {len(catalog['tests'])} stable tests, "
        f"catalog {catalog['catalogVersion']}, complete offline cache"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
