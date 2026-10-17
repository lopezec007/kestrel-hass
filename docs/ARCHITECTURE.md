# Architecture

`kestrel-hass` is a Home Assistant custom integration (domain `kestrel`) for
Nielsen-Kellerman Kestrel Bluetooth instruments. The first supported family is
the Kestrel DROP (D1 / D2 / D3 and variants); the code is layered so that the
Kestrel 5000 / 7000 / 3550 families can be added by implementing one profile.

```
custom_components/kestrel/
├── kestrel_link/          Pure-Python protocol library (no HA imports)
│   ├── const.py           Enums: packet types, commands, field names/units, models
│   ├── types.py           Dataclasses + exceptions shared by every layer
│   ├── hdlc.py            RFC1662 HDLC framing + FCS-16          (LiNK wire layer)
│   ├── packets.py         LiNK packet encode/decode              (LiNK wire layer)
│   ├── decoding.py        Metadata/data record decoding, BT Date Time
│   ├── uuids.py           GATT UUID builders for NK services
│   ├── advertising.py     NK advertisement / scan-response parsing
│   ├── models.py          Model code registry -> ModelInfo / DeviceFamily
│   ├── drop.py            DROP GATT characteristic parsing/encoding
│   ├── k5.py              Kestrel 5000-family GATT parsing/encoding
│   ├── profiles.py        DeviceProfile abstraction + DropProfile / KestrelProfile
│   ├── device.py          KestrelBleDevice: connection handling around a profile
│   ├── transport.py       LiNK over the BLE Mass Transfer Service
│   └── client.py          High-level LiNK commands (snapshot, data log, ...)
├── __init__.py            Entry setup / unload
├── coordinator.py         ActiveBluetoothDataUpdateCoordinator subclass
├── config_flow.py         Bluetooth discovery + manual pick + options
├── entity.py              Base entity (device info)
├── sensor.py / select.py / number.py / switch.py / button.py
├── services.py            `kestrel.import_data_log` (LiNK data log -> statistics)
├── diagnostics.py
└── strings.json, translations/, icons.json, manifest.json
```

## Layers

### 1. Wire layer (`hdlc.py`, `packets.py`, `decoding.py`)

Every LiNK packet is `[type:u16][size:u16][data]` little-endian, wrapped in an
HDLC frame: `0x7E` + escaped(payload + FCS16) + `0x7E`. `0x7E`/`0x7D` inside the
payload become `0x7D, byte ^ 0x20`. FCS is the RFC1662 CRC-16 (poly 0x8408
reflected, init 0xFFFF, final XOR 0xFFFF), appended LSB first.

```python
fcs16(data: bytes) -> int
encode_frame(payload: bytes) -> bytes
decode_frame(frame: bytes) -> bytes            # raises FrameError
class FrameDecoder:                             # streaming; ignores bytes outside frames
    def feed(self, data: bytes) -> list[bytes]  # returns complete, validated payloads

encode_packet(packet: LinkPacket) -> bytes
decode_packet(data: bytes) -> LinkPacket        # raises ProtocolError
encode_command(code: int, params: bytes = b"") -> bytes   # framed, ready to send

decode_int(raw: bytes, *, signed: bool) -> int
is_bad_value(raw_int: int, size: int, *, signed: bool) -> bool
decode_bt_datetime(raw: bytes) -> datetime | None
encode_bt_datetime(dt: datetime) -> bytes
decode_field(desc: FieldDescriptor, raw: bytes) -> Any     # scaled value or None
class RecordLayout:                              # built from FieldDescriptors
    record_size: int
    def decode_records(self, payload: bytes, *, numbered: bool) -> tuple[int | None, list[LinkRecord]]
class MetadataAccumulator:                      # Metadata Start resets, Metadata appends
    def add(self, packet: MetadataPacket) -> None
    def layout(self) -> RecordLayout
```

Data-log data packets are prefixed with a u16 packet number (`numbered=True`);
snapshot data packets are not. Record size is the sum of descriptor sizes.

Bad-value sentinels: unsigned → all-ones for the width; signed → `0x80..01`
(e.g. `0x8001`, `0x800001`). A value hitting its sentinel decodes to `None`.

BT Date Time is 7 bytes: year u16 LE, month, day, hour, minute, second. If the
little-endian year is implausible (<1990 or >2150) but the big-endian reading is
plausible, the big-endian reading is used (the NK worked example shows the year
bytes in that order).

### 2. GATT layer (`uuids.py`, `advertising.py`, `models.py`, `drop.py`, `k5.py`)

Custom 128-bit UUIDs are formed from a family base with a 16-bit short id:

| Service              | Pattern                                      |
|----------------------|----------------------------------------------|
| DROP                 | `1263XXXX-cc25-497d-9854-9b6c02c77054`       |
| Kestrel 5000/3550/7000 | `0329XXXX-eab4-dea1-b24e-44ec023874db`     |
| Mass Transfer        | `8592XXXX-0338-4b83-ae4a-ac1d217adb03` (service short 0x0000; char shorts 0x0001 P→C indicate, 0x0002 C→P write). NK's note is ambiguous about the byte order of the short id, so the transport locates the two characteristics by *property* (indicate vs write) inside the service and only uses the short ids as a hint. |
| Super Mass Transfer  | `3749XXXX-c0e3-4a13-b487-910812b8182f`, service short 0x52C9 |

Advertisement: local name `"<ModelAbbrev> - <serial>"`; scan response carries
the family service UUID and manufacturer data for company `0x00EA` =
`[model_code u16][event_field u16]` (`0xFFFF` = no event).

```python
parse_advertisement(local_name, manufacturer_data, service_uuids) -> NKAdvertisement | None
model_from_code(code) -> ModelInfo | None
family_from_model_code(code) -> DeviceFamily
family_from_service_uuids(uuids) -> DeviceFamily | None
family_from_local_name(name) -> DeviceFamily | None
```

DROP measurements live in characteristics `0x0001`–`0x000F`; byte 0 is a status
byte (bit0 present, bit1 enabled, bit2 valid), the remainder is a little-endian
integer whose width is `len - 1`, scaled by the characteristic's exponent.
Kestrel 5000 packs measurements into fixed-layout 20-byte characteristics with
presence bitmaps in `0x0300`/`0x0380`.

```python
# drop.py
DROP_MEASUREMENT_CHARS: dict[int, DropMeasurementSpec]   # short uuid -> (kind, signed, exponent)
parse_drop_measurement(spec, raw) -> Measurement
parse_drop_settings(raw) -> DropSettings
encode_drop_settings(settings) -> bytes          # 20 bytes; None fields -> ignore sentinel
encode_drop_command(*, erase_log=False, blink_led=False, restore_defaults=False) -> bytes
# k5.py
parse_k5_status(status1, status2) -> set[MeasurementKind]
parse_k5_characteristic(short, raw, present) -> dict[MeasurementKind, Measurement]
parse_kestrel_settings(raw) -> KestrelSettings
encode_kestrel_settings(settings) -> bytes
encode_kestrel_command(*, erase_log=False, restore_defaults=False, visual_identify=False,
                       sync_ble_data=False, store_log_point=False) -> bytes
```

### 3. Device layer (`profiles.py`, `device.py`)

```python
class ProfileCommand(StrEnum): IDENTIFY, ERASE_LOG, RESTORE_DEFAULTS, STORE_LOG_POINT, SYNC_BLE_DATA

class DeviceProfile(ABC):
    family: DeviceFamily
    service_uuid: str
    supported_commands: frozenset[ProfileCommand]
    async def read_device_info(self, client, state: DeviceState) -> None   # DIS + profile version; once
    async def read_state(self, client, state: DeviceState) -> DeviceState  # measurements, battery, settings, time
    async def write_settings(self, client, settings) -> None
    async def send_command(self, client, command: ProfileCommand) -> None
    async def write_time(self, client, when: datetime) -> None

get_profile(family: DeviceFamily) -> DeviceProfile        # raises UnsupportedDeviceError

class KestrelBleDevice:
    def __init__(self, address, family, *, ble_device=None, name=None, max_attempts=...)
    def set_ble_device(self, ble_device) -> None
    state: DeviceState | None
    async def async_poll(self) -> DeviceState              # connect, read, disconnect
    async def async_write_settings(self, settings) -> DeviceState
    async def async_send_command(self, command: ProfileCommand) -> None
    async def async_set_time(self, when: datetime | None = None) -> None
    async def async_run(self, fn: Callable[[BleakClient], Awaitable[T]]) -> T   # serialised connection
```

`client` is any object with `read_gatt_char(uuid)` / `write_gatt_char(uuid, data,
response=True)` / `start_notify` / `stop_notify` / `services`; in production it
is a `BleakClientWithServiceCache` obtained through
`bleak_retry_connector.establish_connection`. Connections are short-lived and
serialised through an `asyncio.Lock`.

### 4. LiNK transport (`transport.py`, `client.py`)

`LinkTransport(client, *, chunk_size=20, timeout=3.0)` subscribes to the P→C
characteristic, writes framed packets in 20-byte zero-padded chunks with
acknowledged writes, reassembles frames with `FrameDecoder`, and acks every
metadata/data packet with `Ack(0xFFFF)`. `send_command(code, params)` returns a
`LinkResponse(ack, metadata, data_packets, end_of_data_params)` or raises
`NackError`/`ResponseTimeoutError`. `LinkClient` wraps it: `get_serial()`,
`get_model()`, `get_firmware()`, `get_hardware()`, `get_name()`, `get_time()`,
`set_time()`, `get_battery()`, `get_data_snapshot() -> LinkRecord | None`,
`get_data_log_record_count()`, `get_data_log(after: int | None) -> DataLogResult`,
`set_log_interval()`, `set_log_wrap()`, `erase_data_log()`.

### 5. Home Assistant layer

* Discovery via `manifest.json` bluetooth matchers (manufacturer id 234, DROP and
  Kestrel service UUIDs). Config entry unique id = BLE address; `data` holds
  `address`, `family`, `model_code`; `options` hold `poll_interval` (seconds,
  default 300, 30–3600).
* `KestrelCoordinator(ActiveBluetoothDataUpdateCoordinator[DeviceState])`:
  `needs_poll` → no poll yet or `poll_age >= poll_interval`; `poll_method` →
  `device.async_poll()`. Initial poll happens in `async_setup_entry` so entities
  can be created from the device's actual measurement set.
* Entities (all `has_entity_name`, unique id `f"{address}_{key}"`):
  * `sensor`: one per present `MeasurementKind`, plus `battery`, `device_time`
    (diagnostic), `signal_strength` (diagnostic, disabled by default).
  * `select.log_interval` (discrete LOG_INTERVALS_S, "off" for 0).
  * `number.transmission_rate` (2–60 s), `number.reference_altitude` (m).
  * `switch.wrap_log`.
  * `button.identify`, `button.sync_time`, `button.erase_log` (disabled by default).
* Writes go through `KestrelBleDevice` and then refresh the coordinator data.
* `kestrel.import_data_log` service (experimental): downloads the LiNK data log
  and imports hourly long-term statistics for the device's measurement sensors.
