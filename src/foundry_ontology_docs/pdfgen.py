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

/* ── cover page ── */
.cover-banner {
    background: #0f2044;
    color: white;
    padding: 36pt 32pt 28pt 32pt;
    margin: -1.6cm -1.4cm 0 -1.4cm;
    border-bottom: 4pt solid #2b6cb0;
}
.cover-banner h1 {
    font-size: 28pt;
    color: white;
    border: none;
    margin: 0 0 4pt 0;
    padding: 0;
    break-before: avoid;
    letter-spacing: 0.5pt;
}
.cover-subtitle {
    font-size: 11pt;
    color: #a0bce0;
    margin: 0 0 20pt 0;
    font-style: italic;
}
.cover-stats-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 6pt;
    margin: 0;
    table-layout: fixed;
}
.cover-stats-table td {
    background: rgba(255,255,255,0.08);
    border: 0.5pt solid rgba(255,255,255,0.2);
    border-radius: 3pt;
    padding: 8pt 10pt;
    vertical-align: top;
    text-align: center;
}
.cover-stat-value {
    font-size: 20pt;
    font-weight: bold;
    color: #63b3ed;
    line-height: 1.1;
    display: block;
}
.cover-stat-label {
    font-size: 7pt;
    color: #90a8c8;
    text-transform: uppercase;
    letter-spacing: 0.4pt;
    display: block;
    margin-top: 2pt;
}
.cover-meta {
    background: #f4f6fb;
    border: 0.5pt solid #c5d3e8;
    border-radius: 3pt;
    padding: 7pt 12pt;
    margin: 14pt 0 10pt 0;
    font-size: 8pt;
}
.cover-meta table { font-size: 8pt; margin: 0; }
.cover-meta td { border: none; padding: 2pt 10pt 2pt 0; background: transparent; }
.cover-meta td:first-child { font-weight: bold; color: #555; width: 110pt; }
.cover-groups-title {
    font-size: 9pt;
    font-weight: bold;
    color: #0f2044;
    margin: 12pt 0 5pt 0;
}
.cover-group-pill {
    display: inline-block;
    background: #e4eaf4;
    border: 0.5pt solid #c5d3e8;
    border-radius: 2pt;
    padding: 2pt 6pt;
    margin: 1.5pt 2pt;
    font-size: 7.5pt;
    color: #2b4a7a;
}

/* cover meta block (legacy) */
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

/* group divider in object-type sections */
.group-heading {
    font-size: 15pt;
    color: #0f2044;
    background: #e4eaf4;
    border-left: 4pt solid #2b4a7a;
    padding: 6pt 10pt;
    margin: 24pt 0 10pt 0;
    break-before: page;
    break-after: avoid;
}
.group-heading.first { break-before: avoid; }

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
/* TOC links rendered as a borderless 3-column table so WeasyPrint emits
   PDF link annotations (it drops annotations inside display:grid) */
.toc-table {
    width: 100%;
    border-collapse: collapse;
    margin: 0;
    table-layout: fixed;
    font-size: 7.8pt;
}
.toc-table td {
    border: none;
    background: transparent;
    padding: 1.5pt 4pt;
    vertical-align: top;
    overflow-wrap: anywhere;
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

/* relationship diagram embed */
.graph-embed {
    margin: 4pt 0 8pt 0;
    max-width: 100%;
    overflow: hidden;
}
.graph-embed svg {
    max-width: 100%;
    height: auto;
    display: block;
}
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
    from collections import Counter
    hostname  = _h(data.get("hostname") or "")
    ontology  = _h(data.get("ontology") or "Foundry Ontology")
    exported  = _h(data.get("exported_at") or "")
    n_links   = sum(len(ot["links"]) for ot in object_types)
    n_props   = sum(len(ot["properties"]) for ot in object_types)

    # Group counts for the cover pill list
    group_counts = Counter(ot["group"] for ot in object_types)
    pills = "".join(
        f'<span class="cover-group-pill"><strong>{count}</strong> {_h(grp)}</span>'
        for grp, count in sorted(group_counts.items(), key=lambda x: -x[1])
    )

    return f"""\
<div class="cover-banner">
  <h1>Ontology Documentation</h1>
  <p class="cover-subtitle">{ontology}</p>
  <table class="cover-stats-table">
    <tr>
      <td><span class="cover-stat-value">{len(object_types)}</span><span class="cover-stat-label">Object Types</span></td>
      <td><span class="cover-stat-value">{len(action_types)}</span><span class="cover-stat-label">Action Types</span></td>
      <td><span class="cover-stat-value">{n_links}</span><span class="cover-stat-label">Link Types</span></td>
      <td><span class="cover-stat-value">{n_props}</span><span class="cover-stat-label">Properties</span></td>
    </tr>
  </table>
</div>
<div class="cover-meta">
  <table>
    <tr><td>Host</td><td><code>{hostname}</code></td></tr>
    <tr><td>Exported</td><td>{exported}</td></tr>
    <tr><td>Domains</td><td>{len(group_counts)} inferred groups</td></tr>
  </table>
</div>
<p class="cover-groups-title">Object Types by Domain</p>
<div>{pills}</div>
"""


def _toc_table(items: list[tuple[str, str]], cols: int = 3) -> str:
    """Render a list of (href, label) pairs as a borderless N-column table.
    WeasyPrint only emits PDF link annotations for <a> elements inside
    block/table layout — display:grid silently drops them."""
    rows = []
    for i in range(0, len(items), cols):
        chunk = items[i:i + cols]
        cells = "".join(
            f'<td><a href="{href}">{_h(label)}</a></td>'
            for href, label in chunk
        )
        # pad to full width so column widths stay stable
        cells += "<td></td>" * (cols - len(chunk))
        rows.append(f"<tr>{cells}</tr>")
    return f'<table class="toc-table"><colgroup>' + '<col>' * cols + f'</colgroup><tbody>{"".join(rows)}</tbody></table>'


def _build_toc(object_types: list[dict], action_types: list[dict]) -> str:
    from collections import defaultdict
    # Group object types by domain, preserving group order from the list
    seen_groups: list[str] = []
    by_group: dict[str, list[dict]] = defaultdict(list)
    for ot in object_types:
        g = ot["group"]
        if g not in seen_groups:
            seen_groups.append(g)
        by_group[g].append(ot)

    obj_sections = ""
    for grp in seen_groups:
        items = [
            (f"#{_slug(ot['api_name'])}", ot["display_name"])
            for ot in by_group[grp]
        ]
        obj_sections += f"""
  <div class="toc-section">
    <div class="toc-section-title">{_h(grp)} ({len(items)})</div>
    {_toc_table(items)}
  </div>"""

    act_items = [
        (f"#{_action_slug(at['api_name'])}", at["display_name"])
        for at in action_types
    ]
    return f"""
<h1>Table of Contents</h1>
<h2 style="margin-top:10pt">Object Types ({len(object_types)})</h2>
{obj_sections}
<div class="toc-section">
  <div class="toc-section-title">Action Types ({len(action_types)})</div>
  {_toc_table(act_items)}
</div>
"""


def _embed_svg(svg_path: Path) -> str:
    """Inline an SVG file, stripping the XML declaration so it embeds cleanly."""
    raw = svg_path.read_text(encoding="utf-8")
    # Remove XML declaration if present
    raw = re.sub(r"<\?xml[^?]*\?>", "", raw).strip()
    return f'<div class="graph-embed">{raw}</div>'


def _build_object_sections(object_types: list[dict], graph_dir: Path | None = None) -> str:
    from collections import defaultdict
    # Preserve group ordering from the sorted object list
    seen_groups: list[str] = []
    by_group: dict[str, list[dict]] = defaultdict(list)
    for ot in object_types:
        g = ot["group"]
        if g not in seen_groups:
            seen_groups.append(g)
        by_group[g].append(ot)

    parts = ["<h1>Object Types</h1>"]
    first_group = True
    for grp in seen_groups:
        cls = "group-heading first" if first_group else "group-heading"
        parts.append(f'<div class="{cls}">{_h(grp)}</div>')
        first_group = False
        for ot in by_group[grp]:
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
            # Embed neighbourhood SVG if it exists and the object has ≤15 distinct
            # link targets — larger spoke graphs are unreadable when embedded at
            # page width, but are still available as standalone SVGs in docs/graph/
            graph_html = ""
            if graph_dir and ot["links"]:
                from foundry_ontology_docs.graphgen import _merge_links
                n_targets = len(_merge_links(ot["links"]))
                if n_targets <= 15:
                    svg_path = graph_dir / f"{ot['api_name']}.svg"
                    if svg_path.exists():
                        graph_html = f"<h3>Relationship Diagram</h3>{_embed_svg(svg_path)}"

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
  {graph_html}
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

def generate_pdf(export_path: Path, out_path: Path, graph_dir: Path | None = None) -> None:
    from foundry_ontology_docs.docgen import build_object_type_rows, build_action_type_rows

    data = json.loads(export_path.read_text())
    full_metadata = data.get("full_metadata", {})
    object_types = build_object_type_rows(full_metadata)
    action_types = build_action_type_rows(full_metadata)

    if graph_dir and not graph_dir.exists():
        print(f"Warning: --graph-dir {graph_dir} not found, skipping diagrams. Run foundry-ontology-graphgen first.")
        graph_dir = None

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>{PAGE_CSS}</style>
</head>
<body>
{_build_cover(data, object_types, action_types)}
{_build_toc(object_types, action_types)}
{_build_object_sections(object_types, graph_dir=graph_dir)}
{_build_action_sections(action_types)}
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # base_url must be set to a file:// URI for WeasyPrint to emit PDF
    # internal-link annotations for fragment hrefs (e.g. href="#obj-BedRequest").
    # Without it, WeasyPrint silently drops all #anchor links from the output.
    HTML(string=html_doc, base_url="file:///tmp/").write_pdf(str(out_path))
    n_graphs = sum(1 for ot in object_types if ot["links"] and graph_dir and (graph_dir / f"{ot['api_name']}.svg").exists())
    print(
        f"Wrote {out_path} ({out_path.stat().st_size:,} bytes) — "
        f"{len(object_types)} objects, {len(action_types)} actions"
        + (f", {n_graphs} relationship diagrams embedded" if n_graphs else "")
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
    parser.add_argument("--graph-dir", dest="graph_dir", default=None,
                        help="Path to neighbourhood SVGs from foundry-ontology-graphgen (default: docs/graph if it exists)")
    args = parser.parse_args()
    _check_native_deps()
    graph_dir = Path(args.graph_dir) if args.graph_dir else Path("docs/graph")
    generate_pdf(Path(args.in_path), Path(args.out), graph_dir=graph_dir)


if __name__ == "__main__":
    main()
