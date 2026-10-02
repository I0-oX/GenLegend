"""Compose the Shiny frontline from pages, components, and Atlas APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shiny import App
from shiny import reactive
from shiny import render
from shiny import ui
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from AtlasActorLudi import summon_player
from AtlasActorLudi.AtlasAlusoris import summon_nonplayer
from AtlasActorLudi.AtlasAlusoris import summon_nonplayer_list
from AtlasPugna.Map_of_Legendary_Actions import Lair
from AtlasPugna.Map_of_Legendary_Actions import Legendary
from AtlasPugna.Map_of_Legendary_Actions import Region
from app.api import api
from app.character_url import character_params_to_hash
from app.character_url import parse_character_params_from_path
from app.choices import BACKGROUND_CHOICES
from app.choices import GUILD_CHOICES
from app.choices import NONPLAYER_BACKGROUND_CHOICES
from app.choices import NONPLAYER_GUILD_CHOICES
from app.choices import RACE_CHOICES
from app.choices import SPECIES_CHOICES
from app.client import Client_Messages
from app.components.shared import safe_int
from app.navigation import Navigator
from app.navigation import Page
from app.pages import alusoris_list_page_ui
from app.pages import alusoris_page_ui
from app.pages import home_page_ui
from app.pages import magistratum_page_ui
from app.pages import mount_alusoris_list_page
from app.pages import mount_alusoris_page
from app.pages import mount_magistratum_page
from app.pages import mount_player_page
from app.pages import player_page_ui
from app.routing import Shareable_Path_Redirect
from app.session import Session_State
from app.shell import app_ui

_PAGE_VIEWS = {
        Page.HOME: home_page_ui(
                SPECIES_CHOICES,
                GUILD_CHOICES,
                BACKGROUND_CHOICES,
                RACE_CHOICES,
                NONPLAYER_GUILD_CHOICES,
                NONPLAYER_BACKGROUND_CHOICES,
                ),
        Page.ACTOR_LUDI_PLAYER: player_page_ui(
                SPECIES_CHOICES,
                GUILD_CHOICES,
                BACKGROUND_CHOICES,
                ),
        Page.ACTOR_LUDI_ALUSORIS: alusoris_page_ui(
                RACE_CHOICES,
                NONPLAYER_BACKGROUND_CHOICES,
                ),
        Page.ACTOR_LUDI_ALUSORIS_LIST: alusoris_list_page_ui(),
        Page.MAGISTRATUM: magistratum_page_ui(),
        }


def server(
        input,
        output,
        session,
        ) -> None:
    state = Session_State.create()
    navigator = Navigator.create()
    client = Client_Messages(
            session
            )

    def open_nonplayer(
            character: Any,
            ) -> None:
        state.nonplayer.set(
                character
                )
        state.nonplayer_error.set(
                None
                )
        navigator.show(
                Page.ACTOR_LUDI_ALUSORIS
                )

    def send_url_hash(
            url_hash: str,
            ) -> None:
        client.send(
                "update_character_url",
                {
                    "hash": url_hash,
                    },
                )

    mount_player_page(
            input,
            output,
            session,
            state=state,
            navigator=navigator,
            client=client,
            summon_player=summon_player,
            species_choices=SPECIES_CHOICES,
            guild_choices=GUILD_CHOICES,
            specialization_choices=_character_choices.specializations,
            background_choices=BACKGROUND_CHOICES,
            )
    mount_alusoris_page(
            input,
            output,
            session,
            state=state,
            navigator=navigator,
            client=client,
            summon_nonplayer=summon_nonplayer,
            legendary_renderer=Legendary,
            lair_renderer=Lair,
            region_renderer=Region,
            )
    mount_alusoris_list_page(
            input,
            output,
            state=state,
            navigator=navigator,
            client=client,
            summon_nonplayer_list=summon_nonplayer_list,
            open_nonplayer=open_nonplayer,
            )
    mount_magistratum_page(
            input,
            output,
            session,
            show_page=navigator.show,
            set_loader=client.set_loader,
            send_url_hash=send_url_hash,
            summon_nonplayer=summon_nonplayer,
            open_nonplayer=open_nonplayer,
            safe_int=safe_int,
            )

    @reactive.effect
    @reactive.event(
            input.go_home
            )
    def open_home(
            ) -> None:
        navigator.show(
                Page.HOME
                )

    @output
    @render.ui
    def active_page(
            ):
        return _PAGE_VIEWS.get(
                navigator.current(),
                _PAGE_VIEWS[Page.HOME],
                )


_shiny_app = App(
        app_ui(),
        server,
        static_assets={
            "/static": Path(
                __file__
                ).resolve().parent / "static",
            },
        )

# The slab frontend owns the site shell: index.html (app/static/site/) plus
# the compiled components under app/static/slab/. Assets are served here so
# the published site never reaches the legacy app; /api/* was answered by
# app.api already; every other request falls through to the legacy Shiny
# frontline (parked NPC/DM surfaces and their routes) until it is retired.
app = api
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

app.mount(
        "/",
        Shareable_Path_Redirect(
                _shiny_app
                ),
        )

__all__ = (
        "app",
        "server",
        )
