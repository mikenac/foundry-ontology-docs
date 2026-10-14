"""Render the ontology export directly to a polished PDF with working TOC links.

Usage:
    uv run foundry-ontology-pdfgen [--in out/ontology_export.json] [--out docs/ontology-documentation.pdf]

Generates HTML directly from the export JSON so internal anchor links in
the TOC are always consistent with section anchor IDs. Uses WeasyPrint.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any

# On macOS, Python's cffi dlopen() can't find Homebrew dylibs unless
# DYLD_FALLBACK_LIBRARY_PATH is set — do this before importing weasyprint.
if platform.system() == "Darwin":
    for prefix in ("/opt/homebrew/lib", "/usr/local/lib"):
        if Path(prefix).is_dir():
            existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
            if prefix not in existing.split(":"):
                os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
                    f"{prefix}:{existing}" if existing else prefix
                )

from weasyprint import HTML  # noqa: E402

# ── helpers ───────────────────────────────────────────────────────────────────

def _slug(api_name: str) -> str:
    return "obj-" + re.sub(r"[^a-zA-Z0-9_-]", "-", api_name)


def _action_slug(api_name: str) -> str:
    return "act-" + re.sub(r"[^a-zA-Z0-9_-]", "-", api_name)


def _h(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _code(text: str) -> str:
    return f"<code>{_h(str(text))}</code>"


def _fmt_data_type(dt: dict[str, Any] | None) -> str:
    if not dt:
        return "unknown"
    t = dt.get("type", "unknown")
    if t == "array":
        return f"array&lt;{_fmt_data_type(dt.get('subType'))}&gt;"
    if t == "struct":
        fields = dt.get("structFieldTypes") or dt.get("fields") or []
        names = [f.get("apiName") or f.get("name") for f in fields] if fields else []
        return f"struct&lt;{', '.join(n for n in names if n)}&gt;" if names else "struct"
    return _h(t)


# ── CSS ───────────────────────────────────────────────────────────────────────

PAGE_CSS = """
@page {
    size: letter;
    margin: 1.6cm 1.4cm 2cm 1.4cm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 7.5pt;
        color: #888;
    }
}
html { font-size: 9pt; }
body {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    line-height: 1.45;
    color: #1a1a1a;
}

h1 {
    font-size: 20pt;
    color: #0f2044;
    border-bottom: 2pt solid #2b4a7a;
    padding-bottom: 5pt;
    margin: 0 0 10pt 0;
    break-before: page;
}
h1.first { break-before: avoid; }
h2 {
    font-size: 12pt;
    color: #2b4a7a;
    border-bottom: 0.5pt solid #c5d3e8;
    padding-bottom: 2pt;
    margin: 16pt 0 5pt 0;
    break-after: avoid;
}
h3 {
    font-size: 9.5pt;
    color: #445;
    margin: 8pt 0 3pt 0;
    break-after: avoid;
}

p { margin: 3pt 0 5pt 0; }
code {
    font-family: "Menlo", "Courier New", monospace;
    background: #f0f2f5;
    padding: 1px 4px;
    border-radius: 2px;
    font-size: 0.87em;
    overflow-wrap: anywhere;
}
hr { border: none; border-top: 0.5pt solid #ddd; margin: 8pt 0; }
a { color: #1a56c4; text-decoration: none; }

/* tables */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 3pt 0 10pt 0;
    table-layout: fixed;
    font-size: 7.8pt;
}
th, td {
    border: 0.5pt solid #c8d0dc;
    padding: 3.5pt 5pt;
    text-align: left;
    vertical-align: top;
    overflow-wrap: anywhere;
    word-break: normal;
    hyphens: auto;
}
th {
    background: #e4eaf4;
    font-weight: bold;
    color: #0f2044;
    font-size: 7.5pt;
}
tr:nth-child(even) td { background: #f7f8fb; }

/* status tags */
.tag {
    display: inline-block;
    font-size: 6.5pt;
    padding: 1pt 4pt;
    border-radius: 2pt;
    font-weight: bold;
    margin-left: 5pt;
    vertical-align: middle;
}
.tag-ACTIVE      { background: #d4edda; color: #155724; }
.tag-DEPRECATED  { background: #f8d7da; color: #721c24; }
.tag-EXPERIMENTAL{ background: #fff3cd; color: #856404; }

/* cover meta block */
.meta-block {
    background: #f4f6fb;
    border: 0.5pt solid #c5d3e8;
    border-radius: 3pt;
    padding: 7pt 10pt;
    margin-bottom: 14pt;
    font-size: 8.5pt;
}
.meta-block table { font-size: 8.5pt; margin: 0; }
.meta-block td { border: none; padding: 2pt 10pt 2pt 0; background: transparent; }
.meta-block td:first-child { font-weight: bold; color: #555; width: 130pt; }

/* TOC */
.toc-section { margin-bottom: 14pt; }
.toc-section-title {
    font-size: 11pt;
    font-weight: bold;
    color: #0f2044;
    border-bottom: 0.5pt solid #c5d3e8;
    padding-bottom: 2pt;
    margin: 0 0 6pt 0;
}
.toc-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    column-gap: 8pt;
    row-gap: 2pt;
    font-size: 7.8pt;
}

/* object & action sections */
.object-meta {
    background: #f4f6fb;
    border-left: 2.5pt solid #2b4a7a;
    padding: 5pt 8pt;
    margin-bottom: 7pt;
    font-size: 8pt;
}
.object-meta table { font-size: 8pt; margin: 0; }
.object-meta td { border: none; padding: 1.5pt 10pt 1.5pt 0; background: transparent; }
.object-meta td:first-child { font-weight: bold; color: #555; width: 110pt; }

.action-block {
    border-left: 2pt solid #c5d3e8;
    padding-left: 8pt;
    margin-bottom: 14pt;
}
.action-ops { font-size: 7.8pt; margin: 3pt 0 6pt 0; color: #444; }
"""


# ── HTML builders ─────────────────────────────────────────────────────────────

def _tag_html(status: str | None) -> str:
    if not status:
        return ""
    key = status.upper()
    cls = f"tag-{key}" if key in ("ACTIVE", "DEPRECATED", "EXPERIMENTAL") else ""
    return f'<span class="tag {cls}">{_h(status)}</span>'


def _property_table(properties: list[dict]) -> str:
    if not properties:
        return "<p><em>No properties.</em></p>"
    rows = []
    for p in properties:
        pk = " <strong>PK</strong>" if p["is_primary_key"] else ""
        rows.append(
            f"<tr>"
            f"<td>{_code(p['api_name'])}{pk}</td>"
            f"<td>{_h(p['display_name'])}</td>"
            f"<td>{_code(p['data_type'])}</td>"
            f"<td>{_h(p['description'])}</td>"
            f"</tr>"
        )
    return (
        "<table>"
        "<colgroup>"
        '<col style="width:26%"><col style="width:22%">'
        '<col style="width:16%"><col style="width:36%">'
        "</colgroup>"
        "<thead><tr>"
        "<th>API Name</th><th>Display Name</th><th>Type</th><th>Description</th>"
        "</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


def _link_table(links: list[dict]) -> str:
    if not links:
        return "<p><em>No links defined.</em></p>"
    rows = []
    for lk in links:
        tgt = lk["target_object_type"] or ""
        tgt_html = (
            f'<a href="#{_slug(tgt)}">{_code(tgt)}</a>'
            if tgt else ""
        )
        rows.append(
            f"<tr>"
            f"<td>{_code(lk['api_name'])}</td>"
            f"<td>{_h(lk['display_name'])}</td>"
            f"<td>{tgt_html}</td>"
            f"<td>{_h(lk['cardinality'] or '')}</td>"
            f"<td>{_tag_html(lk['status'])}</td>"
            f"</tr>"
        )
    return (
        "<table>"
        "<colgroup>"
        '<col style="width:22%"><col style="width:22%">'
        '<col style="width:22%"><col style="width:12%"><col style="width:22%">'
        "</colgroup>"
        "<thead><tr>"
        "<th>API Name</th><th>Display Name</th>"
        "<th>Target Object Type</th><th>Cardinality</th><th>Status</th>"
        "</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


def _param_table(params: list[dict]) -> str:
    if not params:
        return "<p><em>No parameters.</em></p>"
    rows = []
    for p in params:
        req = "<strong>required</strong>" if p["required"] else "optional"
        rows.append(
            f"<tr>"
            f"<td>{_code(p['api_name'])}</td>"
            f"<td>{_h(p['display_name'])}</td>"
            f"<td>{_code(p['data_type'])}</td>"
            f"<td>{req}</td>"
            f"<td>{_h(p['description'])}</td>"
            f"</tr>"
        )
    return (
        "<table>"
        "<colgroup>"
        '<col style="width:22%"><col style="width:22%">'
        '<col style="width:14%"><col style="width:10%"><col style="width:32%">'
        "</colgroup>"
        "<thead><tr>"
        "<th>API Name</th><th>Display Name</th><th>Type</th>"
        "<th>Required</th><th>Description</th>"
        "</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


# ── section builders ──────────────────────────────────────────────────────────

def _build_cover(data: dict, object_types: list[dict], action_types: list[dict]) -> str:
    hostname = _h(data.get("hostname") or "")
    ontology = _h(data.get("ontology") or "")
    exported = _h(data.get("exported_at") or "")
    n_links = sum(len(ot["links"]) for ot in object_types)
    return f"""
<h1 class="first">Ontology Documentation</h1>
<div class="meta-block">
  <table>
    <tr><td>Ontology</td><td><code>{ontology}</code></td></tr>
    <tr><td>Host</td><td><code>{hostname}</code></td></tr>
    <tr><td>Exported</td><td>{exported}</td></tr>
    <tr><td>Object types</td><td>{len(object_types)}</td></tr>
    <tr><td>Action types</td><td>{len(action_types)}</td></tr>
    <tr><td>Link types</td><td>{n_links}</td></tr>
  </table>
</div>
"""


def _build_toc(object_types: list[dict], action_types: list[dict]) -> str:
    obj_links = "\n".join(
        f'<a href="#{_slug(ot["api_name"])}">{_h(ot["display_name"])}</a>'
        for ot in object_types
    )
    act_links = "\n".join(
        f'<a href="#{_action_slug(at["api_name"])}">{_h(at["display_name"])}</a>'
        for at in action_types
    )
    return f"""
<h1>Table of Contents</h1>
<div class="toc-section">
  <div class="toc-section-title">Object Types ({len(object_types)})</div>
  <div class="toc-grid">{obj_links}</div>
</div>
<div class="toc-section">
  <div class="toc-section-title">Action Types ({len(action_types)})</div>
  <div class="toc-grid">{act_links}</div>
</div>
"""


def _build_object_sections(object_types: list[dict]) -> str:
    parts = ["<h1>Object Types</h1>"]
    for ot in object_types:
        slug = _slug(ot["api_name"])
        status_tag = _tag_html(ot["status"])
        ifaces = (
            ", ".join(_code(i) for i in ot["implements_interfaces"])
            if ot["implements_interfaces"] else "—"
        )
        desc_row = (
            f"<tr><td>Description</td><td>{_h(ot['description'])}</td></tr>"
            if ot["description"] else ""
        )
        parts.append(f"""
<div id="{slug}">
  <h2>{_h(ot['display_name'])}{status_tag}
    <small style="font-size:8pt;font-weight:normal;color:#666;margin-left:6pt">{_h(ot['api_name'])}</small>
  </h2>
  <div class="object-meta">
    <table>
      <tr><td>Primary key</td><td>{_code(ot['primary_key'])}</td></tr>
      <tr><td>Plural name</td><td>{_h(ot['plural_display_name'])}</td></tr>
      <tr><td>Interfaces</td><td>{ifaces}</td></tr>
      {desc_row}
    </table>
  </div>
  <h3>Properties</h3>
  {_property_table(ot['properties'])}
  <h3>Links</h3>
  {_link_table(ot['links'])}
</div>
""")
    return "\n".join(parts)


def _build_action_sections(action_types: list[dict]) -> str:
    parts = ["<h1>Action Types</h1>"]
    for at in action_types:
        slug = _action_slug(at["api_name"])
        status_tag = _tag_html(at["status"])
        ops_html = ", ".join(
            f'{_h(op["type"])}({_code(op["object_type"])})'
            for op in at["operations"]
        ) if at["operations"] else "—"
        desc_html = f"<p>{_h(at['description'])}</p>" if at["description"] else ""
        parts.append(f"""
<div class="action-block" id="{slug}">
  <h2>{_h(at['display_name'])}{status_tag}
    <small style="font-size:8pt;font-weight:normal;color:#666;margin-left:6pt">{_h(at['api_name'])}</small>
  </h2>
  {desc_html}
  <p class="action-ops"><strong>Operations:</strong> {ops_html}</p>
  <h3>Parameters</h3>
  {_param_table(at['parameters'])}
</div>
""")
    return "\n".join(parts)


# ── main ──────────────────────────────────────────────────────────────────────

def generate_pdf(export_path: Path, out_path: Path) -> None:
    from foundry_ontology_docs.docgen import build_object_type_rows, build_action_type_rows

    data = json.loads(export_path.read_text())
    full_metadata = data.get("full_metadata", {})
    object_types = build_object_type_rows(full_metadata)
    action_types = build_action_type_rows(full_metadata)

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>{PAGE_CSS}</style>
</head>
<body>
{_build_cover(data, object_types, action_types)}
{_build_toc(object_types, action_types)}
{_build_object_sections(object_types)}
{_build_action_sections(action_types)}
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_doc).write_pdf(str(out_path))
    print(
        f"Wrote {out_path} ({out_path.stat().st_size:,} bytes) — "
        f"{len(object_types)} objects, {len(action_types)} actions"
    )


def _check_native_deps() -> None:
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
    parser.add_argument("--in", dest="in_path", default="out/ontology_export.json")
    parser.add_argument("--out", default="docs/ontology-documentation.pdf")
    args = parser.parse_args()
    _check_native_deps()
    generate_pdf(Path(args.in_path), Path(args.out))


if __name__ == "__main__":
    main()
