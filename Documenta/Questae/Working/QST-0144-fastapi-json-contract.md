# QST-0144 — FastAPI JSON contract: Shiny reduced to an API

Status: **design** (contract-first, per Julio's call; no code until this is approved-in-session).
Decision record: backend = **FastAPI** (chosen over NiceGUI/FastHTML/naive ASGI: slab must own the DOM;
NiceGUI brings its own widget runtime, FastHTML keeps the server fighting over the DOM).

## Why

Julio: "reduce shiny a api json y ya esta … asi puedes usar slab". The Home face already proved
slab can be the UI; every remaining blocker (share ids, nav buttons, wrapper contracts, update_select
no-ops) exists because Shiny owns the DOM and the session. The endpoint below moves state out of the
Shiny session into request/response JSON so slab + vanilla JS can drive every Player surface.

## Endpoint contract (v1)

All responses `application/json; charset=utf-8`. No auth (public generator, same exposure as today).
Same-origin only — no CORS headers.

The contract also ships as OpenAPI 3.1: `GET /openapi.json` is the spec, and `GET /docs` is the one
UI over it (Swagger, interactive). The source is the route docstrings plus the `openapi_extra`
request/response schemas in `app/main.py`; `scripts/verify_player_api.py` stays the wire-shape proof.

### `GET /api/choices`

```json
{ "species": ["Random", "Aasimar", "..."],
  "guilds": ["Random", "Artificer", "..."],
  "backgrounds": ["Random", "..."],
  "specializations": { "Wizard": ["Abjuration", "..."] } }
```

Source: `character_choices()` — identical lists to `app/main.py:45-70` (incl. the `"Random"` first
entry every select shows today).

### `GET /api/specializations?guild=Wizard`

```json
{ "guild": "Wizard", "choices": ["Random", "Abjuration", "..."] }
```

- Unknown/absent guild → `404 {"ok": false, "error": "unknown guild"}` (mirrors
  `_specialization_options` returning `("Random",)` for no guild).
- Replaces `update_specialization_selector` + `ui.update_select` (`player.py:420-443`).

### `POST /api/character/generate`

Request — every field optional:

```json
{ "species": "Elf", "char_class": "Wizard", "specialization": "Illusionist",
  "background": "Sage", "gender": "He", "level": 3, "seed": 3175956810336926383,
  "hash": "#/3/Elf/Wizard/Illusionist/Sage/He/3175956810336926383" }
```

- `"Random"` / `null` / omitted → `None` sent to `summon_player` (today's `_selection_or_none`).
- `level`: int, clamped 1..20 (today's `safe_int` clamp in `player.py:381-390`).
- `hash`: optional restore path — parsed with `character_url.parse_character_params_from_hash`.
  Precedence: explicit body fields override hash fields (hash = base, tweak = override).
- Level up/down: no dedicated endpoint — client re-posts current `parameters` with `level ± 1`
  (seed travels along; mirrors `change_level`, `player.py:527-556`).

Success `200`:

```json
{ "ok": true,
  "parameters": { "species": "Elf", "char_class": "Wizard", "specialization": "Illusionist",
                  "background": "Sage", "gender": "He", "level": 3, "seed": 3175956810336926383 },
  "hash": "#/3/Elf/Wizard/Illusionist/Sage/He/3175956810336926383",
  "sheet_html": "<div class=\"…\">…</div>" }
```

- `parameters` = canonical form from `_parameters_from_data` (moved to a shiny-free
  `app/parameters.py` — it lives in `player.py` today, which imports `shiny`).
- `hash` = `character_params_to_hash(parameters)`; `""` when seed is null (today's `push_url` guard).
- `sheet_html` = `str(build_character_sheet(character.to_dict()))` — exactly what
  `character_result` renders now (`player.py:627-644`).
- Domain failure (summon raises): `200 {"ok": false, "error": "<str>"}` — mirrors
  `state.player_error` (`player.py:417`). Request malformed (wrong types): `422 {"ok": false, "error": …}`.

### Share-link migration

`GET /character/…` and `/character?…` keep resolving: port `Shareable_Path_Redirect` +
`character_url` parsing to a FastAPI route (`302 → /#/<compact>`, exact behavior confirmed from
`app/routing.py` during implementation). Existing shared links are a frozen contract — a replay
hash fixture must round-trip in the proof.

### Static / SPA

`GET /` (and any non-`/api`, non-`/character` GET) → static shell `app/static/site/index.html`;
the shell's hash router keeps today's `#/…` semantics.

## Client contract (slab + vanilla JS)

| today (Shiny) | after |
|---|---|
| `Shiny.setInputValue('btn_gen_char', …)` | `POST /api/character/generate` → inject `sheet_html` into `#character_result`, `location.hash = response.hash`, sync selectors/level from `response.parameters` |
| `ui.update_select(char_sheet_specialization, …)` | `GET /api/specializations?guild=…` rebuilds options |
| `change_level` + `render.text char_level_display` | re-POST generate with `level ± 1`; level text from `response.parameters.level` |
| `client.set_loader("show"/"hide")` custom message | loader class toggle around `fetch` (loaderMagic.js keeps its API) |
| `Shareable_Path_Redirect` + `character_url` JS | unchanged URL format; `buildShareUrl` builds from canonical `response.parameters` |

`shareable-links.js` DOM ids (`#btn_copy_char_link`, `#share-copy-status`) live in the static shell
again — its document-level delegation contract survives verbatim (that was the sheet-face blocker).

## Slab surfaces — which UI is built as `.slab`

The API has no UI; **every visible Player surface is a slab document** compiled with
`make slab` and embedded as a web component. The only "vanilla JS" left is the thin
bridge per element (`fetch` + router glue), same pattern as today's `app.js` bridge.

| surface | source | status |
|---|---|---|
| Home face (filter, 3 columns, Generate) | `app/slab/forge.slab` → `<gl-forge>` | **already shipped** — bridge swaps `setInputValue` for `POST /api/character/generate` |
| Sheet bar (4 selectors, level ±, Generate, Share, result frame) | `app/slab/sheet.slab` → `<gl-sheet>` | **phase 3, unlocked**: the old blockers (no-op `update_select`, shadow-DOM share ids) only existed because Shiny owned those inputs — with `/api` there is no input layer to fight |
| Chrome (header nav, footer, welcome) | `app/slab/shell.slab` → `<gl-shell>` or static render | phase 3 — nav buttons (`go_home`/`go_character`) become hash-route links |
| Sheet body | API `sheet_html` injected into the face's slot | v1 = HTML from `build_character_sheet`; later questa renders it in slab itself (needs shedding `shiny.ui` tags) |

Shiny contributes **zero** markup to the final DOM.

## Composition reuse (no duplicated logic)

| piece | today | API use |
|---|---|---|
| choices | `character_choices()` | `/api/choices` |
| generation | `summon_player` | `generate` |
| canonical params | `player.py:_parameters_from_data` → move to `app/parameters.py` | response `parameters` |
| hash format | `character_url.character_params_to_hash` | response `hash` |
| sheet HTML | `components.character_sheet.build_character_sheet` → `str()` | `sheet_html` |
| share redirect | `routing.Shareable_Path_Redirect` | `/character` route |

## Migration phases

1. **Contract** — this document (design-first, approved in session before code).
2. **Backend** — FastAPI becomes `app.main:app` (Makefile/README/Vercel keep that entry name).
   Mounts `/api`, `/static`, `/character`, shell; **transitional fallthrough** delegates every
   other request to the legacy Shiny ASGI so the site never goes dark mid-migration.
   Proof: `scripts/verify_player_api.py` — in-process ASGI calls: `/api/choices`,
   `POST generate` with `PLAYER_REQUEST` (seed 42) must match `verify_player_replay`'s identity
   fields, `/api/specializations?guild=Wizard`, share-hash round-trip. `make smoke-player` keeps
   passing (`import app.main` still works).
3. **Frontend** — static shell (home + character markup) + JS rewires (forge bridge, reforge bar,
   level, share, router) to `fetch`; browser-verify full flow: filter → pick → generate → sheet →
   level ± → share → restore-from-hash. Then the fallthrough is dead → deleted.
4. **Cutover proofs** — `make smoke-player` becomes boot + `POST generate` seed 42;
   `make replay-player` untouched (engine-level); README/Makefile/`vercel.json` updated.

## Non-goals (v1)

- NPC / DM Companion / Magistratum endpoints — parked chrome (`PLAYER_ONLY_PUBLISH`), restored
  later by adding their routes.
- No websockets/reactivity: request/response only. No auth, no rate limiting.

## Risks / open items

- `character_sheet.py` (~1900 lines) builds `shiny.ui.Tag`; v1 keeps `shiny` installed **as a tag
  library** (str()-rendered). Dropping the package entirely needs a later questa converting the
  sheet builder + `eldritch`/`symbols` to plain HTML — flagged, not v1.
- Old share URLs frozen: proof must include a replay-hash fixture (from `make replay-player`).
- `vercel.json` entry and `run_app_catch_errors.py` update in phase 2.
