import asyncio
import json
import logging
import re
import hashlib

import asyncio_mqtt as aiomqtt
import canopen
from canopen.sdo.exceptions import SdoAbortedError
from canopen.objectdictionary import ObjectDictionary, import_od, datatypes, Record, Variable

from . import consts
from .entities import EntityRegistry, StateMixin, CommandMixin, Entity


CODE_SUBINDEX_NOT_FOUND=0x06090011
CODE_OBJECT_NOT_FOUND=0x06020000


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


async def async_try_iter_items(obj):
    try:
        async for key in obj:
            if not key: continue
            logger.debug("trying to read %s", key)
            try:
                val = await obj[key].aget_raw()
                logger.debug("val: %s", val)
                yield key, val                
            except SdoAbortedError as e:
                if e.code == CODE_SUBINDEX_NOT_FOUND:
                    logger.debug("subindex not found")
                    continue
                logger.info("error: %08x", e.code)
                raise
    except SdoAbortedError as e:
        if e.code != CODE_OBJECT_NOT_FOUND:
            raise


async def can_reader(can_network, mqtt_client, mqtt_topic_prefix):
    async def on_tptd(map):
        node_id = map.pdo_node.node.id
        for v in map.map:
            key = (v.index << 16) | (v.subindex<<8)
            entity = StateMixin.get_entity_by_node_state_key(node_id, key)
            if entity:
                try:
                    state_topic, value = entity.get_mqtt_state(key, v.get_raw())
                    await mqtt_client.publish(state_topic, payload=value, retain=False)
                    logger.debug("MQTT publish topic: %s value: %s - ok", state_topic, value)
                except ValueError as e:
                    logger.error("%s", e)
            else:
                logger.warning("no entity for node: %d, key: %08x", node_id, key)

    while True:
        for node_id in can_network.scanner.nodes:
            if not node_id in can_network:
                od = import_od('eds/esphome.eds')
                node = can_network.add_node(node_id, od)
                node.sdo.MAX_RETRIES = 3
                device_name = await node.sdo["DeviceName"].aget_raw()
                logger.info("node_id: %s device_name: %s", node_id, device_name)
                if device_name != "ESPHome":
                    logger.warning("device %s is not supported, skipping", device_name)
                    continue

                async for entity_index, entity_type in async_try_iter_items(node.sdo["EntityTypes"]):
                    try:
                        entity = EntityRegistry.create(entity_type, node, entity_index, mqtt_topic_prefix=mqtt_topic_prefix)
                        logger.info("  entity: %r", entity)
                    except KeyError:
                        logger.warning("  Unknown entity type: %d, index: %d", entity_type, entity_index)
                        continue

                    base_index = 0x2000 + entity_index * 16
                    node.object_dictionary[base_index + 1] = Record("states", base_index + 1)
                    node.object_dictionary[base_index + 2] = Record("cmds", base_index + 2)

                    entity.setup_object_dictionary(node, base_index)

                    async for key, value in async_try_iter_items(node.sdo[base_index]):
                        entity.set_metadata_property(key, value)

                    await entity.publish_config(mqtt_client)

                logger.debug("reading tpdo config")
                await node.tpdo.aread()

                for key, map in node.tpdo.map.items():
                    map.add_callback(on_tptd)

        await asyncio.sleep(1.0)


async def can_test_upload(can_network, node_id, payload):
    try:
        node = can_network.get(node_id)
        if node:
            firmware = node.sdo['Firmware']
            await firmware['Firmware Size'].aset_raw(len(payload))
            await firmware['Firmware MD5'].aset_raw(hashlib.md5(payload).digest())
            await firmware['Firmware Data'].aset_raw(payload)
            logger.info("successfuly uploaded %d bytes", len(payload))
        else:
            logger.warning("node %s doesn't exist", node_id)
    except Exception as e:
        logger.exception("firmware update error: %s", e)


async def mqtt_reader(mqtt_client, can_network, mqtt_topic_prefix):
    UPLOAD_RE = re.compile(f"{mqtt_topic_prefix}/node_(\d+)/firmware")
    async with mqtt_client.messages() as messages:
        await mqtt_client.subscribe(f"{mqtt_topic_prefix}/#")
        async for message in messages:
            if len(message.payload) < 20:
                logger.debug("recv mqtt topic: %s %s", message.topic, message.payload)
            else:
                logger.debug("recv mqtt topic: %s payload len: %s", message.topic, len(message.payload))

            if message.topic.value == f"{mqtt_topic_prefix}/status":
                if message.payload == b"online":
                    for entity in Entity.entities():
                        await entity.publish_config(mqtt_client)
                continue

            entity = CommandMixin.get_entity_by_cmd_topic(message.topic.value)
            if entity:
                try:
                    cmd_key, value = entity.get_can_cmd(message.topic.value, message.payload)
                    subidx = (cmd_key >> 8) & 255
                    idx = cmd_key >> 16
                    var = entity.node.sdo[idx]
                    if subidx:
                        var = var[subidx]
                    asyncio.create_task(var.aset_raw(value))
                    logger.info("entity: %s cmd_key: %s, value: %s sent successfully", entity, cmd_key, value)
                except ValueError as e:
                    logger.error("%s", e)
            else:
                m = UPLOAD_RE.match(message.topic.value)
                if m:
                    node_id = int(m.group(1))
                    asyncio.create_task(can_test_upload(can_network, node_id, message.payload))

async def start(
    mqtt_server,
    interface,
    channel,
    bitrate,
    mqtt_topic_prefix,
    **kwargs,
):
    async with aiomqtt.Client(mqtt_server) as mqtt_client:
        can_network = canopen.Network()
        # can_network.listeners.append(lambda msg: logger.debug("%s", msg))
        loop = asyncio.get_running_loop()
        can_network.connect(loop=loop, interface=interface, channel=channel, bitrate=bitrate)
        await asyncio.gather(
            can_reader(can_network, mqtt_client, mqtt_topic_prefix=mqtt_topic_prefix),
            mqtt_reader(mqtt_client, can_network, mqtt_topic_prefix=mqtt_topic_prefix),
        )
