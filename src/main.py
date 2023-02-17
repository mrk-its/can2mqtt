import argparse
import asyncio
import logging

import can2mqtt
import can


def main():
    config = can.util.load_config()
    default_mqtt_server = config.get("mqtt_server", "localhost")
    default_mqtt_topic = config.get("mqtt_topic", "homeassistant")
    default_bitrate = config.get("bitrate", 125000)

    parser = argparse.ArgumentParser(
        prog="can2mqtt",
        description="CAN to MQTT converter",
    )
    parser.add_argument("-s", "--mqtt-server", default=default_mqtt_server)
    parser.add_argument("-i", "--interface")
    parser.add_argument("-c", "--channel")
    parser.add_argument("-b", "--bitrate", default=default_bitrate)
    parser.add_argument("-l", "--log-level", default=logging.INFO)
    parser.add_argument("-t", "--mqtt-topic-prefix", default=default_mqtt_topic)
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level)

    asyncio.run(can2mqtt.start(**vars(args)))
