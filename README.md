# Kestrel for Home Assistant

A Home Assistant custom integration for **Nielsen-Kellerman Kestrel** Bluetooth
weather instruments. The first release targets the **Kestrel DROP** family
(D1, D1 Probe, D2, D2 AG, D3, D3 Fire); the protocol library is structured so
the Kestrel 5000 / 7000 / 3550 meters can be added by implementing one profile.

> Status: validated against two Kestrel DROP D3 units (firmware 1.61, BLE
> profile 1.25): discovery, all measurements, settings writes, identify, time
> sync and the LiNK data-log import. See [Hardware validation](#hardware-validation).

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
| Use Home Assistant's elevation as reference altitude | on | Writes the home elevation (*Settings → System → General*) to the device whenever they differ, including when you change the elevation later. Turn off to set the reference altitude manually. |

## Entities

| Entity | Type | Notes |
|---|---|---|
| Temperature, Relative humidity, Heat index, Dew point, Wet bulb temperature, Delta T, Station pressure, Barometric pressure, Density altitude, Humidity ratio, Moisture content, Relative air density, THI (NRC), THI (Yousef) | sensor | Only the measurements present on your model are created (a DROP D3 provides temperature, humidity, heat index, dew point, station pressure and density altitude; barometric pressure is then calculated from station pressure, temperature and the reference altitude, exactly as the Kestrel app does in "Barometer" mode). Values are reported in metric; Home Assistant converts to your unit system. |
| Battery | sensor (diagnostic) | From the standard Battery Service, which on the DROP reports coarse steps (100/50/0 %). The LiNK Get Battery Level value is in diagnostics but DROP firmware 1.61 always answers 100 %. |
| Device time | sensor (diagnostic) | The DROP's running clock, read over LiNK on every poll. Use *Sync time* if it drifts. |
| Signal strength | sensor (diagnostic, disabled) | RSSI of the last advertisement. |
| Log interval | select | 2 s … 12 h or Off. |
| Transmission rate | number | 2–60 s between live notifications (used by the Kestrel LiNK app). |
| Reference altitude | number | Metres; used by the DROP to derive barometric pressure from station pressure. By default it follows Home Assistant's home elevation (see Options). |
| Wrap log | switch | Overwrite the oldest log records when the memory is full. |
| Identify | button | Blinks the LED. |
| Sync time | button | Sets the device clock to Home Assistant's local time (GATT characteristic and LiNK Set Time). |
| Erase log | button (disabled) | Clears the on-device data log. |

### Units

Measurements are read in the metric units the device transmits and declared
with Home Assistant device classes, so they are converted to your configured
unit system automatically (°F, inHg, ft on an imperial system). To change the
unit of one sensor, open the entity's settings (gear icon) and pick a *Unit of
measurement*; this works for temperatures, pressures, altitudes and speeds.
Statistics imported by `kestrel.import_data_log` follow the same conversion.

### Importing the on-device data log

The `kestrel.import_data_log` action downloads the log over NK's LiNK protocol
and stores hourly mean/min/max long-term statistics on the device's sensors
(visible in History and Statistics graphs). Mode *New records only* resumes
from the last imported sequence number; *Entire log* re-reads everything. The
transfer runs at roughly 20 records per second, so a full 6,000-record log
takes about five minutes, during which the device stays connected and regular
polls wait.

Timestamps come from the device clock. On the DROP the GATT Date/Time
characteristic is a plain register (it returns whatever was last written), so
the integration reads and sets the real clock through LiNK; press *Sync time*
once if the imported history looks shifted.

### Logo

Home Assistant loads integration logos from its central brands repository, so
a freshly installed custom integration shows a "logo not available"
placeholder. The Kestrel Instruments assets, sized for that repository, are in
`brands/kestrel/` with submission steps in `brands/README.md`.

## Hardware validation

The integration was written from NK's protocol documents and then validated
on two DROP D3 units; findings and remaining open items are tracked in
`docs/HARDWARE_VALIDATION.md`. `scripts/probe_kestrel.py` is a
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

## Licensing

The code is released under the MIT License (`LICENSE`). Protocol details come
from Nielsen-Kellerman's LiNK developer documentation, obtained through NK's
developer documentation request process; those documents are proprietary and
are not part of this repository, and the Kestrel name and logo remain NK's
trademarks. See `NOTICE.md` for the full statement. This project is not
affiliated with or endorsed by Nielsen-Kellerman Co.
