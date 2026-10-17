"""GATT UUID helpers for Nielsen-Kellerman LiNK devices.

NK devices expose vendor services built from a 128-bit base with a 16-bit
short id inserted into the third and fourth octets of the UUID string.
"""

from __future__ import annotations

from .const import DeviceFamily

# Vendor UUID bases.  ``XXXX`` is replaced by the 16-bit short id.
DROP_BASE = "1263{short}-cc25-497d-9854-9b6c02c77054"
KESTREL_BASE = "0329{short}-eab4-dea1-b24e-44ec023874db"
MASS_TRANSFER_BASE = "8592{short}-0338-4b83-ae4a-ac1d217adb03"
SUPER_MASS_TRANSFER_BASE = "3749{short}-c0e3-4a13-b487-910812b8182f"
SIG_BASE = "0000{short}-0000-1000-8000-00805f9b34fb"

# Prefix / suffix used to recognise any Mass Transfer UUID regardless of the
# short-id byte order.
MASS_TRANSFER_PREFIX = "8592"
MASS_TRANSFER_SUFFIX = "-0338-4b83-ae4a-ac1d217adb03"
SUPER_MASS_TRANSFER_PREFIX = "3749"
SUPER_MASS_TRANSFER_SUFFIX = "-c0e3-4a13-b487-910812b8182f"


def _fmt(base: str, short: int) -> str:
    if not 0 <= short <= 0xFFFF:
        raise ValueError(f"short id out of range: {short}")
    return base.format(short=f"{short:04x}")


def _swap(short: int) -> int:
    """Swap the two bytes of a 16-bit short id."""
    return ((short & 0xFF) << 8) | ((short >> 8) & 0xFF)


def drop_uuid(short: int) -> str:
    """Return a Kestrel DROP service/characteristic UUID."""
    return _fmt(DROP_BASE, short)


def kestrel_uuid(short: int) -> str:
    """Return a Kestrel 5000-family service/characteristic UUID."""
    return _fmt(KESTREL_BASE, short)


def mass_transfer_uuid(short: int) -> str:
    """Return a Mass Transfer Service UUID (MSB-first reading of the spec)."""
    return _fmt(MASS_TRANSFER_BASE, short)


def mass_transfer_uuid_alt(short: int) -> str:
    """Return the Mass Transfer UUID with the short-id bytes swapped.

    NK's documentation is ambiguous about the byte order of the short id in
    this service, so callers should accept either form.
    """
    return _fmt(MASS_TRANSFER_BASE, _swap(short))


def super_mass_transfer_uuid(short: int) -> str:
    """Return a Super Mass Transfer Service UUID."""
    return _fmt(SUPER_MASS_TRANSFER_BASE, short)


def sig_uuid(short: int) -> str:
    """Return a Bluetooth SIG 16-bit UUID in 128-bit form."""
    return _fmt(SIG_BASE, short)


def is_mass_transfer_uuid(uuid: str) -> bool:
    """Return True if ``uuid`` belongs to the (regular) Mass Transfer Service."""
    u = uuid.lower()
    return u.startswith(MASS_TRANSFER_PREFIX) and u.endswith(MASS_TRANSFER_SUFFIX)


def is_super_mass_transfer_uuid(uuid: str) -> bool:
    """Return True if ``uuid`` belongs to the Super Mass Transfer Service."""
    u = uuid.lower()
    return u.startswith(SUPER_MASS_TRANSFER_PREFIX) and u.endswith(
        SUPER_MASS_TRANSFER_SUFFIX
    )


# --------------------------------------------------------------------------- #
# Services
# --------------------------------------------------------------------------- #

DROP_SERVICE_UUID = drop_uuid(0x0000)
KESTREL_SERVICE_UUID = kestrel_uuid(0x0000)
MASS_TRANSFER_SERVICE_UUID = mass_transfer_uuid(0x0000)
SUPER_MASS_TRANSFER_SERVICE_UUID = super_mass_transfer_uuid(0x52C9)

# Mass transfer characteristics: peripheral->central (indicate), central->peripheral (write)
MASS_TRANSFER_P2C_UUID = mass_transfer_uuid(0x0001)
MASS_TRANSFER_C2P_UUID = mass_transfer_uuid(0x0002)
MASS_TRANSFER_P2C_UUID_ALT = mass_transfer_uuid_alt(0x0001)
MASS_TRANSFER_C2P_UUID_ALT = mass_transfer_uuid_alt(0x0002)
SUPER_MASS_TRANSFER_P2C_UUID = super_mass_transfer_uuid(0x0001)
SUPER_MASS_TRANSFER_C2P_UUID = super_mass_transfer_uuid(0x0002)

# Bluetooth SIG services / characteristics
BATTERY_SERVICE_UUID = sig_uuid(0x180F)
BATTERY_LEVEL_UUID = sig_uuid(0x2A19)
DEVICE_INFO_SERVICE_UUID = sig_uuid(0x180A)
MANUFACTURER_NAME_UUID = sig_uuid(0x2A29)
MODEL_NUMBER_UUID = sig_uuid(0x2A24)
SERIAL_NUMBER_UUID = sig_uuid(0x2A25)
HARDWARE_REVISION_UUID = sig_uuid(0x2A27)
FIRMWARE_REVISION_UUID = sig_uuid(0x2A26)
SOFTWARE_REVISION_UUID = sig_uuid(0x2A28)
GAP_DEVICE_NAME_UUID = sig_uuid(0x2A00)

# --------------------------------------------------------------------------- #
# Kestrel DROP characteristics (short ids)
# --------------------------------------------------------------------------- #

DROP_MEASUREMENT_SHORTS: tuple[int, ...] = tuple(range(0x0001, 0x0010))
DROP_PASSWORD_SHORT = 0x0100
DROP_SETTINGS_SHORT = 0x0101
DROP_COMMANDS_SHORT = 0x0102
DROP_NAME_SHORT = 0x0103
DROP_DATETIME_SHORT = 0x0104
DROP_BUTTON_SHORT = 0x0105
DROP_PROFILE_VERSION_SHORT = 0x0200

DROP_PASSWORD_UUID = drop_uuid(DROP_PASSWORD_SHORT)
DROP_SETTINGS_UUID = drop_uuid(DROP_SETTINGS_SHORT)
DROP_COMMANDS_UUID = drop_uuid(DROP_COMMANDS_SHORT)
DROP_NAME_UUID = drop_uuid(DROP_NAME_SHORT)
DROP_DATETIME_UUID = drop_uuid(DROP_DATETIME_SHORT)
DROP_BUTTON_UUID = drop_uuid(DROP_BUTTON_SHORT)
DROP_PROFILE_VERSION_UUID = drop_uuid(DROP_PROFILE_VERSION_SHORT)

# --------------------------------------------------------------------------- #
# Kestrel 5000-family characteristics (short ids)
# --------------------------------------------------------------------------- #

K5_STATUS1_SHORT = 0x0300
K5_STATUS2_SHORT = 0x0380
K5_SENSOR_SHORT = 0x0310
K5_DERIVED1_SHORT = 0x0320
K5_DERIVED2_SHORT = 0x0330
K5_DERIVED3_SHORT = 0x0340
K5_DERIVED4_SHORT = 0x0350
K5_SETTINGS_SHORT = 0x0101
K5_COMMANDS_SHORT = 0x0102
K5_NAME_SHORT = 0x0103
K5_DATETIME_SHORT = 0x0104
K5_EVENTS_SHORT = 0x0107
K5_PROFILE_VERSION_SHORT = 0x0200

K5_MEASUREMENT_SHORTS: tuple[int, ...] = (
    K5_SENSOR_SHORT,
    K5_DERIVED1_SHORT,
    K5_DERIVED2_SHORT,
    K5_DERIVED3_SHORT,
    K5_DERIVED4_SHORT,
)

K5_STATUS1_UUID = kestrel_uuid(K5_STATUS1_SHORT)
K5_STATUS2_UUID = kestrel_uuid(K5_STATUS2_SHORT)
K5_SETTINGS_UUID = kestrel_uuid(K5_SETTINGS_SHORT)
K5_COMMANDS_UUID = kestrel_uuid(K5_COMMANDS_SHORT)
K5_NAME_UUID = kestrel_uuid(K5_NAME_SHORT)
K5_DATETIME_UUID = kestrel_uuid(K5_DATETIME_SHORT)
K5_EVENTS_UUID = kestrel_uuid(K5_EVENTS_SHORT)
K5_PROFILE_VERSION_UUID = kestrel_uuid(K5_PROFILE_VERSION_SHORT)

# Service UUID -> family (used for discovery by scan response).
SERVICE_FAMILIES: dict[str, DeviceFamily] = {
    DROP_SERVICE_UUID: DeviceFamily.DROP,
    KESTREL_SERVICE_UUID: DeviceFamily.KESTREL_5000,
}
