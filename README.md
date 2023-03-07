# Can2MQTT Bridge

ESP32 comes with integrated CAN Bus controller. ESPHome [provides](https://esphome.io/components/canbus.html) low-level support for it (sending / receiving messages from the bus), but it is not able (yet) to automatically expose entities to HomeAssistant over CAN.

This project tries to fill the gap and provides tools for easy exposing ESPHome entities to Home Assistant over CAN Bus:

* It provides `can2mqtt` bridge exposing ESPHome CANopen entities onto MQTT topics. It follows MQTT Discovery protocol, so entities appear automatically in HomeAssistant.
* The [esphome-canopen](https://github.com/mrk-its/esphome-canopen) project converts ESPHome device into CANopen node, exporting selected entities over can by maapping them to CANopen object dictionary. It also allows to define TPDOs for sending entity state on change. Currently following entity types are supported: `sensor`, `binary_sensor`, `switch` and `cover`. Entity metadata is also published in Object Dictionary enabling autodiscovery.

# How to start
## Hardware requirements
 * any ESP8266/ESP32 board with CAN controller. ESP32 boards are preferred, as they have [integrated can controller](https://esphome.io/components/canbus.html#esp32-can-component) (but still cheap external CAN transceiver is needed). For ESP8266 external [MCP2515](https://esphome.io/components/canbus.html#mcp2515-component) CAN controller can be used.
 * Linux box with CAN Bus controller [supported](https://python-can.readthedocs.io/en/stable/interfaces.html) by python-can library
## Software requirements
 * MQTT Broker installed and configured in Home Assistant (with auto-discovery), take a look on [documentation](https://www.home-assistant.io/integrations/mqtt/) for details

## Configure ESPHome with `can_gateway` component

  Example configuration for esp32dev board:

  ```
  esphome:
    name: can-node-1

  external_components:
    - source: github://mrk-its/esphome-canopen

  # Enable logging
  logger:

  # Enable Home Assistant API
  api:
    password: ""
    reboot_timeout: 0s

  ota:
    password: ""

  esp32:
    board: esp32dev
    framework:
      type: arduino

  wifi:
    <<: !include {file: wifi.yaml}

  canbus:
    - platform: esp32_can
      id: can_bus
      rx_pin: GPIO22
      tx_pin: GPIO23
      can_id: 0
      bit_rate: 125kbps

  canopen:
    id: can_gate
    canbus_id: can_bus
    node_id: 1
    entities:
      - id: boot
        index: 1
        tpdo: 0
      - id: blue_led
        index: 2
        tpdo: 0
      - id: uptime_sensor
        index: 3
        tpdo: 0
      - id: cover1
        index: 4
        tpdo: 1
      - id: cover2
        index: 5
        tpdo: 1

  sensor:
    - platform: uptime
      id: uptime_sensor
      name: "Uptime 1"
      update_interval: 5sec
      internal: true

  binary_sensor:
    - platform: gpio
      name: "Boot 1"
      id: boot
      internal: true
      pin:
        number: 0
        inverted: true

  switch:
    - platform: gpio
      name: "Led 1"
      id: blue_led
      internal: true
      pin: 2

  cover:
    - platform: time_based
      name: "Cover 1"
      id: cover1
      internal: true
      device_class: shutter
      has_built_in_endstop: true
      open_action:
        - logger.log: open_action
      open_duration: 10s
      close_action:
        - logger.log: close_action
      close_duration: 10s
      stop_action:
        - logger.log: stop_action

    - platform: time_based
      name: "Cover 2"
      id: cover2
      internal: true
      device_class: shutter
      has_built_in_endstop: true
      open_action:
        - logger.log: open_action
      open_duration: 10s
      close_action:
        - logger.log: close_action
      close_duration: 10s
      stop_action:
        - logger.log: stop_action

  ```

## Install `can2mqtt` bridge

```
  $ python3 -m venv venv
  $ venv/bin/pip install git+https://github.com/mrk-its/can2mqt
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


## Protocol overview

TODO

