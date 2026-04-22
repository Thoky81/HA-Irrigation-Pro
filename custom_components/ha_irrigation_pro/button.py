"""Button platform: manual run, manual custom run, per-zone calibrate, cancel."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ICON_CALIBRATE, ICON_SPRINKLER
from .coordinator import IrrigationCoordinator
from .entity import IrrigationBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[ButtonEntity] = [
        ManualRunButton(coord),
        ManualCustomRunButton(coord),
        CancelButton(coord),
    ]
    for zone in coord.config.zones:
        entities.append(CalibrateZoneButton(coord, zone.index, zone.name))
    async_add_entities(entities)


class ManualRunButton(IrrigationBaseEntity, ButtonEntity):
    _attr_icon = ICON_SPRINKLER

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "manual_run")
        self._attr_translation_key = "manual_run"

    async def async_press(self) -> None:
        await self.coordinator.async_run_manual()


class ManualCustomRunButton(IrrigationBaseEntity, ButtonEntity):
    _attr_icon = "mdi:sprinkler"

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "manual_custom_run")
        self._attr_translation_key = "manual_custom_run"

    async def async_press(self) -> None:
        await self.coordinator.async_run_manual_custom()


class CancelButton(IrrigationBaseEntity, ButtonEntity):
    _attr_icon = "mdi:stop-circle-outline"

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "cancel")
        self._attr_translation_key = "cancel"

    async def async_press(self) -> None:
        await self.coordinator.async_cancel()


class CalibrateZoneButton(IrrigationBaseEntity, ButtonEntity):
    _attr_icon = ICON_CALIBRATE

    def __init__(
        self, coordinator: IrrigationCoordinator, zone_idx: int, zone_name: str
    ) -> None:
        super().__init__(coordinator, f"calibrate_zone{zone_idx}")
        self._zone_idx = zone_idx
        self._attr_name = f"Calibrate {zone_name}"

    async def async_press(self) -> None:
        await self.coordinator.async_calibrate(self._zone_idx)
