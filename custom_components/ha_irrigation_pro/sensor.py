"""Sensor platform: next run, last run, rain multiplier, predicted liters, per-zone calibrated-at."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ICON_CALENDAR,
    ICON_DROP,
    ICON_HISTORY,
    ICON_RAIN,
)
from .coordinator import IrrigationCoordinator
from .entity import IrrigationBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = [
        NextRunSensor(coord),
        LastRunSensor(coord),
        RainMultiplierSensor(coord),
        PredictedLitersSensor(coord),
    ]
    for zone in coord.config.zones:
        entities.append(ZoneCalibratedAtSensor(coord, zone.index, zone.name))
    async_add_entities(entities)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt


class NextRunSensor(IrrigationBaseEntity, SensorEntity):
    _attr_icon = ICON_CALENDAR
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "next_run")
        self._attr_translation_key = "next_run"

    @property
    def native_value(self) -> datetime | None:
        return _parse_iso(self.coordinator.state.next_run_iso)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"slot": self.coordinator.state.next_run_slot}


class LastRunSensor(IrrigationBaseEntity, SensorEntity):
    _attr_icon = ICON_HISTORY
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "last_run")
        self._attr_translation_key = "last_run"

    @property
    def native_value(self) -> datetime | None:
        return _parse_iso(self.coordinator.state.last_run_iso)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        history = self.coordinator.state.run_history
        return {
            "history": history,
            "last_entry": history[0] if history else None,
        }


class RainMultiplierSensor(IrrigationBaseEntity, SensorEntity):
    _attr_icon = ICON_RAIN
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "rain_multiplier")
        self._attr_translation_key = "rain_multiplier"

    @property
    def native_value(self) -> float:
        return round(self.coordinator.state.rain_multiplier, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "rain_5d_mm": round(self.coordinator.state.rain_5d_mm, 1),
            "threshold_mm": self.coordinator.config.rain_threshold_mm,
            "history_days": self.coordinator.config.rain_history_days,
        }


class PredictedLitersSensor(IrrigationBaseEntity, SensorEntity):
    _attr_icon = ICON_DROP
    _attr_native_unit_of_measurement = "L"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "predicted_liters")
        self._attr_translation_key = "predicted_liters"

    def _predict(self) -> dict[str, float]:
        from .logic import compute_predicted_liters

        return compute_predicted_liters(self.coordinator)

    @property
    def native_value(self) -> float:
        return round(self._predict()["primary"], 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self._predict()
        return {
            "morning_liters": round(p["morning"], 0),
            "afternoon_liters": round(p["afternoon"], 0),
            "custom_liters": round(p["custom"], 0),
            "multiplier_applied": round(self.coordinator.state.rain_multiplier, 2),
            "next_slot": self.coordinator.state.next_run_slot or "none",
        }


class ZoneCalibratedAtSensor(IrrigationBaseEntity, SensorEntity):
    _attr_icon = "mdi:tune-variant"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: IrrigationCoordinator, zone_idx: int, zone_name: str
    ) -> None:
        super().__init__(coordinator, f"zone{zone_idx}_calibrated_at")
        self._zone_idx = zone_idx
        self._attr_name = f"{zone_name} calibrated at"

    @property
    def native_value(self) -> datetime | None:
        return _parse_iso(self.coordinator.calibrated_at(self._zone_idx))
