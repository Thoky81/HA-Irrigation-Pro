"""Typed models for HA Irrigation Pro."""
from __future__ import annotations

from dataclasses import dataclass

from .const import (
    CONF_CALIBRATION_SETTLE_SECS,
    CONF_FORECAST_SKIP_MM,
    CONF_MAX_DURATION_MIN,
    CONF_MIN_DURATION_MIN,
    CONF_NAME,
    CONF_RAIN_HISTORY_DAYS,
    CONF_RAIN_LAST_HOUR,
    CONF_RAIN_RATE,
    CONF_RAIN_THRESHOLD_MM,
    CONF_RAIN_TODAY,
    CONF_RUN_HISTORY_MAX,
    CONF_RUN_SETTLE_SECS,
    CONF_TANK_VOLUME,
    CONF_WEATHER_ENTITY,
    CONF_ZONE_COUNT,
    CONF_ZONE_NAME,
    CONF_ZONE_PAUSE_SECS,
    CONF_ZONE_SWITCH,
    CONF_ZONES,
    DEFAULT_CALIBRATION_SETTLE_SECS,
    DEFAULT_FORECAST_SKIP_MM,
    DEFAULT_MAX_DURATION_MIN,
    DEFAULT_MIN_DURATION_MIN,
    DEFAULT_NAME,
    DEFAULT_RAIN_HISTORY_DAYS,
    DEFAULT_RAIN_THRESHOLD_MM,
    DEFAULT_RUN_HISTORY_MAX,
    DEFAULT_RUN_SETTLE_SECS,
    DEFAULT_ZONE_COUNT,
    DEFAULT_ZONE_PAUSE_SECS,
)


@dataclass(frozen=True, slots=True)
class ZoneConfig:
    index: int  # 1-based
    name: str
    switch_entity: str

    @property
    def slug(self) -> str:
        return f"zone{self.index}"


@dataclass(frozen=True, slots=True)
class IrrigationConfig:
    name: str
    zones: tuple[ZoneConfig, ...]
    weather_entity: str | None
    rain_today: str | None
    rain_last_hour: str | None
    rain_rate: str | None
    tank_volume: str | None
    forecast_skip_mm: float
    rain_threshold_mm: float
    rain_history_days: int
    min_duration_min: int
    max_duration_min: int
    zone_pause_secs: int
    calibration_settle_secs: int
    run_settle_secs: int
    run_history_max: int

    @property
    def zone_count(self) -> int:
        return len(self.zones)

    @classmethod
    def from_entry(cls, merged: dict) -> "IrrigationConfig":
        zones_raw = merged.get(CONF_ZONES) or []
        zones = tuple(
            ZoneConfig(
                index=i + 1,
                name=z[CONF_ZONE_NAME],
                switch_entity=z[CONF_ZONE_SWITCH],
            )
            for i, z in enumerate(zones_raw)
        )
        return cls(
            name=merged.get(CONF_NAME, DEFAULT_NAME),
            zones=zones,
            weather_entity=merged.get(CONF_WEATHER_ENTITY),
            rain_today=merged.get(CONF_RAIN_TODAY),
            rain_last_hour=merged.get(CONF_RAIN_LAST_HOUR),
            rain_rate=merged.get(CONF_RAIN_RATE),
            tank_volume=merged.get(CONF_TANK_VOLUME),
            forecast_skip_mm=float(
                merged.get(CONF_FORECAST_SKIP_MM, DEFAULT_FORECAST_SKIP_MM)
            ),
            rain_threshold_mm=float(
                merged.get(CONF_RAIN_THRESHOLD_MM, DEFAULT_RAIN_THRESHOLD_MM)
            ),
            rain_history_days=int(
                merged.get(CONF_RAIN_HISTORY_DAYS, DEFAULT_RAIN_HISTORY_DAYS)
            ),
            min_duration_min=int(
                merged.get(CONF_MIN_DURATION_MIN, DEFAULT_MIN_DURATION_MIN)
            ),
            max_duration_min=int(
                merged.get(CONF_MAX_DURATION_MIN, DEFAULT_MAX_DURATION_MIN)
            ),
            zone_pause_secs=int(
                merged.get(CONF_ZONE_PAUSE_SECS, DEFAULT_ZONE_PAUSE_SECS)
            ),
            calibration_settle_secs=int(
                merged.get(
                    CONF_CALIBRATION_SETTLE_SECS, DEFAULT_CALIBRATION_SETTLE_SECS
                )
            ),
            run_settle_secs=int(
                merged.get(CONF_RUN_SETTLE_SECS, DEFAULT_RUN_SETTLE_SECS)
            ),
            run_history_max=int(
                merged.get(CONF_RUN_HISTORY_MAX, DEFAULT_RUN_HISTORY_MAX)
            ),
        )


@dataclass(slots=True)
class RunHistoryEntry:
    """A single completed irrigation run (persisted)."""

    timestamp: str
    slot: str
    zones: list[str]
    zones_count: int
    total_min: float
    multiplier: float
    rain_ignored: bool
    planned_liters: float | None
    actual_liters: float | None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "slot": self.slot,
            "zones": self.zones,
            "zones_count": self.zones_count,
            "total_min": self.total_min,
            "multiplier": self.multiplier,
            "rain_ignored": self.rain_ignored,
            "planned_liters": self.planned_liters,
            "actual_liters": self.actual_liters,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RunHistoryEntry":
        return cls(
            timestamp=data["timestamp"],
            slot=data["slot"],
            zones=list(data.get("zones") or []),
            zones_count=int(data.get("zones_count") or 0),
            total_min=float(data.get("total_min") or 0.0),
            multiplier=float(data.get("multiplier") or 1.0),
            rain_ignored=bool(data.get("rain_ignored") or False),
            planned_liters=(
                float(data["planned_liters"])
                if data.get("planned_liters") is not None
                else None
            ),
            actual_liters=(
                float(data["actual_liters"])
                if data.get("actual_liters") is not None
                else None
            ),
        )
