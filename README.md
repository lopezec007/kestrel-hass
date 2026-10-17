# Kestrel for Home Assistant

A Home Assistant custom integration for **Nielsen-Kellerman Kestrel** Bluetooth
weather instruments. The first release targets the **Kestrel DROP** family
(D1, D1 Probe, D2, D2 AG, D3, D3 Fire); the protocol library is structured so
the Kestrel 5000 / 7000 / 3550 meters can be added by implementing one profile.

> Status: the DROP code path is complete and unit-tested against the worked
> examples in NK's protocol documentation. Validation against physical DROPs is
> in progress; see [Hardware validation](#hardware-validation).

## Features

* **Automatic discovery** over Bluetooth (local adapter or ESPHome Bluetooth
  proxy) using NK's manufacturer ID and service UUIDs.
* **Sensors** for every measurement the specific DROP model implements:
  temperature, relative humidity, heat index, dew point, wet bulb temperature,
  Delta T, station and barometric pressure, density altitude, humidity ratio,
  moisture content, relative air density and the livestock THI indices
  (NRC / Yousef). Plus battery, device clock and signal strength diagnostics.
* **Settings** exposed as entities: data-log interval (select), measurement
  transmission rate and reference altitude (number), log wrap (switch).
* **Actions**: identify (blink the LED), sync the device clock to Home
  Assistant, erase the data log (disabled by default).
* **Low battery impact**: the integration connects briefly on a configurable
  interval (default 5 minutes), reads the GATT characteristics, and
  disconnects. Between polls it only listens to advertisements, which also
  drives availability.
* **Experimental** `kestrel.import_data_log` action that downloads the
  on-device data log over NK's LiNK protocol and imports it as long-term
  statistics.

## Installation

### HACS (recommended)

1. In HACS, add this repository as a custom repository of type *Integration*.
2. Install **Kestrel** and restart Home Assistant.

### Manual

Copy `custom_components/kestrel` into your Home Assistant `config/custom_components/`
directory and restart.

## Configuration

Home Assistant discovers Kestrel devices automatically once a Bluetooth adapter
(or proxy) can see them. Accept the discovery notification, or add the
integration manually from *Settings → Devices & services* and pick the device.

Options (gear icon on the integration entry):

| Option | Default | Notes |
|---|---|---|
| Poll interval | 300 s | How often to connect and read measurements (30–3600 s). Shorter intervals drain the DROP's coin cell faster. |

## Entities

| Entity | Type | Notes |
|---|---|---|
| Temperature, Relative humidity, Heat index, Dew point, Wet bulb temperature, Delta T, Station pressure, Barometric pressure, Density altitude, Humidity ratio, Moisture content, Relative air density, THI (NRC), THI (Yousef) | sensor | Only the measurements present on your model are created. Values are reported in metric; Home Assistant converts to your unit system. |
| Battery | sensor (diagnostic) | From the standard Battery Service. |
| Device time | sensor (diagnostic) | The DROP's internal clock. Use *Sync time* if it drifts. |
| Signal strength | sensor (diagnostic, disabled) | RSSI of the last advertisement. |
| Log interval | select | 2 s … 12 h or Off. |
| Transmission rate | number | 2–60 s between live notifications (used by the Kestrel LiNK app). |
| Reference altitude | number | Metres; used by the DROP to derive barometric pressure from station pressure. |
| Wrap log | switch | Overwrite the oldest log records when the memory is full. |
| Identify | button | Blinks the LED. |
| Sync time | button | Writes Home Assistant's local time to the device. |
| Erase log | button (disabled) | Clears the on-device data log. |

## Hardware validation

The integration was written from NK's protocol documents and validated with
their worked packet examples. Items still to confirm against real devices are
tracked in `docs/HARDWARE_VALIDATION.md`. `scripts/probe_kestrel.py` is a
standalone `bleak` tool that scans for devices, dumps a DROP's GATT profile and
exercises the LiNK protocol so that fixtures can be captured from real units.

## Extending to other Kestrel models

All device-specific knowledge lives in `custom_components/kestrel/kestrel_link/`:

* `models.py` maps scan-response model codes to a `DeviceFamily`.
* `profiles.py` holds one `DeviceProfile` per family. `DropProfile` reads the
  DROP's per-measurement characteristics; `KestrelProfile` reads the packed
  Kestrel 5000-family characteristics (`k5.py`). A new family needs a profile
  plus an entry in `WEATHER_FAMILIES`.
* The Home Assistant layer is family-agnostic: it creates entities from the
  `MeasurementKind`s a profile reports as present.

See `docs/ARCHITECTURE.md` for the layer contracts.

## Development

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python homeassistant pytest-homeassistant-custom-component \
    pytest pytest-asyncio pytest-cov ruff
# install the bluetooth stack HA core components need (see .github/workflows/ci.yml)
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format .
```

The protocol library has no Home Assistant dependency and can be exercised on
its own with `scripts/probe_kestrel.py`.

## Acknowledgements

Protocol details come from Nielsen-Kellerman's LiNK developer documentation,
obtained through NK's developer documentation request process. The documents
are proprietary; this repository contains only the numeric constants and
behaviour needed to interoperate.

## License

MIT
