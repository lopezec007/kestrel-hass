"""Registry of Kestrel / NK device models."""

from __future__ import annotations

from collections.abc import Iterable

from .const import DeviceFamily, ModelCode
from .types import ModelInfo


def _m(code: ModelCode, name: str, family: DeviceFamily, adv: str | None) -> ModelInfo:
    return ModelInfo(code=int(code), name=name, family=family, advertising_name=adv)


_K5 = DeviceFamily.KESTREL_5000
_SC = DeviceFamily.SPEEDCOACH

MODELS: dict[int, ModelInfo] = {
    int(m.code): m
    for m in (
        _m(ModelCode.K5000L, "Kestrel 5000L Environmental Meter", _K5, "ENVIRO"),
        _m(ModelCode.K5100L, "Kestrel 5100L Racing Weather Meter", _K5, "RACING"),
        _m(ModelCode.K5200L, "Kestrel 5200L Professional Meter", _K5, "PRO"),
        _m(ModelCode.K5500L, "Kestrel 5500L Weather Meter", _K5, "WEATHER"),
        _m(ModelCode.K5500XL, "Kestrel 5500XL Weather Meter", _K5, "WEATHER"),
        _m(ModelCode.K5700SL, "Kestrel 5700 Sportsman", _K5, "BALLISTIC"),
        _m(ModelCode.K5700SL_B, "Kestrel 5700 Sportsman (B)", _K5, "BALLISTIC"),
        _m(ModelCode.K5700AL, "Kestrel 5700 Elite", _K5, "ELITE"),
        _m(ModelCode.K5700AL_I, "Kestrel 5700 Elite TacX", _K5, "TACX"),
        _m(ModelCode.K5400CL, "Kestrel 5400 Heat Stress Tracker", _K5, "HEAT"),
        _m(
            ModelCode.K5400AGCL,
            "Kestrel 5400AG Cattle Heat Stress Tracker",
            _K5,
            "CATTLE",
        ),
        _m(ModelCode.K5400FWCL, "Kestrel 5400FW Fire Weather Pro", _K5, "FIRE"),
        _m(ModelCode.K5500FWL, "Kestrel 5500FW Fire Weather Meter", _K5, "FIRE"),
        _m(ModelCode.K5000AGL, "Kestrel 5000AG Livestock Meter", _K5, "LIVESTOCK"),
        _m(ModelCode.K5500AGL, "Kestrel 5500AG Agriculture Meter", _K5, "AGRICULTR"),
        _m(ModelCode.K5700BL, "Kestrel 5700 Ballistics", _K5, "BALLISTIC"),
        _m(ModelCode.K5700AL_TUR, "Kestrel 5700 Elite (TUR)", _K5, "ELITE"),
        _m(ModelCode.K5700SL_R, "Kestrel 5700 Sportsman (R)", _K5, "BALLISTIC"),
        _m(ModelCode.K5700AL_R, "Kestrel 5700 Elite (R)", _K5, "ELITE"),
        _m(ModelCode.K5500CL, "Kestrel 5500 Weather Meter", _K5, "WEATHER"),
        _m(ModelCode.K5700HL, "Kestrel 5700H", _K5, None),
        _m(ModelCode.K5700EL, "Kestrel 5700E", _K5, None),
        _m(ModelCode.K5700XL, "Kestrel 5700X", _K5, None),
        _m(ModelCode.K5700XAL, "Kestrel 5700X Elite", _K5, None),
        _m(ModelCode.K5700XALSF, "Kestrel 5700X Elite SF", _K5, None),
        _m(ModelCode.K5500XCL, "Kestrel 5500X Weather Meter", _K5, "WEATHER"),
        _m(ModelCode.K5700XBL, "Kestrel 5700X Ballistics", _K5, None),
        _m(ModelCode.K5700XEL, "Kestrel 5700X Elite", _K5, None),
        _m(ModelCode.K5700XALW, "Kestrel 5700X Elite W", _K5, None),
        _m(ModelCode.SPEEDCOACH_GPS_BASIC, "SpeedCoach GPS Basic", _SC, "SpdCoach"),
        _m(
            ModelCode.SPEEDCOACH_GPS1_SUP_BASIC,
            "SpeedCoach GPS1 SUP Basic",
            _SC,
            "SpdCoach",
        ),
        _m(ModelCode.SPEEDCOACH_GPS_PRO, "SpeedCoach GPS Pro", _SC, "SpdCoach"),
        _m(ModelCode.SPEEDCOACH_GPS1_SUP_HR, "SpeedCoach GPS1 SUP HR", _SC, "SpdCoach"),
        _m(ModelCode.SPEEDCOACH_GPS2_SUP, "SpeedCoach GPS2 SUP", _SC, "SpdCoach"),
        _m(ModelCode.SPEEDCOACH_GPS2_SUP_TP, "SpeedCoach GPS2 SUP TP", _SC, "SpdCoach"),
        _m(ModelCode.SPEEDCOACH_GPS2_OC, "SpeedCoach GPS2 OC", _SC, "SpdCoach"),
        _m(ModelCode.SPEEDCOACH_GPS2_OC_TP, "SpeedCoach GPS2 OC TP", _SC, "SpdCoach"),
        _m(ModelCode.COXBOX_5, "CoxBox 5", DeviceFamily.COXBOX, None),
        _m(ModelCode.COXBOX_5_GPS, "CoxBox 5 GPS", DeviceFamily.COXBOX, None),
        _m(
            ModelCode.OARLOCK_SWEEP,
            "EmPower Oarlock Sweep",
            DeviceFamily.OARLOCK,
            "EmPower Sweep",
        ),
        _m(
            ModelCode.OARLOCK_SCULL,
            "EmPower Oarlock Scull",
            DeviceFamily.OARLOCK,
            "EmPower Scull",
        ),
        _m(ModelCode.SPEEDCOACH_GPS2_EQUINE, "SpeedCoach GPS2 Equine", _SC, "SpdCoach"),
        _m(
            ModelCode.LINK_ROWING_GATEWAY,
            "LiNK Rowing Gateway",
            DeviceFamily.GATEWAY,
            None,
        ),
        _m(
            ModelCode.LINK_BALLISTICS_ANDROID,
            "LiNK Ballistics (Android)",
            DeviceFamily.UNKNOWN,
            None,
        ),
        _m(
            ModelCode.LINK_BALLISTICS_IOS,
            "LiNK Ballistics (iOS)",
            DeviceFamily.UNKNOWN,
            None,
        ),
        _m(
            ModelCode.K2700,
            "Kestrel 2700 Ballistics Weather Meter",
            DeviceFamily.KESTREL_2700,
            "2700",
        ),
        _m(ModelCode.K3550AG, "Kestrel 3550AG", DeviceFamily.KESTREL_3550, "3550AG"),
        _m(ModelCode.K3550FW, "Kestrel 3550FW", DeviceFamily.KESTREL_3550, "3550FW"),
        _m(ModelCode.HUD_0750L, "Kestrel HUD", DeviceFamily.HUD, "HUD"),
        _m(ModelCode.DROP_1, "Kestrel DROP D1", DeviceFamily.DROP, "D1"),
        _m(ModelCode.DROP_2, "Kestrel DROP D2", DeviceFamily.DROP, "D2"),
        _m(ModelCode.DROP_3, "Kestrel DROP D3", DeviceFamily.DROP, "D3"),
        _m(ModelCode.DROP_3_FIRE, "Kestrel DROP D3 Fire", DeviceFamily.DROP, "D3 FIRE"),
        _m(ModelCode.DROP_2_AG, "Kestrel DROP D2 AG", DeviceFamily.DROP, "D2 AG"),
        _m(
            ModelCode.DROP_1_PROBE,
            "Kestrel DROP D1 Probe",
            DeviceFamily.DROP,
            "D1 PROBE",
        ),
        _m(
            ModelCode.SHOT_TIMER_BASIC,
            "Kestrel KST1000 Shot Timer Basic",
            DeviceFamily.SHOT_TIMER,
            "KST",
        ),
        _m(
            ModelCode.SHOT_TIMER_PRO,
            "Kestrel KST1000 Shot Timer Pro",
            DeviceFamily.SHOT_TIMER,
            "KST",
        ),
        _m(
            ModelCode.CELLULAR_WEATHER_STATION,
            "KestrelMet Cellular Weather Station",
            DeviceFamily.WEATHER_STATION,
            "WS_",
        ),
        _m(
            ModelCode.WIFI_WEATHER_STATION,
            "KestrelMet WiFi Weather Station",
            DeviceFamily.WEATHER_STATION,
            "WS_",
        ),
        _m(
            ModelCode.K7000,
            "Kestrel 7000 Humidity Meter",
            DeviceFamily.KESTREL_7000,
            "HUMIDITY",
        ),
        _m(
            ModelCode.KESTREL_GATEWAY,
            "Kestrel Gateway",
            DeviceFamily.GATEWAY,
            "GATEWAY",
        ),
        _m(
            ModelCode.LASER_RANGE_FINDER,
            "Laser Range Finder",
            DeviceFamily.UNKNOWN,
            None,
        ),
    )
}

# Default advertising-name prefixes -> family, used when no model code is seen.
# Longer prefixes are matched first.
_LOCAL_NAME_PREFIXES: tuple[tuple[str, DeviceFamily], ...] = (
    ("KESTREL DROP", DeviceFamily.DROP),
    ("D1 PROBE", DeviceFamily.DROP),
    ("D2 AG", DeviceFamily.DROP),
    ("D3 FIRE", DeviceFamily.DROP),
    ("D1", DeviceFamily.DROP),
    ("D2", DeviceFamily.DROP),
    ("D3", DeviceFamily.DROP),
    ("ENVIRO", _K5),
    ("LIVESTOCK", _K5),
    ("RACING", _K5),
    ("PRO", _K5),
    ("HEAT", _K5),
    ("FIRE", _K5),
    ("CATTLE", _K5),
    ("WEATHER", _K5),
    ("AGRICULTR", _K5),
    ("BALLISTIC", _K5),
    ("ELITE", _K5),
    ("TACX", _K5),
    ("K5", _K5),
    ("HUMIDITY", DeviceFamily.KESTREL_7000),
    ("K7000", DeviceFamily.KESTREL_7000),
    ("3550AG", DeviceFamily.KESTREL_3550),
    ("3550FW", DeviceFamily.KESTREL_3550),
    ("3550", DeviceFamily.KESTREL_3550),
    ("2700", DeviceFamily.KESTREL_2700),
    ("HUD", DeviceFamily.HUD),
    ("SPDCOACH", _SC),
    ("EMPOWER", DeviceFamily.OARLOCK),
    ("KST", DeviceFamily.SHOT_TIMER),
    ("WS_", DeviceFamily.WEATHER_STATION),
    ("GATEWAY", DeviceFamily.GATEWAY),
)


def model_from_code(code: int | None) -> ModelInfo | None:
    """Return the ModelInfo for a scan-response model code, if known."""
    if code is None:
        return None
    return MODELS.get(int(code))


def family_from_model_code(code: int | None) -> DeviceFamily:
    """Return the DeviceFamily for a model code (UNKNOWN if not registered)."""
    info = model_from_code(code)
    return info.family if info is not None else DeviceFamily.UNKNOWN


def family_from_service_uuids(uuids: Iterable[str]) -> DeviceFamily | None:
    """Infer the family from advertised service UUIDs."""
    from .uuids import SERVICE_FAMILIES  # noqa: PLC0415

    for uuid in uuids:
        family = SERVICE_FAMILIES.get(uuid.lower())
        if family is not None:
            return family
    return None


def family_from_local_name(name: str | None) -> DeviceFamily | None:
    """Infer the family from the advertised local name prefix."""
    if not name:
        return None
    upper = name.strip().upper()
    for prefix, family in _LOCAL_NAME_PREFIXES:
        if upper.startswith(prefix):
            # Guard against unrelated names such as "D3xxx" by requiring a
            # separator or end of string after the two-character DROP prefixes.
            rest = upper[len(prefix) :]
            if prefix in ("D1", "D2", "D3") and rest and rest[0] not in " -_":
                continue
            return family
    return None
