"""Domain service registration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_CALIBRATE,
    SERVICE_CANCEL,
    SERVICE_MANUAL_CUSTOM_RUN,
    SERVICE_MANUAL_RUN,
)
from .coordinator import IrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

CONF_ENTRY_ID = "entry_id"
CONF_ZONE = "zone"

_BASE_SCHEMA = vol.Schema({vol.Optional(CONF_ENTRY_ID): cv.string})
_CALIBRATE_SCHEMA = _BASE_SCHEMA.extend(
    {vol.Required(CONF_ZONE): vol.All(vol.Coerce(int), vol.Range(min=1, max=16))}
)


def _resolve_coordinator(hass: HomeAssistant, entry_id: str | None) -> IrrigationCoordinator:
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise ServiceValidationError("HA Irrigation Pro is not configured")

    if entry_id:
        bucket = entries.get(entry_id)
        if not bucket:
            raise ServiceValidationError(f"Unknown entry_id: {entry_id}")
        return bucket["coordinator"]

    # Default to the first (there's usually only one)
    first = next(iter(entries.values()))
    return first["coordinator"]


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_MANUAL_RUN):
        return  # already registered (multi-entry scenario)

    async def _handle_manual_run(call: ServiceCall) -> None:
        coord = _resolve_coordinator(hass, call.data.get(CONF_ENTRY_ID))
        await coord.async_run_manual()

    async def _handle_manual_custom_run(call: ServiceCall) -> None:
        coord = _resolve_coordinator(hass, call.data.get(CONF_ENTRY_ID))
        await coord.async_run_manual_custom()

    async def _handle_calibrate(call: ServiceCall) -> None:
        coord = _resolve_coordinator(hass, call.data.get(CONF_ENTRY_ID))
        zone = int(call.data[CONF_ZONE])
        if not any(z.index == zone for z in coord.config.zones):
            raise ServiceValidationError(
                f"Zone {zone} is not configured (have {coord.config.zone_count})"
            )
        await coord.async_calibrate(zone)

    async def _handle_cancel(call: ServiceCall) -> None:
        coord = _resolve_coordinator(hass, call.data.get(CONF_ENTRY_ID))
        await coord.async_cancel()

    hass.services.async_register(
        DOMAIN, SERVICE_MANUAL_RUN, _handle_manual_run, schema=_BASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_MANUAL_CUSTOM_RUN, _handle_manual_custom_run, schema=_BASE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CALIBRATE, _handle_calibrate, schema=_CALIBRATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL, _handle_cancel, schema=_BASE_SCHEMA
    )

    _LOGGER.debug("HA Irrigation Pro services registered")


async def async_unregister_services_if_last(hass: HomeAssistant) -> None:
    if hass.data.get(DOMAIN):
        return  # other entries still loaded
    for svc in (SERVICE_MANUAL_RUN, SERVICE_MANUAL_CUSTOM_RUN, SERVICE_CALIBRATE, SERVICE_CANCEL):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)
