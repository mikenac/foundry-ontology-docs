"""Export a Foundry ontology's full metadata via the Foundry Platform SDK.

Usage:
    uv run foundry-ontology-export [--ontology RID_OR_API_NAME] [--out PATH]

Auth/config comes from environment variables (see README):
    FOUNDRY_HOSTNAME        e.g. teletracking.palantirfoundry.com
    FOUNDRY_TOKEN           a Foundry user/service token
    FOUNDRY_ONTOLOGY_RID    default ontology identifier if --ontology omitted
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from foundry_sdk import FoundryClient, UserTokenAuth


def _load_dotenv() -> None:
    """Load .env from the repo root into os.environ (if present).
    Pure-stdlib implementation — no python-dotenv dependency required.
    Variables already set in the environment take precedence."""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_or_die(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"error: required environment variable {name} is not set", file=sys.stderr)
        sys.exit(1)
    return val


def build_client() -> FoundryClient:
    hostname = _env_or_die("FOUNDRY_HOSTNAME")
    token = _env_or_die("FOUNDRY_TOKEN")
    return FoundryClient(auth=UserTokenAuth(token=token), hostname=hostname)


def _to_jsonable(obj: Any) -> Any:
    """Best-effort conversion of SDK/pydantic models to plain JSON-safe data."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    # pydantic v2 models (foundry_sdk uses pydantic internally)
    if hasattr(obj, "model_dump"):
        return _to_jsonable(obj.model_dump(by_alias=True, exclude_none=False))
    if hasattr(obj, "dict"):
        return _to_jsonable(obj.dict())
    return str(obj)


def export_ontology(ontology: str, out_path: Path) -> Path:
    client = build_client()
    print(f"Fetching full metadata for ontology {ontology!r} ...", file=sys.stderr)
    metadata = client.ontologies.Ontology.get_full_metadata(ontology, preview=True)
    payload = {
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ontology": ontology,
        "hostname": os.environ.get("FOUNDRY_HOSTNAME"),
        "full_metadata": _to_jsonable(metadata),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    n_objects = len(payload["full_metadata"].get("objectTypes", {}) or {})
    n_links = len(payload["full_metadata"].get("linkTypes", {}) or {})
    n_actions = len(payload["full_metadata"].get("actionTypes", {}) or {})
    print(
        f"Wrote {out_path} "
        f"({n_objects} object types, {n_links} link types, {n_actions} action types)",
        file=sys.stderr,
    )
    return out_path


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ontology",
        default=os.environ.get("FOUNDRY_ONTOLOGY_RID"),
        help="Ontology RID or API name (default: $FOUNDRY_ONTOLOGY_RID)",
    )
    parser.add_argument(
        "--out",
        default="out/ontology_export.json",
        help="Output JSON path (default: out/ontology_export.json)",
    )
    args = parser.parse_args()

    if not args.ontology:
        print(
            "error: pass --ontology or set FOUNDRY_ONTOLOGY_RID",
            file=sys.stderr,
        )
        sys.exit(1)

    export_ontology(args.ontology, Path(args.out))


if __name__ == "__main__":
    main()
