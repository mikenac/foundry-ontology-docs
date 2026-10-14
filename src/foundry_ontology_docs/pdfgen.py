"""Render the generated Markdown documentation into a single combined PDF.

Usage:
    uv run foundry-ontology-pdfgen [--docs-dir docs] [--out docs/ontology-documentation.pdf]

Uses WeasyPrint (markdown -> HTML -> PDF), which has far better CSS table
support than xhtml2pdf (correct row-height handling for wrapped cells,
proper column sizing, real @page/footer support). WeasyPrint depends on
native Cairo/Pango/GLib libraries (via Homebrew on macOS: `brew install
cairo pango gdk-pixbuf libffi`) rather than being pure Python.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
from pathlib import Path

# On macOS, Python's cffi dlopen() for libgobject/libpango/libcairo often
# can't find Homebrew's .dylibs unless DYLD_FALLBACK_LIBRARY_PATH points at
# the Homebrew lib dir. Set this *before* importing weasyprint.
if platform.system() == "Darwin":
    for prefix in ("/opt/homebrew/lib", "/usr/local/lib"):
        if Path(prefix).is_dir():
            existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
            if prefix not in existing.split(":"):
                os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
                    f"{prefix}:{existing}" if existing else prefix
                )

import markdown as md  # noqa: E402
from weasyprint import HTML  # noqa: E402

PAGE_CSS = """
@page {
    size: letter;
    margin: 1.6cm 1.4cm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 7.5pt;
        color: #888;
    }
}
html { font-size: 9pt; }
body {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    line-height: 1.4;
    color: #1a1a1a;
}
h1 {
    font-size: 17pt;
    color: #111;
    border-bottom: 1.5pt solid #2b4a7a;
    padding-bottom: 4pt;
    margin-top: 0;
    break-before: page;
}
h1:first-of-type { break-before: avoid; }
h2 {
    font-size: 12.5pt;
    color: #2b4a7a;
    margin-top: 16pt;
    break-after: avoid;
}
h3 { font-size: 10.5pt; color: #2b4a7a; break-after: avoid; }
p { margin: 4pt 0; }
code {
    font-family: "Menlo", "Courier New", monospace;
    background: #f0f0f0;
    padding: 1px 3px;
    border-radius: 2px;
    font-size: 0.92em;
    word-wrap: break-word;
}
hr { border: none; border-top: 0.5pt solid #ccc; margin: 10pt 0; }
a { color: #1a56c4; text-decoration: none; }

table {
    width: 100%;
    border-collapse: collapse;
    margin: 6pt 0 12pt 0;
    table-layout: fixed;
    font-size: 7.6pt;
}
th, td {
    border: 0.5pt solid #bbb;
    padding: 3pt 5pt;
    text-align: left;
    vertical-align: top;
    overflow-wrap: anywhere;
    word-break: normal;
    hyphens: auto;
}
code {
    overflow-wrap: anywhere;
    word-break: normal;
}
th {
    background: #e8eef7;
    font-weight: bold;
    color: #1a1a1a;
}
tr:nth-child(even) td { background: #fafbfd; }

/* First two columns are almost always identifier/name columns that need
   more room than the status/cardinality/count columns that follow. */
table th:first-child, table td:first-child { width: 22%; }
table th:nth-child(2), table td:nth-child(2) { width: 20%; }
"""

# Order matters: this is the reading order of the combined PDF.
SECTION_FILES = [
    "index.md",
    "all-properties.md",
    "all-links.md",
    "interfaces.md",
    "shared-property-types.md",
    "action-types.md",
]


def _strip_relative_links(html: str) -> str:
    """Combined single-document PDF can't resolve relative .md links across
    sections; de-link them to plain text/code so the PDF has no dead links."""
    import re

    return re.sub(r"\[(`[^`]+`|[^\]]+)\]\([^)]+\.md\)", r"\1", html)


def _sanitize_glyphs(text: str) -> str:
    """Normalize a symbol some fonts render poorly."""
    return text.replace("←", "<-")


def _md_to_html_body(markdown_text: str) -> str:
    markdown_text = _sanitize_glyphs(markdown_text)
    html = md.markdown(markdown_text, extensions=["tables", "fenced_code"])
    return _strip_relative_links(html)


def collect_markdown(docs_dir: Path) -> str:
    parts: list[str] = []

    for name in SECTION_FILES:
        f = docs_dir / name
        if f.exists():
            parts.append(f.read_text())

    ot_dir = docs_dir / "object-types"
    if ot_dir.exists():
        parts.append("# Object Types (detail)\n")
        for f in sorted(ot_dir.glob("*.md")):
            parts.append(f.read_text())

    return "\n\n".join(parts)


def generate_pdf(docs_dir: Path, out_path: Path) -> Path:
    combined_md = collect_markdown(docs_dir)
    body_html = _md_to_html_body(combined_md)
    html_doc = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{PAGE_CSS}</style></head>
<body>
{body_html}
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_doc, base_url=str(docs_dir)).write_pdf(str(out_path))
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    return out_path


def _check_native_deps() -> None:
    """Fail with a clear, actionable message instead of a cffi stack trace
    if Homebrew's Cairo/Pango/GLib libs aren't installed."""
    if platform.system() != "Darwin":
        return
    if shutil.which("brew") and not Path("/opt/homebrew/lib/libgobject-2.0.dylib").exists():
        raise SystemExit(
            "WeasyPrint needs native Cairo/Pango/GLib libraries.\n"
            "Install them with: brew install cairo pango gdk-pixbuf libffi\n"
            "See https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#macos"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--out", default="docs/ontology-documentation.pdf")
    args = parser.parse_args()
    _check_native_deps()
    generate_pdf(Path(args.docs_dir), Path(args.out))


if __name__ == "__main__":
    main()
