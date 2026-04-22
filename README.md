# HA Irrigation Pro

A Home Assistant custom integration for multi-zone irrigation scheduling with rain-aware skipping, per-zone flow calibration, and water-use prediction.

Ported from a pyscript controller into a proper HA integration with UI setup.

## Status

**Round 1 — scaffold + config flow only.** The integration installs, shows a configuration UI, and stores your settings. No irrigation logic runs yet.

Upcoming rounds:

- Round 2 — entity platforms (switches, sensors, buttons, numbers) and the update coordinator.
- Round 3 — full port of scheduling, rain multiplier, forecast skip, calibration, prediction, and run history.

## Installation (development)

1. Copy `custom_components/ha_irrigation_pro/` into your HA `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration**, search for "HA Irrigation Pro".
4. Walk through the four-step setup wizard (name → zones → sensors → thresholds).

After install, the integration appears in Devices & Services; click **Configure** to edit zones, sensors, and thresholds. To change the zone count, remove and re-add.

## Installation via HACS (future)

Once published, this repo can be added to HACS as a custom repository (type: Integration).

## Requirements

- Home Assistant 2024.1.0 or newer.
- One switch entity per irrigation zone.
- A weather entity providing a rain-mm forecast (e.g. `weather.forecast_home`).
- Optional: rain sensors (today / last hour / rate) and a water tank volume sensor.
