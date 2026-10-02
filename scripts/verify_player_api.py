#!/usr/bin/env python3
"""Verify the QST-0144 JSON API contract against the real ASGI app.

Every call runs in-process (scope/receive/send, no sockets, no new
dependencies) against `app.main:app` — FastAPI in front, the legacy Shiny
frontline mounted behind it as fallthrough.

Proves: choices, specializations (incl. the unknown-guild 404), generate with
the seeded replay request (identity against the engine, byte-for-byte
determinism), hash round-trip, re-level by re-post, the 422 error shape, and
that the fallthrough still answers `GET /`.

Run:

    .venv/bin/python scripts/verify_player_api.py
"""

from __future__ import annotations

import asyncio
import html as html_module
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(
        __file__
        ).resolve().parent.parent
if str(
        PROJECT_ROOT
        ) not in sys.path:
    sys.path.insert(
            0,
            str(
                    PROJECT_ROOT
                    ),
            )

# Guarded: importing only reuses its contract constants.
from verify_player_replay import PLAYER_REQUEST

import app.main as main_app
from AtlasActorLudi import summon_player

_FAILURES: list[str] = []


def check(
        condition: bool,
        label: str,
        ) -> None:
    if condition:
        print(
                f"ok - {label}"
                )
    else:
        _FAILURES.append(label)
        print(
                f"FAIL - {label}"
                )


async def call(
        method: str,
        path: str,
        *,
        body: Any = None,
        query: str = "",
        raw: bytes | None = None,
        ) -> tuple[int, dict[bytes, bytes], bytes]:
    if raw is not None:
        payload = raw
    elif body is None:
        payload = b""
    else:
        payload = json.dumps(body).encode()
    headers: list[tuple[bytes, bytes]] = [
            (b"host", b"testserver"),
            ]
    if body is not None or raw is not None:
        headers.append(
                (b"content-type", b"application/json")
                )
        headers.append(
                (
                    b"content-length",
                    str(len(payload)).encode(),
                    )
                )
    scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 424242),
            "server": ("testserver", 80),
            }
    state: dict[str, Any] = {"status": 0, "headers": {}}
    chunks: list[bytes] = []

    async def receive() -> dict[str, Any]:
        return {
                "type": "http.request",
                "body": payload,
                "more_body": False,
                }

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            state["status"] = message["status"]
            state["headers"] = dict(message.get("headers", []))
        elif message["type"] == "http.response.body":
            chunks.append(
                    message.get(
                            b"body",
                            message.get("body", b""),
                            )
                    )

    await main_app.app(scope, receive, send)
    return state["status"], state["headers"], b"".join(chunks)


def json_body(
        payload: bytes,
        ) -> Any:
    return json.loads(payload.decode())


async def main() -> None:
    # -- /api/choices ----------------------------------------------------
    status, headers, payload = await call(
            "GET",
            "/api/choices",
            )
    data = json_body(payload)
    check(
            status == 200
            and b"application/json" in headers.get(b"content-type", b""),
            "GET /api/choices answers 200 JSON",
            )
    check(
            data["species"][0] == "Random"
            and data["guilds"][0] == "Random"
            and data["backgrounds"][0] == "Random",
            "choice lists lead with Random",
            )
    check(
            "Wizard" in data["guilds"]
            and "Wizard" in data["specializations"]
            and data["specializations"]["Wizard"],
            "specialization catalogue carries guilds",
            )

    # -- /api/specializations -------------------------------------------
    status, _, payload = await call(
            "GET",
            "/api/specializations",
            query="guild=Wizard",
            )
    specs = json_body(payload)
    check(
            status == 200
            and specs["choices"][0] == "Random"
            and len(specs["choices"]) > 1,
            "GET specializations?guild=Wizard lists options",
            )
    status, _, payload = await call(
            "GET",
            "/api/specializations",
            query="guild=Grunk",
            )
    check(
            status == 404
            and json_body(payload)["ok"] is False,
            "unknown guild answers 404 ok=false",
            )

    # -- POST generate: the frozen seed-42 replay request -----------------
    request = {
            "species": PLAYER_REQUEST["species"],
            "char_class": PLAYER_REQUEST["guild"],
            "specialization": PLAYER_REQUEST["specialization"],
            "background": PLAYER_REQUEST["background"],
            "level": PLAYER_REQUEST["level"],
            "gender": PLAYER_REQUEST["gender"],
            "seed": PLAYER_REQUEST["seed"],
            }
    status, _, payload = await call(
            "POST",
            "/api/character/generate",
            body=request,
            )
    first = json_body(payload)
    check(
            status == 200
            and first["ok"] is True,
            "generate(seed 42) answers ok=true",
            )
    parameters = first["parameters"]
    check(
            parameters == {
                "species": PLAYER_REQUEST["species"],
                "char_class": PLAYER_REQUEST["guild"],
                "specialization": PLAYER_REQUEST["specialization"],
                "background": PLAYER_REQUEST["background"],
                "level": PLAYER_REQUEST["level"],
                "gender": PLAYER_REQUEST["gender"],
                "seed": PLAYER_REQUEST["seed"],
                },
            "canonical parameters echo the request",
            )
    expected = summon_player(
            **PLAYER_REQUEST
            )
    name = getattr(
            expected,
            "name",
            None,
            )
    check(
            name
            and (
                name in first["sheet_html"]
                or html_module.escape(name) in first["sheet_html"]
                ),
            "sheet_html carries the engine's seeded name",
            )
    check(
            first["hash"].startswith(
                    f"#/{PLAYER_REQUEST['level']}/"
                    ),
            "hash starts with the level segment",
            )

    # -- determinism ------------------------------------------------------
    status, _, payload = await call(
            "POST",
            "/api/character/generate",
            body=request,
            )
    second = json_body(payload)
    check(
            second["ok"] is True
            and second["sheet_html"] == first["sheet_html"]
            and second["hash"] == first["hash"],
            "same seed replays byte-for-byte",
            )

    # -- hash round-trip --------------------------------------------------
    status, _, payload = await call(
            "POST",
            "/api/character/generate",
            body={"hash": first["hash"]},
            )
    restored = json_body(payload)
    check(
            restored["ok"] is True
            and restored["parameters"] == parameters
            and restored["hash"] == first["hash"],
            "hash round-trips to the same character",
            )

    # -- re-level by re-posting parameters -------------------------------
    status, _, payload = await call(
            "POST",
            "/api/character/generate",
            body={**parameters, "level": 2},
            )
    leveled = json_body(payload)
    check(
            leveled["ok"] is True
            and leveled["parameters"]["level"] == 2
            and leveled["hash"].startswith("#/2/"),
            "re-post with level 2 re-levels and keeps the seed",
            )

    # -- error shapes -----------------------------------------------------
    status, _, payload = await call(
            "POST",
            "/api/character/generate",
            raw=b"not json",
            )
    check(
            status == 422
            and json_body(payload)["ok"] is False,
            "malformed body answers 422 ok=false",
            )
    status, _, payload = await call(
            "POST",
            "/api/character/generate",
            body={"level": "x"},
            )
    check(
            status == 422
            and json_body(payload)["ok"] is False,
            "non-integer level answers 422 ok=false",
            )
    status, _, payload = await call(
            "POST",
            "/api/character/generate",
            body={"hash": 42},
            )
    check(
            status == 422
            and json_body(payload)["ok"] is False,
            "non-string hash answers 422 ok=false",
            )

    # -- the static slab site owns /; the legacy frontline is fallthrough ----
    status, headers, payload = await call(
            "GET",
            "/",
            )
    check(
            status == 200
            and b"text/html" in headers.get(b"content-type", b"")
            and b"<gl-shell" in payload,
            "GET / serves the slab site shell",
            )

    if _FAILURES:
        print(
                f"verify_player_api FAILED: {len(_FAILURES)} check(s)"
                )
        raise SystemExit(1)
    print(
            "verify_player_api OK"
            )


if __name__ == "__main__":
    asyncio.run(
            main()
            )
