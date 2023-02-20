from collections import defaultdict

MQTT_TOPIC_PREFIX = "homeassistant"
CAN_CMD_BIT = 0x8

PROPERTY_STATE0 = 0
PROPERTY_STATE1 = 1
PROPERTY_STATE2 = 2
PROPERTY_STATE3 = 3

PROPERTY_CMD0 = 4
PROPERTY_CMD1 = 5
PROPERTY_CMD2 = 6
PROPERTY_CMD3 = 7

PROPERTY_CONFIG = 8
PROPERTY_CONFIG_NAME = 9
PROPERTY_CONFIG_NAME2 = 10
PROPERTY_CONFIG_UNIT = 11


ENTITY_TYPE_SENSOR = 0
ENTITY_TYPE_BINARY_SENSOR = 1
ENTITY_TYPE_SWITCH = 2
ENTITY_TYPE_COVER = 3
ENTITY_TYPE_CAN_STATUS = 254
ENTITY_TYPE_OTA = 255

DEVICE_CLASS = {
    "sensor": {
        1: "apparent_power",
        2: "aqi",
        3: "atmospheric_pressure",
        4: "battery",
        5: "carbon_dioxide",
        6: "carbon_monoxide",
        7: "current",
        8: "data_rate",
        9: "data_size",
        10: "date",
        11: "distance",
        12: "duration",
        13: "energy",
        14: "enum",
        15: "frequency",
        16: "gas",
        17: "humidity",
        18: "illuminance",
        19: "irradiance",
        20: "moisture",
        21: "monetary",
        22: "nitrogen_dioxide",
        23: "nitrogen_monoxide",
        24: "nitrous_oxide",
        25: "ozone",
        26: "pm1",
        27: "pm10",
        28: "pm25",
        29: "power_factor",
        30: "power",
        31: "precipitation",
        32: "precipitation_intensity",
        33: "pressure",
        34: "reactive_power",
        35: "signal_strength",
        36: "sound_pressure",
        37: "speed",
        38: "sulphur_dioxide",
        39: "temperature",
        40: "timestamp",
        41: "volatile_organic_compounds",
        42: "voltage",
        43: "volume",
        44: "water",
        45: "weight",
        46: "wind_speed",
    },
    "cover": {
        1: "awning",
        2: "blind",
        3: "curtain",
        4: "damper",
        5: "door",
        6: "garage",
        7: "gate",
        8: "shade",
        9: "shutter",
        10: "window",
    },
    "binary_sensor": {
        1: "battery",
        2: "battery_charging",
        3: "carbon_monoxide",
        4: "cold",
        5: "connectivity",
        6: "door",
        7: "garage_door",
        8: "gas",
        9: "heat",
        10: "light",
        11: "lock",
        12: "moisture",
        13: "motion",
        14: "moving",
        15: "occupancy",
        16: "opening",
        17: "plug",
        18: "power",
        19: "presence",
        20: "problem",
        21: "running",
        22: "safety",
        23: "smoke",
        24: "sound",
        25: "tamper",
        26: "update",
        27: "vibration",
        28: "window",
    },
}

STATE_CLASS = {
    1: "measurement",
    2: "total",
    3: "total_increasing",
}
