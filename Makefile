# foundry-ontology-docs — task runner
#
# Copy .env.example → .env and fill in your credentials before running.
# All tasks use `uv run` so no manual venv activation is needed.
#
# Usage:
#   make            # export → graphs → pdf  (full pipeline)
#   make export     # pull latest ontology data from Foundry
#   make graphs     # regenerate SVG diagrams
#   make pdf        # regenerate PDF from current export
#   make docs       # generate Markdown docs
#   make all        # export → docs → graphs → pdf
#   make clean      # remove generated outputs (out/ and docs/)
#   make setup      # install dependencies via uv

# ── config ────────────────────────────────────────────────────────────────────
EXPORT_PATH   ?= out/ontology_export.json
GRAPH_DIR     ?= docs/graph
PDF_OUT       ?= docs/ontology-documentation.pdf
GROUPS_CONFIG ?= groups.json

# Do NOT -include .env here — the .env parser in export.py handles command
# substitutions like $(security ...) which make would misinterpret.
# Set FOUNDRY_HOSTNAME / FOUNDRY_ONTOLOGY_RID on the command line to override,
# or just let the Python tools read .env themselves.
FOUNDRY_HOSTNAME    ?=
FOUNDRY_ONTOLOGY_RID ?=

# ── targets ───────────────────────────────────────────────────────────────────

.DEFAULT_GOAL := pipeline

.PHONY: pipeline all export graphs pdf docs clean setup help

## Full pipeline: export → graphs → pdf
pipeline: export graphs pdf

## Full pipeline including Markdown docs
all: export docs graphs pdf

## Install / sync Python dependencies
setup:
	uv sync
	@if [ ! -f groups.json ]; then \
		cp groups.example.json groups.json; \
		echo "✅  Created groups.json from groups.example.json — edit it to match your ontology."; \
	fi

## Pull latest ontology metadata from Foundry into $(EXPORT_PATH)
export:
	uv run foundry-ontology-export --out "$(EXPORT_PATH)"

## Generate SVG relationship diagrams (overview + per-object ERDs)
graphs: $(EXPORT_PATH)
	uv run foundry-ontology-graphgen \
		--in "$(EXPORT_PATH)" \
		--out-dir "$(GRAPH_DIR)"

## Render the PDF documentation
pdf: $(EXPORT_PATH)
	uv run foundry-ontology-pdfgen \
		--in "$(EXPORT_PATH)" \
		--out "$(PDF_OUT)" \
		--graph-dir "$(GRAPH_DIR)"

## Generate Markdown documentation
docs: $(EXPORT_PATH)
	uv run foundry-ontology-docgen \
		--in "$(EXPORT_PATH)" \
		--out-dir docs

## Remove all generated outputs
clean:
	rm -rf out/ docs/

## Show this help
help:
	@echo ""
	@echo "  foundry-ontology-docs"
	@echo ""
	@grep -E '^##' Makefile | sed 's/^## /  /'
	@echo ""
	@echo "  Variables (override on command line or in .env):"
	@echo "    EXPORT_PATH=$(EXPORT_PATH)"
	@echo "    GRAPH_DIR=$(GRAPH_DIR)"
	@echo "    PDF_OUT=$(PDF_OUT)"
	@echo "    GROUPS_CONFIG=$(GROUPS_CONFIG)"
	@echo ""

# ── file deps ─────────────────────────────────────────────────────────────────
$(EXPORT_PATH):
	@echo "⚠️  $(EXPORT_PATH) not found — run 'make export' first."
	@exit 1
