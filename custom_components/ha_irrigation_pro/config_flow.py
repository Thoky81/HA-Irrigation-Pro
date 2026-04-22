"""Config flow for HA Irrigation Pro."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

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
    DOMAIN,
    MAX_ZONES,
    MIN_ZONES,
)


def _switch_selector() -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="switch"))


def _sensor_selector() -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))


def _weather_selector() -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="weather"))


def _zone_schema(count: int, defaults: list[dict[str, str]] | None = None) -> vol.Schema:
    """Build a dynamic schema with N (name, switch) pairs."""
    fields: dict[Any, Any] = {}
    defaults = defaults or []
    for i in range(count):
        default_name = defaults[i][CONF_ZONE_NAME] if i < len(defaults) else f"Zone {i + 1}"
        default_switch = defaults[i].get(CONF_ZONE_SWITCH) if i < len(defaults) else None

        fields[vol.Required(f"zone_{i + 1}_name", default=default_name)] = str
        if default_switch:
            fields[
                vol.Required(f"zone_{i + 1}_switch", default=default_switch)
            ] = _switch_selector()
        else:
            fields[vol.Required(f"zone_{i + 1}_switch")] = _switch_selector()
    return vol.Schema(fields)


def _sensors_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}

    def _d(key: str) -> dict[str, Any]:
        val = defaults.get(key)
        return {"default": val} if val else {}

    return vol.Schema(
        {
            vol.Required(CONF_WEATHER_ENTITY, **_d(CONF_WEATHER_ENTITY)): _weather_selector(),
            vol.Optional(CONF_RAIN_TODAY, **_d(CONF_RAIN_TODAY)): _sensor_selector(),
            vol.Optional(CONF_RAIN_LAST_HOUR, **_d(CONF_RAIN_LAST_HOUR)): _sensor_selector(),
            vol.Optional(CONF_RAIN_RATE, **_d(CONF_RAIN_RATE)): _sensor_selector(),
            vol.Optional(CONF_TANK_VOLUME, **_d(CONF_TANK_VOLUME)): _sensor_selector(),
        }
    )


def _thresholds_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_FORECAST_SKIP_MM,
                default=d.get(CONF_FORECAST_SKIP_MM, DEFAULT_FORECAST_SKIP_MM),
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Required(
                CONF_RAIN_THRESHOLD_MM,
                default=d.get(CONF_RAIN_THRESHOLD_MM, DEFAULT_RAIN_THRESHOLD_MM),
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Required(
                CONF_RAIN_HISTORY_DAYS,
                default=d.get(CONF_RAIN_HISTORY_DAYS, DEFAULT_RAIN_HISTORY_DAYS),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=14)),
            vol.Required(
                CONF_MIN_DURATION_MIN,
                default=d.get(CONF_MIN_DURATION_MIN, DEFAULT_MIN_DURATION_MIN),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=240)),
            vol.Required(
                CONF_MAX_DURATION_MIN,
                default=d.get(CONF_MAX_DURATION_MIN, DEFAULT_MAX_DURATION_MIN),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=240)),
            vol.Required(
                CONF_ZONE_PAUSE_SECS,
                default=d.get(CONF_ZONE_PAUSE_SECS, DEFAULT_ZONE_PAUSE_SECS),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
            vol.Required(
                CONF_CALIBRATION_SETTLE_SECS,
                default=d.get(CONF_CALIBRATION_SETTLE_SECS, DEFAULT_CALIBRATION_SETTLE_SECS),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
            vol.Required(
                CONF_RUN_SETTLE_SECS,
                default=d.get(CONF_RUN_SETTLE_SECS, DEFAULT_RUN_SETTLE_SECS),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
            vol.Required(
                CONF_RUN_HISTORY_MAX,
                default=d.get(CONF_RUN_HISTORY_MAX, DEFAULT_RUN_HISTORY_MAX),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=200)),
        }
    )


def _extract_zones(user_input: dict[str, Any], count: int) -> list[dict[str, str]]:
    """Collapse zone_{i}_name / zone_{i}_switch pairs into a list of dicts."""
    return [
        {
            CONF_ZONE_NAME: user_input[f"zone_{i + 1}_name"],
            CONF_ZONE_SWITCH: user_input[f"zone_{i + 1}_switch"],
        }
        for i in range(count)
    ]


class IrrigationProConfigFlow(ConfigFlow, domain=DOMAIN):
    """Multi-step setup: name/count → zones → sensors → thresholds."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_NAME] = user_input[CONF_NAME]
            self._data[CONF_ZONE_COUNT] = user_input[CONF_ZONE_COUNT]
            return await self.async_step_zones()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_ZONE_COUNT, default=DEFAULT_ZONE_COUNT): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_ZONES, max=MAX_ZONES)
                    ),
                }
            ),
        )

    async def async_step_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        count = self._data[CONF_ZONE_COUNT]
        if user_input is not None:
            self._data[CONF_ZONES] = _extract_zones(user_input, count)
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="zones",
            data_schema=_zone_schema(count),
            description_placeholders={"count": str(count)},
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_thresholds()

        return self.async_show_form(step_id="sensors", data_schema=_sensors_schema())

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)

            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self._data[CONF_NAME], data=self._data
            )

        return self.async_show_form(step_id="thresholds", data_schema=_thresholds_schema())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IrrigationProOptionsFlow(config_entry)


class IrrigationProOptionsFlow(OptionsFlow):
    """Edit zones, sensors, and thresholds after install.

    Zone count is fixed post-install (changing it would orphan entities).
    To change zone count, delete and re-add the integration.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._data: dict[str, Any] = {}

    @property
    def _merged(self) -> dict[str, Any]:
        return {**self._entry.data, **self._entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_zones()

    async def async_step_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        merged = self._merged
        count = merged[CONF_ZONE_COUNT]
        existing_zones = merged.get(CONF_ZONES, [])

        if user_input is not None:
            self._data[CONF_ZONES] = _extract_zones(user_input, count)
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="zones",
            data_schema=_zone_schema(count, defaults=existing_zones),
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_thresholds()

        return self.async_show_form(
            step_id="sensors", data_schema=_sensors_schema(defaults=self._merged)
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            merged = self._merged
            merged.update(self._data)
            # Persist everything except the invariant keys into options.
            options = {k: v for k, v in merged.items() if k not in (CONF_NAME, CONF_ZONE_COUNT)}
            return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="thresholds", data_schema=_thresholds_schema(defaults=self._merged)
        )
