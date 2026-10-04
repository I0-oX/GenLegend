"""QST-0144: the Player generator — the whole ASGI application.

One entry point for every target (make run, Docker, Vercel, smoke): it
answers `/api/*` for the slab frontend, serves the site shell at `/`, serves
`/static/*` with revalidation, and redirects legacy `/character/…` share paths
onto the hash router.

The file name and the top-level name are load-bearing for Vercel: its Python
runtime detects entrypoints by file name (app.py, index.py, server.py,
main.py, wsgi.py, asgi.py — also inside app/) and loads the `app` variable,
while vercel.json's `functions` key configures that entry instead of
creating one. Renaming this module away from a detected name breaks deploys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from AtlasActorLudi import summon_player
from app.character_url import character_params_to_hash
from app.character_url import parse_character_params_from_hash
from app.character_url import parse_character_params_from_path
from app.choices import BACKGROUND_CHOICES
from app.choices import GUILD_CHOICES
from app.choices import SPECIALIZATIONS
from app.choices import SPECIES_CHOICES
from app.components import character_sheet_data
from app.parameters import clean_parameter
from app.parameters import parameters_from_data
from app.parameters import specialization_options

app = FastAPI(
        title="Gen Legend",
        version="1.0.0",
        description=(
            "The Player Character generator (QST-0144). The slab frontend "
            "reads the catalogues from `/api/choices` / "
            "`/api/specializations` and POSTs picks to "
            "`/api/character/generate`, which answers a canonical hash "
            "(the share URL) plus the character's `sheet_data`. The site "
            "shell, `/static` and legacy `/character/…` share links are "
            "served by the same app."
            ),
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        )

_ERROR_SCHEMA = {
        "type": "object",
        "properties": {
            "ok": {
                "type": "boolean",
                "const": False,
                },
            "error": {
                "type": "string",
                },
            },
        "required": ["ok", "error"],
        }

_GENERATE_REQUEST_SCHEMA = {
        "type": "object",
        "description": (
            "A character's picks. `hash` supplies a base that every explicit "
            "field below overrides, so `{\"hash\": \"…\"}` alone regenerates "
            "that exact character and `{\"seed\": 42}` alone rolls the rest."
            ),
        "properties": {
            "hash": {
                "type": "string",
                "description": (
                    "Canonical character hash: "
                    "`#/level/species/background/class/specialization/"
                    "gender/seed`."
                    ),
                },
            "species": {
                "type": "string",
                "description": "Species name, or `Random`.",
                },
            "char_class": {
                "type": "string",
                "description": "Guild (class) name, or `Random`.",
                },
            "specialization": {
                "type": "string",
                "description": "Specialization name, or `Random`.",
                },
            "background": {
                "type": "string",
                "description": "Background name, or `Random`.",
                },
            "gender": {
                "type": "string",
                "description": "Pronoun label, or `Random`.",
                },
            "level": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                },
            "seed": {
                "type": ["integer", "null"],
                "description": (
                    "`null` (or absent) rolls a fresh seed; an integer "
                    "replays byte-for-byte."
                    ),
                },
            },
        "additionalProperties": True,
        }

_GENERATE_RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "ok": {
                "type": "boolean",
                },
            "parameters": {
                "type": "object",
                "description": (
                    "The canonical, fully resolved character parameters."
                    ),
                "additionalProperties": True,
                },
            "hash": {
                "type": "string",
                "description": "Share hash (empty when no seed was kept).",
                },
            "sheet_data": {
                "type": "object",
                "description": (
                    "The character sheet as the slab body reads it: "
                    "`<gl-sheetbody>` params, field for field."
                    ),
                "additionalProperties": True,
                },
            "error": {
                "type": "string",
                "description": "Present when `ok` is false (engine refusal).",
                },
            },
        "required": ["ok"],
        }

_DIMENSION_FIELDS = (
        "species",
        "char_class",
        "specialization",
        "background",
        "gender",
        )


class _BadRequest(Exception):
    """Malformed request; answered with HTTP 422 and the contract's error shape."""


def _error(
        status: int,
        message: str,
        ) -> JSONResponse:
    return JSONResponse(
            status_code=status,
            content={
                "ok": False,
                "error": message,
                },
            )


def _base_from_body(
        body: dict[str, Any],
        ) -> dict[str, Any]:
    """Hash = base parameters; explicit body fields override it below."""
    if "hash" not in body:
        return {}
    hash_value = body["hash"]
    if not isinstance(
            hash_value,
            str,
            ):
        raise _BadRequest(
                "hash must be a string"
                )
    if not hash_value.strip():
        return {}
    parsed = parse_character_params_from_hash(
            hash_value
            )
    if parsed is None:
        raise _BadRequest(
                "hash did not parse to character parameters"
                )
    return parsed


def _dimension(
        body: dict[str, Any],
        key: str,
        base: dict[str, Any],
        ) -> str | None:
    if key not in body:
        return base.get(
                key
                )
    value = body[key]
    if value is None:
        return None
    if not isinstance(
            value,
            str,
            ):
        raise _BadRequest(
                f"{key} must be a string"
                )
    return clean_parameter(
            value
            )


def _level(
        body: dict[str, Any],
        base: dict[str, Any],
        ) -> int:
    if "level" not in body:
        return base.get(
                "level",
                1,
                )
    value = body["level"]
    if isinstance(
            value,
            bool,
            ) or not isinstance(
                    value,
                    int,
                    ):
        raise _BadRequest(
                "level must be an integer"
                )
    return max(
            1,
            min(
                    20,
                    value,
                    ),
            )


def _seed(
        body: dict[str, Any],
        base: dict[str, Any],
        ) -> int | None:
    if "seed" not in body:
        return base.get(
                "seed"
                )
    value = body["seed"]
    if value is None:
        return None
    if isinstance(
            value,
            bool,
            ) or not isinstance(
                    value,
                    int,
                    ):
        raise _BadRequest(
                "seed must be an integer or null"
                )
    return value


@app.get(
        "/api/choices",
        tags=["catalog"],
        )
def read_choices() -> dict[str, Any]:
    """Every option list the pickers show, with ``"Random"`` first."""
    return {
            "species": list(SPECIES_CHOICES),
            "guilds": list(GUILD_CHOICES),
            "backgrounds": list(BACKGROUND_CHOICES),
            "specializations": {
                guild: list(options)
                for guild, options in SPECIALIZATIONS.items()
                },
            }


@app.get(
        "/api/specializations",
        tags=["catalog"],
        responses={
            404: {
                "description": "Unknown guild.",
                "content": {
                    "application/json": {
                        "schema": _ERROR_SCHEMA,
                        },
                    },
                },
            },
        )
def read_specializations(
        guild: str | None = None,
        ):
    """Specialization options for one guild (mirrors the sheet's class watcher)."""
    if guild != "Random" and guild not in SPECIALIZATIONS:
        return _error(
                404,
                "unknown guild",
                )
    return {
            "guild": guild,
            "choices": list(
                    specialization_options(
                            SPECIALIZATIONS,
                            guild,
                            )
                    ),
            }


@app.post(
        "/api/character/generate",
        tags=["character"],
        openapi_extra={
            "requestBody": {
                "required": False,
                "content": {
                    "application/json": {
                        "schema": _GENERATE_REQUEST_SCHEMA,
                        },
                    },
                },
            },
        responses={
            200: {
                "description": (
                    "`ok: true` with the character (seeded requests replay "
                    "byte-for-byte); `ok: false` when the engine refuses the "
                    "combination — same card the frontend shows."
                    ),
                "content": {
                    "application/json": {
                        "schema": _GENERATE_RESPONSE_SCHEMA,
                        },
                    },
                },
            422: {
                "description": "Malformed body.",
                "content": {
                    "application/json": {
                        "schema": _ERROR_SCHEMA,
                        },
                    },
                },
            },
        )
async def post_generate(
        request: Request,
        ):
    """Generate (or regenerate, or re-level) a character and its sheet data.

    Body = a `hash` base plus/minus the explicit fields below. Level and seed
    ride along, so re-posting a hash at a new level re-levels the character.
    Malformed bodies answer `422 {ok:false, error}`; an engine refusal
    answers `200 {ok:false, error}`.
    """
    try:
        body = await request.json()
    except Exception:
        return _error(
                422,
                "body must be JSON",
                )
    if not isinstance(
            body,
            dict,
            ):
        return _error(
                422,
                "body must be a JSON object",
                )
    try:
        base = _base_from_body(body)
        parameters = dict(base)
        for key in _DIMENSION_FIELDS:
            parameters[key] = _dimension(body, key, base)
        parameters["level"] = _level(body, base)
        parameters["seed"] = _seed(body, base)
    except _BadRequest as error:
        return _error(
                422,
                str(error),
                )

    try:
        character = summon_player(
                species=parameters["species"],
                guild=parameters["char_class"],
                specialization=parameters["specialization"],
                background=parameters["background"],
                level=parameters["level"],
                gender=parameters["gender"],
                seed=parameters["seed"],
                )
        data = character.to_dict()
    except Exception as error:
        # Domain failure (bad combination, engine refusal): 200, ok=false —
        # the same surface the legacy UI shows in its fallback card.
        return {
                "ok": False,
                "error": str(error),
                }

    canonical = parameters_from_data(
            data,
            fallback=parameters,
            )
    hash_value = (
            character_params_to_hash(canonical)
            if canonical.get("seed") is not None
            else ""
            )
    return {
            "ok": True,
            "parameters": canonical,
            "hash": hash_value,
            "sheet_data": character_sheet_data(
                    data
                    ),
            }


class _RevalidateStaticFiles(StaticFiles):
    """`/static/*` with revalidation: rebuilt JS/CSS/slab modules must never
    be shadowed by a heuristically-cached copy (stale-asset phantom bugs)."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.mount(
        "/static",
        _RevalidateStaticFiles(
            directory=Path(
                __file__
                ).resolve().parent / "static",
            ),
        name="static",
        )


@app.get(
        "/",
        include_in_schema=False,
        )
def site_index() -> FileResponse:
    """The static Home shell."""
    return FileResponse(
        Path(
            __file__
            ).resolve().parent / "static" / "site" / "index.html",
        headers={
            # Never let a stale index.html point at yesterday's app.js.
            "Cache-Control": "no-cache, must-revalidate",
            },
        )


@app.get(
        "/character/{path:path}",
        include_in_schema=False,
        )
def character_link(path: str) -> RedirectResponse:
    """Legacy shareable links → the same character under the hash router."""
    params = parse_character_params_from_path(
            f"/character/{path}"
            )
    if params is None:
        return RedirectResponse(
                "/",
                status_code=302,
                )
    return RedirectResponse(
            "/" + character_params_to_hash(params),
            status_code=302,
            )


__all__ = (
        "app",
        )
