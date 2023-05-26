import asyncio
import hashlib
import json
import logging
import re
import time

import asyncio_mqtt as aiomqtt
import canopen
from canopen.sdo.exceptions import SdoAbortedError
from canopen.objectdictionary import ObjectDictionary, import_od, datatypes, Record, Variable

from . import consts
from .entities import EntityRegistry, StateMixin, CommandMixin, Entity


CODE_SUBINDEX_NOT_FOUND=0x06090011
CODE_OBJECT_NOT_FOUND=0x06020000

ESPHOME_VENDOR_ID = 0xa59a08f5
ESPHOME_PRODUCT_CODE = 0x6bdfa1d9

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
    def get_heartbeat_cb(node):
        def on_heartbeat(status):
            logger.debug("heartbeat from %d: %s", node.id, status)
            node.last_heartbeat_time = time.time()
            if node.ntm_state_entity:
                state_topic = node.ntm_state_entity.get_state_topic()
                asyncio.create_task(
                    mqtt_client.publish(state_topic, payload=str(status), retain=False)
                )
        return on_heartbeat

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
                node.is_supported = False
                node.is_operational = False

                node.last_heartbeat_time = time.time()
                node.availability = None
                node.availability_topic = f"{mqtt_topic_prefix}/can_{node_id:03x}/availability"
                node.prod_heartbeat_time = None
                node.sdo.MAX_RETRIES = 3
                node.sw_version = None
                node.hw_version = None
                node.device_name = None
                node.ntm_state_entity = None
                continue

            node = can_network[node_id]
            if not node.is_operational and node.nmt.state == "OPERATIONAL":
                node.is_operational=True

                try:
                    vendor_id = await node.sdo["Identity"]["VendorId"].aget_raw()
                    product_code = await node.sdo["Identity"]["ProductCode"].aget_raw()
                except SdoAbortedError as e:
                    logger.warning("can't read identity info, skipping")
                    continue
                if vendor_id != ESPHOME_VENDOR_ID or product_code != ESPHOME_PRODUCT_CODE:
                    logger.warning("vendor: %s, product: %s is not supported, skipping", vendor_id, product_code)
                    continue

                node.is_supported = True
                node.device_name = await node.sdo["DeviceName"].aget_raw()

                try:
                    node.hw_version = await node.sdo["HardwareVersion"].aget_raw()
                except SdoAbortedError as e:
                    pass
                try:
                    node.sw_version = await node.sdo["SoftwareVersion"].aget_raw()
                except SdoAbortedError as e:
                    pass

                try:
                    node.prod_heartbeat_time = await node.sdo["ProducerHeartbeatTime"].aget_raw()
                    node.nmt.add_hearbeat_callback(get_heartbeat_cb(node))
                except SdoAbortedError as e:
                    pass

                logger.info("node_id: %s device name: %s, heartbeat time (ms): %s",
                            node_id, node.device_name, node.prod_heartbeat_time)

                entity = EntityRegistry.create(0, node, 0, mqtt_topic_prefix=mqtt_topic_prefix)
                node.ntm_state_entity = entity
                entity.set_property("name", "NMT State")
                await entity.publish_config(mqtt_client)
                logger.info("  entity: %r", entity)

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

            if not node.is_supported:
                continue

            is_online = not node.prod_heartbeat_time or (
                (time.time() - node.last_heartbeat_time) < 2 * node.prod_heartbeat_time / 1000.0
            )
            availability = "online" if is_online else "offline"
            if node.availability != availability:
                logger.info("node %s is %s", node_id, availability)
                await mqtt_client.publish(node.availability_topic, payload=availability)
                node.availability = availability

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
    NODE_CMD = re.compile(f"{mqtt_topic_prefix}/node_(\d+)/(nmt|firmware|write)(/.*)?$")
    async with mqtt_client.messages() as messages:
        await mqtt_client.subscribe(f"{mqtt_topic_prefix}/#")
        async for message in messages:
            if len(message.payload) < 20:
                logger.debug("recv mqtt topic: %s %s", message.topic, message.payload)
            else:
                logger.debug("recv mqtt topic: %s payload len: %s", message.topic, len(message.payload))

            if message.topic.value == f"{mqtt_topic_prefix}/nmt":
                await can_network.scanner.scan()
                continue

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
                    logger.debug("entity: %s cmd_key: %s, value: %s sent successfully", entity, cmd_key, value)
                except ValueError as e:
                    logger.error("%s", e)
            else:
                m = NODE_CMD.match(message.topic.value)
                match m and m.groups():
                    case (node_id, "nmt", _):
                        cmd = int(message.payload.decode("utf-8"))
                        logger.info("sent nmt command %d to node %s", cmd, node_id)
                        can_network.send_message(0, [cmd, int(node_id)])
                    case (node_id, "firmware", _):
                        asyncio.create_task(can_test_upload(can_network, node_id, message.payload))
                    case (node_id, "write", arg):
                        arg = arg[1:]
                        try:
                            node_id = int(node_id)
                            dest = [int(i, 16) for i in arg.split(":")]
                            index = dest[0]
                            start_subidx = dest[1] if len(dest) > 1 else 0
                        except ValueError:
                            logger.warning("invalid write command: %s", message.payload)
                            continue
                        try:
                            data = [int(v, 16) for v in re.split(b"[ ,]+", message.payload)]
                            logger.info(f"write to node {node_id} at index: {index:04x}:{start_subidx:02x}, data: {data}")
                            for subidx, value in enumerate(data, start_subidx):
                                await can_network[node_id].sdo[index][subidx].aset_raw(value)
                        except SdoAbortedError as e:
                            logger.error("sdo error: %s", e)

async def start(
    mqtt_server,
    interface,
    channel,
    bitrate,
    mqtt_topic_prefix,
    **kwargs,
):
    status_topic = f"{mqtt_topic_prefix}/can2mqtt/status"
    will = aiomqtt.Will(status_topic, b"offline", 1, retain=True)
    async with aiomqtt.Client(mqtt_server, will=will) as mqtt_client:
        try:
            await mqtt_client.publish(status_topic, payload=b"online", retain=False)
            can_network = canopen.Network()
            # can_network.listeners.append(lambda msg: logger.debug("%s", msg))
            loop = asyncio.get_running_loop()
            can_network.connect(loop=loop, interface=interface, channel=channel, bitrate=bitrate)
            await asyncio.gather(
                can_reader(can_network, mqtt_client, mqtt_topic_prefix=mqtt_topic_prefix),
                mqtt_reader(mqtt_client, can_network, mqtt_topic_prefix=mqtt_topic_prefix),
            )
        except:
            await mqtt_client.publish(status_topic, payload=b"offline", retain=False)
            raise
