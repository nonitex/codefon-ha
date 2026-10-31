"""The line's state: idle, ringing, talking (which flat, since when)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CodefonConfigEntry
from .const import CONF_DEVICE_ID, STATES
from .entity import CodefonEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: CodefonConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([CodefonStateSensor(entry.runtime_data, entry.data[CONF_DEVICE_ID])])


class CodefonStateSensor(CodefonEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATES

    def __init__(self, client, device_id: str) -> None:
        super().__init__(client, device_id, "state")

    @property
    def native_value(self) -> str | None:
        state = self.client.state.get("state")
        return state if state in STATES else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self.client.state
        flat = s.get("flat")
        names = (self.client.hello or {}).get("names", {})
        attrs: dict[str, Any] = {"flat": flat, "since": s.get("since")}
        if flat is not None and str(flat) in names:
            attrs["name"] = names[str(flat)]
        return attrs

    def handle_message(self, kind: str, msg: dict[str, Any]) -> None:
        if kind in ("state", "hello"):
            self.async_write_ha_state()
