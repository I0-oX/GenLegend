"""The sheet's JSON shapes: the constructors both builders use.

`app/slab/sheetbody.slab` compiles to the web component that paints the
sheet; its `params` and `export`ed defs are the contract this module
builds against, field for field. Nothing here renders — it only assembles
the dicts the host passes to `setParam`, so a missing key is a blank the
reader can see and a stray key is a field the compiler never declared.
"""

from __future__ import annotations

from typing import Any

from AtlasVenustas.Charts_of_Printing import Icon_Name
from AtlasVenustas.Charts_of_Printing import Prose_Blocks
from AtlasVenustas.Charts_of_Printing import Prose_Runs

from app.components.shared import safe_str


def run(
        text: Any,
        *,
        bold: bool = False,
        ) -> dict:
    """One run: what it says and whether it says it loudly.

    Tabs, newlines and carriage returns become spaces — the sheet used to
    be HTML, where all three are a space anyway, and slab lays out a run
    by words; a literal tab would paint as a tab stop (a hole in the line).
    """
    content = safe_str(
            text,
            "",
            ).replace(
                    "\n",
                    " ",
                    ).replace(
                            "\t",
                            " ",
                            ).replace(
                                    "\r",
                                    " ",
                                    )

    return {
            "content": content,
            "bold": bool(
                    bold
                    ),
            }


def para(
        text: Any,
        *,
        bold: bool = False,
        ) -> dict:
    """One paragraph of plain text."""
    return {
            "runs": [
                run(
                        text,
                        bold=bold,
                        )
                ],
            }


def cell(
        text: Any,
        *,
        bold: bool = False,
        ) -> dict:
    """One table cell holding a single run."""
    return {
            "runs": [
                run(
                        text,
                        bold=bold,
                        ),
                ],
            }


def cell_runs(
        runs: list[dict],
        ) -> dict:
    """One table cell holding runs read out of trusted HTML."""
    return {
            "runs": _spaced(
                    runs
                    ),
            }


def runs_of(
        html: Any,
        ) -> list[dict]:
    """A blob of trusted HTML as one run list, for a cell or a title."""
    return _spaced(
            Prose_Runs(
                    safe_str(
                            html,
                            "",
                            )
                    )
            )


def _spaced(
        runs: list[dict],
        ) -> list[dict]:
    """Read runs back as words: HTML's whitespace was spaces all along."""
    cleaned: list[dict] = []

    for item in runs:
        content = safe_str(
                item.get(
                    "content",
                    "",
                    ),
                "",
                ).replace(
                        "\n",
                        " ",
                        ).replace(
                                "\t",
                                " ",
                                ).replace(
                                        "\r",
                                        " ",
                                        )

        if content and content.strip( ):
            cleaned.append(
                    {
                        "content": content,
                        "bold": bool(
                            item.get(
                                    "bold",
                                    False,
                                    )
                            ),
                        }
                    )
        elif content and cleaned:
            #-- A <br> run: keep the break as a space, on the words it
            #-- separated, instead of a run of its own.
            cleaned[ -1 ][ "content" ] += " "

    return cleaned


def _split_bold_head(
        runs: list[dict],
        ) -> tuple[dict | None, list[dict]]:
    """A leading bold sentence — `**The Long Memory.** Wherever…` — filed
    out as its own paragraph.

    slab 0.1.0 under-measures a bold run's advance (it lays the line out
    with the regular face and paints the bold one), so text following a
    bold headline would start inside it. Split, each paragraph runs a
    single face and the headline reads as a line of its own.
    """
    if len(
            runs
            ) > 1:
        first = runs[ 0 ]
        nxt = runs[ 1 ]
        if (
            first[ "bold" ]
            and first[ "content" ].rstrip( )[ -1: ] in ".!?"
            ):
            head = {
                "content": first[ "content" ].rstrip( ),
                "bold": True,
                }
            rest = [
                {
                    "content": nxt[ "content" ].lstrip( ),
                    "bold": nxt[ "bold" ],
                    },
                *runs[ 2: ],
                ]
            if rest[ 0 ][ "content" ]:
                return head, rest
    return None, runs


def split_prose(
        html: Any,
        ) -> tuple[list[dict], list[dict], list[dict]]:
    """A body of trusted HTML as (flavour paragraphs, paragraphs, bullets).

    slab 0.1.0 paints italic only whole, so a paragraph every word of which
    is italic — the flavour line under a feature's name — is filed apart and
    sent as `flavor`; everything else reads as prose, and a list becomes one
    bullet per item.
    """
    flavor: list[dict] = []
    paras: list[dict] = []
    bullets: list[dict] = []

    for block in Prose_Blocks(
            safe_str(
                html,
                "",
                )
            ):
        if block[ "kind" ] == "list":
            for item in block[ "items" ]:
                item_runs = _spaced(
                        item
                        )

                if item_runs:
                    bullets.append(
                            {
                                "runs": item_runs,
                                }
                            )
        elif block[ "italic" ]:
            runs = _spaced(
                    block[ "runs" ]
                    )

            if runs:
                flavor.append(
                        {
                            "runs": runs,
                            }
                        )
        else:
            runs = _spaced(
                    block[ "runs" ]
                    )
            head, rest = _split_bold_head(
                    runs
                    )

            if head is not None:
                paras.append(
                        {
                            "runs": [
                                head,
                                ],
                            }
                        )

            if rest:
                paras.append(
                        {
                            "runs": rest,
                            }
                        )

    return flavor, paras, bullets


# Emoji ranges the sheet refuses to paint: the marks are line art now, so a
# symbol that only exists as an emoji is dropped rather than shown.
_EMOJI_RANGES = (
        (0x1F000, 0x1FAFF),
        (0x2600, 0x26FF),
        (0x2B00, 0x2BFF),
        (0xFE0F, 0xFE0F),
        (0x200D, 0x200D),
        )


def _is_emoji(
        text: str,
        ) -> bool:
    return any(
            any(
                low <= ord(
                        char
                        ) <= high
                for low, high in _EMOJI_RANGES
                )
            for char in text
            )


def chip(
        emoji: str,
        caption: str,
        value: str,
        *,
        kind: str = "magic",
        show_mark: bool | None = None,
        ) -> dict:
    """One stat chip: its sigil (never the emoji it replaced), what it
    records, and what it says.

    A mark with line art becomes the sigil; any other non-emoji mark (a
    dingbat, a letter) stands as itself; an emoji is dropped, so the row
    reads as its caption and value alone.
    """
    glyph = Icon_Name(
            emoji
            )
    symbol = (
        ""
        if glyph or _is_emoji(
                emoji
                )
        else emoji
        )
    return {
            "glyph": glyph or "",
            "show_glyph": glyph is not None,
            "symbol": symbol,
            "caption": caption,
            "value": value,
            "kind": kind,
            "has_body": True,
            "show_mark": (
                bool(
                    glyph or symbol
                    )
                if show_mark is None
                else bool(
                        show_mark
                        )
                ),
            }


__all__ = [
    "cell",
    "cell_runs",
    "chip",
    "para",
    "run",
    "runs_of",
    "split_prose",
    ]
