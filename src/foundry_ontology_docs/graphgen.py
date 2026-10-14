"""Generate Graphviz relationship diagrams from the ontology export.

Usage:
    uv run foundry-ontology-graphgen [--in out/ontology_export.json] [--out-dir docs/graph]

Produces:
    overview.svg          — all objects that have at least one link, fdp layout
    <ObjectName>.svg      — per-object 1-hop neighbourhood diagram
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import graphviz

# ── colour palette ────────────────────────────────────────────────────────────
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
CARDINALITY_COLOR = {
    "ONE":  "#2b4a7a",
    "MANY": "#6a5acd",
}
DEFAULT_FILL   = "#e8eef7"
DEFAULT_BORDER = "#2b4a7a"


def _node_attrs(ot: dict) -> dict[str, str]:
    s = (ot.get("status") or "").upper()
    return {
        "label":     f"{ot['display_name']}\n({ot['api_name']})",
        "shape":     "box",
        "style":     "filled,rounded",
        "fillcolor": STATUS_FILL.get(s, DEFAULT_FILL),
        "color":     STATUS_BORDER.get(s, DEFAULT_BORDER),
        "fontname":  "Helvetica",
        "fontsize":  "9",
        "margin":    "0.12,0.06",
    }


def _edge_attrs(link: dict) -> dict[str, str]:
    card = (link.get("cardinality") or "").upper()
    arrow = "normal" if card == "ONE" else "crow"
    color = CARDINALITY_COLOR.get(card, "#666666")
    return {
        # Use xlabel (external label) for ortho splines; regular label for others
        "xlabel":    link.get("link_display_name") or link.get("api_name") or "",
        "color":     color,
        "fontcolor": color,
        "fontname":  "Helvetica",
        "fontsize":  "7",
        "arrowhead": arrow,
        "penwidth":  "1.0",
    }


# ── overview graph ────────────────────────────────────────────────────────────

def build_overview(object_types: list[dict], out_path: Path) -> Path:
    """One graph of all objects that have ≥1 link (fdp force-directed layout)."""
    linked = {ot["api_name"] for ot in object_types if ot["links"]}
    # also include targets of those links even if they have no outgoing links
    targets = set()
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
            "layout":    "fdp",
            "splines":   "curved",
            "overlap":   "false",
            "sep":       "+8",
            "fontname":  "Helvetica",
            "fontsize":  "10",
            "bgcolor":   "white",
            "pad":       "0.4",
            "label":     "Ontology Object Relationships (overview)",
            "labelloc":  "t",
            "labelfontsize": "12",
        },
        node_attr={"fontname": "Helvetica"},
        edge_attr={"fontname": "Helvetica"},
    )

    for name in sorted(nodes_needed):
        ot = ot_by_name.get(name)
        if ot:
            g.node(name, **_node_attrs(ot))
        else:
            # referenced target not in export — render as dashed unknown node
            g.node(name, label=name, shape="box", style="dashed,rounded",
                   fillcolor="#eeeeee", color="#aaaaaa", fontsize="9", fontname="Helvetica")

    seen_edges: set[tuple[str, str, str]] = set()
    for ot in object_types:
        src = ot["api_name"]
        for lk in ot["links"]:
            tgt = lk.get("target_object_type")
            if not tgt:
                continue
            key = (src, tgt, lk.get("api_name", ""))
            if key in seen_edges:
                continue
            seen_edges.add(key)
            g.edge(src, tgt, **_edge_attrs(lk))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path = Path(g.render(filename=str(out_path.with_suffix("")), format="svg", cleanup=True))
    print(f"  overview: {svg_path} ({svg_path.stat().st_size:,} bytes, {len(nodes_needed)} nodes, {len(seen_edges)} edges)")
    return svg_path


# ── per-object neighbourhood ──────────────────────────────────────────────────

def build_neighbourhood(ot: dict, ot_by_name: dict[str, dict], out_path: Path) -> Path:
    """1-hop neighbourhood: the object itself + all objects it links to."""
    if not ot["links"]:
        return None  # type: ignore

    g = graphviz.Digraph(
        name=f"obj_{ot['api_name']}",
        graph_attr={
            "layout":   "dot",
            "rankdir":  "LR",
            "splines":  "ortho",
            "fontname": "Helvetica",
            "fontsize": "9",
            "bgcolor":  "white",
            "pad":      "0.2",
            "label":    f"{ot['display_name']} — relationships",
            "labelloc": "t",
        },
        node_attr={"fontname": "Helvetica"},
        edge_attr={"fontname": "Helvetica"},
    )

    # focal node — slightly larger
    focal_attrs = _node_attrs(ot)
    focal_attrs["penwidth"] = "2"
    focal_attrs["fontsize"] = "10"
    g.node(ot["api_name"], **focal_attrs)

    for lk in ot["links"]:
        tgt = lk.get("target_object_type")
        if not tgt:
            continue
        tgt_ot = ot_by_name.get(tgt)
        if tgt_ot:
            g.node(tgt, **_node_attrs(tgt_ot))
        else:
            g.node(tgt, label=tgt, shape="box", style="dashed,rounded",
                   fillcolor="#eeeeee", color="#aaaaaa", fontsize="9", fontname="Helvetica")
        g.edge(ot["api_name"], tgt, **_edge_attrs(lk))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path = Path(g.render(filename=str(out_path.with_suffix("")), format="svg", cleanup=True))
    return svg_path


# ── main ──────────────────────────────────────────────────────────────────────

def generate_graphs(export_path: Path, out_dir: Path) -> None:
    from foundry_ontology_docs.docgen import build_object_type_rows

    data = json.loads(export_path.read_text())
    object_types = build_object_type_rows(data.get("full_metadata", {}))
    ot_by_name = {ot["api_name"]: ot for ot in object_types}

    out_dir.mkdir(parents=True, exist_ok=True)

    print("Building overview graph...")
    build_overview(object_types, out_dir / "overview.svg")

    print("Building per-object neighbourhood diagrams...")
    n = 0
    for ot in object_types:
        if not ot["links"]:
            continue
        path = out_dir / f"{ot['api_name']}.svg"
        build_neighbourhood(ot, ot_by_name, path)
        n += 1
    print(f"  {n} neighbourhood diagrams written to {out_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", default="out/ontology_export.json")
    parser.add_argument("--out-dir", dest="out_dir", default="docs/graph")
    args = parser.parse_args()
    generate_graphs(Path(args.in_path), Path(args.out_dir))


if __name__ == "__main__":
    main()
