import argparse
import asyncio
from collections import defaultdict
import json
import re
import struct
from dataclasses import dataclass

import asyncio_mqtt as aiomqtt
import can

from . import consts

import logging

logger = logging.getLogger("can2mqtt")


def create_unique_id(entity_id):
    return "can_{:x}".format(entity_id)


class Entity:
    def __init__(self, entity_id, mqtt_topic_prefix):
        unique_id = create_unique_id(entity_id)
        self.type_name = None
        self._mqtt_topic_prefix = mqtt_topic_prefix

        self._properties = {
            "unique_id": unique_id,
            "object_id": unique_id,
        }

    def __repr__(self):
        return repr((self.type_name, self._properties))

    def is_ready(self):
        return self.type_name is not None

    def set_type_id(self, _type):
        self.type_name = consts.ENTITY_TYPE_NAME[_type]
        self._properties["state_topic"] = self.state_topic
        if self.type_name == "switch":
            self._properties.update(
                {"assumed_state": False, "command_topic": self.command_topic}
            )

    def set_type_name(self, type_name):
        self.type_name = type_name

    def update_properties(self, props):
        if hasattr(props, "items"):
            props = props.items()
        for k, v in props:
            if v is not None:
                self._properties[k] = v
            else:
                self._properties.pop(k, None)

    def parse_can_payload(self, data):
        match self.type_name:
            case "switch":
                is_on = data and data[0]
                return is_on and "ON" or "OFF"
            case "binary_sensor":
                is_on = data and data[0]
                return is_on and "ON" or "OFF"
            case "sensor":
                if len(data) == 4:
                    return str(struct.unpack_from("f", data)[0])
                elif len(data) == 8:
                    return str(struct.unpack_from("d", data)[0])

    def parse_mqtt_payload(self, data):
        match self.type_name:
            case "switch":
                return b"\x01" if data == b"ON" else b"\x00"
            case _:
                return data

    @property
    def unique_id(self):
        return self._properties["unique_id"]

    @property
    def topic(self):
        return f"{self._mqtt_topic_prefix}/{self.type_name}/{self.unique_id}"

    @property
    def state_topic(self):
        return f"{self.topic}/state"

    @property
    def command_topic(self):
        return f"{self.topic}/set"

    @property
    def config_topic(self):
        return f"{self.topic}/config"

    def get_config_topic(self, type_name):
        return f"{self._mqtt_topic_prefix}/{type_name}/{self.unique_id}"

    @property
    def config_topics_to_invalidate(self):
        return [self.get_config_topic(type_name) for type_name in consts.SUPPORTED_TYPE_NAMES if type_name != self.type_name]

class EntityRegistry:
    def __init__(self, mqtt_topic_prefix):
        self._registry = {}
        self.mqtt_topic_prefix = mqtt_topic_prefix

    def get_or_create(self, entity_id):
        entity = self._registry.get(entity_id)
        if entity is None:
            entity = self._registry[entity_id] = Entity(
                entity_id, self.mqtt_topic_prefix
            )
        return entity


def device_properties(type_name, data):
    if len(data) > 1 and type_name in consts.DEVICE_CLASS:
        yield "device_class", consts.DEVICE_CLASS[type_name].get(data[1])
    if len(data) > 2:
        yield "state_class", consts.STATE_CLASS.get(data[2])


def single_property(name):
    return lambda type_name, data: [(name, data.decode("utf-8"))]


CONFIG_PROPERTIES = {
    consts.PROPERTY_CONFIG: device_properties,
    consts.PROPERTY_CONFIG_NAME: single_property("name"),
    consts.PROPERTY_CONFIG_UNIT: single_property("unit_of_measurement"),
}


TOPIC_RE = re.compile("(switch|sensor|binary_sensor)/can_([0-9a-fA-F]{1,7})/(.*)")


def parse_topic(topic):
    m = TOPIC_RE.match(topic)
    if m:
        entity_type, entity_id, suffix = m.groups()
        return entity_type, int(entity_id, 16), suffix


async def configure_entity(message, registry: EntityRegistry, mqtt_client):
    property_id = message.arbitration_id & 0xF
    entity_id = message.arbitration_id >> 4

    entity = registry.get_or_create(entity_id)

    if property_id == consts.PROPERTY_CONFIG:
        entity.set_type_id(message.data[0])
        for topic in entity.config_topics_to_invalidate:
            await mqtt_client.publish(topic, payload=b"", retain=True)

    if property_id in CONFIG_PROPERTIES and entity.is_ready():
        entity.update_properties(
            CONFIG_PROPERTIES[property_id](entity.type_name, message.data)
        )
        await mqtt_client.publish(
            entity.config_topic, payload=json.dumps(entity._properties), retain=True
        )
        print(entity.config_topics_to_invalidate)
    return entity, property_id


async def can_reader(reader, mqtt_client, registry):
    while True:
        message = await reader.get_message()
        entity, property_id = await configure_entity(message, registry, mqtt_client)
        if entity.is_ready() and property_id == consts.PROPERTY_STATE0:
            payload = entity.parse_can_payload(message.data)
            if payload is not None:
                await mqtt_client.publish(entity.state_topic, payload=payload)


async def mqtt_reader(client, bus, registry: EntityRegistry):
    async with client.messages() as messages:
        await client.subscribe(f"{registry.mqtt_topic_prefix}/#")
        async for message in messages:
            topic = message.topic.value[len(registry.mqtt_topic_prefix) + 1 :]
            logger.info("mqtt msg: %s %s", topic, message.payload)
            match parse_topic(topic):
                case (type_name, entity_id, "config"):
                    entity = registry.get_or_create(entity_id)
                    entity.set_type_name(type_name)
                    entity.update_properties(json.loads(message.payload))
                case (entity_type, entity_id, "set"):
                    arbitration_id = (entity_id << 4) | consts.PROPERTY_CMD0
                    entity = registry.get_or_create(entity_id)
                    if entity_type == entity.type_name:
                        data = entity.parse_mqtt_payload(message.payload)
                        can_msg = can.Message(arbitration_id=arbitration_id, data=data)
                        logger.debug("send can msg: %r", can_msg)
                        bus.send(can_msg)


async def start(
    mqtt_server,
    interface,
    channel,
    bitrate,
    mqtt_topic_prefix,
    **kwargs,
):
    with can.Bus(
        interface=interface,
        channel=channel,
        bitrate=bitrate,
    ) as bus:
        async with aiomqtt.Client(mqtt_server) as client:
            loop = asyncio.get_running_loop()
            registry = EntityRegistry(mqtt_topic_prefix)
            reader = can.AsyncBufferedReader()
            notifier = can.Notifier(bus, [reader], loop=loop)
            await asyncio.gather(
                can_reader(reader, client, registry), mqtt_reader(client, bus, registry)
            )
            notifier.stop()
