"""Adding a Codefon device: found on the network (zeroconf) or by address,
then paired with the device password (docs/INTEGRACIO_PROTOKOLL.md)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import CodefonAuthError, CodefonError, CodefonTooManyAttempts, async_get_info, async_pair
from .const import CONF_DEVICE_ID, CONF_TOKEN, CONF_WS_PORT, DOMAIN, PAIR_LABEL

PASSWORD_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class CodefonConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._name: str = "Codefon"
        self._ws_port: int = 81

    async def _found(self, host: str, ws_port: int) -> None:
        """Reads /api/info (raises CodefonError); the device's MAC is the unique
        id. Aborts the flow if the device is known (and moves it to host)."""
        info = await async_get_info(async_get_clientsession(self.hass), host)
        await self.async_set_unique_id(info["id"])
        # Known device at a new address: just move it.
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host = host
        self._ws_port = ws_port
        self._name = info.get("name") or "Codefon"
        self.context["title_placeholders"] = {"name": self._name}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._found(user_input[CONF_HOST].strip(), 81)
            except CodefonError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_pair()
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({vol.Required(CONF_HOST): str}), errors=errors
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        props = discovery_info.properties
        if props.get("proto") != "1":
            return self.async_abort(reason="unsupported")
        try:
            ws_port = int(props.get("ws", "81"))
        except ValueError:
            ws_port = 81
        try:
            await self._found(discovery_info.host, ws_port)
        except CodefonError:
            return self.async_abort(reason="cannot_connect")
        return await self.async_step_pair()

    async def _pair(self, password: str) -> tuple[str | None, dict[str, str]]:
        try:
            token = await async_pair(async_get_clientsession(self.hass), self._host, password, PAIR_LABEL)
        except CodefonAuthError:
            return None, {"base": "invalid_auth"}
        except CodefonTooManyAttempts:
            return None, {"base": "too_many_attempts"}
        except CodefonError:
            return None, {"base": "cannot_connect"}
        return token, {}

    async def async_step_pair(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token, errors = await self._pair(user_input[CONF_PASSWORD])
            if token is not None:
                return self.async_create_entry(
                    title=self._name,
                    data={
                        CONF_HOST: self._host,
                        CONF_TOKEN: token,
                        CONF_DEVICE_ID: self.unique_id,
                        CONF_WS_PORT: self._ws_port,
                    },
                )
        return self.async_show_form(
            step_id="pair",
            data_schema=PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={"name": self._name, "host": self._host or ""},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._host = entry_data[CONF_HOST]
        self._name = self._get_reauth_entry().title
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token, errors = await self._pair(user_input[CONF_PASSWORD])
            if token is not None:
                return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={"name": self._name, "host": self._host or ""},
        )
