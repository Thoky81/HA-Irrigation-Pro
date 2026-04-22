"""Number platform: per-slot zone durations, flow rates, calibration duration."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ICON_CALIBRATE, ICON_FLOW, ICON_TIMER, SLOTS
from .coordinator import IrrigationCoordinator
from .entity import IrrigationBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[NumberEntity] = [CalibrationDurationNumber(coord)]

    for zone in coord.config.zones:
        for slot in SLOTS:
            entities.append(SlotZoneDurationNumber(coord, slot, zone.index, zone.name))
        entities.append(CustomZoneDurationNumber(coord, zone.index, zone.name))
        entities.append(ZoneFlowRateNumber(coord, zone.index, zone.name))

    async_add_entities(entities)


class SlotZoneDurationNumber(IrrigationBaseEntity, NumberEntity):
    _attr_icon = ICON_TIMER
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 240
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: IrrigationCoordinator,
        slot: str,
        zone_idx: int,
        zone_name: str,
    ) -> None:
        super().__init__(coordinator, f"slot_{slot}_zone{zone_idx}_duration")
        self._slot = slot
        self._zone_idx = zone_idx
        self._attr_name = f"{slot.capitalize()} — {zone_name} duration"

    @property
    def native_value(self) -> float:
        return self.coordinator.zone_duration(self._slot, self._zone_idx)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_slot_zone_duration(self._slot, self._zone_idx, value)


class CustomZoneDurationNumber(IrrigationBaseEntity, NumberEntity):
    _attr_icon = ICON_TIMER
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 240
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self, coordinator: IrrigationCoordinator, zone_idx: int, zone_name: str
    ) -> None:
        super().__init__(coordinator, f"custom_zone{zone_idx}_duration")
        self._zone_idx = zone_idx
        self._attr_name = f"Custom run — {zone_name} duration"

    @property
    def native_value(self) -> float:
        return self.coordinator.custom_duration(self._zone_idx)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_custom_duration(self._zone_idx, value)


class ZoneFlowRateNumber(IrrigationBaseEntity, NumberEntity):
    _attr_icon = ICON_FLOW
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 500
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "L/min"

    def __init__(
        self, coordinator: IrrigationCoordinator, zone_idx: int, zone_name: str
    ) -> None:
        super().__init__(coordinator, f"zone{zone_idx}_flow_rate")
        self._zone_idx = zone_idx
        self._attr_name = f"{zone_name} flow rate"

    @property
    def native_value(self) -> float:
        return self.coordinator.flow_rate(self._zone_idx)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_flow_rate(self._zone_idx, value)


class CalibrationDurationNumber(IrrigationBaseEntity, NumberEntity):
    _attr_icon = ICON_CALIBRATE
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 15
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "calibration_duration")
        self._attr_translation_key = "calibration_duration"

    @property
    def native_value(self) -> float:
        return self.coordinator.state.calibration_duration_min

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_calibration_duration(value)
