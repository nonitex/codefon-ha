"""Between the Kaputelefon panel's browsers and the device's one socket.

Any number of browsers can watch; the device's listening is shared (on while
any browser listens), its talk sender belongs to one browser at a time. A
browser that goes away leaves nothing switched on behind it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from aiohttp import web

from .api import CodefonClient, CodefonCommandError, CodefonError

_LOGGER = logging.getLogger(__name__)

# What a browser may send: the rest of the device's commands (set, allow,
# ring) are for Home Assistant itself.
BROWSER_COMMANDS = ("up", "down", "door", "listen", "talk")
FRAME_LINE = 1
FRAME_TALK = 2
QUEUE_MAX = 400  # about 8 s of line audio; a browser that cannot keep up loses frames


class Browser:
    def __init__(self, ws: web.WebSocketResponse, user_name: str | None) -> None:
        self.ws = ws
        self.user_name = user_name
        self.listening = False
        self._queue: asyncio.Queue[str | bytes] = asyncio.Queue(QUEUE_MAX)

    def put(self, item: str | bytes) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(item)

    async def writer(self) -> None:
        while True:
            item = await self._queue.get()
            if isinstance(item, bytes):
                await self.ws.send_bytes(item)
            else:
                await self.ws.send_str(item)


class Relay:
    def __init__(self, client: CodefonClient) -> None:
        self.client = client
        self.browsers: set[Browser] = set()
        self.talker: Browser | None = None
        self._listen_flat: int | None = None
        self._unsubs = [client.add_listener(self._on_message), client.add_audio_listener(self._on_audio)]

    def close(self) -> None:
        for unsub in self._unsubs:
            unsub()

    # ---- from the device ----

    def _on_message(self, kind: str, msg: dict[str, Any]) -> None:
        if kind == "audio":
            if not msg.get("listen"):
                self._listen_flat = None
                for b in self.browsers:
                    b.listening = False
            if not msg.get("talk"):
                self.talker = None
        if kind == "connection":
            msg = {"t": "connection", "connected": msg.get("connected", False)}
        text = json.dumps(msg)
        for b in self.browsers:
            b.put(text)

    def _on_audio(self, frame: bytes) -> None:
        if not frame or frame[0] != FRAME_LINE:
            return
        for b in self.browsers:
            if b.listening:
                b.put(frame)

    # ---- from the browsers ----

    def attach(self, b: Browser) -> None:
        self.browsers.add(b)
        b.put(json.dumps({"t": "connection", "connected": self.client.connected}))
        if self.client.hello is not None:
            b.put(json.dumps(self.client.hello))
        b.put(json.dumps(self.client.state))

    async def detach(self, b: Browser) -> None:
        self.browsers.discard(b)
        with contextlib.suppress(CodefonError):
            if self.talker is b:
                self.talker = None
                await self.client.async_command("talk", flat=self.client.state.get("flat") or 0, on=False)
            if b.listening and self._listen_flat is not None and not any(x.listening for x in self.browsers):
                flat, self._listen_flat = self._listen_flat, None
                await self.client.async_command("listen", flat=flat, on=False)

    async def command(self, b: Browser, msg: dict[str, Any]) -> dict[str, Any]:
        """A browser's {"t":"cmd","id":..,"cmd":..,"flat":..,"on":..}; returns the reply for it."""
        rid = msg.get("id")
        cmd = msg.get("cmd")
        flat = msg.get("flat")
        on = bool(msg.get("on"))
        try:
            if cmd not in BROWSER_COMMANDS or not isinstance(flat, int):
                raise CodefonCommandError("bad_request", "ismeretlen parancs vagy hiányzó lakás")
            if cmd == "listen":
                if on:
                    if self._listen_flat != flat:
                        await self.client.async_command("listen", flat=flat, on=True)
                        self._listen_flat = flat
                    b.listening = True
                else:
                    b.listening = False
                    if self._listen_flat is not None and not any(x.listening for x in self.browsers):
                        self._listen_flat = None
                        await self.client.async_command("listen", flat=flat, on=False)
            elif cmd == "talk":
                if on:
                    if self.talker not in (None, b):
                        raise CodefonCommandError("busy", "most valaki más beszél")
                    await self.client.async_command("talk", flat=flat, on=True)
                    self.talker = b
                elif self.talker is b:
                    self.talker = None
                    await self.client.async_command("talk", flat=flat, on=False)
            else:
                await self.client.async_command(cmd, flat=flat)
                if cmd in ("up", "down", "door"):
                    _LOGGER.info("Codefon: %s for flat %s from %s", cmd, flat, b.user_name or "?")
        except CodefonCommandError as err:
            return {"t": "reply", "id": rid, "ok": False, "error": err.code, "msg": err.message}
        except CodefonError as err:
            return {"t": "reply", "id": rid, "ok": False, "error": "unreachable", "msg": f"a naplózó nem érhető el ({err})"}
        return {"t": "reply", "id": rid, "ok": True}

    def audio_in(self, b: Browser, data: bytes) -> asyncio.Future | None:
        """A browser's talk frame; only the talker's goes to the device."""
        if self.talker is not b or not data or data[0] != FRAME_TALK:
            return None
        return asyncio.ensure_future(self.client.async_send_audio(data))
