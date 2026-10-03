"""The generator's choice catalogues — built once, shared by UI and JSON API.

`app.main` serves both the JSON routes and the site shell, so the composition
lives here instead of in the web layer.
"""

from __future__ import annotations

from AtlasActorLudi import character_choices
from AtlasActorLudi.AtlasAlusoris import nonplayer_choices

_character = character_choices()
_nonplayer = nonplayer_choices()

SPECIES_CHOICES = (
        "Random",
        *_character.species,
        )
GUILD_CHOICES = (
        "Random",
        *_character.guilds,
        )
BACKGROUND_CHOICES = (
        "Random",
        *_character.backgrounds,
        )
RACE_CHOICES = (
        "Random",
        *_nonplayer.races,
        )
NONPLAYER_GUILD_CHOICES = (
        "Random",
        *_nonplayer.guilds,
        )
NONPLAYER_BACKGROUND_CHOICES = (
        "Random",
        *_nonplayer.backgrounds,
        )
SPECIALIZATIONS = _character.specializations

__all__ = [
        "BACKGROUND_CHOICES",
        "GUILD_CHOICES",
        "NONPLAYER_BACKGROUND_CHOICES",
        "NONPLAYER_GUILD_CHOICES",
        "RACE_CHOICES",
        "SPECIALIZATIONS",
        "SPECIES_CHOICES",
        ]
