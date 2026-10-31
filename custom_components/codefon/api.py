"""Talks to a Codefon device on the local network (docs/INTEGRACIO_PROTOKOLL.md).

Plain aiohttp, no Home Assistant imports, so it can be tried against a device
on its own.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_WS_PORT = 81
COMMAND_TIMEOUT = 5.0
HEARTBEAT = 10.0
RETRY_MIN = 1.0
RETRY_MAX = 30.0


class CodefonError(Exception):
    """The device could not be reached or answered something unexpected."""


class CodefonAuthError(CodefonError):
    """Wrong password, or a token the device no longer knows."""


class CodefonTooManyAttempts(CodefonError):
    """More than five pairing attempts in a minute."""


class CodefonCommandError(CodefonError):
    """The device refused a command (reply with ok: false)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message


async def async_get_info(session: aiohttp.ClientSession, host: str) -> dict[str, Any]:
    """GET /api/info: what the device is, without a password."""
    try:
        async with session.get(f"http://{host}/api/info", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                raise CodefonError(f"/api/info: HTTP {resp.status}")
            return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        raise CodefonError(str(err)) from err


async def async_pair(session: aiohttp.ClientSession, host: str, password: str, label: str) -> str:
    """POST /api/pair: the device password for a token."""
    try:
        async with session.post(
            f"http://{host}/api/pair",
            json={"password": password, "label": label},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json(content_type=None)
            if resp.status == 401:
                raise CodefonAuthError("bad_password")
            if resp.status == 429:
                raise CodefonTooManyAttempts("too_many")
            if resp.status != 200 or "token" not in body:
                raise CodefonError(f"/api/pair: HTTP {resp.status}")
            return body["token"]
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        raise CodefonError(str(err)) from err


async def async_unpair(session: aiohttp.ClientSession, host: str, token: str) -> None:
    """POST /api/unpair: forget this token on the device."""
    try:
        async with session.post(
            f"http://{host}/api/unpair",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status not in (200, 401):
                raise CodefonError(f"/api/unpair: HTTP {resp.status}")
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise CodefonError(str(err)) from err


# A listener gets (kind, message): kind is "hello", "state", "event", "audio"
# or "connection" (message {"connected": bool}).
Listener = Callable[[str, dict[str, Any]], None]
# An audio listener gets the binary frames as they come (header included).
AudioListener = Callable[[bytes], None]


class CodefonClient:
    """The device's WebSocket, kept open: reconnects by itself until stopped."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        token: str,
        ws_port: int = DEFAULT_WS_PORT,
        create_task: Callable[[Coroutine, str], asyncio.Task] | None = None,
    ) -> None:
        self._session = session
        # Home Assistant passes its own, so that the socket's task ends with it.
        self._create_task = create_task or (lambda coro, name: asyncio.create_task(coro, name=name))
        self.host = host
        self._token = token
        self._ws_port = ws_port
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._listeners: list[Listener] = []
        self._audio_listeners: list[AudioListener] = []
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._stopping = False
        self._first = asyncio.Event()
        self._first_error: Exception | None = None
        self.hello: dict[str, Any] | None = None
        self.state: dict[str, Any] = {"state": "idle"}
        self.connected = False
        self.auth_failed = False

    def add_listener(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def add_audio_listener(self, listener: AudioListener) -> Callable[[], None]:
        self._audio_listeners.append(listener)
        return lambda: self._audio_listeners.remove(listener)

    async def async_start(self, timeout: float = 10.0) -> None:
        """Connects; returns once the first hello is in, or raises."""
        self._stopping = False
        self._task = self._create_task(self._run(), f"codefon {self.host}")
        try:
            await asyncio.wait_for(self._first.wait(), timeout)
        except asyncio.TimeoutError as err:
            await self.async_stop()
            raise CodefonError(f"{self.host}: no answer in {timeout:.0f} s") from err
        if self._first_error is not None:
            await self.async_stop()
            raise self._first_error

    async def async_stop(self) -> None:
        self._stopping = True
        if self._ws is not None:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def async_command(self, cmd: str, **fields: Any) -> dict[str, Any]:
        """Sends a cmd and waits for its reply; raises CodefonCommandError on a refusal."""
        ws = self._ws
        if ws is None or ws.closed:
            raise CodefonError("not connected")
        cid = self._next_id
        self._next_id += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[cid] = fut
        try:
            await ws.send_str(json.dumps({"t": "cmd", "id": cid, "cmd": cmd, **fields}))
            reply = await asyncio.wait_for(fut, COMMAND_TIMEOUT)
        except asyncio.TimeoutError as err:
            raise CodefonError(f"{cmd}: no reply") from err
        finally:
            self._pending.pop(cid, None)
        if not reply.get("ok"):
            raise CodefonCommandError(reply.get("error", "error"), reply.get("msg", ""))
        return reply

    async def async_send_audio(self, frame: bytes) -> None:
        ws = self._ws
        if ws is not None and not ws.closed:
            await ws.send_bytes(frame)

    def _notify(self, kind: str, msg: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(kind, msg)
            except Exception:  # a broken entity must not stop the socket
                _LOGGER.exception("Codefon listener failed")

    def _set_connected(self, connected: bool) -> None:
        if connected != self.connected:
            self.connected = connected
            self._notify("connection", {"connected": connected})

    def _handle_text(self, data: str) -> None:
        try:
            msg = json.loads(data)
        except ValueError:
            return
        kind = msg.get("t")
        if kind == "reply":
            fut = self._pending.get(msg.get("id"))
            if fut is not None and not fut.done():
                fut.set_result(msg)
            return
        if kind == "hello":
            self.hello = msg
            self._first.set()
        elif kind == "state":
            self.state = msg
        elif kind not in ("event", "audio"):
            return
        self._notify(kind, msg)

    async def _run(self) -> None:
        # host may carry the HTTP port ("192.168.0.235:80"); the socket has its own.
        url = f"ws://{self.host.rsplit(':', 1)[0]}:{self._ws_port}/api/ws"
        delay = RETRY_MIN
        while not self._stopping:
            try:
                async with self._session.ws_connect(
                    url,
                    headers={"Authorization": f"Bearer {self._token}"},
                    heartbeat=HEARTBEAT,
                ) as ws:
                    self._ws = ws
                    delay = RETRY_MIN
                    self._set_connected(True)
                    async for m in ws:
                        if m.type == aiohttp.WSMsgType.TEXT:
                            self._handle_text(m.data)
                        elif m.type == aiohttp.WSMsgType.BINARY:
                            for listener in list(self._audio_listeners):
                                listener(m.data)
                        elif m.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except aiohttp.WSServerHandshakeError as err:
                if err.status == 401:
                    self.auth_failed = True
                    if not self._first.is_set():
                        self._first_error = CodefonAuthError("token refused")
                        self._first.set()
                    self._notify("connection", {"connected": False, "auth_failed": True})
                    return
                _LOGGER.debug("Codefon %s: handshake %s", self.host, err.status)
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
                _LOGGER.debug("Codefon %s: %s", self.host, err)
            finally:
                self._ws = None
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(CodefonError("disconnected"))
                self._set_connected(False)
            if self._stopping:
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX)
