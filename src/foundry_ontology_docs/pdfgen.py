"""Render the generated Markdown documentation into a single combined PDF.

Usage:
    uv run foundry-ontology-pdfgen [--docs-dir docs] [--out docs/ontology-documentation.pdf]

Pure-Python (markdown + xhtml2pdf), no system/native dependencies (no
wkhtmltopdf/Chromium needed) — safe to run anywhere `uv sync` works.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import markdown as md
from xhtml2pdf import pisa

PAGE_CSS = """
@page {
    size: letter;
    margin: 1.5cm;
    @frame footer_frame {
        -pdf-frame-content: footer_content;
        bottom: 1cm; margin-left: 1.5cm; margin-right: 1.5cm; height: 1cm;
    }
}
body { font-family: Helvetica, Arial, sans-serif; font-size: 9pt; line-height: 1.35; }
h1 { font-size: 18pt; color: #1a1a1a; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 13pt; color: #2b4a7a; margin-top: 14pt; }
h3 { font-size: 11pt; color: #2b4a7a; }
code { font-family: Courier, monospace; background: #f0f0f0; padding: 1px 3px; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 10pt 0; }
th, td { border: 0.5pt solid #999; padding: 3pt 5pt; font-size: 8pt; text-align: left; }
th { background: #e8eef7; }
hr { border: none; border-top: 0.5pt solid #ccc; margin: 10pt 0; }
a { color: #1a56c4; text-decoration: none; }
"""

# Order matters: this is the reading order of the combined PDF.
SECTION_FILES = [
    "index.md",
    "interfaces.md",
    "shared-property-types.md",
    "action-types.md",
]


def _strip_relative_links(html: str) -> str:
    """xhtml2pdf can't resolve relative .md links across combined pages;
    de-link them to plain text + code so the PDF doesn't contain dead links."""
    import re

    # Turn [`foo`](bar.md) / [`foo`](object-types/bar.md) into just `foo`
    return re.sub(r"\[(`[^`]+`|[^\]]+)\]\([^)]+\.md\)", r"\1", html)


def _sanitize_glyphs(text: str) -> str:
    """xhtml2pdf's default Helvetica font has no glyphs for these symbols;
    swap in ASCII so they don't render as blank boxes."""
    return text.replace("←", "<-").replace("✓", "x")


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
<head><style>{PAGE_CSS}</style></head>
<body>
<div id="footer_content" style="text-align:center;font-size:7pt;color:#888;">
  <pdf:pagenumber/> / <pdf:pagecount/>
</div>
{body_html}
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = io.BytesIO()
    status = pisa.CreatePDF(src=html_doc, dest=result)
    if status.err:
        raise RuntimeError(f"PDF generation failed with {status.err} error(s)")
    out_path.write_bytes(result.getvalue())
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--out", default="docs/ontology-documentation.pdf")
    args = parser.parse_args()
    generate_pdf(Path(args.docs_dir), Path(args.out))


if __name__ == "__main__":
    main()
