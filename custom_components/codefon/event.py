"""Every event the device reports (the same as its MQTT events)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CodefonConfigEntry
from .const import CONF_DEVICE_ID, EVENT_TYPES
from .entity import CodefonEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: CodefonConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([CodefonEventEntity(entry.runtime_data.client, entry.data[CONF_DEVICE_ID])])


class CodefonEventEntity(CodefonEntity, EventEntity):
    _attr_event_types = EVENT_TYPES

    def __init__(self, client, device_id: str) -> None:
        super().__init__(client, device_id, "event")

    def handle_message(self, kind: str, msg: dict[str, Any]) -> None:
        if kind != "event" or msg.get("event_type") not in EVENT_TYPES:
            return
        attrs = {k: v for k, v in msg.items() if k not in ("t", "event_type")}
        self._trigger_event(msg["event_type"], attrs)
        self.async_write_ha_state()
