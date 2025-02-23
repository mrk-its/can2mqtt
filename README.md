# Can2MQTT Bridge

ESP32 comes with integrated CAN Bus controller. ESPHome [provides](https://esphome.io/components/canbus.html) low-level support for it (sending / receiving messages from the bus), but it is not able (yet) to automatically expose entities to HomeAssistant over CAN.

This project tries to fill the gap and provides tools for easy exposing ESPHome entities to Home Assistant over CAN Bus:

* It provides `can2mqtt` bridge exposing ESPHome CANopen entities onto MQTT topics. It follows MQTT Discovery protocol, so entities appear automatically in HomeAssistant.
* The [esphome-canopen](https://github.com/mrk-its/esphome-canopen) project converts ESPHome device into CANopen node, exporting selected entities over CAN by mapping them to CANopen object dictionary. It also allows to define TPDOs for sending entity state on change. Currently following entity types are supported: `sensor`, `binary_sensor`, `switch` and `cover`. Entity metadata is also published in Object Dictionary enabling autodiscovery.

# How to start
## Hardware requirements
 * Linux box with CAN Bus controller [supported](https://python-can.readthedocs.io/en/stable/interfaces.html) by python-can library
 * ESP32 board(s) flashed with ESPHome firmware and configured [esphome-canopen](https://github.com/mrk-its/esphome-canopen) external component.

 There is also [esphome-canbus-usb-serial](https://github.com/mrk-its/esphome-canbus-usb-serial) project turning ESP32 S3/C3 device into USB-CAN interface, with dedicated python-can driver (it is also possible to install `esphome-canbus-usb-serial` component on one of existing ESP32 CANOpen nodes).

 Another way of connecting CANBUS to HA is [esphome-canbus-udp-multicast](https://github.com/mrk-its/esphome-canbus-udp-multicast). It implements `udp_multicast` virtual CANBUS interface and allow to bridge existing CANBUS network to PC via UDP multicasts. It also makes possible to create 'virtual' CAN network with nodes communicating only via UDP packets. It is especially convenient for developing / testing / debugging (a lot of can2mqtt / esphome-canopen features were developed this way)

## Software requirements
 * MQTT Broker installed and configured in Home Assistant (with auto-discovery), take a look on [documentation](https://www.home-assistant.io/integrations/mqtt/) for details

## Installation as HomeAssistant add-on

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmrk-its%2Fcan2mqtt)

## Manual installation

```
  $ python3 -m venv venv
  $ venv/bin/pip install git+https://github.com/mrk-its/can2mqtt
  $ venv/bin/can2mqtt --help

  usage: can2mqtt [-h] [-s MQTT_SERVER] [-i INTERFACE] [-c CHANNEL] [-b BITRATE] [-l LOG_LEVEL] [-t MQTT_TOPIC_PREFIX]

  CAN to MQTT converter

  options:
    -h, --help            show this help message and exit
    -s MQTT_SERVER, --mqtt-server MQTT_SERVER
    -i INTERFACE, --interface INTERFACE
    -c CHANNEL, --channel CHANNEL
    -b BITRATE, --bitrate BITRATE
    -l LOG_LEVEL, --log-level LOG_LEVEL
    -t MQTT_TOPIC_PREFIX, --mqtt-topic-prefix MQTT_TOPIC_PREFIX
```
and run it with proper MQTT server / CAN interface configuration. MQTT server can be provided as `-s` argument or
included in python-can configuration file, like:
```
  $ cat ~/can.conf
  [default]
  interface = seeedstudio
  channel = /dev/ttyUSB1
  bitrate = 500000

  mqtt_server = 192.168.1.200

  $ venv/bin/can2mqtt -l DEBUG

```

If CAN Bus communication is working properly you should see on stdout received CAN frames and data published to MQTT topics.
In HomeAssistant you should see new entities like `switch.can_001_02`

# Firmware updates via CAN (CAN OTA)

can2mqtt and esphome-canopen together support firmware upgrades via CANBUS:

* make sure there is `canopen ota` platform present in esphome's yaml file:
  ```
  ota:
    - platform: canopen
  ```
* compile your node's firmware with
  ```
  esphome compile node.yaml
  ```
  resulting `firmware.bin` typically is located in:
  ```
  .esphome/build/node-xyz/.pioenvs/node-xyz/firmware.bin
  ```

* copy resulting `firmware.bin` to proper firmware directory monitored by can2mqtt.
  - if can2mqtt is installed as an addon of HA supervised, then can2mqtt is ran with `--firmware=/config` parameter, mapped to `/addon_configs/{SLUG}_can2mqtt/` shared directory. SLUG is 8-hexdigit value that can be found on addon's page. It is recommended to create subdirectory for each node and put `firmware.bin` file there, and copy file to path like: `/addon_configs/{SLUG}_can2mqtt/node-xyz/firmware.bin`
  - if can2mqtt is installed standalone, then `--firmware` option can be used to provide firmware directory (it defaults to './firmware`)
* after copying firmware file following message should appear in can2mqtt logs:
  ```
  2025-02-23 17:04:47 can2mqtt.entities  INFO new_firmware: /config/node-xyz/firmware.bin, node_id: ..., ver: 2025.2.0.20250223.001140
  ```
  and new update should be visible in HA
* update may be installed via standard HA update interface, the update progress / final status should be visible in `can2mqtt` logs. When update is finished node will be restarted and should be re-registered in `can2mqtt`.

# Support

* [Discord Server](https://discord.gg/VXjUSnUWsd)

