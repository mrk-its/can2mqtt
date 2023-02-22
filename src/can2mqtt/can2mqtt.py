import asyncio
import json
import logging
import re

import asyncio_mqtt as aiomqtt
import can

from . import consts
from .entities import EntityRegistry

logger = logging.getLogger("can2mqtt.entities")


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


TOPIC_RE = re.compile("([\w-]+)/can_([0-9a-fA-F]{1,7})/(.*)")


def parse_topic(topic):
    m = TOPIC_RE.match(topic)
    if m:
        entity_type, entity_id, suffix = m.groups()
        return entity_type, int(entity_id, 16), suffix


async def configure_entity(message, registry: EntityRegistry, mqtt_client):
    property_id = message.arbitration_id & 0xF
    entity_id = message.arbitration_id >> 4

    entity = registry.get(entity_id)

    if property_id == consts.PROPERTY_CONFIG:
        entity = registry.can_configure(message.data[0], entity_id, message.data)
        if not entity:
            return
        for topic in entity.get_config_topics_to_invalidate(registry.all_type_names()):
            await mqtt_client.publish(topic, payload=b"", retain=True)

    if entity and property_id in CONFIG_PROPERTIES:
        entity.update_properties(
            CONFIG_PROPERTIES[property_id](entity.type_name, message.data)
        )
        await entity.mqtt_publish_config(mqtt_client)
    return entity, property_id


async def can_reader(reader, mqtt_client, registry):
    while True:
        message = await reader.get_message()
        entity, property_id = await configure_entity(message, registry, mqtt_client)
        if entity is not None:
            await entity.process_can_frame(property_id, message.data, mqtt_client)


async def mqtt_reader(client, bus, registry: EntityRegistry):
    async with client.messages() as messages:
        await client.subscribe(f"{registry.mqtt_topic_prefix}/#")
        async for message in messages:
            topic = message.topic.value[len(registry.mqtt_topic_prefix) + 1 :]
            logger.info("mqtt msg: %s %s", topic, message.payload)
            parsed_topic = parse_topic(topic)
            if parsed_topic:
                (type_name, entity_id, cmd) = parsed_topic
                if cmd == "config":
                    registry.mqtt_configure(type_name, entity_id, message.payload)
                else:
                    entity = registry.get(entity_id)
                    if entity is not None:
                        if type_name == entity.type_name:
                            await entity.process_mqtt_command(cmd, message.payload, bus)
                        else:
                            logger.warning("invalid entity type: %s, expected: %s", type_name, entity.type_name)
                    else:
                        logger.warning("entity %s is not registered yet")

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
