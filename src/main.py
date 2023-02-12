import argparse
import asyncio
import logging

import can2mqtt


def main():
    parser = argparse.ArgumentParser(
        prog="can2mqtt",
        description="CAN to MQTT converter",
    )
    parser.add_argument("-s", "--mqtt-server", default="localhost")
    parser.add_argument("-i", "--interface", default="seeedstudio")
    parser.add_argument("-c", "--channel", default="/dev/ttyUSB0")
    parser.add_argument("-b", "--bitrate", type=int, default=125000)
    parser.add_argument("-l", "--log-level", default=logging.INFO)

    args = parser.parse_args()

    logging.basicConfig(level=args.log_level)

    asyncio.run(can2mqtt.start(**vars(args)))
