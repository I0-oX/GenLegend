"""
The sheet snapshot: what a reader SEES on every Character's sheet, before and after.

The fingerprint (``verify_fingerprint.py``) guards what a Character IS: stats,
gear, training. It does not see the sheet's text. This gate does. It prints
every Character on the grid through the real sheet builder
(``app.components.character_sheet.character_sheet_data``), keeps only the
visible text, one line per block, and compares it with a saved copy.

The Player sheet travels as JSON now (the ``sheet_data`` the generate API
answers and ``<gl-sheetbody>`` paints), so ``Sheet_Lines`` walks that payload
in paint order instead of stripping tags. The slab document's own static
labels (``PARTICULARS``, ``SKILLS``, ``MEMENTO``, …) live in
``app/slab/sheetbody.slab`` and are outside this gate; NonPlayer sheets are
still HTML (``build_npc_sheet``), so they keep the tag-stripping reader.

Markup may change freely (a ``<b>`` becoming a ``<strong>``, a table becoming
a list); only a change a reader would notice shows up. That is what lets the
QST-0142 stations move text to Markdown and printers to new code while
proving the sheet reads the same.

Use
    PYTHONHASHSEED=0 FINGERPRINT_LEVELS=1,3,5,9,13,17,20 FINGERPRINT_SEEDS=1,2,3 \\
        .venv/bin/python scripts/verify_sheet_text.py --save /tmp/sheets.json
    ... change the code ...
    PYTHONHASHSEED=0 FINGERPRINT_LEVELS=1,3,5,9,13,17,20 FINGERPRINT_SEEDS=1,2,3 \\
        .venv/bin/python scripts/verify_sheet_text.py --check /tmp/sheets.json

The grid is the fingerprint's grid, read from the same two variables, plus
NonPlayer Characters at the same levels for ``SHEET_NONPLAYER_SEEDS``
(default 1 to 10), printed through ``build_npc_sheet``.
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any

from verify_fingerprint import Grid_Levels
from verify_fingerprint import Grid_Seeds
from verify_fingerprint import hush


# Tags that start a new line for a reader: blocks, rows, list items, breaks.
BLOCK_TAGS = re.compile(
        r"<\s*/?\s*(div|p|li|tr|td|th|h[1-6]|br|ul|ol|table|section|details|summary)\b[^>]*>",
        re.IGNORECASE,
        )
BLOCK_BREAK = "\u2029"
    #-- A paragraph separator no sheet text contains: marks where a block ends.
ANY_TAG = re.compile(
        r"<[^>]+>",
        )
SCRIPT_OR_STYLE = re.compile(
        r"<(script|style)\b.*?</\1\s*>",
        re.IGNORECASE | re.DOTALL,
        )


def Visible_Lines(
        page: str,
        ) -> list[str]:
    """The text a reader sees, one line per block, spaces collapsed."""
    text = SCRIPT_OR_STYLE.sub(
            "",
            page,
            )
    text = BLOCK_TAGS.sub(
            BLOCK_BREAK,
            text,
            )
    text = ANY_TAG.sub(
            "",
            text,
            )
    text = html.unescape(
            text
            )
    lines = []
    for raw in text.split(BLOCK_BREAK):
        line = " ".join(
                raw.split()
                )
            #-- As a browser does: newlines and tabs inside a block are
            #-- plain spaces; only a block tag starts a new line.
        if line:
            lines.append(
                    line
                    )
    return lines


def Sheet_Lines(
        sheet: dict,
        ) -> list[str]:
    """The payload's text, one line per block, in the order the slab paints.

    Every string a reader could read is visited in paint order: the header,
    the rail (chips, abilities, skills, saves, attacks, lists, spell work,
    known spells), then the sections and everything nested under them. Marks
    that are line art (``glyph``, ``symbol``) carry no text and are skipped,
    exactly as the sheet shows them.
    """
    lines: list[str] = []

    def add(
            text: object,
            ) -> None:
        line = " ".join(
                str(
                    text
                    ).split()
                )
        if line:
            lines.append(
                    line
                    )

    def add_runs(
            runs: Any,
            ) -> None:
        add(
            " ".join(
                str(
                    run.get(
                            "content"
                            ) or ""
                    )
                for run in runs or ()
                if isinstance(
                        run,
                        dict,
                        )
                )
            )

    def walk_entry(
            node: dict,
            ) -> None:
        add(
            node.get(
                    "name",
                    ""
                    )
            )
        add(
            node.get(
                    "sub",
                    ""
                    )
            )
        walk_block_body(
            node
            )
        for child in node.get(
                "entries",
                (),
                ):
            walk_entry(
                child
                )

    def walk_block_body(
            node: dict,
            ) -> None:
        for paragraph in (
                *node.get(
                    "flavor",
                    (),
                    ),
                *node.get(
                    "paras",
                    (),
                    ),
                *node.get(
                    "bullets",
                    (),
                    ),
                ):
            add_runs(
                paragraph.get(
                        "runs"
                        )
                )

    def walk_block(
            block: dict,
            ) -> None:
        add(
            block.get(
                    "heading",
                    ""
                    )
            )
        walk_block_body(
            block
            )
        for table in block.get(
                "tables",
                (),
                ):
            for row in table.get(
                    "rows",
                    (),
                    ):
                for cell in row.get(
                        "cells",
                        (),
                        ):
                    add_runs(
                        cell.get(
                                "runs"
                                )
                        )
        for note in block.get(
                "notes",
                (),
                ):
            add_runs(
                note.get(
                        "runs"
                        )
                )
        for child in block.get(
                "entries",
                (),
                ):
            walk_entry(
                child
                )

    add(
        sheet.get(
                "name",
                ""
                )
        )

    if sheet.get(
            "has_title"
            ):
        add(
            sheet.get(
                    "title"
                    )
            )

    for chip in sheet.get(
            "chips",
            (),
            ):
        add(
            chip.get(
                    "caption",
                    ""
                    )
            )
        add(
            chip.get(
                    "value",
                    ""
                    )
            )

    for score in sheet.get(
            "scores",
            (),
            ):
        add(
            f"{score.get('value', '')} {score.get('mod', '')}".strip( )
            )
        add(
            score.get(
                    "caption",
                    ""
                    )
            )

    for skill in sheet.get(
            "skills",
            (),
            ):
        add(
            " ".join(
                part
                for part in (
                    skill.get(
                            "name",
                            ""
                            ),
                    skill.get(
                            "attr",
                            ""
                            ),
                    skill.get(
                            "bonus",
                            ""
                            ),
                    )
                if part
                )
            )

    add(
        sheet.get(
                "passive",
                ""
                )
        )

    for saving_throw in sheet.get(
            "saves",
            (),
            ):
        add(
            f"{saving_throw.get('name', '')} "
            f"{saving_throw.get('bonus', '')}".strip( )
            )

    for attack in sheet.get(
            "attacks",
            (),
            ):
        add(
            " ".join(
                part
                for part in (
                    attack.get(
                            "name",
                            ""
                            ),
                    attack.get(
                            "base",
                            ""
                            ),
                    attack.get(
                            "prof",
                            ""
                            ),
                    )
                if part
                )
            )

    for group in sheet.get(
            "lists",
            (),
            ):
        add(
            group.get(
                    "title",
                    ""
                    )
            )
        for item in group.get(
                "items",
                (),
                ):
            add(
                item.get(
                        "body",
                        ""
                        )
                )

    for chip in sheet.get(
            "magic",
            (),
            ):
        add(
            chip.get(
                    "caption",
                    ""
                    )
            )
        add(
            chip.get(
                    "value",
                    ""
                    )
            )

    if sheet.get(
            "has_slots"
            ):
        add(
            sheet.get(
                    "slots_title"
                    )
            )
        for table in sheet.get(
                "slots",
                (),
                ):
            for row in table.get(
                    "rows",
                    (),
                    ):
                for cell in row.get(
                        "cells",
                        (),
                        ):
                    add_runs(
                        cell.get(
                                "runs"
                                )
                        )
        for note in sheet.get(
                "slot_notes",
                (),
                ):
            add_runs(
                note.get(
                        "runs"
                        )
                )

    for group in sheet.get(
            "spells",
            (),
            ):
        add(
            group.get(
                    "title",
                    ""
                    )
            )
        for item in group.get(
                "names",
                (),
                ):
            add(
                item.get(
                        "body",
                        ""
                        )
                )

    for section in sheet.get(
            "sections",
            (),
            ):
        add(
            section.get(
                    "numeral",
                    ""
                    )
            )
        add(
            section.get(
                    "title",
                    ""
                    )
            )
        for block in section.get(
                "blocks",
                (),
                ):
            walk_block(
                block
                )

    return lines


def Sheet_Of(
        guild: str,
        level: int,
        seed: int,
        ) -> list[str]:
    """One Character's sheet, as visible lines."""
    from AtlasActorLudi.Map_of_Character_Generation import summon_player
    from app.components import character_sheet_data

    with hush():
        character = summon_player(
                seed=seed,
                level=level,
                guild=guild,
                )
        sheet = character_sheet_data(
                character.to_dict( )
                )
    return Sheet_Lines(
            sheet
            )


def NonPlayer_Sheet_Of(
        level: int,
        seed: int,
        ) -> list[str]:
    """
    One NonPlayer Character's sheet, as visible lines.

    ``light=True``: a full NonPlayer cannot be summoned today (QST-0134
    finding 1, ``Grimoire_of_NPC.SetSize``), so the gate reads the light ones.
    """
    from AtlasActorLudi.AtlasAlusoris.Map_of_NonPlayer_Generation import (
            summon_nonplayer,
            )
    from app.components.npc_sheet import build_npc_sheet

    import app.random

    pin = f"nonplayer-{level}-{seed}"
    random.seed(
            pin
            )
    app.random.seed(
            pin
            )
        #-- Some NonPlayer text still draws from Python's shared generator or
        #-- from app.random's private one, instead of the Character's own
        #-- Dice.  Pin both so a sheet reads the same on every run.
    try:
        with hush():
            npc = summon_nonplayer(
                    level=level,
                    seed=seed,
                    light=True,
                    )
            page = str(
                    build_npc_sheet(
                            npc
                            )
                    )
    except Exception as error:
        return [
                f"SHEET FAILED: {type( error ).__name__}: {error}",
                ]
        #-- A failure is part of the picture: if it changes, the gate says so.
    return Visible_Lines(
            page
            )


def Sheet_Grid() -> dict[str, list[str]]:
    """Every Guild at every level for every seed, then NonPlayers on the same grid."""
    import app.main  # noqa: F401  (the sheet builder expects the app's setup)
    from AtlasLusoris.GuildKit import GUILDS

    grid = {}
    for guild in sorted(
            GUILDS
            ):
        for level in Grid_Levels():
            for seed in Grid_Seeds():
                key = f"{guild}-L{level}-s{seed}"
                grid[key] = Sheet_Of(
                        guild,
                        level,
                        seed,
                        )
    for level in Grid_Levels():
        for seed in NonPlayer_Seeds():
            key = f"NonPlayer-L{level}-s{seed}"
            grid[key] = NonPlayer_Sheet_Of(
                    level,
                    seed,
                    )
    return grid


def NonPlayer_Seeds() -> tuple[int, ...]:
    """NonPlayer seeds: more than for Players, since one seed picks everything."""
    setting = os.environ.get(
            "SHEET_NONPLAYER_SEEDS",
            "1,2,3,4,5,6,7,8,9,10",
            )
    return tuple(
            int(
                    piece
                    )
            for piece in setting.split(",")
            if piece.strip()
            )


def Save(
        path: Path,
        ) -> int:
    grid = Sheet_Grid()
    path.write_text(
            json.dumps(
                    grid,
                    indent=1,
                    ensure_ascii=False,
                    )
            )
    print(
            f"Saved {len(grid)} sheets to {path}"
            )
    return 0


def Check(
        path: Path,
        ) -> int:
    before = json.loads(
            path.read_text()
            )
    after = Sheet_Grid()
    changed = []
    for key in sorted(
            set(
                    before
                    ) | set(
                    after
                    )
            ):
        if before.get(key) != after.get(key):
            changed.append(
                    key
                    )
    if not changed:
        print(
                f"OK — {len(after)} sheets read the same as {path}"
                )
        return 0

    print(
            f"{len(changed)} SHEETS READ DIFFERENTLY against {path}:"
            )
    for key in changed[:12]:
        print(
                f"  ! {key}"
                )
        diff = difflib.unified_diff(
                before.get(key, []),
                after.get(key, []),
                lineterm="",
                n=0,
                )
        for line in list(diff)[2:14]:
            print(
                    f"      {line}"
                    )
    if len(changed) > 12:
        print(
                f"  … and {len(changed) - 12} more"
                )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
            description=__doc__.splitlines()[1],
            )
    mode = parser.add_mutually_exclusive_group(
            required=True,
            )
    mode.add_argument(
            "--save",
            type=Path,
            )
    mode.add_argument(
            "--check",
            type=Path,
            )
    arguments = parser.parse_args()
    if arguments.save is not None:
        return Save(
                arguments.save
                )
    return Check(
            arguments.check
            )


if __name__ == "__main__":
    sys.exit(
            main()
            )
