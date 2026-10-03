"""QST-0144: the Player generator — the whole ASGI application.

One entry point for every target (make run, Docker, Vercel, smoke): it
answers `/api/*` for the slab frontend, serves the site shell at `/`, serves
`/static/*` with revalidation, and redirects legacy `/character/…` share paths
onto the hash router.
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
from app.components import build_character_sheet
from app.parameters import clean_parameter
from app.parameters import parameters_from_data
from app.parameters import specialization_options

app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        )

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
        "/api/choices"
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
        "/api/specializations"
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
        "/api/character/generate"
        )
async def post_generate(
        request: Request,
        ):
    """Generate (or regenerate, or re-level) a character and its sheet HTML."""
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
            "sheet_html": str(
                    build_character_sheet(data)
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
