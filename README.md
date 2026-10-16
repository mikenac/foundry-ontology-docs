# foundry-ontology-docs

Generate polished PDF and SVG documentation from a live Palantir Foundry ontology export.

**What you get:**

- A **single-file PDF** — cover page with stats, grouped table of contents, per-object pages with properties, links, and embedded ERD relationship diagrams in crow's foot notation
- **Per-object SVG diagrams** — PlantUML ERD with crow's foot cardinality for every object type with links
- **Overview SVG** — force-directed graph of all 167+ connected objects
- **Markdown docs** — per-object pages, flattened property/link tables, action types

---

## Requirements

| Tool | Purpose | Install |
|------|---------|---------|
| Python ≥ 3.11 | Runtime | [python.org](https://python.org) |
| [uv](https://docs.astral.sh/uv/) | Package/venv manager | `brew install uv` |
| [PlantUML](https://plantuml.com) | ERD diagrams | `brew install plantuml` |
| [Graphviz](https://graphviz.org) | Overview graph | `brew install graphviz` |
| Cairo/Pango/GLib | WeasyPrint PDF rendering | `brew install cairo pango gdk-pixbuf libffi` |

> **macOS only note:** WeasyPrint needs native Cairo/Pango dylibs on the `DYLD_FALLBACK_LIBRARY_PATH`. The PDF generator sets this automatically.

---

## Quick start

```bash
# 1. Clone and install dependencies
git clone <repo-url>
cd foundry-ontology-docs
uv sync

# 2. Configure credentials and groups
cp .env.example .env
cp groups.example.json groups.json
$EDITOR .env          # fill in FOUNDRY_HOSTNAME, FOUNDRY_TOKEN, FOUNDRY_ONTOLOGY_RID
$EDITOR groups.json   # edit prefix → group mappings to match your ontology

# 3. Run the full pipeline
make
```

The generated PDF lands at `docs/ontology-documentation.pdf`.

---

## Configuration

All configuration lives in `.env` (gitignored — never commit real tokens):

```dotenv
FOUNDRY_HOSTNAME=your-instance.palantirfoundry.com
FOUNDRY_TOKEN=your_token_here
FOUNDRY_ONTOLOGY_RID=ri.ontology.main.ontology.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Copy `.env.example` for the full list of options including optional overrides.

### Finding your ontology RID

In **Ontology Manager → Settings**, or via the CLI:

```bash
uv run python -c "
from foundry_ontology_docs.export import build_client, _load_dotenv
_load_dotenv()
for o in build_client().ontologies.Ontology.list().data:
    print(o.rid, o.display_name)
"
```

---

## Make targets

```
make              # export → graphs → pdf  (default pipeline)
make all          # export → markdown docs → graphs → pdf
make export       # pull latest ontology data from Foundry
make graphs       # regenerate SVG diagrams only
make pdf          # regenerate PDF only (uses existing export)
make docs         # generate Markdown docs only
make clean        # remove out/ and docs/
make setup        # install/sync Python dependencies
make help         # show all targets and current variable values
```

Override variables on the command line:

```bash
make pdf EXPORT_PATH=out/my_export.json PDF_OUT=docs/my-ontology.pdf
```

---

## Domain grouping

Object types are grouped into domains for the table of contents and PDF sections. Groups are defined in **`groups.json`** (gitignored — copy from `groups.example.json`):

```json
[
  {
    "group": "Clinical / Patient",
    "prefixes": ["Patient", "Visit", "VitalSign", "Appointment"]
  },
  {
    "group": "HL7 Integration",
    "prefixes": ["Hl7", "HL7"]
  }
]
```

Rules are matched in order; the first matching prefix wins. Objects that match no prefix fall into **"Other"**. Use a completely different file by setting `FOUNDRY_GROUPS_CONFIG=/path/to/your-groups.json` in `.env`.

---

## Output files

All outputs are gitignored (they contain live tenant data):

| Path | Description |
|------|-------------|
| `out/ontology_export.json` | Raw Foundry API export (source of truth for all generators) |
| `docs/ontology-documentation.pdf` | Full documentation PDF |
| `docs/graph/overview.svg` | Force-directed overview of all connected objects |
| `docs/graph/<ObjectType>.svg` | Per-object ERD with crow's foot notation |
| `docs/object-types/<ObjectType>.md` | Per-object Markdown page |
| `docs/all-properties.{md,csv}` | Every property of every object, flattened |
| `docs/all-links.{md,csv}` | Every link between objects, flattened |
| `docs/action-types.md` | All action types with parameters |

---

## Architecture

```
src/foundry_ontology_docs/
├── export.py      # Calls Foundry Platform SDK → out/ontology_export.json
├── docgen.py      # Reshapes export JSON → Markdown via Jinja2 templates
├── graphgen.py    # PlantUML ERD diagrams (per-object) + Graphviz overview SVG
├── pdfgen.py      # Builds HTML from export JSON → WeasyPrint PDF
└── templates/     # Jinja2 .md.j2 templates for Markdown output
groups.json        # Domain grouping rules (prefix → group label)
```

**Key design decisions:**

- `pdfgen.py` generates HTML directly from the export JSON (not from Markdown) so internal PDF link annotations always resolve correctly
- PlantUML is used for per-object ERDs (proper crow's foot notation); Graphviz `sfdp` for the overview (handles 150+ nodes without hanging)
- Diagrams with >15 distinct link targets are generated as standalone SVGs but not embedded in the PDF (they're unreadable at page width with 25+ spokes)
- `.env` is loaded at runtime by a pure-stdlib parser — no `python-dotenv` dependency

---

## Notes

- `get_full_metadata` is a Public Beta Foundry API. It omits entities rather than failing on partial data — check the object/action counts against Ontology Manager
- Link types in the export appear nested inside each object type (`objectTypes.<name>.linkTypes[]`), not at the top level
- The `FOUNDRY_TOKEN` must have read access to the target ontology; a user token or a service account token both work
