"""Sheet builders: the JSON payload the slab body reads, and the NPC page.

The API answers ``sheet_data`` — the JSON the slab sheet body declares —
so these build data, not routes. ``build_npc_sheet`` still renders the
NonPlayer page as HTML through ``shiny.ui``, which is why the ``shiny``
pin stays in requirements.
"""

from app.components.character_sheet import character_sheet_data
from app.components.npc_sheet import build_npc_sheet

__all__ = [
	"build_npc_sheet",
	"character_sheet_data",
	]