"""Constants for HA Irrigation Pro."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "ha_irrigation_pro"
MANUFACTURER = "HA Irrigation Pro"
MODEL = "Multi-zone controller"

# Config entry data/option keys
CONF_NAME = "name"
CONF_ZONE_COUNT = "zone_count"
CONF_ZONES = "zones"
CONF_ZONE_NAME = "name"
CONF_ZONE_SWITCH = "switch"

CONF_WEATHER_ENTITY = "weather_entity"
CONF_RAIN_TODAY = "rain_today_sensor"
CONF_RAIN_LAST_HOUR = "rain_last_hour_sensor"
CONF_RAIN_RATE = "rain_rate_sensor"
CONF_TANK_VOLUME = "tank_volume_sensor"

CONF_FORECAST_SKIP_MM = "forecast_skip_mm"
CONF_RAIN_THRESHOLD_MM = "rain_threshold_mm"
CONF_RAIN_HISTORY_DAYS = "rain_history_days"
CONF_CALIBRATION_SETTLE_SECS = "calibration_settle_secs"
CONF_RUN_SETTLE_SECS = "run_settle_secs"
CONF_MIN_DURATION_MIN = "min_duration_min"
CONF_MAX_DURATION_MIN = "max_duration_min"
CONF_ZONE_PAUSE_SECS = "zone_pause_secs"
CONF_RUN_HISTORY_MAX = "run_history_max"

# Defaults (mirroring irrigation.py)
DEFAULT_NAME = "Irrigation"
DEFAULT_ZONE_COUNT = 5
DEFAULT_FORECAST_SKIP_MM = 5.0
DEFAULT_RAIN_THRESHOLD_MM = 25.0
DEFAULT_RAIN_HISTORY_DAYS = 5
DEFAULT_CALIBRATION_SETTLE_SECS = 60
DEFAULT_RUN_SETTLE_SECS = 15
DEFAULT_MIN_DURATION_MIN = 2
DEFAULT_MAX_DURATION_MIN = 30
DEFAULT_ZONE_PAUSE_SECS = 30
DEFAULT_RUN_HISTORY_MAX = 10

MIN_ZONES = 1
MAX_ZONES = 16

# Slot identity
SLOT_MORNING = "morning"
SLOT_AFTERNOON = "afternoon"
SLOTS = (SLOT_MORNING, SLOT_AFTERNOON)

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Storage
STORAGE_VERSION = 1

# Service names
SERVICE_MANUAL_RUN = "manual_run"
SERVICE_MANUAL_CUSTOM_RUN = "manual_custom_run"
SERVICE_CALIBRATE = "calibrate"
SERVICE_CANCEL = "cancel"

# Signals (dispatcher)
SIGNAL_DATA_UPDATED = f"{DOMAIN}_data_updated"

# Default icons
ICON_MASTER = "mdi:water-pump"
ICON_SPRINKLER = "mdi:sprinkler-variant"
ICON_DROP = "mdi:water"
ICON_RAIN = "mdi:weather-rainy"
ICON_CALENDAR = "mdi:calendar-clock"
ICON_HISTORY = "mdi:history"
ICON_TIMER = "mdi:timer-outline"
ICON_CALIBRATE = "mdi:tune-variant"
ICON_FLOW = "mdi:pipe-valve"

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.TIME,
    Platform.BUTTON,
    Platform.SENSOR,
]
