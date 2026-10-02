# Gen Legend: one door.
#   make run            serve app.main:app on $(PORT)      make dev   the same, reloading on edits
#   make smoke-player   boot and generate seed 42           make replay-player   the seeded-replay rite
#   make sweep-player   every Guild at levels 1 and 5 (add WIDE=1 for every level, Species, Background, Specialization)
#   make slab           recompile the Home generator face (pinned slab CLI)   make slab-check  prove the committed build is in sync
.PHONY: run dev setup smoke-player sweep-player replay-player verify-aasimar safepoint install-hooks loss-check slab slab-check loader-script

PORT ?= 8080
VENV := .venv
SHINY := $(VENV)/bin/shiny
PIP := $(VENV)/bin/pip
VENV_PYTHON := $(VENV)/bin/python
PYTHON := $(PYTHON_BIN)

ifeq ($(PYTHON),)
PYTHON := $(shell command -v python3.14 2>/dev/null || command -v python3.13 2>/dev/null || command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3.10 2>/dev/null || command -v python3 2>/dev/null)
endif

# Homebrew headers and libraries on Apple Silicon, for any dependency built from source.
ifneq ($(wildcard /opt/homebrew/include),)
export CPPFLAGS += -I/opt/homebrew/include
export LDFLAGS += -L/opt/homebrew/lib
endif

run: setup
	$(SHINY) run --port $(PORT) app.main:app

dev: setup
	$(SHINY) run --reload --port $(PORT) app.main:app

setup: $(SHINY)

$(SHINY):
	@test -n "$(PYTHON)" || (echo "Python 3.10+ not found (3.14 recommended: brew install python@3.14)." && exit 1)
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt

smoke-player: setup
	$(VENV_PYTHON) -c "import app.main; from AtlasActorLudi.Map_of_Character_Generation import summon_player; p = summon_player(seed=42, level=1); print('smoke-player OK', getattr(p, 'name', p))"
	$(VENV_PYTHON) -m AtlasVenustas.Charts_of_Printing
	$(VENV_PYTHON) -m AtlasActorLudi.Charts_of_Build

replay-player: setup
	$(VENV_PYTHON) scripts/verify_player_replay.py

# The Aasimar page is locked and owns its code.  This proves the code still
# agrees with it; if it fails, the page is right.
verify-aasimar: setup
	$(VENV_PYTHON) scripts/verify_aasimar_page.py

sweep-player: setup
	$(VENV_PYTHON) scripts/sweep_player.py $(if $(WIDE),--wide,)

safepoint:
	@chmod +x scripts/safepoint.sh
	@./scripts/safepoint.sh

install-hooks:
	@chmod +x scripts/install-git-hooks.sh scripts/git-hooks/pre-commit scripts/git-hooks/pre-push
	@./scripts/install-git-hooks.sh

loss-check:
	$(VENV_PYTHON) scripts/loss_detector.py --staged

# --- slab ------------------------------------------------------------------
# The frontend surfaces are authored in app/slab/*.slab — shell (header),
# footer, forge (the Home generator face), sheet (the character page) — and
# compiled with a PINNED CLI: slab is pre-alpha and its language and kernel
# change without notice, so an upgrade is a deliberate edit of SLAB_VERSION
# followed by `make slab` + `make smoke-player`. The generated modules and
# kernel WASM are committed under app/static/slab/, so no deploy (Cloud Run,
# Vercel, Actions) ever builds them. Needs `bun` on the machine that
# regenerates. Each document compiles to its own gl-<name> web component; the
# shared slab-runtime.js and kernel WASM are identical across documents.
SLAB_VERSION := 0.1.0
SLAB := bunx @stencil-hq/slab@$(SLAB_VERSION)
SLAB_OUT := app/static/slab
SLAB_DOCS := app/slab/shell.slab app/slab/footer.slab app/slab/forge.slab app/slab/sheet.slab app/slab/papiro.slab

slab:
	@for doc in $(SLAB_DOCS); do $(SLAB) check $$doc || exit 1; done
	@for doc in $(SLAB_DOCS); do \
		tag=$$(basename $$doc .slab); \
		$(SLAB) gen wc $$doc -o $(SLAB_OUT) --tag gl-$$tag || exit 1; \
	done

slab-check:
	@tmp=$$(mktemp -d); \
	for doc in $(SLAB_DOCS); do \
		tag=$$(basename $$doc .slab); \
		$(SLAB) gen wc $$doc -o $$tmp --tag gl-$$tag >/dev/null || { \
			echo "$$doc failed to generate"; rm -rf $$tmp; exit 1; \
		}; \
	done; \
	diff -r $$tmp $(SLAB_OUT) || { \
		echo "$(SLAB_OUT) is out of sync with $(SLAB_DOCS)"; \
		rm -rf $$tmp; exit 1; \
	}; \
	rm -rf $$tmp
	@echo "slab build is in sync with $(SLAB_DOCS)"

# The static site loads the summon loader as a file; the Shiny shell inlines
# the same script. Both come from loader_script(), so regenerating here keeps
# them identical.
loader-script:
	$(VENV_PYTHON) -c "import sys; sys.path.insert(0, '.'); from AtlasVenustas.Tools_of_Loader import loader_script; open('app/static/js/summon-loader.js', 'w').write('/* Summon loader for the static slab site.\n * Generated from AtlasVenustas/Tools_of_Loader.py loader_script() -\n * regenerate with make loader-script after editing the source.\n */\n' + loader_script() + '\n')"
