#!/usr/bin/env python3
"""Render the repository's small, controlled Markdown subset without runtime deps."""

from __future__ import annotations

import argparse
import html
import os
import posixpath
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit


LINK_RE = re.compile(r"\[([^]]+)]\(([^)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
STRONG_RE = re.compile(r"\*\*([^*]+)\*\*")
EM_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9 -]", "", value.lower())
    return re.sub(r"[ -]+", "-", value).strip("-") or "section"


def public_href(raw: str) -> str:
    parsed = urlsplit(raw)
    if parsed.scheme or raw.startswith(("#", "/")):
        return raw
    path = parsed.path
    if path.endswith("readme.md"):
        path = path[: -len("readme.md")]
    elif path.endswith(".md"):
        path = f"{path[:-3]}.html"
    suffix = f"?{parsed.query}" if parsed.query else ""
    suffix += f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{suffix}"


def inline(value: str) -> str:
    value = html.escape(value, quote=True)
    value = CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", value)

    def link(match: re.Match[str]) -> str:
        label = match.group(1)
        href = html.escape(public_href(html.unescape(match.group(2))), quote=True)
        return f'<a href="{href}">{label}</a>'

    value = LINK_RE.sub(link, value)
    value = STRONG_RE.sub(r"<strong>\1</strong>", value)
    return EM_RE.sub(r"<em>\1</em>", value)


def is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_markdown(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    output: list[str] = []
    title = "Chrome documentation"
    paragraph: list[str] = []
    list_kind: str | None = None
    in_code = False
    code_lines: list[str] = []
    code_language = ""
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{inline(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            output.append(f"</{list_kind}>")
            list_kind = None

    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                class_name = f' class="language-{html.escape(code_language)}"' if code_language else ""
                output.append(f"<pre><code{class_name}>{html.escape(chr(10).join(code_lines))}</code></pre>")
                in_code = False
                code_lines.clear()
                code_language = ""
            else:
                in_code = True
                code_language = line[3:].strip()
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if not line.strip():
            flush_paragraph()
            close_list()
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            content = heading.group(2).strip()
            if level == 1 and title == "Chrome documentation":
                title = re.sub(r"[`*_]", "", content)
            output.append(f'<h{level} id="{slug(content)}">{inline(content)}</h{level}>')
            index += 1
            continue
        if index + 1 < len(lines) and "|" in line and is_table_separator(lines[index + 1]):
            flush_paragraph()
            close_list()
            headers = table_cells(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(table_cells(lines[index]))
                index += 1
            output.append("<div class=\"table-wrap\"><table><thead><tr>")
            output.extend(f"<th>{inline(cell)}</th>" for cell in headers)
            output.append("</tr></thead><tbody>")
            for row in rows:
                output.append("<tr>")
                output.extend(f"<td>{inline(cell)}</td>" for cell in row)
                output.append("</tr>")
            output.append("</tbody></table></div>")
            continue
        unordered = re.match(r"^\s*[-*]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            requested = "ul" if unordered else "ol"
            if list_kind != requested:
                close_list()
                output.append(f"<{requested}>")
                list_kind = requested
            match = unordered or ordered
            output.append(f"<li>{inline(match.group(1))}</li>")
            index += 1
            continue
        if line.startswith("> "):
            flush_paragraph()
            close_list()
            output.append(f"<blockquote>{inline(line[2:])}</blockquote>")
            index += 1
            continue
        if re.fullmatch(r"-{3,}", line.strip()):
            flush_paragraph()
            close_list()
            output.append("<hr>")
            index += 1
            continue
        paragraph.append(line)
        index += 1

    if in_code:
        output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    close_list()
    return title, "\n".join(output)


def document(title: str, body: str, output_file: Path, site_root: Path) -> str:
    relative = output_file.relative_to(site_root)
    css_href = posixpath.relpath("assets/site.css", relative.parent.as_posix() or ".")
    root_href = posixpath.relpath("index.html", relative.parent.as_posix() or ".")
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="dark light">
    <title>{html.escape(title)} · Chrome Web Labs</title>
    <link rel="stylesheet" href="{html.escape(css_href, quote=True)}">
  </head>
  <body class="docs">
    <header class="docs-header">
      <a href="{html.escape(root_href, quote=True)}">Chrome Web Labs</a>
    </header>
    <main><article>{body}</article></main>
    <footer><p>Rendered from repository-owned Markdown.</p></footer>
  </body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--site-output-root", required=True, type=Path)
    parser.add_argument("--readmes-only", action="store_true")
    parser.add_argument("--preserve-index", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    site_root = args.site_output_root.resolve()
    pattern = "**/readme.md" if args.readmes_only else "**/*.md"

    for markdown in sorted(source.glob(pattern)):
        relative = markdown.relative_to(source)
        destination_dir = output / relative.parent
        destination_dir.mkdir(parents=True, exist_ok=True)
        raw_destination = destination_dir / markdown.name
        if markdown.resolve() != raw_destination.resolve():
            shutil.copy2(markdown, raw_destination)
        html_name = "index.html" if markdown.name == "readme.md" else f"{markdown.stem}.html"
        html_destination = destination_dir / html_name
        if args.preserve_index and html_destination.exists():
            continue
        title, body = render_markdown(markdown.read_text(encoding="utf-8"))
        html_destination.write_text(document(title, body, html_destination, site_root), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
