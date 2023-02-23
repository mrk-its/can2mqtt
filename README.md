# Can2MQTT Bridge

ESP32 comes with integrated CAN Bus controller. ESPHome [provides](https://esphome.io/components/canbus.html) low-level support for it (sending / receiving messages from the bus), but it is not able (yet) to automatically expose entities to HomeAssistant over CAN.

This project tries to fill the gap and provides tools for easy exposing ESPHome entities to Home Assistant over CAN Bus.

Simple CAN protocol is defined, describing how to embed information about entity configuration / state changes in the CAN frame.

Custom ESPHome component `can_gateway` translates state changes of selected entities onto can frames (and vice versa).
`can2mqtt` program is bridge converting CAN frames onto MQTT topics. It follows MQTT Discovery protocol, so entities appear automatically in HomeAssistant.

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
      name: can-test-node

    esp32:
      board: esp32dev

    wifi:
      <<: !include {file: wifi.yaml}

    api:
    password: ""

    ota:
    password: ""

    canbus:
      - platform: esp32_can
        id: can_bus
        rx_pin: GPIO22
        tx_pin: GPIO23
        can_id: 0
        bit_rate: 125kbps

    external_components:
      - source: github://mrk-its/can2mqtt
        refresh: 10s

    can_gateway:
      id: can_gate
      canbus_id: can_bus
      status:
        can_id: 0
      entities:
        - id: blue_led
          can_id: 1
        - id: uptime_sensor
          can_id: 2
        - id: boot
          can_id: 3
        - id: cover1
          can_id: 4

    sensor:
      - platform: uptime
        id: uptime_sensor
        name: "Uptime1"
        update_interval: 5sec
        internal: true

    binary_sensor:
      - platform: gpio
        name: "Boot1"
        id: boot
        internal: true
        pin:
          number: 0
          inverted: true

    switch:
      - platform: gpio
        name: "Led1"
        id: blue_led
        internal: true
        pin: 2

    cover:
      - platform: time_based
        name: "Cover1"
        id: cover1
        internal: true
        device_class: shutter
        has_built_in_endstop: true
        open_action:
          - logger.log: open_action
        open_duration: 5s
        close_action:
          - logger.log: close_action
        close_duration: 5s
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
In HomeAssistant you should see new entities like `switch.can_000001`


## Protocol overview

TODO

