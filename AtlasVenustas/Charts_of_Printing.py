"""
Charts_of_Printing — one Entry or Chip, printed in one medium.

Thought pattern (read this before the code)
	1. The shapes live in ``Compass_of_Features``; this module only prints
	   them. Each medium is one small function with one job:

	       medium   call                  used by
	       html     f"{entry:html}"       the web sheet (also ``str( entry )``)
	       md       f"{entry:md}"         tests, snapshots, a printable sheet
	       json     f"{entry:json}"       the API
	       plain    f"{entry:plain}"      tooltips, logs

	2. Text is Markdown. HTML is made from it by ``markdown-it-py`` (the
	   library Shiny already installs), never by hand. While older text
	   still carries HTML tags, the HTML printer lets them through; the
	   QST-0142 stations remove them family by family.
	3. The HTML keeps the markup the sheet has always used for an Entry
	   (bold title, flavor block, italic rules), so moving to this printer
	   changes nothing a reader sees. The presentation is redesigned later,
	   in one place: here.
	   One exception, from the review of PR #94: a rules body with real
	   block structure — two paragraphs, a bullet list — must keep its
	   blocks, and a ``<p>`` may not sit inside ``<i>``. So a body that is
	   one paragraph prints inline in ``<i>`` exactly as before, and a body
	   of clean block Markdown prints whole, inside
	   ``<div class="entry-rules">``; the stylesheet gives that class the
	   same italics. The parser decides which is which, never a pattern
	   match on the text — and a body the parser reads as code or raw HTML
	   blocks (older text with Python indentation or tags in it) keeps the
	   old inline path until its own station ports it.
	4. Only read Entries and Chips print. One that still holds a reader
	   raises ``Unread_Text`` naming it, instead of printing a function's
	   name onto the sheet.
"""

from __future__ import annotations

import html as html_text
import json
import re

from html.parser import HTMLParser

from markdown_it import MarkdownIt

from AtlasVenustas.Compass_of_Features import Chip
from AtlasVenustas.Compass_of_Features import Entry
from AtlasVenustas.Compass_of_Features import Unread_Text


MARKDOWN = MarkdownIt(
		"commonmark",
		{
				"html": True,
				"breaks": False,
				},
		)
	#-- "html": older text still carries tags; let them through until ported.
	#-- "breaks": off.  A single newline is a space, as Markdown and the
	#-- browser both read it; a new paragraph needs a blank line.


MEDIA = (
		"html",
		"md",
		"json",
		"plain",
		)


class Unknown_Medium( ValueError ):
	"""A format spec that is not one of the known media."""


# ---------------------------------------------------------------------------
# Small helpers, one step each
# ---------------------------------------------------------------------------

def Medium_Of(
		spec: str,
		) -> str:
	"""The medium a format spec names; the empty spec means html."""
	medium = ( spec or "html" ).strip().lower()
	if medium == "markdown":
		medium = "md"
	if medium not in MEDIA:
		raise Unknown_Medium(
				f"Unknown medium {spec!r}; use one of {', '.join( MEDIA )}."
				)
	return medium


def Escaped(
		text,
		) -> str:
	"""
	A plain field, made safe for HTML.

	Titles, symbols, labels and kinds are plain text by design: they never
	carry markup, so ``<``, ``&`` and quotes in them are characters, not
	tags (PR #94 review). A rules or flavor body — and, for now, a Chip's
	value (the spell-slot tables) — may still carry old HTML, and only
	until its station ports it.
	"""
	return html_text.escape(
			str( text ),
			quote=True,
			)


def Inline_Html(
		markdown: str,
		) -> str:
	"""Markdown for one line of a sheet, as HTML without a paragraph around it."""
	return MARKDOWN.renderInline(
			markdown
			)


def Block_Html(
		markdown: str,
		) -> str:
	"""Markdown as HTML blocks: paragraphs, lists and quotes survive."""
	return MARKDOWN.render(
			markdown
			).strip()


def Top_Block_Kinds(
		markdown: str,
		) -> tuple[str, ...]:
	"""The kinds of top-level blocks Markdown parses the text into."""
	return tuple(
			token.type
			for token in MARKDOWN.parse( markdown )
			if token.level == 0
			)


def Is_One_Paragraph(
		markdown: str,
		) -> bool:
	"""True when Markdown parses the whole text as a single paragraph."""
	return Top_Block_Kinds( markdown ) == (
			"paragraph_open",
			"paragraph_close",
			)


CLEAN_BLOCK_KINDS = frozenset(
		(
				"paragraph_open",
				"paragraph_close",
				"bullet_list_open",
				"bullet_list_close",
				"ordered_list_open",
				"ordered_list_close",
				"blockquote_open",
				"blockquote_close",
				)
		)
	#-- The blocks a sheet's rules body may be made of.  Anything else the
	#-- parser finds — a code block, a raw HTML block — is not written
	#-- Markdown: it is older text whose Python indentation or tags leaked
	#-- into the string, and that text keeps the old inline path unchanged.


def Is_Clean_Block_Markdown(
		markdown: str,
		) -> bool:
	"""True when every top-level block is a paragraph, a list or a quote."""
	kinds = set(
			Top_Block_Kinds( markdown )
			)
	return kinds <= CLEAN_BLOCK_KINDS


def Plain_Text(
		markdown: str,
		) -> str:
	"""Markdown (and any leftover tags) with the markup taken out."""
	without_tags = re.sub(
			r"<[^>]+>",
			"",
			Inline_Html(
					markdown
					),
			)
	return html_text.unescape(
			without_tags
			)


def Require_Read(
		thing,
		what: str,
		) -> None:
	if not thing.Is_Read():
		raise Unread_Text(
				f"{what} still holds a reader; call .Read( character ) first."
				)


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------

def Rules_As_Html(
		rules: str,
		) -> str:
	"""
	The rules body as HTML.

	One paragraph keeps the sheet's old shape: inline HTML inside
	``<i>…</i>``. A body of clean block Markdown — two paragraphs, a
	bullet list — keeps its blocks, and a ``<p>`` may not sit inside
	``<i>``, so it prints whole, inside ``<div class="entry-rules">``; the
	stylesheet gives that class the same italics. Older text whose Python
	indentation or HTML tags would parse as code or raw blocks is not
	written Markdown yet: it keeps the old inline path, byte for byte,
	until its own QST-0142 station ports it.
	"""
	if Is_One_Paragraph( rules ):
		inline = Inline_Html(
				rules
				)
		return f"<i>{inline}</i>"
	if Is_Clean_Block_Markdown( rules ):
		blocks = Block_Html(
				rules
				)
		return f'<div class="entry-rules">{blocks}</div>'
	inline = Inline_Html(
			rules
			)
	return f"<i>{inline}</i>"


def Entry_As_Html(
		entry: Entry,
		) -> str:
	head = Escaped(
			entry.title
			)
	if not entry.title:
		return ""
	if not entry.rules and not entry.flavor:
		return f"<b>{head}</b>"
	rules = ""
	if entry.rules:
		rules = Rules_As_Html(
				entry.rules
				)
	if not entry.flavor:
		return f"<b>{head}:</b> {rules}"
	flavor = Inline_Html(
			entry.flavor
			)
	return (
			f"<b>{head}:</b>\n"
			f'<div class="bc4">{flavor}</div>'
			f"{rules}"
			)


def Entry_As_Markdown(
		entry: Entry,
		) -> str:
	lines = []
	if entry.title:
		lines.append(
				f"### {entry.title}"
				)
		#-- Level three: the sheet's name is ``#`` and its sections ``##``,
		#-- so an Entry sits one step under its section (Julio, 2026-09-24).
		#-- No title, no heading: a bare "### " is not a heading at all.
	if entry.flavor:
		lines.append(
				f"*{entry.flavor}*"
				)
	if entry.rules:
		lines.append(
				entry.rules
				)
	return "\n\n".join(
			lines
			)


def Entry_As_Json(
		entry: Entry,
		) -> str:
	return json.dumps(
			{
					"title": entry.title,
					"flavor": entry.flavor,
					"rules": entry.rules,
					"section": entry.section.value,
					"level": entry.level,
					},
			ensure_ascii=False,
			)


def Entry_As_Plain(
		entry: Entry,
		) -> str:
	parts = [
			f"{entry.title}.",
			]
	if entry.flavor:
		parts.append(
				Plain_Text(
						entry.flavor
						)
				)
	if entry.rules:
		parts.append(
				Plain_Text(
						entry.rules
						)
				)
	return " ".join(
			parts
			)


ENTRY_PRINTERS = {
		"html": Entry_As_Html,
		"md": Entry_As_Markdown,
		"json": Entry_As_Json,
		"plain": Entry_As_Plain,
		}


def Print_Entry(
		entry: Entry,
		spec: str,
		) -> str:
	Require_Read(
			entry,
			f"Entry {entry.title!r}",
			)
	printer = ENTRY_PRINTERS[
			Medium_Of( spec )
			]
	return printer(
			entry
			)


# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------

def Chip_As_Html(
		chip: Chip,
		) -> str:
	style = "npc-box stat-chip"
	if chip.kind:
		kind = Escaped(
				chip.kind
				)
		style = f"{style} {kind}-chip"
	symbol = (
			Icon_Html( chip.symbol )
			or Escaped( chip.symbol )
			)
	label = Escaped(
			chip.label
			)
	value = chip.value
		#-- NOT escaped yet.  Some legacy values still ARE markup — the
		#-- Artificer's spell-slot chip carries a whole <table> — and the
		#-- sheet gate proves it: escaping values changes 201 sheets.  A
		#-- value joins the escaped fields when its station ports it to
		#-- plain text (QST-0142; found by the PR #94 review).
	return (
			f'<div class="{style}">'
			f'<div class="symbol">{symbol}</div>'
			f'<div class="record">{label}</div>'
			f'<div class="value">{value}</div>'
			"</div>"
			)


# Colour emoji the sheet draws as self-hosted line-art SVGs so the
# parchment reads as ink instead of colour: game-icons.net, CC BY 3.0
# (attribution in README). Symbols outside this table keep their
# current text rendering — monochrome glyphs (✦, ⚧) already read as
# ink, and the parked NPC sheet keeps its emoji until it un-parks.
EMOJI_ICONS = {
		"🦾": "muscle-fat",
		"🥢": "acrobatic",
		"🫀": "heart-beats",
		"🧩": "puzzle",
		"🦉": "barn-owl",
		"🎭": "carnival-mask",
		"⚖️": "scales",
		"👤": "person",
		"🧑‍🧒": "expand",
		"👞": "boot-prints",
		"🏵️": "star-flag",
		"⚜️": "laurels",
		"💚": "heart-plus",
		"🖤": "dice-six-faces-five",
		"🛡️": "shield",
		"🔥": "flame",
		"⚙️": "gears",
		"⚔️": "crossed-swords",
		"❤️‍🔥": "heart-shield",
		"💨": "dust-cloud",
		"🌑": "moon",
		"💢": "enrage",
		"🪄": "fairy-wand",
		"🔮": "crystal-ball",
		#-- The spell rail: every chip that used to carry an emoji now
		#-- carries a sigil, all of them from the same ink.
		"✨": "spell-book",
		"🪬": "star-swirl",
		"💜": "chained-heart",
		"☯": "vortex",
		"🌀": "fog",
		"🀄": "old-king",
		}


def Icon_Name(
		symbol: str | None,
		) -> str | None:
	"""The declared icon a known emoji stands for; None keeps the text."""
	return EMOJI_ICONS.get(
			symbol or ""
			)


def Icon_Html(
		symbol: str | None,
		) -> str | None:
	"""The <img> for a known emoji symbol; None when the caller keeps text."""
	name = Icon_Name( symbol )
	if not name:
		return None
	return f'<img class="icon" src="/static/icons/{name}.svg" alt="">'


# ---------------------------------------------------------------------------
# Prose as slab runs
# ---------------------------------------------------------------------------


def Run(
		text: str,
		*,
		bold: bool = False,
		italic: bool = False,
		) -> dict:
	"""One run of prose as the parser reads it back.

	``content``/``bold`` is the shape the sheet body consumes; ``italic``
	rides along only so a caller can tell a flavour paragraph (all of it
	italic) from a rules one, and is dropped when the run is emitted.
	"""
	return {
			"content": text,
			"bold": bold,
			"italic": italic,
			}


def _Emitted(
		runs: list[dict],
		) -> list[dict]:
	"""Runs as the sheet body reads them: content and weight, nothing else."""
	return [
			{
				"content": run[ "content" ],
				"bold": run[ "bold" ],
				}
			for run in runs
			]


def _Runs_Speak(
		runs: list[dict],
		) -> bool:
	"""True when a run list carries something a reader would see."""
	return any(
			run[ "content" ].strip( )
			for run in runs
			)


#-- The tags that end a run of prose: a paragraph, any heading, and the
#-- div the block printer wraps a multi-block body in.  ``br`` is not one
#-- of them: a break splits the line, not the paragraph.
_BLOCK_TAGS = frozenset(
		(
				"p",
				"h1",
				"h2",
				"h3",
				"h4",
				"h5",
				"h6",
				"div",
				)
		)


class _Prose_Runs( HTMLParser ):
	"""The trusted HTML a rules body prints as, read back as run blocks.

	Only the tags the printers above emit are understood: ``p``, ``br``,
	``b``/``strong``, ``i``/``em``, ``ul``/``ol``/``li`` and the headings.
	Anything else contributes its text unstyled — losing a wrapper is
	better than losing a sentence.
	"""

	def __init__(
			self,
			) -> None:
		super().__init__(
				convert_charrefs=True,
				)
		self.blocks: list[dict] = []
		self.current: list[dict] = []
		#-- Nesting depth of the two emphasis flags: a run keeps whatever
		#-- was open at the moment its text arrived.
		self.bold_depth = 0
		self.italic_depth = 0
		self.list_items: list[dict] | None = None

	def _flush(
			self,
			) -> None:
		runs = self.current
		self.current = []
		if not _Runs_Speak( runs ):
			return
		if self.list_items is None:
			self.blocks.append(
					{
						"kind": "para",
						#-- A paragraph is flavour — the italic line under a
						#-- feature's name — only when every word of it is
						#-- italic.  slab 0.1.0 paints italic only whole.
						"italic": all(
								run[ "italic" ]
								for run in runs
								),
						"runs": _Emitted( runs ),
						}
					)
			return
		self.list_items.append(
				_Emitted( runs )
				)


	def handle_starttag(
			self,
			tag: str,
			attrs: list[tuple[str, str | None]],
			) -> None:
		if tag in (
				"b",
				"strong",
				):
			self.bold_depth += 1
		elif tag in (
				"i",
				"em",
				):
			self.italic_depth += 1
		elif tag == "br":
			self._emit( "\n" )
		elif tag in _BLOCK_TAGS:
			self._flush( )
		elif tag == "li":
			self._flush( )
		elif tag in (
				"ul",
				"ol",
				):
			self.list_items = []

	def handle_endtag(
			self,
			tag: str,
			) -> None:
		if tag in (
				"b",
				"strong",
				):
			self.bold_depth = max( 0, self.bold_depth - 1 )
		elif tag in (
				"i",
				"em",
				):
			self.italic_depth = max( 0, self.italic_depth - 1 )
		elif tag in _BLOCK_TAGS:
			self._flush( )
		elif tag in (
				"ul",
				"ol",
				):
			self._flush( )
			if self.list_items:
				self.blocks.append(
						{
							"kind": "list",
							"items": self.list_items,
							}
						)
			self.list_items = None

	def handle_data(
			self,
			data: str,
			) -> None:
		self._emit( data )

	def _emit(
			self,
			text: str,
			) -> None:
		if not text:
			return
		self.current.append(
				Run(
						text,
						bold=self.bold_depth > 0,
						italic=self.italic_depth > 0,
						)
				)


def Prose_Blocks(
		html: str,
		) -> list[dict]:
	"""
	Trusted HTML prose as blocks: paragraphs and lists, in order.

	This is the same text :func:`Rules_As_Html` writes, read back as data
	instead of markup: ``{"kind": "para", "runs": [...]}`` per paragraph,
	``{"kind": "list", "items": [runs, ...]}`` per list.  Emphasis survives
	as ``weight``/``italic`` on the run that carried it.
	"""
	reader = _Prose_Runs( )
	reader.feed(
			html or ""
			)
	reader.close( )
	reader._flush( )
	return reader.blocks


def Prose_Runs(
		html: str,
		) -> list[dict]:
	"""Every paragraph and list item of trusted HTML prose, flattened."""
	runs: list[dict] = []
	for block in Prose_Blocks( html ):
		if block[ "kind" ] == "list":
			for item in block[ "items" ]:
				runs.extend( item )
		else:
			runs.extend( block[ "runs" ] )
	return runs


def Chip_As_Markdown(
		chip: Chip,
		) -> str:
	head = f"{chip.symbol} " if chip.symbol else ""
	return f"{head}**{chip.label}:** {chip.value}"


def Chip_As_Json(
		chip: Chip,
		) -> str:
	return json.dumps(
			{
					"symbol": chip.symbol,
					"label": chip.label,
					"value": chip.value,
					"kind": chip.kind,
					},
			ensure_ascii=False,
			default=str,
			)


def Chip_As_Plain(
		chip: Chip,
		) -> str:
	return f"{chip.label}: {chip.value}"


CHIP_PRINTERS = {
		"html": Chip_As_Html,
		"md": Chip_As_Markdown,
		"json": Chip_As_Json,
		"plain": Chip_As_Plain,
		}


def Print_Chip(
		chip: Chip,
		spec: str,
		) -> str:
	Require_Read(
			chip,
			f"Chip {chip.label!r}",
			)
	printer = CHIP_PRINTERS[
			Medium_Of( spec )
			]
	return printer(
			chip
			)


__all__ = (
		"Chip_As_Html",
		"Chip_As_Json",
		"Chip_As_Markdown",
		"Chip_As_Plain",
		"Entry_As_Html",
		"Entry_As_Json",
		"Entry_As_Markdown",
		"Entry_As_Plain",
		"MEDIA",
		"Prose_Blocks",
		"Prose_Runs",
		"Run",
		"Rules_As_Html",
		"Print_Chip",
		"Print_Entry",
		"Unknown_Medium",
		)


# ---------------------------------------------------------------------------
# Self-test:  python -m AtlasVenustas.Charts_of_Printing
# ---------------------------------------------------------------------------

def _self_test() -> None:
	from AtlasVenustas.Compass_of_Features import Section
	from AtlasVenustas.Charts_of_Printing import Unknown_Medium
	from AtlasVenustas.Charts_of_Printing import Prose_Blocks
	from AtlasVenustas.Charts_of_Printing import Prose_Runs
		#-- By package path: run as ``python -m``, this file is also
		#-- ``__main__``, and the printers raise the package's class.

	keen = Entry(
			"Keen Smell",
			"Advantage on **Perception** checks that rely on smell.",
			"Nose to the wind.",
			section=Section.SPECIES,
			level=1,
			)

	#-- One Entry, four media.
	assert f"{keen:html}" == (
			"<b>Keen Smell:</b>\n"
			'<div class="bc4">Nose to the wind.</div>'
			"<i>Advantage on <strong>Perception</strong> checks that rely on smell.</i>"
			), f"{keen:html}"
	assert f"{keen:md}" == (
			"### Keen Smell\n\n"
			"*Nose to the wind.*\n\n"
			"Advantage on **Perception** checks that rely on smell."
			), f"{keen:md}"
	assert json.loads( f"{keen:json}" ) == {
			"title": "Keen Smell",
			"flavor": "Nose to the wind.",
			"rules": "Advantage on **Perception** checks that rely on smell.",
			"section": "Species",
			"level": 1,
			}
	assert f"{keen:plain}" == (
			"Keen Smell. Nose to the wind. "
			"Advantage on Perception checks that rely on smell."
			), f"{keen:plain}"
	assert str( keen ) == f"{keen:html}" == f"{keen}"

	#-- A title alone, and a title with rules only.
	assert f"{Entry( 'Shield' ):html}" == "<b>Shield</b>"
	assert f"{Entry( 'Shield', '+2 AC' ):html}" == "<b>Shield:</b> <i>+2 AC</i>"

	#-- A body with real blocks keeps them (review of PR #94): the two
	#-- paragraphs and the bullet list survive, inside the styled div, and
	#-- the flavor line stays inline in its own block.
	smite = Entry(
			"Smite",
			"Spend a spell slot.\n\nThe extra damage is:\n\n- 2d8 at first level\n- 1d8 more per higher slot",
			"Your weapon burns with judgement.",
			)
	blocks = f"{smite:html}"
	assert '<div class="entry-rules">' in blocks, blocks
	assert "<p>Spend a spell slot.</p>" in blocks, blocks
	assert "<li>2d8 at first level</li>" in blocks, blocks
	assert '<div class="bc4">Your weapon burns with judgement.</div>' in blocks, blocks
	assert "<i>" not in blocks, blocks
		#-- The italics of a block body come from the stylesheet, because
		#-- a <p> may not sit inside <i>.

	#-- Older text is not written Markdown: its Python indentation would
	#-- parse as a code block.  It keeps the old inline path, unchanged.
	legacy = Entry(
			"Levitate",
			"Rises vertically up to 20 feet.\n\t\tThe target can move only by pushing.\n\t\t<br>When the spell ends, it floats down.",
			)
	old_shape = f"{legacy:html}"
	assert old_shape == (
			"<b>Levitate:</b> <i>"
			+ Inline_Html( legacy.rules )
			+ "</i>"
			), old_shape
	assert "<pre>" not in old_shape and "&lt;" not in old_shape, old_shape

	#-- One Chip, four media, and its style family.
	ac = Chip(
			"🛡️",
			"Armor Class",
			16,
			)
	assert f"{ac:md}" == "🛡️ **Armor Class:** 16"
	assert f"{ac:plain}" == "Armor Class: 16"
	assert json.loads( f"{ac:json}" ) == {
			"symbol": "🛡️",
			"label": "Armor Class",
			"value": 16,
			"kind": "",
			}
	assert 'class="npc-box stat-chip"' in f"{ac:html}"
	magic = Chip(
			"✨",
			"Spell DC",
			13,
			kind="magic",
			)
	assert 'class="npc-box stat-chip magic-chip"' in f"{magic:html}"

	#-- Plain fields are text, never markup: < and & print as characters
	#-- (PR #94 review), and a kind cannot break out of the class attribute.
	sharp = Chip(
			"<",
			"AC & more",
			"the value passes through",
			kind='x" onload="y',
			)
	safe = f"{sharp:html}"
	assert '<div class="symbol">&lt;</div>' in safe, safe
	assert "AC &amp; more" in safe, safe
	assert 'onload="y"' not in safe, safe
	assert f"{Entry( 'A & B', '+1' ):html}".startswith( "<b>A &amp; B" )

	#-- A reader that answers nothing prints nothing, never "None".
	silent = Entry(
			"Quiet",
			lambda character: None,
			).Read( 0 )
	assert silent.rules == "", silent.rules
	assert f"{silent:html}" == "<b>Quiet</b>", f"{silent:html}"

	#-- No title, no heading: the Markdown of a titleless Entry has no "### ".
	assert f"{Entry( '', 'Only rules.' ):md}" == "Only rules.", (
			f"{Entry( '', 'Only rules.' ):md}"
			)

	#-- A reader must be read before it prints, and says so by name.
	live = Entry(
			"Rage",
			lambda character: f"You can rage **{character}** times.",
			)
	try:
		f"{live:md}"
	except Unread_Text as error:
		assert "Rage" in str( error )
	else:
		raise AssertionError( "an unread Entry printed" )
	assert f"{live.Read( 3 ):md}".endswith( "You can rage **3** times." )

	#-- An unknown medium is refused by name.
	try:
		f"{keen:pdf}"
	except Unknown_Medium as error:
		assert "pdf" in str( error )
	else:
		raise AssertionError( "an unknown medium printed" )

	#-- The same body, read back as runs for the sheet: emphasis travels on
	#-- the run, paragraphs and list items stay separate blocks, and the
	#-- text a reader sees never changes.
	assert Prose_Blocks(
			"<p>Keen <b>Smell</b>:</p><p>Nose to the wind.</p>"
			) == [
					{
						"kind": "para",
						"italic": False,
						"runs": [
								{"content": "Keen ", "bold": False},
								{"content": "Smell", "bold": True},
								{"content": ":", "bold": False},
								],
						},
					{
						"kind": "para",
						"italic": False,
						"runs": [
								{"content": "Nose to the wind.", "bold": False},
								],
						},
					], "two paragraphs split on the tag, not on the sentence"

	#-- A paragraph written entirely in <em> is the flavour line, and the
	#-- sheet body paints it as one.
	assert Prose_Blocks(
			"<p><em>Ride the wind.</em></p>"
			) == [
					{
						"kind": "para",
						"italic": True,
						"runs": [
								{"content": "Ride the wind.", "bold": False},
								],
						},
					], "an all-italic paragraph is flavour"
	assert Prose_Blocks(
			"<p><em>Ride</em> and <b>fall</b>.</p>"
			)[0]["italic"] is False, "mixed emphasis keeps its words, drops the italics"

	assert Prose_Blocks(
			'<div class="entry-rules"><p>Take a slot:</p>'
			"<ul><li><em>2d8</em> force</li><li>1d8 more</li></ul></div>"
			) == [
					{
						"kind": "para",
						"italic": False,
						"runs": [
								{"content": "Take a slot:", "bold": False},
								],
						},
					{
						"kind": "list",
						"items": [
								[
										{"content": "2d8", "bold": False},
										{"content": " force", "bold": False},
										],
								[
										{"content": "1d8 more", "bold": False},
										],
								],
						},
					], "a bullet list keeps its items"
	assert Prose_Runs( "" ) == [], "no prose, no runs"
	assert [ run[ "content" ] for run in Prose_Runs(
			"<p>One</p><ul><li>Two</li></ul>"
			) ] == [
					"One",
					"Two",
					], "flattening keeps the reading order"

	print( "Charts_of_Printing: all checks passed." )


if __name__ == "__main__":
	_self_test()
