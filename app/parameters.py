"""Canonical character parameters — pure Python, no web framework imports.

The Shiny page and the QST-0144 JSON API must agree byte-for-byte on what a
"resolved parameter set" means, so the helpers live here instead of inside a
page module.
"""

from __future__ import annotations

from typing import Any

__all__ = [
        "clean_parameter",
        "parameters_from_data",
        "selection_or_none",
        "specialization_options",
        "specialization_selection",
        ]


def selection_or_none(
        value: Any,
        ) -> str | None:
    """Treat ``None`` and ``"Random"`` as "let the generator pick"."""
    if not value or value == "Random":
        return None
    return value


def clean_parameter(
        value: Any,
        ) -> str | None:
    if value is None:
        return None
    return selection_or_none(
            str(value).strip()
            )


def _to_level(
        value: Any,
        default: int = 1,
        ) -> int:
    try:
        parsed = int(value)
    except (
            TypeError,
            ValueError,
            ):
        return default
    return max(
            1,
            min(
                    20,
                    parsed,
                    ),
            )


def specialization_options(
        catalogue,
        guild,
        ):
    return tuple(
            ["Random"]
            + list(
                    catalogue.get(
                            guild,
                            (),
                            )
                    )
            )


def specialization_selection(
        current,
        selected_guild,
        available,
        ):
    if current.get("char_class") != selected_guild:
        return "Random"
    specialization = current.get("specialization")
    if specialization in available:
        return specialization
    return "Random"


def parameters_from_data(
        data,
        fallback=None,
        ):
    """Resolve a generated character's canonical request parameters."""
    base = fallback or {}
    payload = data or {}
    level = _to_level(
            payload.get(
                    "Level",
                    base.get("level", 1),
                    ),
            )
    seed_value = payload.get(
            "Seed",
            payload.get(
                    "seed",
                    base.get("seed"),
                    ),
            )
    try:
        seed = (
                int(seed_value)
                if seed_value is not None
                else None
                )
    except (
            TypeError,
            ValueError,
            ):
        seed = None
    return {
            "species": clean_parameter(
                    payload.get(
                            "Species",
                            base.get("species"),
                            )
                    ),
            "char_class": clean_parameter(
                    payload.get(
                            "Class",
                            base.get("char_class"),
                            )
                    ),
            "specialization": clean_parameter(
                    payload.get(
                            "Specialization",
                            base.get("specialization"),
                            )
                    ),
            "background": clean_parameter(
                    payload.get(
                            "Background",
                            base.get("background"),
                            )
                    ),
            "level": level,
            "gender": clean_parameter(
                    payload.get(
                            "Gender",
                            base.get("gender"),
                            )
                    ),
            "seed": seed,
            }
