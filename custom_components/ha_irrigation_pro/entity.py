"""Base entity class — shared device info + dispatcher subscription."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL, SIGNAL_DATA_UPDATED
from .coordinator import IrrigationCoordinator


class IrrigationBaseEntity(Entity):
    """All entities inherit from this so they appear under one device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: IrrigationCoordinator, unique_suffix: str) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={coordinator.device_identifier},
            name=coordinator.config.name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            configuration_url=None,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_DATA_UPDATED}_{self.coordinator.entry.entry_id}",
                self._handle_coordinator_update,
            )
        )

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
