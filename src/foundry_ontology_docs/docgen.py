"""Generate Markdown documentation from a Foundry ontology metadata export.

Usage:
    uv run foundry-ontology-docgen [--in out/ontology_export.json] [--out-dir docs]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=(".md.j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def _fmt_data_type(dt: dict[str, Any] | None) -> str:
    if not dt:
        return "unknown"
    t = dt.get("type", "unknown")
    if t == "array":
        return f"array<{_fmt_data_type(dt.get('subType'))}>"
    if t == "struct":
        fields = dt.get("structFieldTypes") or dt.get("fields") or []
        names = [f.get("apiName") or f.get("name") for f in fields] if fields else []
        return f"struct<{', '.join(n for n in names if n)}>" if names else "struct"
    return t


def load_export(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def build_object_type_rows(full_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    object_types = full_metadata.get("objectTypes", {}) or {}
    for api_name, entry in sorted(object_types.items()):
        ot = entry.get("objectType", {}) or {}
        props = ot.get("properties", {}) or {}
        prop_rows = [
            {
                "api_name": p_name,
                "display_name": p.get("displayName") or p_name,
                "data_type": _fmt_data_type(p.get("dataType")),
                "description": p.get("description") or "",
                "is_primary_key": p_name == ot.get("primaryKey"),
            }
            for p_name, p in sorted(props.items())
        ]
        link_rows = [
            {
                "api_name": lt.get("apiName"),
                "display_name": lt.get("displayName") or lt.get("apiName"),
                "target_object_type": lt.get("objectTypeApiName"),
                "cardinality": lt.get("cardinality"),
                "status": lt.get("status"),
            }
            for lt in entry.get("linkTypes", []) or []
        ]
        rows.append(
            {
                "api_name": api_name,
                "display_name": ot.get("displayName") or api_name,
                "plural_display_name": ot.get("pluralDisplayName") or "",
                "description": ot.get("description") or "",
                "primary_key": ot.get("primaryKey") or "",
                "status": (ot.get("status") or {}).get("type")
                if isinstance(ot.get("status"), dict)
                else ot.get("status"),
                "rid": ot.get("rid") or "",
                "properties": prop_rows,
                "links": link_rows,
                "implements_interfaces": entry.get("implementsInterfaces", []) or [],
            }
        )
    return rows


def build_action_type_rows(full_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    action_types = full_metadata.get("actionTypes", {}) or {}
    for api_name, at in sorted(action_types.items()):
        params = at.get("parameters", {}) or {}
        param_rows = [
            {
                "api_name": p_name,
                "display_name": p.get("displayName") or p_name,
                "data_type": _fmt_data_type(p.get("dataType")),
                "required": bool(p.get("required")),
                "description": p.get("description") or "",
            }
            for p_name, p in sorted(params.items())
        ]
        op_rows = [
            {"type": op.get("type"), "object_type": op.get("objectTypeApiName")}
            for op in at.get("operations", []) or []
        ]
        rows.append(
            {
                "api_name": api_name,
                "display_name": at.get("displayName") or api_name,
                "description": at.get("description") or "",
                "status": at.get("status") or "",
                "rid": at.get("rid") or "",
                "parameters": param_rows,
                "operations": op_rows,
            }
        )
    return rows


def build_interface_rows(full_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    interfaces = full_metadata.get("interfaceTypes", {}) or {}
    for api_name, it in sorted(interfaces.items()):
        props = it.get("properties", {}) or {}
        rows.append(
            {
                "api_name": api_name,
                "display_name": it.get("displayName") or api_name,
                "description": it.get("description") or "",
                "properties": sorted(props.keys()),
                "extends_interfaces": it.get("extendsInterfaces", []) or [],
            }
        )
    return rows


def build_shared_property_rows(full_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    spts = full_metadata.get("sharedPropertyTypes", {}) or {}
    for api_name, spt in sorted(spts.items()):
        rows.append(
            {
                "api_name": api_name,
                "display_name": spt.get("displayName") or api_name,
                "data_type": _fmt_data_type(spt.get("dataType")),
                "description": spt.get("description") or "",
            }
        )
    return rows


def build_all_properties_rows(object_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten every property of every object type into one list, for a
    single scannable table/CSV instead of paging through 227 files."""
    rows = []
    for ot in object_types:
        for p in ot["properties"]:
            rows.append(
                {
                    "object_type": ot["api_name"],
                    "object_display_name": ot["display_name"],
                    "property_api_name": p["api_name"],
                    "property_display_name": p["display_name"],
                    "data_type": p["data_type"],
                    "is_primary_key": p["is_primary_key"],
                    "description": p["description"],
                }
            )
    return rows


def build_all_links_rows(object_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten every link of every object type into one list (one row per
    direction, as the API reports it) for a single scannable table/CSV."""
    rows = []
    for ot in object_types:
        for l in ot["links"]:
            rows.append(
                {
                    "source_object_type": ot["api_name"],
                    "link_api_name": l["api_name"],
                    "link_display_name": l["display_name"],
                    "target_object_type": l["target_object_type"],
                    "cardinality": l["cardinality"],
                    "status": l["status"],
                }
            )
    return rows


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    import csv

    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def generate(export_path: Path, out_dir: Path) -> None:
    data = load_export(export_path)
    full_metadata = data.get("full_metadata", {})
    object_types = build_object_type_rows(full_metadata)
    action_types = build_action_type_rows(full_metadata)
    interfaces = build_interface_rows(full_metadata)
    shared_properties = build_shared_property_rows(full_metadata)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "object-types").mkdir(exist_ok=True)

    env = _env()
    meta = {
        "ontology": data.get("ontology"),
        "hostname": data.get("hostname"),
        "exported_at": data.get("exported_at"),
        "n_object_types": len(object_types),
        "n_action_types": len(action_types),
        "n_interfaces": len(interfaces),
        "n_shared_properties": len(shared_properties),
        "n_link_types": sum(len(ot["links"]) for ot in object_types),
    }

    index_tpl = env.get_template("index.md.j2")
    (out_dir / "index.md").write_text(
        index_tpl.render(meta=meta, object_types=object_types, action_types=action_types)
    )

    ot_tpl = env.get_template("object_type.md.j2")
    for ot in object_types:
        (out_dir / "object-types" / f"{ot['api_name']}.md").write_text(
            ot_tpl.render(ot=ot, meta=meta)
        )

    actions_tpl = env.get_template("action_types.md.j2")
    (out_dir / "action-types.md").write_text(
        actions_tpl.render(action_types=action_types, meta=meta)
    )

    interfaces_tpl = env.get_template("interfaces.md.j2")
    (out_dir / "interfaces.md").write_text(
        interfaces_tpl.render(interfaces=interfaces, meta=meta)
    )

    spt_tpl = env.get_template("shared_properties.md.j2")
    (out_dir / "shared-property-types.md").write_text(
        spt_tpl.render(shared_properties=shared_properties, meta=meta)
    )

    all_properties = build_all_properties_rows(object_types)
    all_links = build_all_links_rows(object_types)

    all_props_tpl = env.get_template("all_properties.md.j2")
    (out_dir / "all-properties.md").write_text(
        all_props_tpl.render(rows=all_properties, meta=meta)
    )

    all_links_tpl = env.get_template("all_links.md.j2")
    (out_dir / "all-links.md").write_text(all_links_tpl.render(rows=all_links, meta=meta))

    _write_csv(all_properties, out_dir / "all-properties.csv")
    _write_csv(all_links, out_dir / "all-links.csv")

    print(
        f"Wrote docs to {out_dir}/ "
        f"({meta['n_object_types']} object types, {meta['n_action_types']} action types, "
        f"{meta['n_interfaces']} interfaces, {meta['n_shared_properties']} shared properties, "
        f"{len(all_properties)} properties total, {len(all_links)} links total)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", default="out/ontology_export.json")
    parser.add_argument("--out-dir", dest="out_dir", default="docs")
    args = parser.parse_args()
    generate(Path(args.in_path), Path(args.out_dir))


if __name__ == "__main__":
    main()
