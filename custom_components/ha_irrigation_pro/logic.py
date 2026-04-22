"""Irrigation logic: rain math, forecast, zone runner, scheduler, calibration.

Ported from the pyscript controller at HA-Irrigation/irrigation.py. Functions
here take the coordinator as first argument; the coordinator remains the
single source of truth for runtime state.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SLOT_AFTERNOON, SLOT_MORNING, SLOTS, WEEKDAYS
from .models import RunHistoryEntry, ZoneConfig

if TYPE_CHECKING:
    from .coordinator import IrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

_WEEKDAY_IDX = {d: i for i, d in enumerate(WEEKDAYS)}


# ── State reading helpers ────────────────────────────────────────────────────


def _get_state_float(hass: HomeAssistant, entity_id: str | None, default: float = 0.0) -> float:
    if not entity_id:
        return default
    st = hass.states.get(entity_id)
    if st is None:
        return default
    raw = st.state
    if raw in (None, "", "unknown", "unavailable"):
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


def _read_tank_litres(coord: "IrrigationCoordinator") -> float | None:
    """Return tank volume in L, or None if sensor not configured/available."""
    if not coord.config.tank_volume:
        return None
    st = coord.hass.states.get(coord.config.tank_volume)
    if st is None or st.state in ("unknown", "unavailable", None, ""):
        return None
    try:
        return float(st.state)
    except (ValueError, TypeError):
        return None


# ── Notifications ────────────────────────────────────────────────────────────


async def _notify(coord: "IrrigationCoordinator", title: str, message: str) -> None:
    """Send a persistent notification. Logs regardless."""
    _LOGGER.info("NOTIFY | %s | %s", title, message)
    try:
        await coord.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": title,
                "message": message,
                "notification_id": f"{DOMAIN}_{coord.entry.entry_id}_{title[:40]}",
            },
            blocking=False,
        )
    except Exception as err:  # pragma: no cover — defensive
        _LOGGER.debug("persistent_notification failed: %s", err)


# ── Rain multiplier ──────────────────────────────────────────────────────────


def _fetch_rain_history_blocking(hass: HomeAssistant, entity_id: str, days: int):
    """Recorder query — runs in the executor (blocking)."""
    from homeassistant.components.recorder.history import get_significant_states

    start = dt_util.utcnow() - timedelta(days=days)
    return get_significant_states(hass, start, None, [entity_id])


async def compute_rain_multiplier(
    coord: "IrrigationCoordinator",
) -> tuple[float, float]:
    """Return (multiplier, cumulative_5d_mm).

    Multiplier is clamp(0, 1, 1 - cumulative / threshold). If the rain sensor
    isn't configured or the recorder returns nothing, falls back to just the
    current value of the rain_today sensor (or 0 if also missing).
    """
    cfg = coord.config
    if not cfg.rain_today:
        return 1.0, 0.0

    today_val = _get_state_float(coord.hass, cfg.rain_today, 0.0)

    try:
        from homeassistant.components.recorder import get_instance

        recorder = get_instance(coord.hass)
        hist = await recorder.async_add_executor_job(
            _fetch_rain_history_blocking,
            coord.hass,
            cfg.rain_today,
            cfg.rain_history_days,
        )
    except Exception as err:
        _LOGGER.warning("Rain history query failed: %s", err)
        return _mult_from_total(today_val, cfg.rain_threshold_mm), today_val

    records = (hist or {}).get(cfg.rain_today, [])
    if not records:
        _LOGGER.info("No rain history records — using today's value only")
        return _mult_from_total(today_val, cfg.rain_threshold_mm), today_val

    # Daily max per calendar day — the sensor is a running total that resets at midnight.
    daily_max: dict = {}
    for rec in records:
        try:
            val = float(rec.state)
        except (ValueError, TypeError, AttributeError):
            continue
        try:
            local_day = dt_util.as_local(rec.last_updated).date()
        except Exception:
            continue
        prev = daily_max.get(local_day)
        if prev is None or val > prev:
            daily_max[local_day] = val

    today = dt_util.now().date()
    past_total = sum(v for d, v in daily_max.items() if d != today)
    total = past_total + today_val
    _LOGGER.info(
        "Daily rain: %s | today: %.1f | total: %.1f",
        dict(sorted(daily_max.items())),
        today_val,
        total,
    )
    return _mult_from_total(total, cfg.rain_threshold_mm), total


def _mult_from_total(cumulative_mm: float, threshold_mm: float) -> float:
    if threshold_mm <= 0:
        return 1.0
    ratio = cumulative_mm / threshold_mm
    return round(max(0.0, min(1.0, 1.0 - ratio)), 2)


# ── Forecast ─────────────────────────────────────────────────────────────────


async def fetch_forecast_precipitation(coord: "IrrigationCoordinator") -> float:
    if not coord.config.weather_entity:
        return 0.0
    try:
        result = await coord.hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": coord.config.weather_entity, "type": "daily"},
            blocking=True,
            return_response=True,
        )
        if result:
            data = result.get(coord.config.weather_entity) or {}
            forecasts = data.get("forecast") or []
            if forecasts:
                return float(forecasts[0].get("precipitation") or 0)
    except Exception as err:
        _LOGGER.warning("Forecast fetch failed: %s", err)

    # Fallback to legacy attribute
    try:
        st = coord.hass.states.get(coord.config.weather_entity)
        if st is not None:
            forecast = st.attributes.get("forecast") or []
            if forecast:
                return float(forecast[0].get("precipitation") or 0)
    except Exception:
        pass
    return 0.0


# ── Zone runner ──────────────────────────────────────────────────────────────


async def run_zone(
    coord: "IrrigationCoordinator", zone: ZoneConfig, duration_secs: int
) -> None:
    """Open valve, wait, close. Safe against CancelledError — valve always closes."""
    coord.state.currently_running_zone = str(zone.index)
    coord.async_notify()
    try:
        await coord.hass.services.async_call(
            "switch",
            SERVICE_TURN_ON,
            {"entity_id": zone.switch_entity},
            blocking=True,
        )
        await asyncio.sleep(duration_secs)
    finally:
        try:
            await coord.hass.services.async_call(
                "switch",
                SERVICE_TURN_OFF,
                {"entity_id": zone.switch_entity},
                blocking=True,
            )
        except Exception as err:  # pragma: no cover
            _LOGGER.error("Failed to close valve %s: %s", zone.switch_entity, err)
        coord.state.currently_running_zone = None
        coord.async_notify()


# ── Planning / adjustment ────────────────────────────────────────────────────


def _adjusted_secs(base_min: float, multiplier: float, cfg) -> int:
    raw = int(base_min * multiplier * 60)
    min_secs = cfg.min_duration_min * 60
    max_secs = cfg.max_duration_min * 60
    return max(min_secs, min(raw, max_secs))


def compute_predicted_liters(coord: "IrrigationCoordinator") -> dict[str, float]:
    """Estimate liters for morning/afternoon/custom cycles using current state."""
    mult = coord.state.rain_multiplier or 1.0
    cfg = coord.config

    def _sum(duration_for_zone):
        total = 0.0
        for zone in cfg.zones:
            base_min = duration_for_zone(zone.index)
            if base_min <= 0:
                continue
            secs = _adjusted_secs(base_min, mult, cfg)
            flow = coord.flow_rate(zone.index)
            total += flow * (secs / 60)
        return total

    morning = _sum(lambda i: coord.zone_duration(SLOT_MORNING, i))
    afternoon = _sum(lambda i: coord.zone_duration(SLOT_AFTERNOON, i))
    custom = _sum(lambda i: coord.custom_duration(i))

    next_slot = coord.state.next_run_slot
    if next_slot == SLOT_MORNING:
        primary = morning
    elif next_slot == SLOT_AFTERNOON:
        primary = afternoon
    else:
        primary = morning if morning > 0 else afternoon

    return {
        "primary": primary,
        "morning": morning,
        "afternoon": afternoon,
        "custom": custom,
    }


# ── Scheduling / next-run ────────────────────────────────────────────────────


def compute_next_run(
    coord: "IrrigationCoordinator",
) -> tuple[datetime | None, str | None]:
    """Earliest upcoming enabled slot within the next 8 days."""
    if not coord.state.master_enabled:
        return None, None

    now = dt_util.now()
    candidates: list[tuple[datetime, str]] = []

    for slot_name in SLOTS:
        slot = coord.slot(slot_name)
        if not slot.enabled:
            continue
        try:
            hh, mm = (int(x) for x in slot.time.split(":")[:2])
        except (ValueError, IndexError):
            continue

        for delta_days in range(8):
            candidate_date = (now + timedelta(days=delta_days)).date()
            weekday = candidate_date.weekday()  # 0 = Mon
            day_key = WEEKDAYS[weekday]
            if not slot.days.get(day_key, False):
                continue
            candidate_dt = now.replace(
                year=candidate_date.year,
                month=candidate_date.month,
                day=candidate_date.day,
                hour=hh,
                minute=mm,
                second=0,
                microsecond=0,
            )
            if candidate_dt > now:
                candidates.append((candidate_dt, slot_name))
                break  # earliest for this slot

    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0])
    return candidates[0]


# ── Cycle runners ────────────────────────────────────────────────────────────


async def _plan_zones_for_slot(
    coord: "IrrigationCoordinator", slot_name: str, multiplier: float
) -> list[tuple[ZoneConfig, float, int]]:
    """Return list of (zone, base_min, adjusted_secs) for a scheduled slot."""
    planned: list[tuple[ZoneConfig, float, int]] = []
    for zone in coord.config.zones:
        base_min = coord.zone_duration(slot_name, zone.index)
        if base_min <= 0:
            continue
        secs = _adjusted_secs(base_min, multiplier, coord.config)
        planned.append((zone, base_min, secs))
    return planned


async def _plan_zones_for_custom(
    coord: "IrrigationCoordinator", multiplier: float
) -> list[tuple[ZoneConfig, float, int]]:
    planned: list[tuple[ZoneConfig, float, int]] = []
    for zone in coord.config.zones:
        base_min = coord.custom_duration(zone.index)
        if base_min <= 0:
            continue
        secs = _adjusted_secs(base_min, multiplier, coord.config)
        planned.append((zone, base_min, secs))
    return planned


async def _execute_plan(
    coord: "IrrigationCoordinator",
    label: str,
    planned: list[tuple[ZoneConfig, float, int]],
    multiplier: float,
    rain_ignored: bool,
    slot_name: str,
) -> None:
    """Run a planned set of zones back-to-back, log to history."""
    cfg = coord.config
    if not planned:
        _LOGGER.info("[%s] no zones to run", label)
        await _notify(coord, f"Irrigation — {label}", "No zones scheduled (all durations 0)")
        return

    tank_before = _read_tank_litres(coord)
    planned_liters = sum(
        coord.flow_rate(z.index) * (s / 60) for z, _, s in planned
    )

    await _notify(
        coord,
        f"Irrigation starting 💧 {label}",
        f"Zones: {len(planned)} | "
        f"Multiplier: {('100% (rain ignored)' if rain_ignored else f'{multiplier:.0%}')} | "
        f"Est. use: {planned_liters:.0f} L",
    )

    zones_run: list[str] = []
    total_secs = 0
    try:
        for i, (zone, base_min, adj_secs) in enumerate(planned):
            adj_min = adj_secs / 60
            _LOGGER.info(
                "[%s] (%d/%d) %s base=%.1fmin → adj=%.1fmin",
                label, i + 1, len(planned), zone.name, base_min, adj_min,
            )
            await run_zone(coord, zone, adj_secs)
            zones_run.append(f"{zone.name} ({adj_min:.1f}m)")
            total_secs += adj_secs
            if i < len(planned) - 1:
                await asyncio.sleep(cfg.zone_pause_secs)
    except asyncio.CancelledError:
        _LOGGER.warning("[%s] cycle cancelled", label)
        await _notify(coord, f"Irrigation cancelled ⛔ {label}",
                      f"Ran {len(zones_run)}/{len(planned)} zone(s) before cancel")
        raise

    await asyncio.sleep(cfg.run_settle_secs)
    tank_after = _read_tank_litres(coord)
    actual_l = None
    if tank_before is not None and tank_after is not None:
        actual_l = max(0.0, tank_before - tank_after)

    _log_run(
        coord,
        slot_name=slot_name,
        zones_run=zones_run,
        total_min=total_secs / 60,
        multiplier=multiplier,
        rain_ignored=rain_ignored,
        planned_liters=planned_liters,
        actual_liters=actual_l,
    )

    used = f" | Used: {actual_l:.0f} L" if actual_l is not None else ""
    await _notify(
        coord,
        f"Irrigation complete ✅ {label}",
        f"All {len(zones_run)} zone(s) finished. Est: {planned_liters:.0f} L{used}",
    )


async def run_slot_cycle(coord: "IrrigationCoordinator", slot_name: str) -> None:
    """Scheduled slot cycle: rain check → forecast skip → run zones."""
    if not coord.state.master_enabled:
        _LOGGER.info("[%s] master disabled — skipping", slot_name)
        return

    mult, rain_5d = await compute_rain_multiplier(coord)
    coord.state.rain_multiplier = mult
    coord.state.rain_5d_mm = rain_5d
    coord.async_notify()

    _LOGGER.info("[%s] rain_5d=%.1fmm | multiplier=%.2f", slot_name, rain_5d, mult)

    if mult == 0.0:
        await _notify(
            coord,
            f"Irrigation skipped 🌧 {slot_name}",
            f"Too much recent rain — {rain_5d:.1f}mm over {coord.config.rain_history_days} days",
        )
        return

    forecast_mm = await fetch_forecast_precipitation(coord)
    _LOGGER.info("[%s] forecast=%.1fmm (skip threshold=%.1f)",
                 slot_name, forecast_mm, coord.config.forecast_skip_mm)
    if forecast_mm >= coord.config.forecast_skip_mm:
        await _notify(
            coord,
            f"Irrigation skipped ⛈ {slot_name}",
            f"Rain forecast today ({forecast_mm:.1f}mm)",
        )
        return

    planned = await _plan_zones_for_slot(coord, slot_name, mult)
    await _execute_plan(coord, slot_name, planned, mult, False, slot_name)


async def run_manual_cycle(coord: "IrrigationCoordinator") -> None:
    """Manual "run now": runs any enabled slots (respecting rain)."""
    if not coord.state.master_enabled:
        await _notify(coord, "Irrigation skipped", "Master switch is OFF")
        return

    # Use the slot that has durations set. If both enabled, run them back-to-back.
    ran_any = False
    for slot_name in SLOTS:
        if not coord.slot(slot_name).enabled:
            continue
        await run_slot_cycle(coord, slot_name)
        ran_any = True

    if not ran_any:
        await _notify(coord, "Irrigation skipped", "No slots enabled")


async def run_custom_cycle(coord: "IrrigationCoordinator") -> None:
    """Custom manual run using per-zone custom durations; respects ignore-rain flag."""
    if not coord.state.master_enabled:
        await _notify(coord, "Custom run skipped", "Master switch is OFF")
        return

    if coord.state.ignore_rain_next_custom:
        mult = 1.0
        rain_ignored = True
    else:
        mult, rain_5d = await compute_rain_multiplier(coord)
        coord.state.rain_multiplier = mult
        coord.state.rain_5d_mm = rain_5d
        coord.async_notify()
        rain_ignored = False

        if mult == 0.0:
            await _notify(
                coord,
                "Custom run skipped 🌧",
                f"Too much recent rain — {rain_5d:.1f}mm over {coord.config.rain_history_days} days",
            )
            return

    planned = await _plan_zones_for_custom(coord, mult)
    await _execute_plan(coord, "custom", planned, mult, rain_ignored, "custom")

    # One-shot flag — reset after use.
    if coord.state.ignore_rain_next_custom:
        coord.state.ignore_rain_next_custom = False
        coord.async_notify()


# ── Calibration ──────────────────────────────────────────────────────────────


async def calibrate_zone(coord: "IrrigationCoordinator", zone: ZoneConfig) -> None:
    """Measure flow rate by running a zone and reading tank drop."""
    if not coord.config.tank_volume:
        await _notify(
            coord, "Calibration failed", "No tank volume sensor configured"
        )
        return

    duration_min = coord.state.calibration_duration_min
    duration_secs = int(duration_min * 60)

    before = _read_tank_litres(coord)
    if before is None:
        await _notify(
            coord,
            "Calibration failed",
            f"{zone.name}: tank sensor unavailable",
        )
        return

    await _notify(
        coord,
        f"Calibrating {zone.name} 🛠",
        f"Running {duration_min:.0f} min — tank: {before:.0f} L",
    )

    await run_zone(coord, zone, duration_secs)
    await asyncio.sleep(coord.config.calibration_settle_secs)
    after = _read_tank_litres(coord)
    if after is None:
        await _notify(
            coord, "Calibration failed", f"{zone.name}: tank sensor unavailable after run"
        )
        return

    drop = before - after
    if drop <= 0:
        await _notify(
            coord,
            "Calibration failed",
            f"{zone.name}: no drop detected (Δ={drop:.0f} L). Tank refilling?",
        )
        return

    flow_rate = round(drop / duration_min, 1)
    coord.state.zone_flow_rates[str(zone.index)] = flow_rate
    coord.state.zone_calibrated_at[str(zone.index)] = dt_util.now().isoformat(
        timespec="seconds"
    )
    coord.async_notify()

    _LOGGER.info(
        "Calibration: %s → %.1f L/min (Δ=%.0fL over %.1fmin)",
        zone.name, flow_rate, drop, duration_min,
    )
    await _notify(
        coord,
        f"Calibration done ✅ {zone.name}",
        f"{flow_rate:.1f} L/min ({drop:.0f} L in {duration_min:.0f} min)",
    )


# ── Run history ──────────────────────────────────────────────────────────────


def _log_run(
    coord: "IrrigationCoordinator",
    slot_name: str,
    zones_run: list[str],
    total_min: float,
    multiplier: float,
    rain_ignored: bool,
    planned_liters: float | None,
    actual_liters: float | None,
) -> None:
    entry = RunHistoryEntry(
        timestamp=dt_util.now().isoformat(timespec="seconds"),
        slot=slot_name,
        zones=zones_run,
        zones_count=len(zones_run),
        total_min=round(total_min, 1),
        multiplier=round(multiplier, 2),
        rain_ignored=rain_ignored,
        planned_liters=round(planned_liters, 1) if planned_liters is not None else None,
        actual_liters=round(actual_liters, 1) if actual_liters is not None else None,
    ).to_dict()

    history = [entry] + list(coord.state.run_history)
    max_keep = coord.config.run_history_max
    coord.state.run_history = history[:max_keep]
    coord.state.last_run_iso = entry["timestamp"]
    coord.async_notify()


# ── Scheduler ────────────────────────────────────────────────────────────────


def setup_scheduler(
    hass: HomeAssistant, coord: "IrrigationCoordinator"
) -> Callable[[], None]:
    """Register a per-minute tick + state-driven recomputations.

    Returns an unsub function that cleans everything up.
    """

    @callback
    def _on_minute(_now) -> None:
        hass.async_create_task(_check_schedule(coord))

    unsub_tick = async_track_time_change(hass, _on_minute, second=0)

    # Prime derived values immediately.
    _recompute_derived(coord)

    def _unsub() -> None:
        unsub_tick()

    return _unsub


def _recompute_derived(coord: "IrrigationCoordinator") -> None:
    """Update next-run and predicted-liters from current state."""
    next_dt, next_slot = compute_next_run(coord)
    coord.state.next_run_iso = next_dt.isoformat(timespec="seconds") if next_dt else None
    coord.state.next_run_slot = next_slot
    coord.async_notify()


async def _check_schedule(coord: "IrrigationCoordinator") -> None:
    """Fire at :00 every minute: run any slot whose time == now and day matches."""
    if not coord.state.master_enabled:
        return

    now = dt_util.now()
    current_hm = now.strftime("%H:%M")
    day_key = WEEKDAYS[now.weekday()]

    for slot_name in SLOTS:
        slot = coord.slot(slot_name)
        if not slot.enabled:
            continue
        if slot.time[:5] != current_hm:
            continue
        if not slot.days.get(day_key, False):
            continue
        _LOGGER.info("Schedule fired: %s at %s", slot_name, current_hm)
        try:
            await run_slot_cycle(coord, slot_name)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.error("Scheduled %s run failed: %s", slot_name, err)

    # After any potential run, recompute next-run for display.
    _recompute_derived(coord)
