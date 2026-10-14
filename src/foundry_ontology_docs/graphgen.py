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
        "margin":    "0.15,0.08",
    }


def _node_attrs_with_links(ot: dict, link_labels: list[str]) -> dict[str, str]:
    """Target node that shows the link name(s) inside the box instead of on the edge.

    This avoids hub-spoke label crowding: for high-degree source nodes, all
    the relationship names sit inside their target boxes rather than jostling
    around the centre of the diagram.
    """
    s = (ot.get("status") or "").upper()
    via = "\n".join(f"← {l}" for l in link_labels)
    return {
        "label":     f"{ot['display_name']}\n({ot['api_name']})\n{via}",
        "shape":     "box",
        "style":     "filled,rounded",
        "fillcolor": STATUS_FILL.get(s, DEFAULT_FILL),
        "color":     STATUS_BORDER.get(s, DEFAULT_BORDER),
        "fontname":  "Helvetica",
        "fontsize":  "8",
        "margin":    "0.15,0.08",
    }


def _unknown_node_attrs_with_links(name: str, link_labels: list[str]) -> dict[str, str]:
    via = "\n".join(f"← {l}" for l in link_labels)
    return {
        "label":     f"{name}\n{via}",
        "shape":     "box",
        "style":     "dashed,rounded",
        "fillcolor": "#eeeeee",
        "color":     "#aaaaaa",
        "fontsize":  "8",
        "fontname":  "Helvetica",
    }


def _merge_links(links: list[dict]) -> dict[str, dict]:
    """Merge parallel edges (same source→target pair) into one edge.

    When multiple links go to the same target object, bundle them into a
    single edge whose label lists all the link display names separated by
    newlines.  Cardinality: MANY wins over ONE (crow arrow); color: purple
    if any MANY, blue otherwise.
    """
    merged: dict[str, dict] = {}
    for lk in links:
        tgt = lk.get("target_object_type") or ""
        src_api = lk.get("api_name") or ""  # not used for key — tgt is enough
        card = (lk.get("cardinality") or "").upper()
        key = tgt  # group by target
        if key not in merged:
            merged[key] = {
                "target": tgt,
                "labels": [],
                "cardinality": card,
            }
        merged[key]["labels"].append(lk.get("link_display_name") or lk.get("api_name") or "")
        # MANY beats ONE
        if card == "MANY":
            merged[key]["cardinality"] = "MANY"

    return merged


def _edge_attrs_merged(info: dict) -> dict[str, str]:
    card = info["cardinality"]
    arrow = "normal" if card == "ONE" else "crow"
    color = CARDINALITY_COLOR.get(card, "#666666")
    label = "\n".join(info["labels"])
    return {
        "label":     label,
        "color":     color,
        "fontcolor": "#333333",
        "fontname":  "Helvetica",
        "fontsize":  "7",
        "arrowhead": arrow,
        "penwidth":  "1.2",
    }


# ── overview graph ────────────────────────────────────────────────────────────

def build_overview(object_types: list[dict], out_path: Path) -> Path:
    """One graph of all objects that have ≥1 link (fdp force-directed layout)."""
    linked = {ot["api_name"] for ot in object_types if ot["links"]}
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
            "layout":        "sfdp",   # scalable fdp — handles 100+ nodes without hanging
            "splines":       "curved",
            "overlap":       "prism",  # prism overlap removal is fast; "false" with fdp hangs
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
            g.node(name, **_node_attrs(ot))
        else:
            g.node(name, label=name, shape="box", style="dashed,rounded",
                   fillcolor="#eeeeee", color="#aaaaaa", fontsize="9", fontname="Helvetica")

    # Merge parallel edges per source→target pair for the overview too
    for ot in object_types:
        src = ot["api_name"]
        merged = _merge_links(ot["links"])
        for info in merged.values():
            tgt = info["target"]
            if not tgt:
                continue
            g.edge(src, tgt, **_edge_attrs_merged(info))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path = Path(g.render(filename=str(out_path.with_suffix("")), format="svg", cleanup=True))
    total_edges = sum(len(_merge_links(ot["links"])) for ot in object_types)
    print(f"  overview: {svg_path} ({svg_path.stat().st_size:,} bytes, {len(nodes_needed)} nodes, {total_edges} merged edges)")
    return svg_path


# ── per-object neighbourhood ──────────────────────────────────────────────────

def build_neighbourhood(ot: dict, ot_by_name: dict[str, dict], out_path: Path) -> Path | None:
    """1-hop neighbourhood: the object itself + all objects it links to.

    Parallel edges (multiple links to same target) are merged into one edge
    with a multi-line label.  Layout uses 'dot' TB for small graphs, 'neato'
    for large ones (>8 targets) which handles sprawling spoke-graphs better.
    """
    if not ot["links"]:
        return None

    merged = _merge_links(ot["links"])
    n_targets = len(merged)

    # dot LR: clean for small/medium graphs (≤12 targets)
    # twopi: radial layout spreads targets evenly around the hub — prevents
    #         arrow bundling at the centre for large spoke graphs (>12 targets)
    if n_targets <= 12:
        layout   = "dot"
        rankdir  = "LR"
        splines  = "spline"
        nodesep  = "0.5"
        ranksep  = "1.4"
        overlap  = "false"
    else:
        layout   = "twopi"
        rankdir  = ""
        splines  = "spline"
        nodesep  = "0.8"
        ranksep  = "2.5"
        overlap  = "false"

    graph_attr: dict[str, str] = {
        "layout":   layout,
        "splines":  splines,
        "overlap":  overlap,
        "sep":      "+6",
        "fontname": "Helvetica",
        "fontsize": "9",
        "bgcolor":  "white",
        "pad":      "0.3",
        "label":    f"{ot['display_name']} — relationships",
        "labelloc": "t",
        "nodesep":  nodesep,
    }
    if rankdir:
        graph_attr["rankdir"] = rankdir
    if layout == "dot":
        graph_attr["ranksep"] = ranksep

    g = graphviz.Digraph(
        name=f"obj_{ot['api_name']}",
        graph_attr=graph_attr,
        node_attr={"fontname": "Helvetica"},
        edge_attr={"fontname": "Helvetica"},
    )

    # focal node — bolder border
    focal_attrs = _node_attrs(ot)
    focal_attrs["penwidth"] = "2.5"
    focal_attrs["fontsize"] = "10"
    g.node(ot["api_name"], **focal_attrs)

    # add target nodes + one unlabelled edge per target
    # Link names go INSIDE the target node box to avoid hub-spoke label crowding
    for info in merged.values():
        tgt = info["target"]
        if not tgt:
            continue
        tgt_ot = ot_by_name.get(tgt)
        if tgt_ot:
            g.node(tgt, **_node_attrs_with_links(tgt_ot, info["labels"]))
        else:
            g.node(tgt, **_unknown_node_attrs_with_links(tgt, info["labels"]))
        # Edge carries only cardinality arrow — no text label
        card = info["cardinality"]
        arrow = "normal" if card == "ONE" else "crow"
        color = CARDINALITY_COLOR.get(card, "#666666")
        g.edge(ot["api_name"], tgt,
               color=color, arrowhead=arrow, penwidth="1.5")

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
