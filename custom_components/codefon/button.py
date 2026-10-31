"""Pick up, hang up, open the door: in the call on the line now.

The device decides whether it may (docs/INTEGRACIO_PROTOKOLL.md, the
per-flat guard): pick up only while the flat rings, the rest in an answered
call, and only for the allowed flats. A refusal shows up as an error with
the device's own text.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CodefonConfigEntry
from .api import CodefonCommandError, CodefonError
from .const import CONF_DEVICE_ID
from .entity import CodefonEntity


@dataclass(frozen=True, kw_only=True)
class CodefonButtonDescription(ButtonEntityDescription):
    cmd: str
    cap: str = "signal"


BUTTONS = (
    CodefonButtonDescription(key="pick_up", cmd="up", icon="mdi:phone"),
    CodefonButtonDescription(key="hang_up", cmd="down", icon="mdi:phone-hangup"),
    CodefonButtonDescription(key="open_door", cmd="door", icon="mdi:door-open"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: CodefonConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    client = entry.runtime_data.client
    caps = (client.hello or {}).get("caps", {})
    async_add_entities(
        CodefonButton(client, entry.data[CONF_DEVICE_ID], d) for d in BUTTONS if caps.get(d.cap)
    )


class CodefonButton(CodefonEntity, ButtonEntity):
    entity_description: CodefonButtonDescription

    def __init__(self, client, device_id: str, description: CodefonButtonDescription) -> None:
        super().__init__(client, device_id, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        flat = self.client.state.get("flat")
        if not flat:
            raise HomeAssistantError("Nincs hívás a vonalon.")
        try:
            await self.client.async_command(self.entity_description.cmd, flat=flat)
        except CodefonCommandError as err:
            raise HomeAssistantError(f"A naplózó nem hajtotta végre: {err.message or err.code}") from err
        except CodefonError as err:
            raise HomeAssistantError(f"A naplózó nem érhető el: {err}") from err
