import argparse
import asyncio
from collections import defaultdict
import json
import re
import struct

import asyncio_mqtt as aiomqtt
import can

from .consts import (
    DEVICE_CLASS,
    STATE_CLASS,
    NAME_TO_TYPE,
    TYPE_TO_NAME,
    MQTT_TOPIC_PREFIX,
    CAN_CMD_BIT,
)

import logging

logger = logging.getLogger(__name__)


TOPIC_RE = re.compile(
    MQTT_TOPIC_PREFIX
    + "/(switch|sensor|binary_switch)/can_([0-9a-fA-F]{2})_([0-9a-fA-F])/(.*)"
)


def device_properties(node_type, data):
    if len(data) > 0 and node_type in DEVICE_CLASS:
        yield "device_class", DEVICE_CLASS[node_type].get(data[0], "None")
    if len(data) > 1:
        yield "state_class", STATE_CLASS.get(data[1], "None")
    if len(data) > 2:
        yield "suggested_display_precision", data[2]


def single_property(name):
    return lambda node_type, data: [(name, data.decode("utf-8"))]


CONFIG_PROPERTIES = {
    0xC: single_property("suggested_unit_of_measurement"),
    0xD: single_property("unit_of_measurement"),
    0xE: device_properties,
    0xF: single_property("name"),
}


def parse_topic(topic):
    m = TOPIC_RE.match(topic)
    if m:
        entity_type, can_id, sub_id, suffix = m.groups()
        return entity_type, int(can_id, 16), int(sub_id, 16), suffix


def create_unique_id(node_id, sub_id):
    return f"can_{node_id:02x}_{sub_id:x}"


def create_topic(unique_id, node_type):
    return f"{MQTT_TOPIC_PREFIX}/{node_type}/{unique_id}"


def parse_can_message(msg: can.Message):
    node_id = msg.arbitration_id & 0xFF
    sub_id = (msg.arbitration_id >> 8) & 0xF
    node_type = (msg.arbitration_id >> 12) & 0xF
    property_id = msg.arbitration_id >> 16
    return (node_id, sub_id, TYPE_TO_NAME.get(node_type), property_id)


async def configure_entity(
    unique_id, node_type, property_id, data, registry, mqtt_client
):
    topic = create_topic(unique_id, node_type)
    if node_type and property_id in CONFIG_PROPERTIES:
        registry_data = registry[topic]
        cfg = {}
        cfg.update(CONFIG_PROPERTIES[property_id](node_type, data))
        cfg.update(
            {
                "unique_id": unique_id,
                "object_id": unique_id,
                "state_topic": f"{topic}/state",
            }
        )
        match node_type:
            case "switch":
                cfg.update(
                    {
                        "assumed_state": False,
                        "command_topic": f"{topic}/set",
                    }
                )

        if any(v != registry_data.get(k) for k, v in cfg.items()):
            registry_data.update(cfg)
            logger.info("configuring %s", topic)
            await mqtt_client.publish(
                f"{topic}/config", payload=json.dumps(registry_data), retain=True
            )


async def can_reader(reader, mqtt_client, registry):
    timestamps = defaultdict(float)

    while True:
        message = await reader.get_message()
        node_id = message.arbitration_id & 0xFF
        last_ts = timestamps[node_id]
        td = message.timestamp - last_ts
        if last_ts and td >= 90:
            logger.warning("too big delay from #%d: %d", node_id, td)
        timestamps[node_id] = message.timestamp

        node_id, sub_id, node_type, property_id = parse_can_message(message)
        unique_id = create_unique_id(node_id, sub_id)

        await configure_entity(
            unique_id, node_type, property_id, message.data, registry, mqtt_client
        )

        if property_id == 0:
            topic = create_topic(unique_id, node_type)
            payload = None
            match node_type:
                case "switch":
                    is_on = message.data and message.data[0]
                    payload = is_on and "ON" or "OFF"
                case "binary_sensor":
                    is_on = message.data and message.data[0]
                    payload = is_on and "ON" or "OFF"
                case "sensor":
                    if len(message.data) == 4:
                        value = struct.unpack_from("f", message.data)[0]
                    elif len(message.data) == 8:
                        value = struct.unpack_from("d", message.data)[0]
                    else:
                        continue
                    payload = str(value)
            await mqtt_client.publish(f"{topic}/state", payload=payload)


async def mqtt_reader(client, bus, registry):
    async with client.messages() as messages:
        await client.subscribe(f"{MQTT_TOPIC_PREFIX}/#")
        async for message in messages:
            logger.info("mqtt msg: %s %s", message.topic, message.payload)

            if message.topic.value.endswith("/config"):
                key = message.topic.value[:-7]
                registry[key].update(json.loads(message.payload))

            match parse_topic(message.topic.value):
                case (entity_type, can_id, sub_id, "set"):
                    arbitration_id = (
                        can_id
                        | (sub_id << 8)
                        | (NAME_TO_TYPE[entity_type] << 12)
                        | CAN_CMD_BIT
                    )
                    match entity_type:
                        case "switch":
                            data = b"\x01" if message.payload == b"ON" else b"\x00"
                        case _:
                            data = message.payload
                    can_msg = can.Message(arbitration_id=arbitration_id, data=data)
                    logger.debug("send can msg: %r", can_msg)
                    bus.send(can_msg)


async def start(mqtt_server, interface, channel, bitrate, **kwargs):
    with can.Bus(
        interface=interface,
        channel=channel,
        bitrate=bitrate,
    ) as bus:
        async with aiomqtt.Client(mqtt_server) as client:
            loop = asyncio.get_running_loop()
            registry = defaultdict(dict)
            reader = can.AsyncBufferedReader()
            notifier = can.Notifier(bus, [reader], loop=loop)
            await asyncio.gather(
                can_reader(reader, client, registry),
                mqtt_reader(client, bus, registry)
            )
            notifier.stop()
