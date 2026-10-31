"""The Codefon integration: a Codefon intercom logger on the local network."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CodefonAuthError, CodefonClient, CodefonError, async_unpair
from .const import CONF_TOKEN, CONF_WS_PORT, DOMAIN
from .panel import async_remove_panel, async_setup_panel
from .relay import Relay

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BUTTON, Platform.EVENT, Platform.SENSOR]

@dataclass
class CodefonData:
    client: CodefonClient
    relay: Relay


type CodefonConfigEntry = ConfigEntry[CodefonData]


async def async_setup_entry(hass: HomeAssistant, entry: CodefonConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = CodefonClient(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_TOKEN],
        entry.data.get(CONF_WS_PORT, 81),
        create_task=lambda coro, name: entry.async_create_background_task(hass, coro, name),
    )
    try:
        await client.async_start()
    except CodefonAuthError as err:
        raise ConfigEntryAuthFailed("A naplózó nem fogadja el a párosítást") from err
    except CodefonError as err:
        raise ConfigEntryNotReady(f"A naplózó nem érhető el: {err}") from err

    def on_message(kind: str, msg: dict) -> None:
        # The token was removed on the device while we were running.
        if kind == "connection" and msg.get("auth_failed"):
            entry.async_start_reauth(hass)

    entry.async_on_unload(client.add_listener(on_message))
    relay = Relay(client)
    entry.async_on_unload(relay.close)
    entry.runtime_data = CodefonData(client, relay)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CodefonConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_stop()
        others = [
            e for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
        ]
        if not others:
            async_remove_panel(hass)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Removed from Home Assistant: the device forgets the token too, if reachable."""
    try:
        await async_unpair(async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_TOKEN])
    except CodefonError as err:
        _LOGGER.warning("Codefon %s: a párosítás nem törölhető a naplózón: %s", entry.data[CONF_HOST], err)
