"""Serve the Toon Program Lovelace card from the integration itself."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import CARD_FILENAME, CARD_URL_BASE, DOMAIN

_LOGGER = logging.getLogger(__name__)

_REGISTERED = f"{DOMAIN}_card_registered"


async def async_register_card(hass: HomeAssistant) -> None:
    """Make ``toon-program-card`` available on every dashboard.

    The file is served from the integration folder and added as an extra
    module, so no Lovelace resource has to be created by hand. The integration
    version is part of the URL, which refreshes the browser cache on updates.
    """
    if hass.data.get(_REGISTERED) or hass.http is None:
        return
    path = Path(__file__).parent / "frontend" / CARD_FILENAME
    if not path.is_file():
        _LOGGER.warning("The Toon Program card file is missing: %s", path)
        return

    url = f"{CARD_URL_BASE}/{CARD_FILENAME}"
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(url, str(path), cache_headers=False)]
        )
    except RuntimeError:
        # Already registered by an earlier setup of this integration.
        _LOGGER.debug("Static path %s was already registered", url)

    integration = await async_get_integration(hass, DOMAIN)
    add_extra_js_url(hass, f"{url}?v={integration.version}")
    hass.data[_REGISTERED] = True
