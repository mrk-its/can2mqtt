# can2mqtt developer documentation

User-facing documentation (installation, CAN OTA) is in the top-level [README](../README.md).
This folder is for people working on can2mqtt itself.

| Document | Contents |
|---|---|
| [architecture.md](architecture.md) | Runtime overview: main loop, node lifecycle, MQTT topics, SDO concurrency rules |
| [parallel-registration.md](parallel-registration.md) | Parallel node registration at startup and heartbeat tracking |

## Module map

| Path | Role |
|---|---|
| `src/main.py` | CLI (`can2mqtt` entry point): parses arguments, merges them with python-can config, runs `can2mqtt.start()` |
| `src/can2mqtt/can2mqtt.py` | Main loop: CAN network, node discovery and registration, MQTT command handling, firmware upload |
| `src/can2mqtt/entities.py` | Entity classes (sensor, switch, light, cover, …) keyed by entity type id; Home Assistant MQTT discovery config, state / command topic mapping |
| `src/can2mqtt/remote_logs.py` | ESPHome remote logs read from the node over SDO (OD 0x3100) |
| `src/can2mqtt/firmware_scanner.py` | Watches the firmware directory (inotify), extracts node id and version from firmware images |
| `src/can2mqtt/utils.py` | `parse_mqtt_server_url()` |
| `src/can2mqtt/eds/` | `esphome.eds` object dictionary used for every node, plus the templates it is generated from (`create.sh`) |
| `tests/` | pytest tests; `fake_node.py` is a fake esphome-canopen node on a python-can virtual bus |

CANopen is handled by [canopen-asyncio](https://github.com/mrk-its/canopen-asyncio), a fork of
python-canopen with `async` SDO / PDO methods (`aget_raw()`, `aupload()`, `tpdo.aread()`, …).

## Running tests

```sh
python -m venv venv
./venv/bin/pip install -e '.[dev]'
./venv/bin/python -m pytest tests
```

Tests use the python-can `virtual` interface, no CAN hardware is needed.
