"""Serve the slab Character Generator face from the static assets."""

from __future__ import annotations

from pathlib import Path

from shiny import ui


STATIC_DIR = (
        Path(
            __file__
            ).resolve().parents[1]
        / "static"
        )
SCRIPT_PATH = STATIC_DIR / "js" / "slab-forge.js"
SCRIPT_URL = "/static/js/slab-forge.js"
SLAB_MODULE_PATH = STATIC_DIR / "slab" / "forge.js"
SLAB_MODULE_URL = "/static/slab/forge.js"


def forge_head_tags(
        ) -> list[ui.Tag]:
    version = int(
            SCRIPT_PATH.stat().st_mtime
            ) if SCRIPT_PATH.exists() else 0
    return [
            ui.tags.script(
                    src=f"{SCRIPT_URL}?v={version}",
                    defer="",
                    ),
            ]


def forge_host_attrs(
        ) -> dict[str, str]:
    """Attributes for the div the bridge mounts <gl-forge> into.

    The data-slab-version value cache-busts the dynamic import of the
    generated module, so a regeneration is never served from a stale cache.
    """
    version = int(
            SLAB_MODULE_PATH.stat().st_mtime
            ) if SLAB_MODULE_PATH.exists() else 0
    return {
            "class": "forge-host",
            "id": "forge-host",
            "data-slab-version": str(version),
            }


__all__ = [
        "SCRIPT_PATH",
        "SCRIPT_URL",
        "SLAB_MODULE_PATH",
        "SLAB_MODULE_URL",
        "forge_head_tags",
        "forge_host_attrs",
        ]
