"""Generate relationship diagrams from the ontology export.

Usage:
    uv run foundry-ontology-graphgen [--in out/ontology_export.json] [--out-dir docs/graph]

Produces:
    overview.svg          — all objects that have ≥1 link (Graphviz sfdp, handles 167 nodes)
    <ObjectName>.svg      — per-object 1-hop neighbourhood (PlantUML IE/ERD, proper crow's foot)

PlantUML is used for per-object diagrams because it renders crow's foot cardinality
symbols (||--o{ for MANY, ||--o| for ONE) cleanly as proper ERD notation.
Graphviz is kept for the overview because PlantUML cannot scale to 167 nodes.
Requires: `plantuml` CLI on PATH (brew install plantuml).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import graphviz

# ── colour palette (shared) ───────────────────────────────────────────────────
STATUS_FILL = {
    "ACTIVE":       "#d4edda",
    "EXPERIMENTAL": "#fff3cd",
    "DEPRECATED":   "#f8d7da",
}
STATUS_BORDER = {
    "ACTIVE":       "#155724",
    "EXPERIMENTAL": "#856404",
    "DEPRECATED":   "#721c24",
}
# PlantUML header colours per status (header bg, header font)
PUML_HEADER = {
    "ACTIVE":       ("#155724", "white"),
    "EXPERIMENTAL": ("#856404", "white"),
    "DEPRECATED":   ("#721c24", "white"),
}
DEFAULT_FILL   = "#e8eef7"
DEFAULT_BORDER = "#2b4a7a"


# ── shared: merge parallel edges ──────────────────────────────────────────────

def _merge_links(links: list[dict]) -> dict[str, dict]:
    """Collapse multiple links to the same target into one entry.
    Cardinality: MANY wins over ONE."""
    merged: dict[str, dict] = {}
    for lk in links:
        tgt = lk.get("target_object_type") or ""
        card = (lk.get("cardinality") or "").upper()
        if tgt not in merged:
            merged[tgt] = {"target": tgt, "labels": [], "cardinality": card}
        merged[tgt]["labels"].append(lk.get("link_display_name") or lk.get("api_name") or "")
        if card == "MANY":
            merged[tgt]["cardinality"] = "MANY"
    return merged


# ── PlantUML neighbourhood diagrams ───────────────────────────────────────────

def _puml_escape(s: str) -> str:
    """Escape characters that break PlantUML string literals."""
    return s.replace('"', "'").replace("\n", "\\n").replace("<", "~<").replace(">", "~>")


def _puml_entity(api_name: str, ot: dict, is_focal: bool = False,
                 link_labels: list[str] | None = None) -> str:
    """Render one PlantUML entity block."""
    s = (ot.get("status") or "").upper()
    fill = STATUS_FILL.get(s, DEFAULT_FILL)
    hdr_bg, hdr_fg = PUML_HEADER.get(s, ("#2b4a7a", "white"))
    display = _puml_escape(ot.get("display_name") or api_name)

    # PlantUML entity colour syntax: entity "Name" as alias #fillcolor/headercolor {
    # fill already contains the leading #; don't add another one.
    lines = [f'entity "{display}" as {api_name} {fill}/white {{']

    # Primary key first
    props = ot.get("properties", []) or []
    pk_props = [p for p in props if p.get("is_primary_key")]
    other_props = [p for p in props if not p.get("is_primary_key")]

    for p in pk_props:
        lines.append(f'  * **{_puml_escape(p["api_name"])}** : {p["data_type"]} <<PK>>')

    if other_props:
        lines.append("  ==")
        # For focal entity show all properties; for neighbours show at most 5
        shown = other_props if is_focal else other_props[:5]
        for p in shown:
            lines.append(f'  {_puml_escape(p["api_name"])} : {p["data_type"]}')
        if not is_focal and len(other_props) > 5:
            lines.append(f"  .. +{len(other_props) - 5} more ..")

    # Link names inside the box for neighbour nodes
    if link_labels:
        lines.append("  ==")
        for lbl in link_labels:
            lines.append(f"  //← {_puml_escape(lbl)}//")

    lines.append("}")
    return "\n".join(lines)


def _puml_unknown_entity(api_name: str, link_labels: list[str]) -> str:
    lines = [f'entity "{api_name}" as {api_name} #eeeeee/white {{']
    lines.append("  * id : string <<PK>>")
    if link_labels:
        lines.append("  ==")
        for lbl in link_labels:
            lines.append(f"  //← {_puml_escape(lbl)}//")
    lines.append("}")
    return "\n".join(lines)


def _puml_relation(src: str, tgt: str, cardinality: str) -> str:
    """IE crow's foot notation:
        ||--o|   one-to-zero-or-one  (ONE)
        ||--o{   one-to-zero-or-many (MANY)
    """
    if cardinality == "MANY":
        return f"{src} ||--o{{ {tgt} : \" \""
    else:
        return f"{src} ||--o| {tgt} : \" \""


def build_neighbourhood_puml(ot: dict, ot_by_name: dict[str, dict], out_path: Path) -> Path | None:
    """Generate a PlantUML IE ERD for one object's 1-hop neighbourhood."""
    if not ot["links"]:
        return None

    merged = _merge_links(ot["links"])
    api_name = ot["api_name"]
    display = ot.get("display_name") or api_name

    n_targets = len(merged)
    # ortho gives the cleanest right-angle routing for PlantUML ERDs
    lines = [
        "@startuml",
        "hide circle",
        "skinparam linetype ortho",
        "skinparam defaultFontName Helvetica",
        "skinparam defaultFontSize 11",
    ]
    lines.append(f'title {_puml_escape(display)} — relationships')
    lines.append("")

    # Focal entity (all properties)
    lines.append(_puml_entity(api_name, ot, is_focal=True))
    lines.append("")

    # Neighbour entities
    for info in merged.values():
        tgt = info["target"]
        if not tgt:
            continue
        tgt_ot = ot_by_name.get(tgt)
        if tgt_ot:
            lines.append(_puml_entity(tgt, tgt_ot, is_focal=False, link_labels=info["labels"]))
        else:
            lines.append(_puml_unknown_entity(tgt, info["labels"]))
        lines.append("")

    # Relationships
    for info in merged.values():
        tgt = info["target"]
        if not tgt:
            continue
        lines.append(_puml_relation(api_name, tgt, info["cardinality"]))

    lines.append("")
    lines.append("@enduml")

    puml_src = "\n".join(lines)

    # Write .puml alongside the final SVG so plantuml -o writes into the same dir,
    # then rename the output to the canonical api_name.svg path.
    # Use resolved absolute paths — plantuml -o resolves relative to the .puml
    # file's location, not the cwd, so relative paths silently produce no output.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir_abs = out_path.parent.resolve()
    tmp_puml = out_dir_abs / f"_{api_name}_tmp.puml"
    tmp_puml.write_text(puml_src)
    expected_svg = out_dir_abs / f"_{api_name}_tmp.svg"
    # Remove any stale output from a previous run so plantuml always re-renders
    expected_svg.unlink(missing_ok=True)

    try:
        result = subprocess.run(
            ["plantuml", "-tsvg", str(tmp_puml), "-o", str(out_dir_abs)],
            capture_output=True, text=True, timeout=30,
        )
        if expected_svg.exists():
            expected_svg.rename(out_path)
            return out_path
        raise RuntimeError(
            f"plantuml did not produce SVG for {api_name}:\n"
            f"  stderr: {result.stderr[:200]}\n"
            f"  looked for: {expected_svg}"
        )
    finally:
        tmp_puml.unlink(missing_ok=True)
        expected_svg.unlink(missing_ok=True)


# ── Graphviz overview (unchanged) ─────────────────────────────────────────────

def _gv_node_attrs(ot: dict) -> dict[str, str]:
    s = (ot.get("status") or "").upper()
    return {
        "label":     f"{ot['display_name']}\n({ot['api_name']})",
        "shape":     "box",
        "style":     "filled,rounded",
        "fillcolor": STATUS_FILL.get(s, DEFAULT_FILL),
        "color":     STATUS_BORDER.get(s, DEFAULT_BORDER),
        "fontname":  "Helvetica",
        "fontsize":  "9",
        "margin":    "0.15,0.08",
    }


def _gv_edge_attrs(info: dict) -> dict[str, str]:
    card = info["cardinality"]
    color = "#6a5acd" if card == "MANY" else "#2b4a7a"
    arrow = "crow" if card == "MANY" else "normal"
    return {"color": color, "arrowhead": arrow, "penwidth": "1.0", "fontname": "Helvetica"}


def build_overview(object_types: list[dict], out_path: Path) -> Path:
    """Graphviz sfdp overview of all connected objects."""
    linked = {ot["api_name"] for ot in object_types if ot["links"]}
    targets: set[str] = set()
    for ot in object_types:
        for lk in ot["links"]:
            t = lk.get("target_object_type")
            if t:
                targets.add(t)
    nodes_needed = linked | targets
    ot_by_name = {ot["api_name"]: ot for ot in object_types}

    g = graphviz.Digraph(
        name="ontology_overview",
        graph_attr={
            "layout":        "sfdp",
            "splines":       "curved",
            "overlap":       "prism",
            "fontname":      "Helvetica",
            "fontsize":      "10",
            "bgcolor":       "white",
            "pad":           "0.5",
            "label":         "Ontology Object Relationships (overview)",
            "labelloc":      "t",
            "labelfontsize": "12",
        },
        node_attr={"fontname": "Helvetica"},
        edge_attr={"fontname": "Helvetica"},
    )

    for name in sorted(nodes_needed):
        ot = ot_by_name.get(name)
        if ot:
            g.node(name, **_gv_node_attrs(ot))
        else:
            g.node(name, label=name, shape="box", style="dashed,rounded",
                   fillcolor="#eeeeee", color="#aaaaaa", fontsize="9", fontname="Helvetica")

    for ot in object_types:
        src = ot["api_name"]
        for info in _merge_links(ot["links"]).values():
            tgt = info["target"]
            if tgt:
                g.edge(src, tgt, **_gv_edge_attrs(info))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path = Path(g.render(filename=str(out_path.with_suffix("")), format="svg", cleanup=True))
    total_edges = sum(len(_merge_links(ot["links"])) for ot in object_types)
    print(f"  overview: {svg_path} ({svg_path.stat().st_size:,} bytes, "
          f"{len(nodes_needed)} nodes, {total_edges} edges)")
    return svg_path


# ── main ──────────────────────────────────────────────────────────────────────

def generate_graphs(export_path: Path, out_dir: Path) -> None:
    if not shutil.which("plantuml"):
        raise SystemExit("plantuml not found on PATH. Install with: brew install plantuml")

    from foundry_ontology_docs.docgen import build_object_type_rows

    data = json.loads(export_path.read_text())
    object_types = build_object_type_rows(data.get("full_metadata", {}))
    ot_by_name = {ot["api_name"]: ot for ot in object_types}

    out_dir.mkdir(parents=True, exist_ok=True)

    print("Building overview graph (Graphviz sfdp)...")
    build_overview(object_types, out_dir / "overview.svg")

    print("Building per-object neighbourhood diagrams (PlantUML ERD)...")
    n = 0
    errors = 0
    for ot in object_types:
        if not ot["links"]:
            continue
        path = out_dir / f"{ot['api_name']}.svg"
        try:
            build_neighbourhood_puml(ot, ot_by_name, path)
            n += 1
        except Exception as e:
            print(f"  WARNING: {ot['api_name']}: {e}")
            errors += 1
    print(f"  {n} diagrams written to {out_dir}/"
          + (f" ({errors} errors)" if errors else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", default="out/ontology_export.json")
    parser.add_argument("--out-dir", dest="out_dir", default="docs/graph")
    args = parser.parse_args()
    generate_graphs(Path(args.in_path), Path(args.out_dir))


if __name__ == "__main__":
    main()
