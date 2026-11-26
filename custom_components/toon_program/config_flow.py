"""Config flow for the Toon Program integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .toon_client import ToonApiError, ToonConfigClient, ToonConnectionError

_LOGGER = logging.getLogger(__name__)

_SCAN_INTERVAL = vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL))

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): _SCAN_INTERVAL,
    }
)

STEP_RECONFIGURE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    }
)


def clean_host(value: str) -> str:
    """Strip a scheme, path and whitespace from what a person typed as host."""
    host = value.strip()
    host = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", host)
    host = host.split("/", 1)[0]
    # Drop a ":port" that was pasted along with the address (not for IPv6).
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host.strip().lower()


async def _async_validate(hass: Any, host: str, port: int) -> str | None:
    """Check that a Toon answers; return an error key, or None when it is fine."""
    client = ToonConfigClient(async_get_clientsession(hass), host, port)
    try:
        await client.async_get_locale()
        await client.async_get_states()
        await client.async_get_program()
    except ToonConnectionError:
        return "cannot_connect"
    except ToonApiError:
        return "invalid_response"
    except Exception:
        _LOGGER.exception("Unexpected error while validating the Toon")
        return "unknown"
    return None


class ToonProgramConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for a Toon."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ToonProgramOptionsFlow:
        """Return the options flow."""
        return ToonProgramOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the address of the Toon."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = {**user_input, CONF_HOST: clean_host(user_input[CONF_HOST])}
            if not user_input[CONF_HOST]:
                errors[CONF_HOST] = "invalid_host"
            else:
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                error = await _async_validate(
                    self.hass, user_input[CONF_HOST], user_input[CONF_PORT]
                )
                if error is None:
                    return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
                errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_DATA_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of a Toon, for example after a new IP address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = clean_host(user_input[CONF_HOST])
            port = user_input[CONF_PORT]
            if not host:
                errors[CONF_HOST] = "invalid_host"
            else:
                unique_id = f"{host}:{port}"
                for other in self._async_current_entries():
                    if other.entry_id != entry.entry_id and other.unique_id == unique_id:
                        return self.async_abort(reason="already_configured")
                error = await _async_validate(self.hass, host, port)
                if error is None:
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=unique_id,
                        data={**entry.data, CONF_HOST: host, CONF_PORT: port},
                        reason="reconfigure_successful",
                    )
                errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_RECONFIGURE_DATA_SCHEMA,
                user_input
                or {
                    CONF_HOST: entry.data[CONF_HOST],
                    CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
                },
            ),
            errors=errors,
        )


class ToonProgramOptionsFlow(OptionsFlow):
    """Handle the options of a Toon."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the polling interval."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_SCAN_INTERVAL, default=current): _SCAN_INTERVAL}
            ),
        )
