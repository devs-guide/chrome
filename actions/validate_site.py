#!/usr/bin/env python3
"""Validate the generated Pages tree and its stable internal links."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


REQUIRED = (
    ".nojekyll",
    "index.html",
    "web/index.html",
    "web/touch/index.html",
    "web/touch/data/catalog.json",
    "web/touch/schema/report.schema.json",
    "web/app/index.html",
    "web/extension/index.html",
    "web/pwa/index.html",
    "web/rtc/index.html",
    "web/wasm/index.html",
    "build/index.html",
    "build/source/index.html",
    "docs/index.html",
    "meta/publication.json",
    "meta/checksums.sha256",
)
PRIVATE_MARKERS = tuple(
    b"-----BEGIN " + kind + b"PRIVATE KEY-----"
    for kind in (b"", b"RSA ", b"EC ")
)


class References(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for attribute in ("href", "src"):
            value = values.get(attribute)
            if value:
                self.refs.append((tag, attribute, value))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def resolve_reference(root: Path, html_file: Path, reference: str) -> Path | None:
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or reference.startswith(("#", "mailto:", "data:", "javascript:")):
        return None
    path = unquote(parsed.path)
    if not path:
        return None
    if path.startswith("/chrome/"):
        candidate = root / path[len("/chrome/"):]
    elif path == "/chrome":
        candidate = root / "index.html"
    elif path.startswith("/"):
        return root / "__invalid_absolute_path__"
    else:
        candidate = html_file.parent / path
    if path.endswith("/") or candidate.is_dir():
        candidate /= "index.html"
    return candidate.resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    failures: list[str] = []

    for relative in REQUIRED:
        path = root / relative
        if relative == ".nojekyll":
            if not path.is_file():
                failures.append(f"missing required file: {relative}")
        elif not path.is_file() or path.stat().st_size == 0:
            failures.append(f"missing or empty required file: {relative}")

    for path in root.rglob("*"):
        if path.is_symlink():
            failures.append(f"artifact symlink: {path.relative_to(root)}")
        if path.is_file() and (path.name.endswith((".key", ".key.pem")) or path.name in {"root-ca.key.pem", "server.key.pem"}):
            failures.append(f"private-key-like path: {path.relative_to(root)}")
        if path.is_file():
            data = path.read_bytes()
            if any(marker in data for marker in PRIVATE_MARKERS):
                failures.append(f"private-key material: {path.relative_to(root)}")

    publication_path = root / "meta/publication.json"
    if publication_path.is_file():
        try:
            publication = json.loads(publication_path.read_text(encoding="utf-8"))
            for key in ("schemaVersion", "repository", "sourceRef", "sourceSha", "buildTime", "release", "catalogVersion", "artifactVersion"):
                if key not in publication:
                    failures.append(f"publication metadata missing key: {key}")
        except (OSError, json.JSONDecodeError) as error:
            failures.append(f"invalid publication metadata: {error}")

    checksum_path = root / "meta/checksums.sha256"
    expected_paths: set[str] = set()
    if checksum_path.is_file():
        for line_number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), 1):
            match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
            if not match:
                failures.append(f"invalid checksum line {line_number}")
                continue
            expected, relative = match.groups()
            target = (root / relative).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                failures.append(f"checksum path escapes root: {relative}")
                continue
            expected_paths.add(relative)
            if not target.is_file():
                failures.append(f"checksum target missing: {relative}")
            elif digest(target) != expected:
                failures.append(f"checksum mismatch: {relative}")
        actual_paths = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path != checksum_path
        }
        for relative in sorted(actual_paths - expected_paths):
            failures.append(f"file absent from checksums: {relative}")
        for relative in sorted(expected_paths - actual_paths):
            failures.append(f"checksum has absent file: {relative}")

    for html_file in root.rglob("*.html"):
        parser_ = References()
        parser_.feed(html_file.read_text(encoding="utf-8"))
        for tag, attribute, reference in parser_.refs:
            parsed = urlsplit(reference)
            if parsed.scheme in {"http", "https"}:
                if tag in {"script", "img", "audio", "video", "source"} or (tag == "link" and attribute == "href"):
                    failures.append(f"external runtime resource in {html_file.relative_to(root)}: {reference}")
                continue
            target = resolve_reference(root, html_file, reference)
            if target is None:
                continue
            try:
                target.relative_to(root)
            except ValueError:
                failures.append(f"link escapes artifact in {html_file.relative_to(root)}: {reference}")
                continue
            if not target.is_file():
                failures.append(f"broken link in {html_file.relative_to(root)}: {reference}")

    if failures:
        for failure in failures:
            print(f"[validate.pages][FAIL] {failure}")
        print(f"[validate.pages][FAIL] {len(failures)} issue(s)")
        return 1
    print(f"[validate.pages][PASS] validated {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
