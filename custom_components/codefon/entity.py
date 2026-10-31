"""What every Codefon entity shares: the device, availability, the socket's messages."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.entity import Entity

from .api import CodefonClient
from .const import DOMAIN

KIND_MODEL = {"gate": "Kapuegység-naplózó", "line": "Vonali naplózó"}


class CodefonEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, client: CodefonClient, device_id: str, key: str) -> None:
        self.client = client
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_translation_key = key
        hello = client.hello or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            connections={(CONNECTION_NETWORK_MAC, format_mac(device_id))},
            name=hello.get("name") or "Codefon",
            manufacturer="codefonlogger",
            model=KIND_MODEL.get(hello.get("kind", ""), "Codefon naplózó"),
            sw_version=hello.get("fw"),
            configuration_url=f"http://{client.host}/",
        )

    @property
    def available(self) -> bool:
        return self.client.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.client.add_listener(self._on_message))

    def _on_message(self, kind: str, msg: dict[str, Any]) -> None:
        if kind == "connection":
            self.async_write_ha_state()
        else:
            self.handle_message(kind, msg)

    def handle_message(self, kind: str, msg: dict[str, Any]) -> None:
        """A hello, state, event or audio message; override where it matters."""
