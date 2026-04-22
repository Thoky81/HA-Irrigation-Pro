"""Runtime coordinator: owns mutable runtime state and persists it via Store.

Round 2 scope: coordinator exists, holds state, persists across restarts, and
dispatches updates to entities. Round 3 adds actual irrigation logic on top.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    SIGNAL_DATA_UPDATED,
    SLOT_AFTERNOON,
    SLOT_MORNING,
    SLOTS,
    STORAGE_VERSION,
    WEEKDAYS,
)
from .models import IrrigationConfig, RunHistoryEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class SlotState:
    enabled: bool = False
    time: str = "06:00"  # HH:MM 24h
    days: dict[str, bool] = field(
        default_factory=lambda: {d: True for d in WEEKDAYS}
    )
    # zone_index (1-based, as str) -> duration in minutes
    zone_durations: dict[str, float] = field(default_factory=dict)


@dataclass
class RuntimeState:
    """Everything the coordinator owns that changes at runtime.

    This is the single source of truth for entity state in Round 2.
    Round 3 will add computed fields (rain multiplier, predicted liters, etc).
    """

    master_enabled: bool = True
    ignore_rain_next_custom: bool = False

    slots: dict[str, SlotState] = field(
        default_factory=lambda: {
            SLOT_MORNING: SlotState(time="06:00"),
            SLOT_AFTERNOON: SlotState(time="19:00"),
        }
    )
    # Manual custom-run durations per zone (zone_index str -> minutes)
    custom_durations: dict[str, float] = field(default_factory=dict)

    # Calibrated flow rate per zone (L/min). 0 = not yet calibrated.
    zone_flow_rates: dict[str, float] = field(default_factory=dict)
    zone_calibrated_at: dict[str, str] = field(default_factory=dict)
    calibration_duration_min: float = 3.0

    # Computed / runtime
    rain_multiplier: float = 1.0
    rain_5d_mm: float = 0.0
    next_run_iso: str | None = None
    next_run_slot: str | None = None
    last_run_iso: str | None = None
    run_history: list[dict] = field(default_factory=list)

    # Transient — not persisted
    currently_running_zone: str | None = field(default=None, metadata={"persist": False})


_PERSIST_KEYS = {
    "master_enabled",
    "ignore_rain_next_custom",
    "slots",
    "custom_durations",
    "zone_flow_rates",
    "zone_calibrated_at",
    "calibration_duration_min",
    "rain_multiplier",
    "rain_5d_mm",
    "next_run_iso",
    "next_run_slot",
    "last_run_iso",
    "run_history",
}


def _state_to_dict(state: RuntimeState) -> dict:
    d = asdict(state)
    return {k: v for k, v in d.items() if k in _PERSIST_KEYS}


def _state_from_dict(data: dict) -> RuntimeState:
    state = RuntimeState()
    if not data:
        return state

    state.master_enabled = bool(data.get("master_enabled", True))
    state.ignore_rain_next_custom = bool(data.get("ignore_rain_next_custom", False))
    state.calibration_duration_min = float(data.get("calibration_duration_min", 3.0))

    slots_raw = data.get("slots") or {}
    for slot_name in SLOTS:
        raw = slots_raw.get(slot_name) or {}
        state.slots[slot_name] = SlotState(
            enabled=bool(raw.get("enabled", False)),
            time=str(raw.get("time", "06:00"))[:5],
            days={d: bool((raw.get("days") or {}).get(d, True)) for d in WEEKDAYS},
            zone_durations={k: float(v) for k, v in (raw.get("zone_durations") or {}).items()},
        )

    state.custom_durations = {
        k: float(v) for k, v in (data.get("custom_durations") or {}).items()
    }
    state.zone_flow_rates = {
        k: float(v) for k, v in (data.get("zone_flow_rates") or {}).items()
    }
    state.zone_calibrated_at = {
        k: str(v) for k, v in (data.get("zone_calibrated_at") or {}).items()
    }

    state.rain_multiplier = float(data.get("rain_multiplier", 1.0))
    state.rain_5d_mm = float(data.get("rain_5d_mm", 0.0))
    state.next_run_iso = data.get("next_run_iso")
    state.next_run_slot = data.get("next_run_slot")
    state.last_run_iso = data.get("last_run_iso")
    state.run_history = list(data.get("run_history") or [])
    return state


class IrrigationCoordinator:
    """Lightweight state coordinator.

    Not a DataUpdateCoordinator (no periodic polling yet) — just a state bag
    with dispatcher fan-out and Store persistence. Round 3 may graduate to
    DataUpdateCoordinator once we add periodic computations.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config = IrrigationConfig.from_entry({**entry.data, **entry.options})
        self.state = RuntimeState()
        self._store: Store[dict] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.state"
        )
        self._save_pending: bool = False

        # Seed per-zone duration defaults so entities have sane starting values.
        for slot in self.state.slots.values():
            for zone in self.config.zones:
                slot.zone_durations.setdefault(str(zone.index), 10.0)
        for zone in self.config.zones:
            self.state.custom_durations.setdefault(str(zone.index), 0.0)
            self.state.zone_flow_rates.setdefault(str(zone.index), 0.0)

    @property
    def device_identifier(self) -> tuple[str, str]:
        return (DOMAIN, self.entry.entry_id)

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        loaded = _state_from_dict(data)
        # Preserve any seeded defaults that the loaded state didn't know about.
        for slot_name, slot in loaded.slots.items():
            for zone in self.config.zones:
                slot.zone_durations.setdefault(str(zone.index), 10.0)
        for zone in self.config.zones:
            loaded.custom_durations.setdefault(str(zone.index), 0.0)
            loaded.zone_flow_rates.setdefault(str(zone.index), 0.0)
        self.state = loaded

    async def async_save(self) -> None:
        await self._store.async_save(_state_to_dict(self.state))
        self._save_pending = False

    def async_notify(self) -> None:
        """Fire the dispatcher signal so entities refresh + schedule a save."""
        async_dispatcher_send(self.hass, self._signal)
        self.hass.async_create_task(self._schedule_save())

    async def _schedule_save(self) -> None:
        if self._save_pending:
            return
        self._save_pending = True
        await self.async_save()

    @property
    def _signal(self) -> str:
        return f"{SIGNAL_DATA_UPDATED}_{self.entry.entry_id}"

    # ── mutations (Round 2: plain setters; Round 3 will wrap these in logic) ─

    def set_master(self, value: bool) -> None:
        self.state.master_enabled = value
        self.async_notify()

    def set_ignore_rain(self, value: bool) -> None:
        self.state.ignore_rain_next_custom = value
        self.async_notify()

    def set_slot_enabled(self, slot: str, value: bool) -> None:
        self.state.slots[slot].enabled = value
        self.async_notify()

    def set_slot_time(self, slot: str, hm: str) -> None:
        self.state.slots[slot].time = hm[:5]
        self.async_notify()

    def set_slot_day(self, slot: str, day: str, value: bool) -> None:
        self.state.slots[slot].days[day] = value
        self.async_notify()

    def set_slot_zone_duration(self, slot: str, zone_idx: int, minutes: float) -> None:
        self.state.slots[slot].zone_durations[str(zone_idx)] = float(minutes)
        self.async_notify()

    def set_custom_duration(self, zone_idx: int, minutes: float) -> None:
        self.state.custom_durations[str(zone_idx)] = float(minutes)
        self.async_notify()

    def set_flow_rate(self, zone_idx: int, lpm: float) -> None:
        self.state.zone_flow_rates[str(zone_idx)] = float(lpm)
        self.async_notify()

    def set_calibration_duration(self, minutes: float) -> None:
        self.state.calibration_duration_min = float(minutes)
        self.async_notify()

    # ── read helpers ─────────────────────────────────────────────────────────

    def slot(self, name: str) -> SlotState:
        return self.state.slots[name]

    def zone_duration(self, slot: str, zone_idx: int) -> float:
        return float(self.state.slots[slot].zone_durations.get(str(zone_idx), 0.0))

    def custom_duration(self, zone_idx: int) -> float:
        return float(self.state.custom_durations.get(str(zone_idx), 0.0))

    def flow_rate(self, zone_idx: int) -> float:
        return float(self.state.zone_flow_rates.get(str(zone_idx), 0.0))

    def calibrated_at(self, zone_idx: int) -> str | None:
        return self.state.zone_calibrated_at.get(str(zone_idx))

    # ── services (stubbed in Round 2) ────────────────────────────────────────

    async def async_run_manual(self) -> None:
        _LOGGER.info("[stub] manual_run invoked — logic arrives in Round 3")

    async def async_run_manual_custom(self) -> None:
        _LOGGER.info("[stub] manual_custom_run invoked — logic arrives in Round 3")

    async def async_calibrate(self, zone_idx: int) -> None:
        _LOGGER.info("[stub] calibrate(zone=%s) — logic arrives in Round 3", zone_idx)
        # Round 2 placeholder: stamp timestamp so we can see it flow through
        self.state.zone_calibrated_at[str(zone_idx)] = datetime.now().isoformat(
            timespec="seconds"
        )
        self.async_notify()

    async def async_cancel(self) -> None:
        _LOGGER.info("[stub] cancel invoked — logic arrives in Round 3")


def get_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> IrrigationCoordinator:
    return hass.data[DOMAIN][entry.entry_id]["coordinator"]
