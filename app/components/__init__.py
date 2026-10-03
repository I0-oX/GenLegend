"""Presentation helpers for character-shaped sheets.

The API returns sheet HTML (``sheet_html``), so these build markup rather than
routes: they render through ``shiny.ui`` as their HTML DSL, which is why the
``shiny`` pin stays in requirements.
"""

from app.components.character_sheet import build_character_sheet
from app.components.npc_sheet import build_npc_sheet

__all__ = [
	"build_character_sheet",
	"build_npc_sheet",
	]
