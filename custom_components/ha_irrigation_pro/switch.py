"""Switch platform: master, slot enables, per-day toggles, ignore-rain."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ICON_MASTER, ICON_RAIN, SLOTS, WEEKDAYS
from .coordinator import IrrigationCoordinator
from .entity import IrrigationBaseEntity

_WEEKDAY_LABELS = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SwitchEntity] = [
        MasterSwitch(coord),
        IgnoreRainSwitch(coord),
    ]
    for slot in SLOTS:
        entities.append(SlotEnabledSwitch(coord, slot))
        for day in WEEKDAYS:
            entities.append(SlotDaySwitch(coord, slot, day))
    async_add_entities(entities)


class MasterSwitch(IrrigationBaseEntity, SwitchEntity):
    _attr_icon = ICON_MASTER

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "master_enabled")
        self._attr_translation_key = "master_enabled"

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.master_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_master(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_master(False)


class IgnoreRainSwitch(IrrigationBaseEntity, SwitchEntity):
    _attr_icon = ICON_RAIN

    def __init__(self, coordinator: IrrigationCoordinator) -> None:
        super().__init__(coordinator, "ignore_rain_next_custom")
        self._attr_translation_key = "ignore_rain_next_custom"

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.ignore_rain_next_custom

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_ignore_rain(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_ignore_rain(False)


class SlotEnabledSwitch(IrrigationBaseEntity, SwitchEntity):
    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator: IrrigationCoordinator, slot: str) -> None:
        super().__init__(coordinator, f"slot_{slot}_enabled")
        self._slot = slot
        self._attr_translation_key = f"slot_{slot}_enabled"

    @property
    def is_on(self) -> bool:
        return self.coordinator.slot(self._slot).enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_slot_enabled(self._slot, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_slot_enabled(self._slot, False)


class SlotDaySwitch(IrrigationBaseEntity, SwitchEntity):
    _attr_icon = "mdi:calendar"

    def __init__(
        self, coordinator: IrrigationCoordinator, slot: str, day: str
    ) -> None:
        super().__init__(coordinator, f"slot_{slot}_day_{day}")
        self._slot = slot
        self._day = day
        self._attr_translation_key = f"slot_{slot}_day_{day}"
        self._attr_name = f"{slot.capitalize()} — {_WEEKDAY_LABELS[day]}"

    @property
    def is_on(self) -> bool:
        return self.coordinator.slot(self._slot).days.get(self._day, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_slot_day(self._slot, self._day, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_slot_day(self._slot, self._day, False)
