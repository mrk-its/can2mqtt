# Can2MQTT Bridge

ESP32 comes with integrated CAN Bus controller. ESPHome [provides](https://esphome.io/components/canbus.html) low-level support for it (sending / receiving messages from the bus), but it is not able (yet) to expose entities to HomeAssistant over CAN.

This project tries to fill the gap and provides tools for easy exposing ESPHome entities to Home Assistant over CAN Bus.

Simple CAN protocol is defined, describing how to embed information about entity configuration / state change in the CAN frame.

Take a look on example [ESPHome configuration](https://github.com/mrk-its/can2mqtt/tree/main/esphome/config).
It defines three entities: `sensor`, `binary_sensor` and `switch`. These entitie are marked as `internal`, so they are not exposed to Home Assistant over WIFI. Following `on-boot` lambda code makes these entities available over CAN:
```
  on_boot:
    priority: 500
    then:
      - lambda: |
          can_configure_switch(id(can_bus), id(blue_led), 1);
          can_configure_sensor(id(can_bus), id(uptime_sensor), 2);
          can_configure_binary_sensor(id(can_bus), id(boot), 3);
```

`can2mqtt` bridge converts CAN frames onto MQTT topics. It follows MQTT Discovery protocol, so entities appear automatically in HomeAssistant.

## Requirements

* python >= 3.10
* any CAN device supported by `python-can`

### Installation

```
  $ cd can2mqtt
  $ pip install .
```

### Running

```
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

`python-can` documentation describes all [supported interfaces](https://python-can.readthedocs.io/en/stable/configuration.html#interface-names)

## Protocol overview

TODO

