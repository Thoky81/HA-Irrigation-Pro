"""Time platform: morning and afternoon run times."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SLOTS
from .coordinator import IrrigationCoordinator
from .entity import IrrigationBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(SlotTimeEntity(coord, s) for s in SLOTS)


class SlotTimeEntity(IrrigationBaseEntity, TimeEntity):
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: IrrigationCoordinator, slot: str) -> None:
        super().__init__(coordinator, f"slot_{slot}_time")
        self._slot = slot
        self._attr_translation_key = f"slot_{slot}_time"

    @property
    def native_value(self) -> time | None:
        hm = self.coordinator.slot(self._slot).time
        try:
            h, m = hm.split(":")[:2]
            return time(int(h), int(m))
        except (ValueError, IndexError):
            return None

    async def async_set_value(self, value: time) -> None:
        self.coordinator.set_slot_time(self._slot, value.strftime("%H:%M"))
