"""The Kaputelefon panel: its JavaScript, its socket (/api/codefon/ws/<entry>)
and the codefon/list command it starts with.

The socket is an ordinary authenticated Home Assistant view: the panel opens
it with a signed path (auth/sign_path), so it works wherever the frontend does
(the local address, Nabu Casa, an own domain), and it carries the audio as
binary both ways, which Home Assistant's own WebSocket does not send.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from aiohttp import WSMsgType, web

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.components.http.const import KEY_HASS_USER
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.http import KEY_HASS
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DOMAIN
from .relay import Browser

_LOGGER = logging.getLogger(__name__)

PANEL_URL = "kaputelefon"
STATIC_URL = "/codefon_static"
WS_URL = "/api/codefon/ws/{entry_id}"


def _secure_url(hass: HomeAssistant) -> str | None:
    """Where the panel works with a microphone (HTTPS), if Home Assistant has such an address."""
    try:
        return get_url(hass, require_ssl=True, allow_internal=False, prefer_cloud=True)
    except NoURLAvailableError:
        return None


@websocket_api.websocket_command({vol.Required("type"): "codefon/list"})
@callback
def ws_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    devices = [
        {"entry_id": e.entry_id, "name": e.title}
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    connection.send_result(msg["id"], {"devices": devices, "secure_url": _secure_url(hass)})


class CodefonWsView(HomeAssistantView):
    url = WS_URL
    name = "api:codefon:ws"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.StreamResponse:
        hass = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            return web.Response(status=404)
        relay = entry.runtime_data.relay
        user = request.get(KEY_HASS_USER)
        ws = web.WebSocketResponse(heartbeat=15, max_msg_size=65536)
        await ws.prepare(request)
        browser = Browser(ws, user.name if user else None)
        writer = asyncio.ensure_future(browser.writer())
        pending: set[asyncio.Future] = set()
        relay.attach(browser)

        async def run(msg: dict[str, Any]) -> None:
            browser.put(json.dumps(await relay.command(browser, msg)))

        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    try:
                        msg = json.loads(m.data)
                    except ValueError:
                        continue
                    if isinstance(msg, dict) and msg.get("t") == "cmd":
                        task = asyncio.ensure_future(run(msg))
                        pending.add(task)
                        task.add_done_callback(pending.discard)
                elif m.type == WSMsgType.BINARY:
                    if (fut := relay.audio_in(browser, m.data)) is not None:
                        pending.add(fut)
                        fut.add_done_callback(pending.discard)
        finally:
            writer.cancel()
            for task in pending:
                task.cancel()
            # Shielded: the handler is cancelled when the browser goes, and the
            # device must still be told to stop listening and talking.
            await asyncio.shield(relay.detach(browser))
        return ws


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Once per Home Assistant run: the static files, the socket and the command;
    the sidebar panel whenever it is not there."""
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("http_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
        )
        hass.http.register_view(CodefonWsView())
        websocket_api.async_register_command(hass, ws_list)
        data["http_registered"] = True
    if data.get("panel_registered") or "frontend" not in hass.config.components:
        return
    from homeassistant.components import panel_custom

    version = (Path(__file__).parent / "frontend" / "codefon-panel.js").stat().st_mtime_ns
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="codefon-panel",
        sidebar_title="Kaputelefon",
        sidebar_icon="mdi:doorbell-video",
        module_url=f"{STATIC_URL}/codefon-panel.js?v={version}",
        require_admin=False,
    )
    data["panel_registered"] = True


def async_remove_panel(hass: HomeAssistant) -> None:
    data = hass.data.get(DOMAIN, {})
    if not data.get("panel_registered"):
        return
    from homeassistant.components import frontend

    frontend.async_remove_panel(hass, PANEL_URL)
    data["panel_registered"] = False
