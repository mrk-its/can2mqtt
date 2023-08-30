# Can2MQTT Bridge

ESP32 comes with integrated CAN Bus controller. ESPHome [provides](https://esphome.io/components/canbus.html) low-level support for it (sending / receiving messages from the bus), but it is not able (yet) to automatically expose entities to HomeAssistant over CAN.

This project tries to fill the gap and provides tools for easy exposing ESPHome entities to Home Assistant over CAN Bus:

* It provides `can2mqtt` bridge exposing ESPHome CANopen entities onto MQTT topics. It follows MQTT Discovery protocol, so entities appear automatically in HomeAssistant.
* The [esphome-canopen](https://github.com/mrk-its/esphome-canopen) project converts ESPHome device into CANopen node, exporting selected entities over CAN by mapping them to CANopen object dictionary. It also allows to define TPDOs for sending entity state on change. Currently following entity types are supported: `sensor`, `binary_sensor`, `switch` and `cover`. Entity metadata is also published in Object Dictionary enabling autodiscovery.

# How to start
## Hardware requirements
 * Linux box with CAN Bus controller [supported](https://python-can.readthedocs.io/en/stable/interfaces.html) by python-can library
 * ESP32 board flashed with ESPHome firmware and configured [esphome-canopen](https://github.com/mrk-its/esphome-canopen) external component.
## Software requirements
 * MQTT Broker installed and configured in Home Assistant (with auto-discovery), take a look on [documentation](https://www.home-assistant.io/integrations/mqtt/) for details
## Installation

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

# Support

* [Discord Server](https://discord.gg/f5UTFFnp)

