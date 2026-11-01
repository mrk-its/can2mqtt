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

## Development setup

can2mqtt is developed in a local virtualenv in `venv/` (ignored by git).

### Create the venv

Use a Python interpreter that doesn't change under the venv. A venv links to the interpreter it was
created with and its packages live in `venv/lib/pythonX.Y/`: if it's created from the system
`/usr/bin/python` and a distribution upgrade bumps it (e.g. 3.13 → 3.14 on Arch), `venv/bin/python`
starts the new version, which doesn't see the installed packages (`No module named 'can'`).
A [pyenv](https://github.com/pyenv/pyenv) (or uv / mise) managed interpreter stays where it is:

```sh
pyenv install 3.13          # once
~/.pyenv/versions/3.13.13/bin/python -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -e '.[dev]'
```

`-e` (editable) installs can2mqtt from `src/`, so code changes take effect without reinstalling;
`[dev]` adds pytest and black. The dependencies come from git (canopen-asyncio,
esphome-canbus-usb-serial), so `git` and network access are needed.

Check it: `./venv/bin/python --version` and `./venv/bin/can2mqtt --help`.

### Recreate the venv

When the interpreter changed or was removed, or the dependencies in `pyproject.toml` changed
(pip doesn't upgrade git dependencies by itself), build it from scratch:

```sh
rm -rf venv
# then the commands from "Create the venv"
```

To update only a git dependency (e.g. a new canopen-asyncio commit):

```sh
./venv/bin/pip install --force-reinstall --no-deps "canopen@git+https://github.com/mrk-its/canopen-asyncio"
```

### Run

```sh
./venv/bin/can2mqtt -i socketcan -c can0 -s mqtt://user:password@localhost
```

(see `./venv/bin/can2mqtt --help`; `-i esp_usb_serial -c /dev/ttyACM0` for an ESP USB-serial CAN
adapter).

### Tests

```sh
./venv/bin/python -m pytest tests
```

Tests use the python-can `virtual` interface, no CAN hardware is needed.

### Formatting

```sh
./venv/bin/black src tests
```
