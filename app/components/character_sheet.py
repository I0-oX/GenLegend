"""Sheet data for generated player-character sheets, read by <gl-sheetbody>."""

from __future__ import annotations

import json
import re
from typing import Any

from shiny import ui

from AtlasVenustas import Chip
from AtlasVenustas import Section
from AtlasVenustas.Charts_of_Printing import Icon_Name

from app.components.shared import Feature_Chip_Triples
from app.components.shared import safe_int
from app.components.shared import safe_str
from app.components.shared import space_feature_labels
from app.components.sheet_data import cell
from app.components.sheet_data import cell_runs
from app.components.sheet_data import chip
from app.components.sheet_data import para
from app.components.sheet_data import runs_of
from app.components.sheet_data import split_prose
from app.components.spellbook import ABILITY_NAMES
from app.components.spellbook import known_spells_groups
from app.components.spellbook import spell_slots_data
from app.components.spellbook import spellbook_block
from app.components.spellbook import spellcasting_chip_data


_ABILITY_EMOJI = {
    "Strength": "🦾",
    "Dexterity": "🥢",
    "Constitution": "🫀",
    "Intelligence": "🧩",
    "Wisdom": "🦉",
    "Charisma": "🎭",
    }

# Slot labels, read off GearKit's Loadout view. "Wearing" reads better than "Defense" for the body slot — what sits there is a garment, not a statistic. Empty slots are dropped rather than rendered as rows of "-".
_EQUIPMENT_FIELDS = (
    (
        "Wearing",
        "wearing",
        ),
    (
        "Off-hand",
        "offhand",
        ),
    (
        "Melee",
        "melee",
        ),
    (
        "Ranged",
        "ranged",
        ),
    (
        "Head",
        "headwear",
        ),
    (
        "Cloak",
        "cloak",
        ),
    (
        "Hands",
        "handwear",
        ),
    (
        "Feet",
        "footwear",
        ),
    )


def _creature_type_label(
        data: dict[str, Any],
        default: str = "Humanoid",
        ) -> str:
    explicit = safe_str(
            data.get(
                    "CreatureType",
                    "",
                    ),
            "",
            )

    if explicit:
        return explicit.replace(
                "_",
                " ",
                )

    for feature in data.get(
            "features",
            (),
            ) or ():
        if getattr(
                feature,
                "name",
                "",
                ) == "Creature Type":
            return (
                getattr(
                        feature,
                        "description",
                        default,
                        )
                or default
                )

    return default


def _build_chips(
        build: Any,
        ) -> list[Chip]:
    """The Chips the Character's Tags declare, read now (``Find_Build``)."""
    if build is None:
        return []
    return [
            built.chip
            for built in build.chips
            ]


def _chip_groups_in_rail_order(
        features: Any,
        build: Any,
        ) -> list[Any]:
    """
    The rail's chip groups, in order: Features before the Class section,
    then the Chips the build declares (the ported families), then the rest.

    That is where the Training chips stood while Training still wrote
    Features, so moving a family onto the build does not move its chips.
    """
    features = list(
            features or []
            )
    first_class = next(
            (
                    index
                    for index, current_feature in enumerate(
                            features
                            )
                    if _feature_place(
                            current_feature
                            )[ 0 ] == _SECTION_CLASS
                    ),
            len(
                    features
                    ),
            )
    before = [
            _feature_chips(
                    current_feature
                    )
            for current_feature in features[ :first_class ]
            ]
    after = [
            _feature_chips(
                    current_feature
                    )
            for current_feature in features[ first_class: ]
            ]
    return before + [ _build_chips( build ) ] + after


def _feature_chips(
        current_feature: Any,
        ) -> Any:
    chips = getattr(
            current_feature,
            "chips",
            None,
            )
    if chips is None and isinstance(
            current_feature,
            dict,
            ):
        chips = current_feature.get(
                "chips",
                )
    return chips


def _iter_feature_chips(
        features: Any,
        build: Any = None,
        ) -> list[tuple[str, str, str]]:
    """Collect Feature and build chips for the left rail (not the Entry body)."""
    pairs: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for chips in _chip_groups_in_rail_order(
            features,
            build,
            ):
        for key in Feature_Chip_Triples(
                chips
                ):
            if key in seen:
                continue
            seen.add(
                    key
                    )
            pairs.append(
                    key
                    )
    return pairs


# The sheet reads outward from what a Character *is* toward what they chose:
# the Species they were born, the Background they came up in and will not
# change, and last the Class they are still becoming.
#
# Each block opens with its own title-and-description entry and then its
# rules. Within Species and Background, the second number pins a fixed
# reading order (title, description, hook, entries); within Class there is
# only one part after the Guild's own description, and it is ordered purely
# by the level each lesson was gained — "all the entries organized by level."
# Where two entries land on the same (section, part, level), the sort is
# stable, so they keep the order they were created in.
_SECTION_SPECIES = 0
_SECTION_BACKGROUND = 1
_SECTION_CLASS = 2
_SECTION_OTHER = 3

# Checked as a prefix, in order, first match wins. A longer, more specific
# prefix ("Background Hook") must be listed before the shorter one it starts
# with ("Background"), or the shorter entry would claim it first.
_SOURCE_PLACES = (
    ("Species Feature", (_SECTION_SPECIES, 1)),
    ("Background Hook", (_SECTION_BACKGROUND, 1)),
    ("Secret Order", (_SECTION_BACKGROUND, 2)),
    ("Order Hook", (_SECTION_BACKGROUND, 3)),
    ("Origin Feat", (_SECTION_BACKGROUND, 4)),  # incl. "Origin Feat — X"
    ("Background Feat", (_SECTION_BACKGROUND, 4)),  # legacy Origin Feat path
    ("Background", (_SECTION_BACKGROUND, 0)),
    ("Guild", (_SECTION_CLASS, 0)),
    ("Training:", (_SECTION_CLASS, 1)),
    ("Class:", (_SECTION_CLASS, 1)),  # legacy pre-Guild class features
    ("Fighting Style", (_SECTION_CLASS, 1)),
    ("Weapon Mastery", (_SECTION_CLASS, 1)),
    ("Eldritch Invocation", (_SECTION_CLASS, 1)),
    ("Invocation", (_SECTION_CLASS, 1)),  # incl. "Invocation — <name>" grants
    ("Invocation", (_SECTION_CLASS, 1)),  # incl. "Invocation — <name>" grants
    ("Epic Boon", (_SECTION_CLASS, 1)),
    ("Feat", (_SECTION_CLASS, 1)),
    )


def _feature_place(
        current_feature: Any,
        ) -> tuple[int, int, int]:
    """Where one Feature sits on the sheet: section, part, then level."""
    source = safe_str(
            getattr(
                    current_feature,
                    "source",
                    "",
                    ),
            "",
            )
    level = int(
            getattr(
                    current_feature,
                    "level",
                    0,
                    )
            or 0
            )
    section, part = _SECTION_OTHER, 0

    for prefix, place in _SOURCE_PLACES:
        if source.startswith(
                prefix
                ):
            section, part = place
            break

    # A block's own description is level 0 and heads it; the rules follow in
    # the order they are gained, which is what a reader climbing levels wants.
    return (
        section,
        part,
        level,
        )


def _ordered_features(
        features: Any,
        ) -> list[Any]:
    """Species, then Background, then Class, each headed by its description."""
    return sorted(
            features or [],
            key=_feature_place,
            )


def _practice_markdown(
        practice: Any,
        ) -> str:
    """Project one structured Practice into flavour plus rules Markdown."""
    if isinstance(
            practice,
            dict,
            ):
        flavour = safe_str(
                practice.get(
                        "flavour",
                        "",
                        ),
                "",
                )
        sections = practice.get(
                "sections",
                (),
                ) or ()
    else:
        flavour = safe_str(
                getattr(
                        practice,
                        "flavour",
                        "",
                        ),
                "",
                )
        sections = getattr(
                practice,
                "sections",
                (),
                ) or ()

    paragraphs = []

    if flavour:
        paragraphs.append(
                f"*{flavour}*"
                )

    for section in sections:
        if isinstance(
                section,
                dict,
                ):
            title = safe_str(
                    section.get(
                            "title",
                            "",
                            ),
                    "",
                    )
            guidance = safe_str(
                    section.get(
                            "guidance",
                            "",
                            ),
                    "",
                    )
        else:
            title = safe_str(
                    getattr(
                            section,
                            "title",
                            "",
                            ),
                    "",
                    )
            guidance = safe_str(
                    getattr(
                            section,
                            "guidance",
                            "",
                            ),
                    "",
                    )

        if not title or not guidance:
            continue

        paragraphs.append(
                f"**{title.rstrip('.')}.** {guidance}"
                )

    return "\n\n".join(
            paragraphs
            )


def _feature_source(
        current_feature: Any,
        ) -> str:
    return safe_str(
            getattr(
                    current_feature,
                    "source",
                    "",
                    ),
            "",
            )


def _feature_name(
        current_feature: Any,
        ) -> str:
    return safe_str(
            getattr(
                    current_feature,
                    "name",
                    "",
                    ),
            "",
            )


def _feature_description(
        current_feature: Any,
        ) -> str:
    return safe_str(
            getattr(
                    current_feature,
                    "description",
                    "",
                    ),
            "",
            )


def _is_species_description(
        current_feature: Any,
        data: dict[str, Any],
        ) -> bool:
    name = _feature_name(
            current_feature
            ).casefold()
    species = safe_str(
            data.get(
                    "Species",
                    "",
                    ),
            "",
            ).casefold()
    heritage = safe_str(
            data.get(
                    "Heritage",
                    "",
                    ),
            "",
            ).casefold()
    identity = _species_identity(
            data
            ).casefold()

    return name in {
            species,
            heritage,
            identity,
            }


def _is_versatile_origin(
        current_feature: Any,
        ) -> bool:
    source = _feature_source(
            current_feature
            )
    return (
            source.startswith(
                    "Species Feature"
                    )
            and "Versatile" in source
            )


def _present(
        *nodes: Any | None,
        ) -> list[Any]:
    return [
            node
            for node in nodes
            if node is not None
            ]


_TOOL_MARKERS = (
    "Tools",
    "Kit",
    "Supplies",
    "Utensils",
    "Set",
    "Instrument",
    )


def _is_tool_proficiency(
        name: str,
        ) -> bool:
    # A tool is known by its catalog name ("Lute", "Dice Set"); the markers
    # still catch a kind the old sheet printed without naming one.
    from AtlasInventarium.ToolsKit import TOOLS

    return name in {
            tool.name
            for tool in TOOLS
            } or any(
            marker in name
            for marker in _TOOL_MARKERS
            )


def _tool_proficiency_names(
        data: dict[str, Any],
        ) -> list[str]:
    names = []
    seen: set[str] = set()

    for raw in data.get(
            "other_proficiencies"
            ) or []:
        name = safe_str(
                raw
                ).strip()

        if (
                not name
                or name in seen
                or not _is_tool_proficiency(
                        name
                        )
                ):
            continue

        seen.add(
                name
                )
        names.append(
                name
                )

    return names


def _combat_proficiency_names(
        data: dict[str, Any],
        ) -> list[str]:
    names = []

    for raw in data.get(
            "other_proficiencies"
            ) or []:
        name = safe_str(
                raw
                ).strip()

        if (
                name
                and not _is_tool_proficiency(
                        name
                        )
                ):
            names.append(
                    name
                    )

    return names


def _spell_branch_title(
        data: dict[str, Any],
        ) -> str:
    guild = safe_str(
            data.get(
                    "Class",
                    "",
                    ),
            "",
            )

    if guild.casefold() == "warlock":
        return "Pact Spells"

    return "Spells"


def _class_identity(
        data: dict[str, Any],
        ) -> str:
    """The Class branch names the guild, then the subclass if there is one."""
    guild = safe_str(
            data.get(
                    "Class",
                    "-",
                    ),
            "-",
            )
    subclass = safe_str(
            data.get(
                    "Subclass",
                    "",
                    ),
            "",
            )

    if not subclass or subclass == "-":
        return guild

    return f"{guild}, {subclass}"


def _split_described_layers(
        text: str,
        ) -> tuple[str, list[tuple[str, str]]]:
    """
    Split a composed Guild Describe() into the Guild's own prose and each
    named layer beneath it (``### Path of the Wild Heart``, ``### Archfey
    Patron``, …).
    """
    chunks = re.split(
            r"^### ",
            text.strip(),
            flags=re.MULTILINE,
            )
    if not chunks:
        return "", []

    lead = chunks[ 0 ].strip()
    layers: list[tuple[str, str]] = []

    for chunk in chunks[ 1: ]:
        heading, _, rest = chunk.partition(
                "\n"
                )
        title = heading.strip()
        body = rest.strip()

        if title and body:
            layers.append(
                    (
                            title,
                            body,
                            )
                    )

    return lead, layers


def _is_spellcasting_parameter_chip(
        label: str,
        ) -> bool:
    """Keep spell parameters in their one source-aware rail projection."""
    return label.endswith(
            (
                "Spellcasting Ability",
                "Spell Save DC",
                "Spell Attack Bonus",
                )
            )


def _species_identity(
        data: dict[str, Any],
        ) -> str:
    """Prefer a Heritage that already names its Species in plain language."""
    species = safe_str(
            data.get(
                    "Species",
                    "-",
                    )
            )
    heritage = safe_str(
            data.get(
                    "Heritage",
                    "",
                    ),
            "",
            )

    if not heritage:
        return species

    heritage_words = {
            word.casefold()
            for word in heritage.replace(
                    "-",
                    " ",
                    ).split()
            }

    if species.casefold() in heritage_words:
        return heritage

    return f"{species} ({heritage})"


def _class_heading(
        data: dict[str, Any],
        ) -> str:
    """``Covenantor (Warlock), Great Old One`` — the same string the header
    uses, shared so the Class section title never drifts from it."""
    class_title = safe_str(
            data.get(
                    "Class_Title"
                    )
            or data.get(
                    "Class",
                    "-",
                    ),
            "-",
            )
    subclass = safe_str(
            data.get(
                    "Subclass",
                    "",
                    ),
            "",
            )

    if not subclass or subclass == "-":
        return class_title

    return f"{class_title}, {subclass}"


# ---------------------------------------------------------------------------
# The sheet as data — what <gl-sheetbody> reads
# ---------------------------------------------------------------------------
# The sheet used to be built as shiny tags and rendered to HTML; it is now
# built as the JSON the slab body declares, so a reader sees the same words
# and the page looks like a page of a manuscript rather than a form.

# Each section of the main column opens with its own line-art sigil and a
# rubric numeral — no emoji anywhere on the sheet.
_SECTION_MARKS = {
        "Species": "beast-eye",
        "Background": "footprint",
        "Class": "crossed-swords",
        "Equipment": "black-hand-shield",
        "Backstory": "moon",
        }

_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII")

_ABILITY_ORDER = (
        "STR",
        "DEX",
        "CON",
        "INT",
        "WIS",
        "CHA",
        )

BUILD_RANK = 0
FEATURE_RANK = 1
    #-- At the same level, what the build declares prints before the
    #-- Features still written the old way: Guild Training was always granted
    #-- before the legacy class Progression filled its gaps.


def _signed(
        value: Any,
        ) -> str:
    """A modifier the way a reader writes one: ``+4``, not ``4``."""
    try:
        modifier = int(
                value
                )
    except Exception:
        return safe_str(
                value,
                "-",
                )

    return f"{modifier:+d}"


def _md_html(
        text: Any,
        ) -> str:
    """Markdown through shiny's own converter, so the words never drift."""
    return safe_str(
            ui.markdown(
                    safe_str(
                            text,
                            "",
                            )
                    ),
            "",
            )


def _heading(
        name: Any,
        ) -> str:
    """A feature name as a heading: the full stop a lead line took goes."""
    return safe_str(
            name,
            "",
            ).strip( ).rstrip(
                    "."
                    )


def _entry(
        name: str = "",
        *,
        sub: str = "",
        flavor: list[dict] | None = None,
        paras: list[dict] | None = None,
        bullets: list[dict] | None = None,
        entries: list[dict] | None = None,
        ) -> dict:
    """One node of a section: a heading if it has one, then what it says."""
    return {
            "name": name,
            "sub": sub,
            "flavor": flavor or [],
            "paras": paras or [],
            "bullets": bullets or [],
            "entries": entries or [],
            }


def _block(
        heading: str = "",
        *,
        flavor: list[dict] | None = None,
        paras: list[dict] | None = None,
        bullets: list[dict] | None = None,
        tables: list[dict] | None = None,
        notes: list[dict] | None = None,
        entries: list[dict] | None = None,
        seal: bool = False,
        ) -> dict:
    """One branch of a section: its heading, then its content in order."""
    return {
            "heading": heading,
            "flavor": flavor or [],
            "paras": paras or [],
            "bullets": bullets or [],
            "tables": tables or [],
            "notes": notes or [],
            "entries": entries or [],
            "seal": seal,
            }


def _section(
        title: str,
        blocks: list[dict],
        *,
        numeral: str = "",
        ) -> dict:
    """One column section: sigil, rubric numeral, title, then its blocks."""
    glyph = _SECTION_MARKS.get(
            title,
            "",
            )
    return {
            "glyph": glyph,
            "show_glyph": bool(
                    glyph
                    ),
            "numeral": numeral,
            "title": title,
            "blocks": blocks,
            }


def _prose_node(
        description: Any,
        ) -> dict | None:
    """Prose with no heading of its own — a nameless Entry."""
    flavor, paras, bullets = split_prose(
            _md_html(
                    description
                    )
            )

    if not (
            flavor
            or paras
            or bullets
            ):
        return None

    return _entry(
            flavor=flavor,
            paras=paras,
            bullets=bullets,
            )


def _feature_node(
        name: Any,
        description: Any,
        ) -> dict | None:
    """One feature as an Entry: its name, then the rules it grants."""
    node = _prose_node(
            space_feature_labels(
                    safe_str(
                            description,
                            "",
                            ).strip( )
                    )
            )

    if node is None:
        return None

    node[ "name" ] = _heading(
            name
            )

    return node


def _branch(
        title: str,
        children: list[Any],
        ) -> dict | None:
    """A titled branch as one Block, its children kept in the order given."""
    entries = [
        _entry_of(
            child
            )
        for child in _present(
                *children
                )
        ]

    if not entries:
        return None

    return _block(
            title,
            entries=entries,
            )


def _entry_of(
        node: dict,
        ) -> dict:
    """A nested branch read as an Entry, its heading as the name.

    A nested branch never carries a table or a note — those belong to the
    section's own blocks — so nothing of it is lost here.
    """
    if "name" in node:
        return node

    return _entry(
            safe_str(
                    node.get(
                            "heading",
                            "",
                            ),
                    "",
                    ),
            flavor=node.get(
                    "flavor",
                    [],
                    ),
            paras=node.get(
                    "paras",
                    [],
                    ),
            bullets=node.get(
                    "bullets",
                    [],
                    ),
            entries=node.get(
                    "entries",
                    [],
                    ),
            )


def _description_data(
        current_feature: Any,
        ) -> dict | None:
    """Identity prose, without repeating the section title as a lead line."""
    if _feature_name(
            current_feature
            ) == "Creature Type":
        return None

    description = _feature_description(
            current_feature
            ).strip( )

    if not description:
        return None

    return _prose_node(
            description
            )


def _feature_data(
        current_feature: Any,
        ) -> dict | None:
    """One Feature as an Entry, or None for a record with nothing to say."""
    name = getattr(
            current_feature,
            "name",
            None,
            )

    if name == "Creature Type":
        return None

    if not name:
        return _prose_node(
                str(
                    current_feature
                    )
                )

    description = safe_str(
            getattr(
                    current_feature,
                    "description",
                    "",
                    ),
            "",
            )

    # A Feature with a chip and no prose is a record, not an entry: its
    # chips were already collected by _iter_feature_chips.
    if not description.strip( ):
        return None

    return _feature_node(
            safe_str(
                name
                ),
            description,
            )


def _versatile_origin_data(
        current_feature: Any,
        ) -> list[dict]:
    """Human Versatile: the extra Origin Feat, named as a species rule."""
    name = _feature_name(
            current_feature
            )
    entries: list[dict] = []
    lead = _prose_node(
            "Humans have complex lives, and they adapt quickly.\n\n"
            f"You have this extra Origin Feat: **{name}**."
            )

    if lead is not None:
        entries.append(
                lead
                )

    rendered = _feature_data(
            current_feature
            )

    if rendered is not None:
        entries.append(
                rendered
                )

    return entries


def _guild_layers_data(
        tree: dict[str, list[Any]],
        current_feature: Any,
        ) -> None:
    """A Guild description split into its lead prose and its named layers."""
    lead, layers = _split_described_layers(
            _feature_description(
                    current_feature
                    )
            )

    if lead:
        node = _prose_node(
                lead
                )

        if node is not None:
            tree[ "class_description" ].append(
                    node
                    )

    for title, body in layers:
        branch = _branch(
                title,
                [
                    _prose_node(
                        body
                        ),
                    ],
                )

        if branch is not None:
            tree[ "class_layers" ].append(
                    branch
                    )


def _guild_build_data(
        build: Any,
        ) -> list[tuple]:
    """The Guild section's Entries from the build, placed by level."""
    if build is None:
        return []

    items: list[tuple] = []

    for order, built in enumerate(
            build.entries
            ):
        entry = built.entry

        if entry.section is not Section.GUILD:
            continue

        if not entry.rules.strip( ):
            continue

        node = _feature_node(
                entry.title,
                entry.rules,
                )

        if node is None:
            continue

        items.append(
                (
                    (
                        _SECTION_CLASS,
                        1,
                        entry.level or 0,
                        ),
                    BUILD_RANK,
                    order,
                    node,
                    )
                )

    return items


def _practice_entries_data(
        practices: Any,
        ) -> list[dict]:
    """Learned Practices as Entries, without pretending they are Features."""
    entries: list[dict] = []

    for practice in practices or ():
        title = safe_str(
                practice.get(
                        "title",
                        "",
                        )
                if isinstance(
                        practice,
                        dict,
                        )
                else getattr(
                        practice,
                        "title",
                        "",
                        ),
                "",
                )
        description = _practice_markdown(
                practice
                )

        if not title or not description:
            continue

        node = _feature_node(
                title,
                description,
                )

        if node is not None:
            entries.append(
                    node
                    )

    return entries


def _tool_branch_data(
        data: dict[str, Any],
        ) -> dict | None:
    """Tools and the Practices learned with them, under one branch."""
    names = _tool_proficiency_names(
            data
            )
    practices = _practice_entries_data(
            data.get(
                    "Practices",
                    (),
                    )
            )
    children: list[dict] = []

    if names:
        children.append(
                _entry(
                    bullets=[
                        para(
                            name
                            )
                        for name in names
                        ],
                    )
                )

    if practices:
        children.append(
                _entry(
                    "Practices",
                    entries=practices,
                    )
                )

    if not children:
        return None

    return _branch(
            "Tool Proficiencies",
            children,
            )


def _feature_tree_data(
        features: Any,
        data: dict[str, Any],
        ) -> dict[str, list[Any]]:
    """The same tree _feature_tree builds, as data nodes instead of tags."""
    tree: dict[str, list[Any]] = {
            "species_description": [],
            "species_features": [],
            "species_versatile": [],
            "background_description": [],
            "background_hook": [],
            "background_origin": [],
            "class_description": [],
            "class_layers": [],
            "class_levels": [],
            "class_invocations": [],
            }

    class_levels: list[tuple] = []

    for order, current_feature in enumerate(
            _ordered_features(
                    features
                    )
            ):
        source = _feature_source(
                current_feature
                )
        section = _feature_place(
                current_feature
                )[ 0 ]

        if section == _SECTION_SPECIES:
            if _is_versatile_origin(
                    current_feature
                    ):
                tree[ "species_versatile" ].extend(
                        _versatile_origin_data(
                                current_feature
                                )
                        )
                continue
            if _is_species_description(
                    current_feature,
                    data,
                    ):
                rendered = _description_data(
                        current_feature
                        )
                bucket = "species_description"
            else:
                rendered = _feature_data(
                        current_feature
                        )
                bucket = "species_features"
        elif section == _SECTION_BACKGROUND:
            if source.startswith(
                    "Background Hook"
                    ):
                rendered = _feature_data(
                        current_feature
                        )
                bucket = "background_hook"
            elif source.startswith(
                    (
                        "Origin Feat",
                        "Background Feat",
                        )
                    ):
                rendered = _feature_data(
                        current_feature
                        )
                bucket = "background_origin"
            else:
                rendered = _description_data(
                        current_feature
                        ) or _feature_data(
                        current_feature
                        )
                bucket = "background_description"
        else:
            if source.startswith(
                    "Guild"
                    ):
                _guild_layers_data(
                        tree,
                        current_feature,
                        )
                continue
            elif (
                    source.startswith(
                            "Eldritch Invocation"
                            )
                    or source.startswith(
                            "Invocation"
                            )
                    ):
                rendered = _feature_data(
                        current_feature
                        )
                bucket = "class_invocations"
            else:
                rendered = _feature_data(
                        current_feature
                        )
                bucket = "class_levels"

        if rendered is None:
            continue

        if bucket == "class_levels":
            class_levels.append(
                    (
                        _feature_place(
                                current_feature
                                ),
                        FEATURE_RANK,
                        order,
                        rendered,
                        )
                    )
            continue

        tree[ bucket ].append(
                rendered
                )

    class_levels.extend(
            _guild_build_data(
                    data.get(
                            "build"
                            )
                    )
            )
    class_levels.sort(
            key=lambda item: item[ :3 ]
            )
    tree[ "class_levels" ] = [
            item[ 3 ]
            for item in class_levels
            ]

    return tree


def _sections_data(
        data: dict[str, Any],
        raw_features: Any,
        spellcaster: Any,
        ) -> list[dict]:
    """Species, Background, Class, Equipment, Backstory — in that order."""
    tree = _feature_tree_data(
            raw_features,
            data,
            )
    species_name = _species_identity(
            data
            )
    background_name = safe_str(
            data.get(
                    "Background",
                    "-",
                    ),
            "-",
            )
    class_name = safe_str(
            data.get(
                    "Class",
                    "-",
                    ),
            "-",
            )
    class_children = _present(
            _branch(
                f"{class_name} Description",
                tree[ "class_description" ],
                ),
            *tree[ "class_layers" ],
            _branch(
                "Level features",
                tree[ "class_levels" ],
                ),
            _branch(
                "Invocations",
                tree[ "class_invocations" ],
                ),
            )

    if spellcaster is not None:
        spellbook = spellbook_block(
                spellcaster,
                title=_spell_branch_title(
                        data
                        ),
                )

        if spellbook is not None:
            class_children.append(
                    spellbook
                    )

    species_children = _present(
            *tree[ "species_description" ],
            *tree[ "species_versatile" ],
            *tree[ "species_features" ],
            )
    background_children = _present(
            _branch(
                "Description",
                tree[ "background_description" ],
                ),
            _branch(
                "Hook",
                tree[ "background_hook" ],
                ),
            _branch(
                "Origin Feat",
                tree[ "background_origin" ],
                ),
            _tool_branch_data(
                data
                ),
            )

    parts: list[tuple[str, list[dict]]] = [
            (
                species_name,
                [_block(entries=species_children)] if species_children else [],
                ),
            (
                background_name,
                background_children,
                ),
            (
                _class_identity(
                    data
                    ),
                class_children,
                ),
            ]

    equipment = data.get(
            "equipment"
            )

    if equipment is not None:
        equipment_blocks = _equipment_blocks_data(
                equipment
                )

        if equipment_blocks:
            parts.append(
                    (
                        "Equipment",
                        equipment_blocks,
                        )
                    )

    story = _prose_node(
            data.get(
                    "Story",
                    "",
                    )
            ) or _prose_node(
            "—"
            )
    parts.append(
            (
                "Backstory",
                [_block(entries=[story])] if story else [],
                )
            )

    return [
        _section(
            title,
            blocks,
            numeral=(
                _ROMAN[ index ]
                if index < len(
                        _ROMAN
                        )
                else ""
                ),
            )
        for index, (title, blocks) in enumerate(
                parts
                )
        if blocks
        ]


def _equipment_blocks_data(
        equipment: Any,
        ) -> list[dict]:
    """What the Character wears, carries and keeps, in reading order."""
    blocks: list[dict] = []
    rows: list[dict] = []

    for label, attribute in _EQUIPMENT_FIELDS:
        item = getattr(
                equipment,
                attribute,
                None,
                )

        if item is None:
            continue

        rows.append(
                {
                    "cells": [
                        cell(
                            label
                            ),
                        cell_runs(
                            runs_of(
                                safe_str(
                                    item
                                    )
                                )
                            ),
                        ],
                    }
                )

    # Jewelry is the one slot that holds several at once.
    for worn in getattr(
            equipment,
            "jewelry",
            [],
            ) or []:
        rows.append(
                {
                    "cells": [
                        cell(
                            "Jewelry"
                            ),
                        cell_runs(
                            runs_of(
                                safe_str(
                                    worn
                                    )
                                )
                            ),
                        ],
                    }
                )

    if rows:
        blocks.append(
                _block(
                    "Equipment",
                    tables=[
                        {
                            "rows": rows,
                            },
                        ],
                    )
                )

    bag_rows = [
        {
            "cells": [
                cell(
                    safe_str(
                        # `called` prefers an earned title
                        # ("Club of Wounding") over the plain name.
                        getattr(
                                item,
                                "called",
                                None,
                                )
                        or getattr(
                                item,
                                "name",
                                "item",
                                )
                        )
                    ),
                cell(
                    f"x{safe_str(getattr(item, 'quantity', 1))}"
                    ),
                cell(
                    f"{safe_str(getattr(item, 'weight', 0))} lbs"
                    ),
                cell(
                    f"{safe_str(getattr(item, 'value', 0))} gp"
                    ),
                ],
            }
        for item in getattr(
                equipment,
                "bag",
                [],
                ) or []
        ]
    purse = para(
            (
                "Purse: "
                f"{safe_str(getattr(equipment, 'purse', '-'))} gp"
                )
            )

    if bag_rows:
        blocks.append(
                _block(
                    "Bag",
                    tables=[
                        {
                            "rows": bag_rows,
                            },
                        ],
                    notes=[purse],
                    )
                )
    elif purse:
        blocks.append(
                _block(
                    notes=[purse],
                    )
                )

    return blocks


def _stat_chip_data(
        data: dict[str, Any],
        ) -> list[dict]:
    """The rail's particulars: what a player checks before the fight."""
    rows = [
            (
                "⚖️",
                "Alignment",
                data.get(
                        "Alignment",
                        "-",
                        ),
                ),
            (
                "👤",
                "Creature Type",
                _creature_type_label(
                        data
                        ),
                ),
            (
                "⚧",
                "Gender",
                data.get(
                        "Gender",
                        "-",
                        ),
                ),
            (
                "🧑‍🧒",
                "Size",
                data.get(
                        "size",
                        "-",
                        ),
                ),
            (
                "👞",
                "Speed",
                data.get(
                        "Speed",
                        "-",
                        ),
                ),
            (
                "🏵️",
                "Level",
                data.get(
                        "Level",
                        "-",
                        ),
                ),
            (
                "⚜️",
                "Proficiency Bonus",
                f"+{safe_str(data.get('PB', '-'))}",
                ),
            (
                # The number is the ceiling, not the current pool — say so, or
                # a reader takes it for how much the Character has left.
                "💚",
                "Max Hit Points",
                data.get(
                        "Health",
                        "-",
                        ),
                ),
            (
                "🖤",
                "Hit Dice",
                data.get(
                        "HPD",
                        "-",
                        ),
                ),
            (
                "🛡️",
                "Armor Class",
                data.get(
                        "AC",
                        "-",
                        ),
                ),
            ]
    chips = [
        chip(
            symbol,
            label,
            safe_str(
                value
                ),
            kind="stat",
            )
        for symbol, label, value in rows
        ]

    for symbol, label, value in _iter_feature_chips(
            data.get(
                    "features"
                    ),
            data.get(
                    "build"
                    ),
            ):
        if _is_spellcasting_parameter_chip(
                label
                ):
            continue

        chips.append(
                chip(
                    symbol,
                    label,
                    safe_str(
                        value
                        ),
                    kind="stat",
                    )
                )

    return chips


def _score_data(
        stats: Any,
        ) -> list[dict]:
    """The six abilities as a roll: sigil, score, modifier, name."""
    scores: list[dict] = []

    for stat, value in (
            stats or {}
            ).items( ):
        score = safe_int(
                value,
                10,
                )
        modifier = (
            score - 10
            ) // 2
        glyph = Icon_Name(
                _ABILITY_EMOJI.get(
                        safe_str(
                            stat
                            ),
                        "",
                        )
                )
        scores.append(
                {
                    "glyph": glyph or "",
                    "caption": safe_str(
                            stat
                            ),
                    "value": safe_str(
                            score
                            ),
                    "mod": f"{modifier:+d}",
                    }
                )

    return scores


def _skill_data(
        data: dict[str, Any],
        ) -> list[dict]:
    """The skills table as rows: name, ability, bonus, and how trained."""
    skills = data.get(
            "Skills"
            )

    if not hasattr(
            skills,
            "list",
            ):
        return []

    rows: list[dict] = []

    try:
        for skill, label in skills.list:
            ability = re.search(
                    r"\(([A-Z]{3})\)",
                    safe_str(
                            label
                            ),
                    )
            level = safe_int(
                    getattr(
                            skill,
                            "proficiency_level",
                            0,
                            ),
                    0,
                    )
            rows.append(
                    {
                        "name": safe_str(
                            getattr(
                                    skill,
                                    "name",
                                    label,
                                    )
                            ),
                        "attr": (
                            ability.group(
                                1
                                )
                            if ability
                            else ""
                            ),
                        "bonus": _signed(
                            skill.calculate_modifier( )
                            if hasattr(
                                    skill,
                                    "calculate_modifier",
                                    )
                            else 0
                            ),
                        "prof": level >= 1,
                        "expert": level >= 2,
                        }
                    )
    except Exception:
        return []

    return rows


def _save_data(
        data: dict[str, Any],
        ) -> list[dict]:
    """The six saving throws as rows, with the trained ones marked."""
    saving_throws = data.get(
            "SavingThrow"
            )

    if saving_throws is None:
        return []

    trained = getattr(
            saving_throws,
            "proficiency",
            {},
            ) or {}
    rows: list[dict] = []

    for abbreviation in _ABILITY_ORDER:
        value = getattr(
                saving_throws,
                abbreviation,
                None,
                )

        if value is None:
            continue

        rows.append(
                {
                    "name": ABILITY_NAMES.get(
                            abbreviation,
                            abbreviation,
                            ),
                    "bonus": _signed(
                            value
                            ),
                    "prof": bool(
                        trained.get(
                                abbreviation,
                                False,
                                )
                        ),
                    "expert": False,
                    }
                )

    return rows


def _attack_data(
        data: dict[str, Any],
        ) -> list[dict]:
    """Attack rolls as rows: the ability, what it adds, the total."""
    attack_rolls = data.get(
            "AttackRolls"
            )

    if attack_rolls is None:
        return []

    rows: list[dict] = []

    for abbreviation in getattr(
            attack_rolls,
            "ABILITIES",
            _ABILITY_ORDER,
            ):
        base = getattr(
                attack_rolls,
                f"{abbreviation}_base",
                None,
                )
        proficient = getattr(
                attack_rolls,
                f"{abbreviation}_prof",
                None,
                )

        if base is None or proficient is None:
            continue

        rows.append(
                {
                    "name": abbreviation,
                    "base": _signed(
                            base
                            ),
                    "prof": _signed(
                            proficient
                            ),
                    }
                )

    return rows


def _language_names(
        languages: Any,
        ) -> list[str]:
    """Languages as plain names, however the model spells them."""
    if languages is None:
        return []

    langs = getattr(
            languages,
            "langs",
            None,
            )

    if langs:
        return [
            safe_str(
                name
                )
            for name in sorted(
                    langs
                    )
            ]

    body = (
        languages.AsListHTML( )
        if hasattr(
                languages,
                "AsListHTML",
                )
        else safe_str(
                languages,
                "",
                )
        )
    names = [
        line.strip( )
        for line in re.split(
                r"<br\s*/?>|,",
                re.sub(
                        r"<[^>]+>",
                        "",
                        safe_str(
                                body,
                                "",
                                ),
                        ),
                )
        if line.strip( )
        ]

    return names


def _list_data(
        data: dict[str, Any],
        ) -> list[dict]:
    """Proficiencies, Tools and Languages as titled lists in the rail."""
    groups = [
            (
                "Proficiencies",
                _combat_proficiency_names(
                    data
                    ),
                ),
            (
                "Tools",
                _tool_proficiency_names(
                    data
                    ),
                ),
            (
                "Languages",
                _language_names(
                    data.get(
                            "Languages"
                            )
                    ),
                ),
            ]

    return [
        {
            "title": title,
            "items": [
                {
                    "body": safe_str(
                        name
                        ),
                    }
                for name in names
                ],
            }
        for title, names in groups
        if names
        ]


def _decorate(
        node: dict,
        ) -> None:
    """Ship the bools slab's `when` reads, beside what they guard.

    `when` takes a name and only understands bools, so an entry that has a
    name says so (`has_name`), a block that has a heading says so
    (`has_heading`). Decorating once, from the built tree, means no builder
    can forget one and leave a heading unpainted — or paint an empty line.
    """
    if "numeral" in node:
        node[ "has_numeral" ] = bool(
                safe_str(
                    node.get(
                            "numeral",
                            "",
                            ),
                    "",
                    )
                )

    if "heading" in node:
        node[ "has_heading" ] = bool(
                safe_str(
                    node.get(
                            "heading",
                            "",
                            ),
                    "",
                    ).strip( )
                )

    #-- Every list a slab `when` guards ships its own emptiness flag, so a
    #-- mixed block/entry still reads top-down: slab paints unconditional
    #-- children before conditional ones.
    for key, flag in (
            ( "flavor", "has_flavor" ),
            ( "paras", "has_paras" ),
            ( "bullets", "has_bullets" ),
            ( "tables", "has_tables" ),
            ( "notes", "has_notes" ),
            ( "entries", "has_children" ),
            ):
        if key in node:
            node[ flag ] = bool(
                    node.get(
                        key,
                        (),
                        )
                    )

    if "blocks" in node:
        #-- A section: its title rides the rubric row beside the numeral.
        node[ "show_title" ] = True

    if "name" in node:
        node[ "has_name" ] = bool(
                safe_str(
                    node.get(
                            "name",
                            "",
                            ),
                    "",
                    ).strip( )
                )
        node[ "has_sub" ] = bool(
                safe_str(
                    node.get(
                            "sub",
                            "",
                            ),
                    "",
                    ).strip( )
                )

    for child in node.get(
            "entries",
            (),
            ):
        _decorate(
            child
            )

    for child in node.get(
            "blocks",
            (),
            ):
        _decorate(
            child
            )


def character_sheet_data(
        data: dict[str, Any],
        ) -> dict:
    """The whole sheet as the JSON <gl-sheetbody> reads.

    Every key here is a param the slab document declares; a key that is not
    declared is a field no one paints, and a key missing is a blank a reader
    would see.
    """
    stats = data.get(
            "Stats"
            ) or {}
    spellcaster = data.get(
            "Spellcaster"
            )
    raw_features = data.get(
            "features",
            [],
            )
    chips = _stat_chip_data(
            data
            )
    scores = _score_data(
            stats
            )
    skills = _skill_data(
            data
            )
    saves = _save_data(
            data
            )
    attacks = _attack_data(
            data
            )
    lists = _list_data(
            data
            )
    magic = (
        spellcasting_chip_data(
                spellcaster
                )
        if spellcaster is not None
        else []
        )
    slots = (
        spell_slots_data(
                spellcaster
                )
        if spellcaster is not None
        else None
        )
    spells = (
        known_spells_groups(
                spellcaster
                )
        if spellcaster is not None
        else []
        )
    sections = _sections_data(
            data,
            raw_features,
            spellcaster,
            )

    for section in sections:
        _decorate(
            section
            )
    title = safe_str(
            data.get(
                    "title",
                    "",
                    ),
            "",
            )

    return {
            "name": safe_str(
                    data.get(
                            "name",
                            "-",
                            ),
                    "-",
                    ),
            "has_name": bool(
                    safe_str(
                        data.get(
                            "name",
                            "-",
                            ),
                        "-",
                        ).strip( )
                    ),
            "title": title,
            "has_title": bool(
                    title.strip( )
                    ),
            "show_seal": True,
            "has_chips": bool(
                    chips
                    ),
            "has_scores": bool(
                    scores
                    ),
            "has_skills": bool(
                    skills
                    ),
            "has_saves": bool(
                    saves
                    ),
            "has_attacks": bool(
                    attacks
                    ),
            "has_lists": bool(
                    lists
                    ),
            "has_magic": bool(
                    magic
                    ),
            "has_slots": slots is not None,
            "has_spells": bool(
                    spells
                    ),
            "chips": chips,
            "scores": scores,
            "skills": skills,
            "passive": (
                "Passive Perception: "
                f"{safe_str(data.get('passive_perception', '-'))}"
                ),
            "saves": saves,
            "attacks": attacks,
            "lists": lists,
            "magic": magic,
            "slots": (
                [
                    slots[ "table" ],
                    ]
                if slots
                else []
                ),
            "slots_title": (
                slots[ "title" ]
                if slots
                else "SPELL SLOTS"
                ),
            "slot_notes": (
                slots[ "notes" ]
                if slots
                else []
                ),
            "spells": spells,
            "sections": sections,
            }


__all__ = [
    "character_sheet_data",
    ]


def _test_generated_practices() -> None:
    """A trained Tool projects exactly one rendered Practice Entry."""
    from contextlib import redirect_stdout
    from io import StringIO

    from AtlasActorLudi.Map_of_Character_Generation import summon_player

    fixtures = (
        (
            "Charlatan",
            700,
            "Forgery Kit Proficiency",
            "Power often travels on paper.",
            "Borrowed Authority.",
            ),
        (
            "Hermit",
            701,
            "Herbalism Proficiency",
            "The smallest leaf may close a wound",
            "The Living Apothecary.",
            ),
        (
            "Investigator",
            702,
            "Disguise Kit Proficiency",
            "Most doors are guarded by expectations",
            "Play the Part.",
            ),
        )

    for background, seed, title, flavour, heading in fixtures:
        with redirect_stdout(
                StringIO()
                ):
            character = summon_player(
                    species="Human",
                    guild="Fighter",
                    background=background,
                    level=1,
                    seed=seed,
                    )
            data = character.to_dict()

        matches = tuple(
                practice
                for practice in data[ "Practices" ]
                if practice[ "title" ] == title
                )
        assert len( matches ) == 1, background

        payload = json.dumps(
                character_sheet_data(
                        data
                        ),
                ensure_ascii = False,
                )
        assert payload.count( title ) == 1, background
        assert flavour in payload, background
        assert heading in payload, background
        assert payload.index( "Practices" ) < payload.index( "Equipment" )


def _self_test() -> None:
    assert _species_identity(
            {
                "Species": "Elf",
                "Heritage": "Dark Elf",
                }
            ) == "Dark Elf"
    assert _species_identity(
            {
                "Species": "Gnome",
                "Heritage": "Forest Gnome",
                }
            ) == "Forest Gnome"
    assert _species_identity(
            {
                "Species": "Tiefling",
                "Heritage": "Infernal",
                }
            ) == "Tiefling (Infernal)"
    assert _class_heading(
            {
                "Class": "Fighter",
                "Subclass": "Battle Master League",
                }
            ) == "Fighter, Battle Master League"
    assert _is_spellcasting_parameter_chip(
            "Species Spell Save DC"
            )
    assert _is_spellcasting_parameter_chip(
            "Spell Attack Bonus"
            )
    assert not _is_spellcasting_parameter_chip(
            "Attack Rolls"
            )
    lead, layers = _split_described_layers(
            "Guild prose.\n\n### Path of the Wild Heart\n\nPath prose."
            )
    assert lead == "Guild prose."
    assert layers == [
            (
                    "Path of the Wild Heart",
                    "Path prose.",
                    ),
            ]

    _test_generated_practices()
    _test_sheet_tree()

    print( "OK — character sheet presentation self-test" )


def _test_sheet_tree() -> None:
    """The main column is a tree: Species, Background, Class, tools, Backstory."""
    from contextlib import redirect_stdout
    from io import StringIO

    from AtlasActorLudi.Map_of_Character_Generation import summon_player

    with redirect_stdout(
            StringIO()
            ):
        character = summon_player(
                seed=42,
                level=1,
                )
        data = character.to_dict()

    sheet_data = character_sheet_data(
            data
            )
    payload = json.dumps(
            sheet_data,
            ensure_ascii = False,
            )
    species = _species_identity(
            data
            )
    background = safe_str(
            data.get(
                    "Background",
                    "",
                    ),
            "",
            )
    guild = safe_str(
            data.get(
                    "Class",
                    "",
                    ),
            "",
            )
    tools = _tool_proficiency_names(
            data
            )

    assert species in payload
    assert background in payload
    assert "Level features" in payload
    assert guild in payload
    assert "Tool Proficiencies" in payload
    assert tools, "seed 42 should grant a tool"
    assert tools[ 0 ] in payload
    list_titles = [
            group[ "title" ]
            for group in sheet_data[ "lists" ]
            ]
    assert list_titles.count( "Languages" ) == 1
    assert list_titles.index( "Tools" ) < list_titles.index( "Languages" )
    assert payload.index(
            background
            ) < payload.index(
            "Tool Proficiencies"
            )
    assert payload.index(
            "Tool Proficiencies"
            ) < payload.index(
            "Level features"
            )

    rail_tools = _combat_proficiency_names(
            data
            )
    assert tools[ 0 ] not in rail_tools
    assert tools[ 0 ] in _tool_proficiency_names(
            data
            )
    assert "Extra Origin Feat" not in payload

    with redirect_stdout(
            StringIO()
            ):
        warlock = summon_player(
                species="Human",
                guild="Warlock",
                background="Acolyte",
                level=1,
                seed=11,
                )
        warlock_data = warlock.to_dict()

    warlock_payload = json.dumps(
            character_sheet_data(
                    warlock_data
                    ),
            ensure_ascii = False,
            )
    assert "Invocations" in warlock_payload or "Pact Spells" in warlock_payload
    assert "Pact Spells" in warlock_payload
    assert warlock_payload.index(
            "Pact Spells"
            ) < warlock_payload.index(
            "Backstory"
            )

    with redirect_stdout(
            StringIO()
            ):
        barbarian = summon_player(
                species="Human",
                guild="Barbarian",
                background="Hermit",
                specialization="Wild Heart",
                level=3,
                seed=21,
                )
        wild_data = barbarian.to_dict()

    wild_payload = json.dumps(
            character_sheet_data(
                    wild_data
                    ),
            ensure_ascii = False,
            )
    assert "Path of the Wild Heart" in wild_payload
    assert "harmony, and harmony" not in wild_payload
    assert wild_payload.index(
            "Barbarian Description"
            ) < wild_payload.index(
            "Path of the Wild Heart"
            )
    assert wild_payload.index(
            "Path of the Wild Heart"
            ) < wild_payload.index(
            "Level features"
            )

    with redirect_stdout(
            StringIO()
            ):
        human = summon_player(
                species="Human",
                guild="Fighter",
                background="Farmer",
                level=1,
                seed=42,
                )
        human_data = human.to_dict()

    human_payload = json.dumps(
            character_sheet_data(
                    human_data
                    ),
            ensure_ascii = False,
            )
    extra = next(
            getattr(
                    feature,
                    "name",
                    "",
                    )
            for feature in human_data.get(
                    "features",
                    (),
                    )
            if "Versatile" in safe_str(
                    getattr(
                            feature,
                            "source",
                            "",
                            ),
                    "",
                    )
            )
    background_feat = next(
            getattr(
                    feature,
                    "name",
                    "",
                    )
            for feature in human_data.get(
                    "features",
                    (),
                    )
            if safe_str(
                    getattr(
                            feature,
                            "source",
                            "",
                            ),
                    "",
                    ) == "Origin Feat"
            )
    assert "Humans have complex lives, and they adapt quickly." in human_payload
    assert "You have this extra Origin Feat:" in human_payload
    assert extra in human_payload
    assert "Extra Origin Feat" not in human_payload
    assert human_payload.index(
            extra
            ) < human_payload.index(
            "Farmer"
            )
    assert human_payload.index(
            "Farmer"
            ) < human_payload.index(
            background_feat
            )


if __name__ == "__main__":
    _self_test()
