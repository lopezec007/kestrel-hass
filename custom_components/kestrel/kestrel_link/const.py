"""Protocol constants for Nielsen-Kellerman LiNK devices.

Values here are derived from NK's LiNK Communications Protocol (doc 355204)
and Kestrel Weather Protocol (doc 355207).  Only the numeric codes are
reproduced; see the NK developer documentation for the full specification.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Final, Literal

# Bluetooth SIG company identifier assigned to Nielsen-Kellerman.
NK_COMPANY_ID = 0x00EA

# Little-endian byte order is used for every multi-byte value on the wire.
BYTE_ORDER: Final[Literal["little"]] = "little"

# Mass Transfer Service chunking.
MASS_TRANSFER_CHUNK_SIZE = 20
SUPER_MASS_TRANSFER_CHUNK_SIZE = 244

# Device statistics that matter to the transport (DROP family).
DROP_MAX_HDLC_FRAME = 256
DROP_MAX_PACKET = 128
DROP_PACKET_TIMEOUT_S = 3.0
# Kestrel 5000 family allows larger frames.
K5_MAX_HDLC_FRAME = 512
K5_MAX_PACKET = 256
K5_PACKET_TIMEOUT_S = 3.0
K5_COMMAND_RESPONSE_TIMEOUT_S = 7.0

# "No command" sentinel used in Ack/Nack packets.
NO_COMMAND = 0xFFFF
# "None" sentinel for field name / unit codes.
NO_FIELD = 0xFFFF


class PacketType(IntEnum):
    """LiNK packet type codes."""

    COMMAND = 0
    METADATA_START = 1
    METADATA = 2
    DATA = 3
    ACK = 4
    NACK = 5


class NackReason(IntEnum):
    """LiNK Nack reason codes."""

    BAD_CHECKSUM = 0
    SHORT_PACKET = 1
    PACKET_TIMEOUT = 2
    BAD_COMMAND = 3
    UNEXPECTED_PACKET_TYPE = 4
    NOT_IN_BOOTLOADER_MODE = 5
    INVALID_PACKET_SEQUENCE = 6
    BOOTLOADER_FLASH_IO_ERROR = 7
    BOOTLOADER_MODEL_ERROR = 8
    BOOTLOADER_SERIAL_ERROR = 9
    FEATURE_NOT_PRESENT = 10
    BAD_DATA = 11
    DATA_NOT_AVAILABLE = 12
    FEATURE_NOT_AVAILABLE = 13
    UNSPECIFIED_ERROR = 14
    INVALID_ADVERTISING_DATA = 15
    SOFTDEVICE_BUSY = 16
    INVALID_STATE = 17


class CommandCode(IntEnum):
    """LiNK command codes used by the weather product lines."""

    # Weather protocol (355207)
    GET_DATA_SNAPSHOT = 0
    ERASE_DATA_LOG = 1
    GET_DATA_LOG_RECORD_COUNT = 2
    GET_DATA_LOG_RECORD_COUNT_AFTER = 3
    GET_DATA_LOG = 4
    GET_DATA_LOG_AFTER = 5
    # General LiNK (355204)
    GET_DEVICE_SERIAL = 6
    GET_DEVICE_MODEL = 7
    GET_DEVICE_FIRMWARE = 8
    GET_DEVICE_HARDWARE = 9
    GET_DEVICE_NAME = 10
    SET_DEVICE_NAME = 11
    GET_AUTOSTORE = 12
    SET_AUTOSTORE = 13
    GET_TIME = 14
    SET_TIME = 15
    END_OF_DATA = 18
    GET_BATTERY_LEVEL = 20
    SET_LOG_INTERVAL = 26
    SET_LOG_WRAP_ENABLE = 27
    GET_MAGNETOMETER_CAL_BUFFER = 30
    OUTPUT_RAW_COMPASS_DATA = 31
    GET_HEAT_STRESS_SETTING = 32
    SET_HEAT_STRESS_SETTING = 33
    GET_EEPROM_VERSION_NUMBERS = 34
    RESET_CONFIG_DEFAULTS = 37
    BLUETOOTH_PERIPHERAL_MODE = 48
    BLUETOOTH_CENTRAL_MODE = 49
    GET_BLUETOOTH_PROFILE_VERSION = 50
    START_SLEEP = 51
    GET_BLE_MODE = 71
    SET_BLE_MODE = 72
    GET_CONTRAST_PERCENT = 80
    SET_CONTRAST_PERCENT = 81
    GET_BACKLIGHT_COLOR = 82
    SET_BACKLIGHT_COLOR = 83
    GET_LANGUAGE = 84
    SET_LANGUAGE = 85
    GET_BATTERY_CHEMISTRY = 86
    SET_BATTERY_CHEMISTRY = 87
    GET_AUTO_SHUTDOWN = 88
    SET_AUTO_SHUTDOWN = 89
    SET_CONNECTION_PARAMETERS = 93
    GET_DIAGNOSTICS = 106
    LOCK_PERIPHERAL_DEVICE = 125
    REQUEST_TO_AUTHENTICATE = 126
    AUTHENTICATION_CHALLENGE = 127
    GET_LOCK_ID = 128
    GET_PRIVACY_MODE_STATUS = 129
    AUTHENTICATE_PRIVACY_MODE = 130
    STOP_ENCRYPTING_CONNECTION = 131
    GET_SETTINGS = 132
    SET_SETTINGS = 133
    START_STOP_STREAMING = 146
    GET_ACTIVE_INDEX = 148
    SET_ACTIVE_INDEX = 149
    ECHO_TEST_PACKET = 154
    SET_ATTITUDE_LOG = 155
    SET_CAN_ID = 156
    ENABLE_NKPEX = 157
    GET_SCREEN_MODE = 162
    SET_SCREEN_MODE = 163
    SYSTEM_EVENT = 164
    FREE_TO_COMMUNICATE = 168
    KEEP_ALIVE = 169
    GET_SUPPORTED_UNITS = 172
    GET_UNITS = 173
    SET_UNITS = 174
    GET_THI_MODEL = 175
    SET_THI_MODEL = 176
    GET_WEATHER_STATION_DIAGNOSTICS = 179
    GET_DEVICE_STATUS = 180
    GET_CHARGER_VERSION = 182
    GET_BLE_ADDRESS = 191
    NO_COMMAND = 0xFFFF


class FieldName(IntEnum):
    """LiNK field name codes (Table 12 of 355204)."""

    TIMESTAMP = 0
    BATTERY_PERCENTAGE = 1
    DRY_BULB_TEMP = 2
    WET_BULB_TEMP = 3
    GLOBE_TEMP_6IN = 4
    RELATIVE_HUMIDITY = 5
    BAROMETRIC_PRESSURE = 6
    ALTITUDE = 7
    STATION_PRESSURE = 8
    WIND_SPEED = 9
    HEAT_INDEX = 10
    DEW_POINT = 11
    MOISTURE_CONTENT = 12
    HUMIDITY_RATIO = 13
    DENSITY_ALTITUDE = 14
    RELATIVE_AIR_DENSITY = 15
    AIR_FLOW = 16
    RESERVED_17 = 17
    AIR_SPEED = 18
    CROSSWIND = 20
    EVAPORATION_RATE = 21
    HEADWIND = 22
    COMPASS_MAGNETIC_DIRECTION = 23
    NATURALLY_ASPIRATED_WET_BULB = 24
    COMPASS_TRUE_DIRECTION = 25
    THERMAL_WORK_LIMIT = 26
    WET_BULB_GLOBE_TEMP = 27
    WIND_CHILL = 28
    DELTA_T = 29
    AIR_DENSITY = 30
    GLOBE_TEMP_1IN = 31
    HUMIDITY_TEMP = 32
    HUMIDITY_THERMISTOR_TEMP = 33
    AVERAGE_NORMAL_FORCE = 34
    RELATIVE_WORK_PER_STROKE = 35
    DRIVE_TIME = 37
    CATCH_ANGLE = 38
    FINISH_ANGLE = 39
    MAX_FORCE = 40
    FORCE_GRADIENT_CATCH = 41
    PEAK_FORCE_AT = 42
    FORCE_GRADIENT_FINISH = 43
    DETAILED_MEASUREMENTS_TIMESTAMP = 44
    NORMAL_FORCE = 45
    AXIAL_FORCE = 46
    ANGULAR_OAR_POSITION = 47
    ANGULAR_OAR_SPEED = 48
    STROKE_CATCH_TIMESTAMP = 49
    CYCLE_TIME = 50
    LOCK_ANGLE = 51
    UNLOCK_ANGLE = 52
    OARLOCK_SIDE = 53
    BOAT_ID = 54
    SEAT_NUMBER = 55
    OAR_LENGTH = 56
    INBOARD_LENGTH = 57
    TEMPERATURE_HUMIDITY_INDEX = 58
    HEAT_LOAD_INDEX = 59
    RANGE = 60
    INCLINATION_ANGLE = 61
    DIRECTION_OF_FIRE = 62
    ELEVATION = 63
    WINDAGE = 64
    PROBABILITY_OF_IGNITION = 65
    THI_NRC = 66
    THI_YOUSEF = 67
    AHLU_1 = 68
    AHLU_2 = 69
    AHLU_3 = 70
    CRC_CHECKSUM = 71
    BYTE_PAD = 72
    DISCOMFORT_INDEX = 73
    MAX_WIND_SPEED = 74
    AVG_WIND_SPEED = 75
    RAW_RH = 76
    TEMP_CORRECTED_RH = 77
    LATITUDE = 78
    TARGET_SPEED = 79
    TARGET_MOVEMENT_DIRECTION = 80
    WIND_DIRECTION = 81
    BULLET_DROP = 82
    TARGET_LEAD = 83
    TIME_OF_FLIGHT = 84
    REMAINING_ENERGY = 85
    REMAINING_VELOCITY = 86
    SPIN_DRIFT = 87
    HORIZONTAL_CORIOLIS = 88
    VERTICAL_CORIOLIS = 89
    AERODYNAMIC_JUMP = 90
    TRACE = 91
    MAX_ORDINATE = 92
    TRANSONIC_RANGE = 93
    SUBSONIC_RANGE = 94
    FLAGS_16 = 95
    BATTERY_VOLTAGE = 96
    BATTERY_TEMPERATURE = 97
    BATTERY_CHARGE_CURRENT = 98
    PROCESSOR_TEMPERATURE = 99
    MUZZLE_VELOCITY = 100
    MAGNETOMETER_RAW_X = 101
    MAGNETOMETER_RAW_Y = 102
    MAGNETOMETER_RAW_Z = 103
    DATA_LOG_INTERVAL = 104
    WRAP_LOG = 105
    MEASUREMENT_TRANSMISSION_RATE = 106
    SECURITY_LEVEL = 107
    SETUP_COMPLETE = 108
    REFERENCE_ALTITUDE = 109
    AUTO_SHUTDOWN_TIMEOUT = 110
    ERASE_DATA_LOG = 111
    BLINK_LED = 112
    RESTORE_DEFAULTS = 113
    WIND_SPEED_UNITS = 114
    TEMPERATURE_UNITS = 115
    TEMPERATURE_DIFFERENCE_UNITS = 116
    PRESSURE_UNITS = 117
    ALTITUDE_UNITS = 118
    AIRFLOW_UNITS = 119
    MOISTURE_CONTENT_UNITS = 120
    EVAPORATION_RATE_UNITS = 121
    AIR_DENSITY_UNITS = 122
    AIR_DUCT_UNITS = 123
    DIRECTION_UNITS = 124
    VISUAL_IDENTIFY_MODE = 125
    EVENT_ENVIRO_CAPTURE = 126
    DYNAMIC_VARIABLE = 127
    PRIORITY_DEVICE = 128
    PRECIPITATION = 129
    PANEL_VOLTAGE = 130
    SOLAR_RADIATION = 131
    LEAF_WETNESS = 132
    SOIL_TENSION_1 = 133
    SOIL_TENSION_2 = 134
    SOIL_TENSION_3 = 135
    SOIL_TENSION_4 = 136
    SOIL_TEMPERATURE_1 = 137
    SOIL_TEMPERATURE_2 = 138
    SOIL_TEMPERATURE_3 = 139
    SOIL_TEMPERATURE_4 = 140
    EVENT_LOCAL_START = 141
    EVENT_STRING_READY = 142
    DRY_BULB_RAW_COUNTS = 143
    GLOBE_RAW_COUNTS = 144
    HS_DRY_BULB_TEMPERATURE = 145
    VAPOR_PRESSURE_DEFICIT = 146
    EVENT_MUTE_TIMER = 147
    EVENT_UNMUTE_TIMER = 148
    EVENT_INVALID_STRING = 149
    EVENT_ACTIVE_STRING_IDS_READY = 150
    HUMIDEX_CANADA = 151
    NONE = 0xFFFF


class FieldUnit(IntEnum):
    """LiNK field unit codes (Table 13 of 355204).

    Codes below 70 (and a few above) describe the *wire encoding* of a value
    (integer width, signedness and scaling).  Codes marked "no precision" in
    the specification only identify a display unit and carry no scaling; they
    are used by the Get/Set Units commands.
    """

    UINT8 = 0
    INT8 = 1
    UINT16 = 2
    INT16 = 3
    UINT32 = 4
    INT32 = 5
    UINT64 = 6
    INT64 = 7
    FLOAT32 = 8
    FLOAT64 = 9
    ASCII_STRING = 10
    SECONDS = 25
    GPS_TIME = 26
    PERCENT_X100_U16 = 27
    DEGREES_C_X100_I16 = 28
    MILLIBAR_X10_U16 = 31
    BLUETOOTH_DATE_TIME = 36
    METERS_X100_I24 = 37
    GRAMS_PER_KG_X100_U24 = 38
    KG_PER_M3_X1000_U16 = 39
    NEWTONS_X10_I16 = 40
    ARC_DEGREES_X100_I16 = 41
    ARC_DEGREES_PER_SEC_X100_I16 = 42
    MILLISECONDS_U16 = 43
    M3_PER_S_X1000_U24 = 44
    JOULES_X10_U16 = 45
    ARC_DEGREES_I8 = 46
    ARC_DEGREES_U8 = 47
    WATTS_X10_U16 = 48
    KG_PER_M2_PER_H_X100_U16 = 53
    M_PER_S_X1000_U16 = 56
    PERCENT_X10_U16 = 57
    DEGREES_DIRECTION = 59
    METERS_X10_I24 = 60
    W_PER_M2_X10_U16 = 61
    DEGREES_C_X100_I24 = 62
    M_PER_S_X1000_I24 = 63
    DIFF_DEGREES_C_X100_I16 = 64
    CENTIMETERS_X10_U16 = 65
    METERS_X100_U24 = 66
    YARDS_UNKNOWN = 67
    DEGREES_X1000_I24 = 68
    UNITLESS_X100_I16 = 69
    METERS_NP = 70
    YARDS_NP = 71
    DEGREES_NP = 72
    OCLOCK_NP = 73
    MILS_NP = 74
    SMOA_NP = 75
    TMOA_NP = 76
    CLICKS_MILS_NP = 77
    CLICKS_SMOA_NP = 78
    CLICKS_TMOA_NP = 79
    CENTIMETERS_NP = 80
    INCHES_NP = 81
    METERS_PER_SECOND_NP = 82
    MILLIBAR_X100_U24 = 83
    VOLTS_X1000_U16 = 84
    MILLIAMPS_I16 = 85
    KM_PER_HOUR_NP = 86
    MILES_PER_HOUR_NP = 87
    FEET_PER_SECOND_NP = 88
    KNOTS_NP = 89
    JOULES_NP = 90
    FOOT_POUNDS_NP = 91
    FEET_NP = 92
    UINT24 = 93
    METERS_I16 = 94
    MILLIMETERS_NP = 95
    CELSIUS_NP = 96
    FAHRENHEIT_NP = 97
    CELSIUS_DIFFERENCE_NP = 98
    FAHRENHEIT_DIFFERENCE_NP = 99
    WATTS_PER_M2_NP = 100
    PERCENT_NP = 101
    MILLIBARS_NP = 102
    INCH_HG_NP = 103
    HECTOPASCAL_NP = 104
    PSI_NP = 105
    GAUSS_NP = 106
    ACCEL_GRAVITY_NP = 107
    FEET_PER_MINUTE_NP = 108
    BEAUFORT_NP = 109
    CUBIC_FEET_PER_MINUTE_NP = 110
    M3_PER_HOUR_NP = 111
    M3_PER_MINUTE_NP = 112
    M3_PER_SECOND_NP = 113
    LITER_PER_SECOND_NP = 114
    LB_PER_FT2_PER_HOUR_NP = 115
    KG_PER_M2_PER_HOUR_NP = 116
    GRAINS_PER_POUND_NP = 117
    GRAMS_PER_KG_NP = 118
    GRAMS_NP = 119
    UNITLESS_THI_NP = 120
    UNITLESS_AHLU_NP = 121
    KG_PER_M3_NP = 122
    LB_PER_FT3_NP = 123
    KELVIN_NP = 124
    KELVIN_DIFFERENCE_NP = 125
    MILLIMETERS_X10_U16 = 126
    WET_DRY = 127
    SOIL_TENSION = 128
    DEGREES_C_X10_I16 = 129
    DEGREES_F_X10_I16 = 130
    KILOPASCAL_NP = 131
    JOULES_PER_M2_NP = 132
    NONE = 0xFFFF


class ModelCode(IntEnum):
    """Scan response model codes (Table 14 of 355204)."""

    K5000L = 1
    K5100L = 2
    K5200L = 3
    K5500L = 5
    K5500XL = 6
    K5700SL = 8
    K5700SL_B = 9
    K5700AL = 10
    K5700AL_I = 11
    K5400CL = 14
    K5400AGCL = 15
    K5400FWCL = 16
    K5500FWL = 17
    K5000AGL = 18
    K5500AGL = 19
    K5700BL = 20
    K5700AL_TUR = 21
    K5700SL_R = 22
    K5700AL_R = 23
    K5500CL = 24
    K5700HL = 25
    K5700EL = 26
    K5700XL = 27
    K5700XAL = 28
    K5700XALSF = 29
    K5500XCL = 30
    K5700XBL = 31
    K5700XEL = 32
    K5700XALW = 33
    SPEEDCOACH_GPS_BASIC = 128
    SPEEDCOACH_GPS1_SUP_BASIC = 129
    SPEEDCOACH_GPS_PRO = 130
    SPEEDCOACH_GPS1_SUP_HR = 131
    SPEEDCOACH_GPS2_SUP = 132
    SPEEDCOACH_GPS2_SUP_TP = 133
    SPEEDCOACH_GPS2_OC = 134
    SPEEDCOACH_GPS2_OC_TP = 135
    COXBOX_5 = 136
    COXBOX_5_GPS = 137
    OARLOCK_SWEEP = 138
    OARLOCK_SCULL = 139
    SPEEDCOACH_GPS2_EQUINE = 140
    LINK_ROWING_GATEWAY = 256
    LINK_BALLISTICS_ANDROID = 257
    LINK_BALLISTICS_IOS = 258
    K2700 = 320
    K3550AG = 321
    K3550FW = 322
    HUD_0750L = 448
    DROP_1 = 550
    DROP_2 = 551
    DROP_3 = 552
    DROP_3_FIRE = 553
    DROP_2_AG = 554
    DROP_1_PROBE = 555
    SHOT_TIMER_BASIC = 656
    SHOT_TIMER_PRO = 657
    CELLULAR_WEATHER_STATION = 756
    WIFI_WEATHER_STATION = 757
    K7000 = 856
    KESTREL_GATEWAY = 956
    LASER_RANGE_FINDER = 65499


class DeviceFamily(StrEnum):
    """Product families that share a BLE profile / command subset."""

    DROP = "drop"
    KESTREL_5000 = "kestrel_5000"
    KESTREL_7000 = "kestrel_7000"
    KESTREL_3550 = "kestrel_3550"
    KESTREL_2700 = "kestrel_2700"
    HUD = "hud"
    SPEEDCOACH = "speedcoach"
    OARLOCK = "oarlock"
    COXBOX = "coxbox"
    SHOT_TIMER = "shot_timer"
    WEATHER_STATION = "weather_station"
    GATEWAY = "gateway"
    UNKNOWN = "unknown"


# Families this integration knows how to read measurements from.
WEATHER_FAMILIES = frozenset(
    {
        DeviceFamily.DROP,
        DeviceFamily.KESTREL_5000,
        DeviceFamily.KESTREL_7000,
        DeviceFamily.KESTREL_3550,
    }
)


class MeasurementKind(StrEnum):
    """Normalised measurement identifiers shared by every Kestrel family.

    The string value doubles as the Home Assistant translation / unique-id
    key, so it must stay stable once released.
    """

    TEMPERATURE = "temperature"  # dry bulb
    RELATIVE_HUMIDITY = "relative_humidity"
    HEAT_INDEX = "heat_index"  # "Heat Stress Index" on the DROP
    DEW_POINT = "dew_point"
    WET_BULB_TEMPERATURE = "wet_bulb_temperature"  # psychrometric wet bulb
    DELTA_T = "delta_t"
    STATION_PRESSURE = "station_pressure"
    BAROMETRIC_PRESSURE = "barometric_pressure"
    PRESSURE_TREND = "pressure_trend"
    DENSITY_ALTITUDE = "density_altitude"
    HUMIDITY_RATIO = "humidity_ratio"
    MOISTURE_CONTENT = "moisture_content"
    RELATIVE_AIR_DENSITY = "relative_air_density"
    THI_NRC = "thi_nrc"
    THI_YOUSEF = "thi_yousef"
    # Kestrel 5000-family extras
    WIND_SPEED = "wind_speed"
    GLOBE_TEMPERATURE = "globe_temperature"
    MAGNETIC_DIRECTION = "magnetic_direction"
    TRUE_DIRECTION = "true_direction"
    AIR_DENSITY = "air_density"
    ALTITUDE = "altitude"
    CROSSWIND = "crosswind"
    HEADWIND = "headwind"
    EVAPORATION_RATE = "evaporation_rate"
    THERMAL_WORK_LIMIT = "thermal_work_limit"
    WET_BULB_GLOBE_TEMPERATURE = "wet_bulb_globe_temperature"
    NATURALLY_ASPIRATED_WET_BULB = "naturally_aspirated_wet_bulb"
    WIND_CHILL = "wind_chill"
    AIR_SPEED = "air_speed"
    AIR_FLOW = "air_flow"
    HEAT_LOAD_INDEX = "heat_load_index"
    PROBABILITY_OF_IGNITION = "probability_of_ignition"
    AHLU_1 = "ahlu_1"
    AHLU_2 = "ahlu_2"
    AHLU_3 = "ahlu_3"
    VAPOR_PRESSURE_DEFICIT = "vapor_pressure_deficit"
    HUMIDEX = "humidex"
    DISCOMFORT_INDEX = "discomfort_index"


class NativeUnit(StrEnum):
    """Units in which LiNK devices transmit measurements (always metric)."""

    CELSIUS = "°C"
    PERCENT = "%"
    HPA = "hPa"
    METERS = "m"
    GRAMS_PER_KG = "g/kg"
    METERS_PER_SECOND = "m/s"
    DEGREES = "°"
    KG_PER_M3 = "kg/m³"
    KG_PER_M2_PER_HOUR = "kg/m²/h"
    WATTS_PER_M2 = "W/m²"
    M3_PER_SECOND = "m³/s"
    UNITLESS = ""


# Measurement kind -> (LiNK field name code, native unit).  The field name code
# is what appears in LiNK metadata packets (data snapshot / data log).
MEASUREMENT_FIELDS: dict[MeasurementKind, tuple[FieldName, NativeUnit]] = {
    MeasurementKind.TEMPERATURE: (FieldName.DRY_BULB_TEMP, NativeUnit.CELSIUS),
    MeasurementKind.RELATIVE_HUMIDITY: (
        FieldName.RELATIVE_HUMIDITY,
        NativeUnit.PERCENT,
    ),
    MeasurementKind.HEAT_INDEX: (FieldName.HEAT_INDEX, NativeUnit.CELSIUS),
    MeasurementKind.DEW_POINT: (FieldName.DEW_POINT, NativeUnit.CELSIUS),
    MeasurementKind.WET_BULB_TEMPERATURE: (FieldName.WET_BULB_TEMP, NativeUnit.CELSIUS),
    MeasurementKind.DELTA_T: (FieldName.DELTA_T, NativeUnit.CELSIUS),
    MeasurementKind.STATION_PRESSURE: (FieldName.STATION_PRESSURE, NativeUnit.HPA),
    MeasurementKind.BAROMETRIC_PRESSURE: (
        FieldName.BAROMETRIC_PRESSURE,
        NativeUnit.HPA,
    ),
    MeasurementKind.PRESSURE_TREND: (FieldName.NONE, NativeUnit.HPA),
    MeasurementKind.DENSITY_ALTITUDE: (FieldName.DENSITY_ALTITUDE, NativeUnit.METERS),
    MeasurementKind.HUMIDITY_RATIO: (FieldName.HUMIDITY_RATIO, NativeUnit.GRAMS_PER_KG),
    MeasurementKind.MOISTURE_CONTENT: (
        FieldName.MOISTURE_CONTENT,
        NativeUnit.GRAMS_PER_KG,
    ),
    MeasurementKind.RELATIVE_AIR_DENSITY: (
        FieldName.RELATIVE_AIR_DENSITY,
        NativeUnit.PERCENT,
    ),
    MeasurementKind.THI_NRC: (FieldName.THI_NRC, NativeUnit.UNITLESS),
    MeasurementKind.THI_YOUSEF: (FieldName.THI_YOUSEF, NativeUnit.UNITLESS),
    MeasurementKind.WIND_SPEED: (FieldName.WIND_SPEED, NativeUnit.METERS_PER_SECOND),
    MeasurementKind.GLOBE_TEMPERATURE: (FieldName.GLOBE_TEMP_6IN, NativeUnit.CELSIUS),
    MeasurementKind.MAGNETIC_DIRECTION: (
        FieldName.COMPASS_MAGNETIC_DIRECTION,
        NativeUnit.DEGREES,
    ),
    MeasurementKind.TRUE_DIRECTION: (
        FieldName.COMPASS_TRUE_DIRECTION,
        NativeUnit.DEGREES,
    ),
    MeasurementKind.AIR_DENSITY: (FieldName.AIR_DENSITY, NativeUnit.KG_PER_M3),
    MeasurementKind.ALTITUDE: (FieldName.ALTITUDE, NativeUnit.METERS),
    MeasurementKind.CROSSWIND: (FieldName.CROSSWIND, NativeUnit.METERS_PER_SECOND),
    MeasurementKind.HEADWIND: (FieldName.HEADWIND, NativeUnit.METERS_PER_SECOND),
    MeasurementKind.EVAPORATION_RATE: (
        FieldName.EVAPORATION_RATE,
        NativeUnit.KG_PER_M2_PER_HOUR,
    ),
    MeasurementKind.THERMAL_WORK_LIMIT: (
        FieldName.THERMAL_WORK_LIMIT,
        NativeUnit.WATTS_PER_M2,
    ),
    MeasurementKind.WET_BULB_GLOBE_TEMPERATURE: (
        FieldName.WET_BULB_GLOBE_TEMP,
        NativeUnit.CELSIUS,
    ),
    MeasurementKind.NATURALLY_ASPIRATED_WET_BULB: (
        FieldName.NATURALLY_ASPIRATED_WET_BULB,
        NativeUnit.CELSIUS,
    ),
    MeasurementKind.WIND_CHILL: (FieldName.WIND_CHILL, NativeUnit.CELSIUS),
    MeasurementKind.AIR_SPEED: (FieldName.AIR_SPEED, NativeUnit.METERS_PER_SECOND),
    MeasurementKind.AIR_FLOW: (FieldName.AIR_FLOW, NativeUnit.M3_PER_SECOND),
    MeasurementKind.HEAT_LOAD_INDEX: (FieldName.HEAT_LOAD_INDEX, NativeUnit.UNITLESS),
    MeasurementKind.PROBABILITY_OF_IGNITION: (
        FieldName.PROBABILITY_OF_IGNITION,
        NativeUnit.PERCENT,
    ),
    MeasurementKind.AHLU_1: (FieldName.AHLU_1, NativeUnit.UNITLESS),
    MeasurementKind.AHLU_2: (FieldName.AHLU_2, NativeUnit.UNITLESS),
    MeasurementKind.AHLU_3: (FieldName.AHLU_3, NativeUnit.UNITLESS),
    MeasurementKind.VAPOR_PRESSURE_DEFICIT: (
        FieldName.VAPOR_PRESSURE_DEFICIT,
        NativeUnit.HPA,
    ),
    MeasurementKind.HUMIDEX: (FieldName.HUMIDEX_CANADA, NativeUnit.UNITLESS),
    MeasurementKind.DISCOMFORT_INDEX: (FieldName.DISCOMFORT_INDEX, NativeUnit.CELSIUS),
}

# Reverse lookup used when decoding LiNK records.
FIELD_TO_MEASUREMENT: dict[FieldName, MeasurementKind] = {
    field: kind
    for kind, (field, _unit) in MEASUREMENT_FIELDS.items()
    if field is not FieldName.NONE
}

# Log intervals (seconds) accepted by the Set Log Interval command on the
# DROP and Kestrel 5000 families.  0 disables logging.
LOG_INTERVALS_S: tuple[int, ...] = (
    0,
    2,
    5,
    10,
    20,
    30,
    60,
    120,
    300,
    360,
    600,
    1200,
    1800,
    3600,
    7200,
    21600,
    43200,
)
