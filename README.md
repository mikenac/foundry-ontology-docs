# foundry-ontology-docs

Exports a Foundry ontology's full metadata via the live Foundry Platform
Python SDK (`foundry-platform-sdk`, package `foundry_sdk`) and generates
browsable Markdown documentation from it.

Managed with `uv`.

## Setup

```bash
uv sync
```

Set credentials/config as environment variables (do not hardcode tokens):

```bash
export FOUNDRY_HOSTNAME=teletracking.palantirfoundry.com
export FOUNDRY_TOKEN="$(security find-generic-password -a "$USER" -s hermes-foundry-us-token -w)"
export FOUNDRY_ONTOLOGY_RID="ri.ontology.main.ontology.a5937116-b788-4690-aeb5-1a257846a8ff"  # default ontology to export
```

(On this machine, Foundry tokens live in macOS Keychain under
`hermes-foundry-us-token` / `hermes-foundry-uk-token` — see the
`macos-keychain-secrets` skill.)

To find other ontology RIDs/API names visible to your token:

```bash
uv run python -c "
from foundry_ontology_docs.export import build_client
c = build_client()
for o in c.ontologies.Ontology.list().data:
    print(o.rid, o.api_name, o.display_name)
"
```

## Usage

1. Export the ontology's full metadata to JSON:

   ```bash
   uv run foundry-ontology-export --ontology "$FOUNDRY_ONTOLOGY_RID" --out out/ontology_export.json
   ```

2. Generate Markdown docs from the export:

   ```bash
   uv run foundry-ontology-docgen --in out/ontology_export.json --out-dir docs
   ```

   Output:
   - `docs/index.md` — summary + object type index
   - `docs/object-types/<ApiName>.md` — one page per object type (properties, links)
   - `docs/action-types.md` — all action types with parameters and operations
   - `docs/interfaces.md` — interface types
   - `docs/shared-property-types.md` — shared property types

Both `out/` (raw export) and `docs/` (generated docs) are gitignored because
they contain live tenant data pulled straight from Foundry. Re-run the two
commands whenever you need a fresh snapshot.

## How it works

- `src/foundry_ontology_docs/export.py` calls
  `client.ontologies.Ontology.get_full_metadata(ontology, preview=True)` —
  the one Public-Beta endpoint that returns object types, link types, action
  types, query types, interfaces, and shared property types in a single
  call — and dumps it to JSON via pydantic's `model_dump`.
- `src/foundry_ontology_docs/docgen.py` reshapes that JSON into flat rows
  and renders Jinja2 templates (`src/foundry_ontology_docs/templates/*.md.j2`)
  into Markdown.

## Notes / known limitations

- `get_full_metadata` is Public Beta and documented to omit entities rather
  than fail the whole request, so very large ontologies may come back
  partial — check the counts the export script prints against what you
  expect in Ontology Manager.
- Link types in this export only ever appear nested under each object type
  (`objectTypes.<name>.linkTypes[]`), not as a separate top-level
  `linkTypes` map — `docgen.py` reads them from there.
- The real `[DEV] TeleTracking Development Ontology` export (227 object
  types / 1046 action types / 13 interfaces / 55 shared property types) was
  used to validate every template field name against the live API response
  shape, not a guessed schema.
