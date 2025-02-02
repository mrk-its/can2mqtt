import asyncio
import hashlib
from collections import defaultdict
import logging
import json
import os
import re
import time
import zlib

import aiomqtt
import canopen

from canopen.network import Network
from canopen.node import RemoteNode

from canopen.sdo.exceptions import SdoAbortedError, SdoCommunicationError
from canopen.objectdictionary import (
    import_od,
    datatypes,
    ODRecord,
    ODArray,
    ODVariable,
)

from .utils import parse_mqtt_server_url
from .entities import EntityRegistry, StateMixin, CommandMixin, Entity
from . import firmware_scanner


CODE_SUBINDEX_NOT_FOUND = 0x06090011
CODE_OBJECT_NOT_FOUND = 0x06020000

ESPHOME_VENDOR_ID = 0xA59A08F5
ESPHOME_PRODUCT_CODE = 0x6BDFA1D9

logger = logging.getLogger("can2mqtt.entities")


TOPIC_RE = re.compile("([\w-]+)/can_([0-9a-fA-F]{1,7})/(.*)")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


FIRMWARE_MAP = defaultdict(lambda: (None, None))


WATCHDOG_TIMEOUT_EXIT_CODE = 42


class QuitException(Exception):
    def __init__(self, descr, exit_code=127):
        super().__init__(descr)
        self.exit_code = exit_code


async def async_try_iter_items(obj):
    try:
        async for key in obj:
            if not key:
                continue
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


class WatchdogTimer:
    _time = 0

    def __init__(self, timeout):
        self._timeout = timeout
        self.reset()

    def reset(self):
        self._time = time.time()

    def passed(self):
        return time.time() - self._time >= self._timeout


watchdog_timer = None


def reload_node(node):
    logger.info("reloading node %02x", node.id)
    node.is_initialized = False
    for _, map in node.tpdo.map.items():
        map.clear()
        map.callbacks.clear()  # probably above clear should do that??

def get_heartbeat_cb(mqtt_client, node):
    def on_heartbeat(status):
        watchdog_timer.reset()
        logger.debug("heartbeat from %02x: %s", node.id, status)
        if status == 0:
            reload_node(node)
        node.last_heartbeat_time = time.time()
        if node.ntm_state_entity:
            state_topic = node.ntm_state_entity.get_state_topic()
            asyncio.create_task(
                mqtt_client.publish(state_topic, payload=str(status), retain=False)
            )
    return on_heartbeat


def get_tptd_cb(mqtt_client):
    async def on_tptd(map):
        node_id = map.pdo_node.node.id
        for v in map.map:
            key = (v.index << 16) | (v.subindex << 8)
            entity = StateMixin.get_entity_by_node_state_key(node_id, key)
            if entity:
                try:
                    state_topic, value = entity.get_mqtt_state(key, await v.aget_raw())
                    await mqtt_client.publish(state_topic, payload=value, retain=False)
                    logger.debug(
                        "MQTT publish topic: %s value: %s - ok", state_topic, value
                    )
                except ValueError as e:
                    logger.error("%s", e)
            else:
                logger.warning("no entity for node: %d, key: %08x", node_id, key)
    return on_tptd


def od_variable(_type, name, index, subindex, default=None):
    var = ODVariable(name, index, subindex)
    var.data_type = _type
    if default is not None:
        var.default = default
    return var


async def process_node(mqtt_client, mqtt_topic_prefix: str, node: RemoteNode, revision: int):

    try:
        node.sw_version = await node.sdo["SoftwareVersion"].aget_raw()
    except SdoAbortedError as e:
        node.sw_version = None

    # TODO - implement node caching using (node.id, sw_version) as a key

    node.device_name = await node.sdo["DeviceName"].aget_raw()

    try:
        node.hw_version = await node.sdo["HardwareVersion"].aget_raw()
    except SdoAbortedError as e:
        pass

    try:
        node.prod_heartbeat_time = await node.sdo[
            "ProducerHeartbeatTime"
        ].aget_raw()
        if not node.has_nmt_callback:
            node.nmt.add_hearbeat_callback(get_heartbeat_cb(mqtt_client, node))
            node.has_nmt_callback = True
    except SdoAbortedError as e:
        pass

    props = [
        ("node_id", node.id),
        ("device name", node.device_name),
        ("heartbeat time (ms)", node.prod_heartbeat_time)
    ]
    if node.sw_version:
        props.append(("ver", node.sw_version))

    logger.info(", ".join(f"{k}: {v}" for k, v in props))

    entity = EntityRegistry.create(
        0, node, 0, mqtt_topic_prefix=mqtt_topic_prefix
    )
    node.ntm_state_entity = entity
    entity.set_property("name", "NMT State")
    await entity.publish_config(mqtt_client)
    logger.info("  entity: %r", entity)

    try:
        has_firmware_update = await node.sdo["Firmware"]["Firmware Max Index"].aget_raw()
    except SdoAbortedError as e:
        has_firmware_update = 0

    update_entity = EntityRegistry.create(
        255, node, 255, mqtt_topic_prefix=mqtt_topic_prefix
    )
    update_entity.disable_upload = not has_firmware_update

    await update_entity.publish_config(mqtt_client)
    logger.info("  entity: %r", update_entity)
    node.update_entity = update_entity

    if revision == 0:
        entity_types_index = 0x2000
        data_type = datatypes.UNSIGNED8
    elif revision == 1:
        entity_types_index = 0x2001
        data_type = datatypes.UNSIGNED32
    else:
        logger.warning("node revision: %d is not supported")
        return

    entity_types_index = 0x2000 if revision == 0 else 0x2001

    entity_types = ODArray("EntityTypes", entity_types_index)
    entity_types.add_member(od_variable(datatypes.UNSIGNED8, "EntityTypes_len", entity_types_index, 0))
    entity_types.add_member(od_variable(data_type, "EntityTypes_item1", entity_types_index, 1))
    node.object_dictionary.add_object(entity_types)

    node_entity_ids = set()

    async for entity_index, entity_type in async_try_iter_items(
        node.sdo["EntityTypes"]
    ):
        try:
            entity = EntityRegistry.create(
                entity_type,
                node,
                entity_index,
                mqtt_topic_prefix=mqtt_topic_prefix,
            )
            node_entity_ids.add(entity.unique_id)
            logger.info("  entity: %r", entity)
        except KeyError:
            logger.warning(
                "  Unknown entity type: %d, index: %d",
                entity_type,
                entity_index,
            )
            continue

        base_index = 0x2000 + entity_index * 16
        node.object_dictionary.add_object(ODRecord(
            "states", base_index + 1
        ))
        node.object_dictionary.add_object(ODRecord(
            "cmds", base_index + 2
        ))

        entity.setup_object_dictionary(node, base_index)

        async for key, value in async_try_iter_items(node.sdo[base_index]):
            entity.set_metadata_property(key, value)

        await entity.publish_config(mqtt_client)

    await asyncio.sleep(1.0)
    for entity in Entity.entities():
        if entity.entity_index in (0, 255):
            continue  # skip NMT State entity
        if entity.node.id == node.id:
            if entity.unique_id in node_entity_ids:
                await entity.mqtt_initial_publish(mqtt_client)
            else:
                await entity.remove_config(mqtt_client)
                Entity.remove_entity(entity.unique_id)

    for _, map in node.tpdo.map.items():
        map.clear()
        map.callbacks.clear()  # probably above clear should do that??

    await node.tpdo.aread()

    on_tptd = get_tptd_cb(mqtt_client)
    for _, map in node.tpdo.map.items():
        map.add_callback(on_tptd)

    if node.update_entity:
        rev, _ = FIRMWARE_MAP[node.id]
        await node.update_entity.publish_version(mqtt_client, rev)


async def register_node(mqtt_client, mqtt_topic_prefix: str, can_network: Network, node: RemoteNode):

    try:
        vendor_id = await node.sdo["Identity"]["VendorId"].aget_raw()
        product_code = await node.sdo["Identity"]["ProductCode"].aget_raw()
        revision = await node.sdo["Identity"]["RevisionNumber"].aget_raw()
    except SdoAbortedError as e:
        logger.warning("node: %02x can't read identity info, skipping", node.id)
        return

    node.is_supported = (vendor_id == ESPHOME_VENDOR_ID and product_code == ESPHOME_PRODUCT_CODE)

    if not node.is_supported:
        logger.warning(
            "node %02x: vendor: %s, product: %s is not supported, skipping",
            node.id,
            vendor_id,
            product_code,
        )
        node.is_initialized = True
        return

    logger.info("RevisionNumber: %08x", revision)

    await process_node(mqtt_client, mqtt_topic_prefix, node, revision)

    node.is_initialized = True


def setup_common_od(od):
    for tpdo_index in range(8):
        tpdo_params = ODRecord(f"TPDO{tpdo_index}_params", 0x1800 + tpdo_index)
        tpdo_params.add_member(
            od_variable(datatypes.UNSIGNED8, f"TPDO{tpdo_index}_params_len", 0x1800 + tpdo_index, 0, default=2)
        )
        tpdo_params.add_member(od_variable(datatypes.UNSIGNED32, f"TPDO{tpdo_index}_cob_id", 0x1800 + tpdo_index, 1))
        tpdo_params.add_member(od_variable(datatypes.UNSIGNED8, f"TPDO{tpdo_index}_transmission_type", 0x1800 + tpdo_index, 2))
        od.add_object(tpdo_params)

        tpdo_mappings = ODRecord(f"TPDO{tpdo_index}_mappings", 0x1a00 + tpdo_index)
        tpdo_mappings.add_member(
            od_variable(datatypes.UNSIGNED8, f"TPDO{tpdo_index}_mappings_len", 0x1a00 + tpdo_index, 0, default=64)
        )
        for subidx in range(64):
            tpdo_mappings.add_member(
                od_variable(
                    datatypes.UNSIGNED32,
                    f"TPDO{tpdo_index}_mappings_item{subidx+1}",
                    0x1a00 + tpdo_index,
                    subidx+1,
                )
            )
        od.add_object(tpdo_mappings)


async def can_reader(can_network, mqtt_client, mqtt_topic_prefix, sdo_response_timeout=None, sdo_max_retries=None):
    watchdog_timer.reset()
    await publish_can2mqtt_status(mqtt_client, mqtt_topic_prefix, "online")

    while True:
        for node_id in can_network.scanner.nodes:
            node = can_network.get(node_id)
            if not node:
                od = import_od(os.path.join(BASE_DIR, "eds/esphome.eds"))
                setup_common_od(od)
                node = can_network.add_node(node_id, od)
                if sdo_response_timeout is not None:
                    node.sdo.RESPONSE_TIMEOUT = sdo_response_timeout
                if sdo_max_retries is not None:
                    node.sdo.MAX_RETRIES = sdo_max_retries

                node.is_initialized = False  # basic initialization was done, reset on node reboot
                node.is_supported = False  # it is ESPHome node

                node.last_heartbeat_time = time.time()
                node.availability = None
                node.availability_topic = (
                    f"{mqtt_topic_prefix}/can_{node_id:03x}/availability"
                )
                node.prod_heartbeat_time = None
                node.sw_version = None
                node.hw_version = None
                node.device_name = None
                node.ntm_state_entity = None
                node.has_nmt_callback = False

            if not node.is_initialized and node.nmt.state == "OPERATIONAL":
                try:
                    logger.info("registering node: %02x", node.id)
                    await register_node(mqtt_client, mqtt_topic_prefix, can_network, node)
                except SdoCommunicationError as e:
                    logger.warning("node: %02x: %r", node.id, e)
                except:
                    logger.exception("node: %02x: unknown exception", node.id)

            if node.is_supported:
                is_online = not node.prod_heartbeat_time or (
                    (time.time() - node.last_heartbeat_time)
                    < 2 * node.prod_heartbeat_time / 1000.0
                )
                availability = "online" if is_online else "offline"
                if node.availability != availability:
                    logger.info("node %s is %s", node_id, availability)
                    node.availability = availability
                    await mqtt_client.publish(
                        node.availability_topic, payload=node.availability
                    )

        await asyncio.sleep(1.0)

        if watchdog_timer.passed():
            raise QuitException("watchdog timeout", WATCHDOG_TIMEOUT_EXIT_CODE)


async def firmware_upload(can_network: Network, node_id: int, payload):
    try:
        node: RemoteNode = can_network.get(node_id)
        if node:
            # TODO:
            # node.nmt.send_command(NMT_COMMANDS["PRE-OPERATIONAL"])
            logger.info("Upload of %d bytes to node %d started", len(payload), node_id)
            t = time.time()
            firmware = node.sdo["Firmware"]
            await firmware["Firmware Size"].aset_raw(len(payload))
            await firmware["Firmware MD5"].aset_raw(hashlib.md5(payload).digest())
            logger.info("writing Firmware Data (block transfer)")
            compressed = zlib.compress(payload)
            logger.info("firmware size: %d, compressed: %d", len(payload), len(compressed))
            await firmware["Firmware Data"].aset_data(compressed, block_transfer=True)
            dt = time.time() - t
            logger.info(
                "Successfuly uploaded %d bytes to node %d, (%.1f seconds, %.0f bytes/sec)",
                len(compressed), node_id, dt, len(compressed) / dt
            )
        else:
            logger.warning("node %d doesn't exist", node_id)
    except Exception as e:
        logger.exception("firmware update error: %s", e)


async def mqtt_reader(mqtt_client, can_network, mqtt_topic_prefix):
    NODE_CMD = re.compile(f"{mqtt_topic_prefix}/node_cmd_([0-9a-f]{{3}})/(nmt|firmware|write|update)(/.*)?$")
    async with mqtt_client.messages() as messages:
        await mqtt_client.subscribe(f"{mqtt_topic_prefix}/#")
        async for message in messages:
            if len(message.payload) < 20:
                logger.debug("recv mqtt topic: %s %s", message.topic, message.payload)
            else:
                logger.debug(
                    "recv mqtt topic: %s payload len: %s",
                    message.topic,
                    len(message.payload),
                )

            if message.topic.value == f"{mqtt_topic_prefix}/nmt":
                await can_network.scanner.scan()
                continue

            if message.topic.value == f"{mqtt_topic_prefix}/status":
                if message.payload == b"online":
                    for entity in Entity.entities():
                        await entity.publish_config(mqtt_client)
                    await asyncio.sleep(1.0)
                    await publish_can2mqtt_status(mqtt_client, mqtt_topic_prefix, "online")
                    for entity in Entity.entities():
                        await entity.mqtt_initial_publish(mqtt_client)
                    for node_id in can_network.scanner.nodes:
                            node = can_network.get(node_id)
                            if node and node.is_supported:
                                await mqtt_client.publish(
                                    node.availability_topic, payload="online"
                                )
                continue

            entity = CommandMixin.get_entity_by_cmd_topic(message.topic.value)
            if entity:
                try:
                    cmd_key, value = entity.get_can_cmd(
                        message.topic.value, message.payload
                    )
                    logger.info(
                        "entity: %s cmd_key: %08x, value: %s",
                        entity,
                        cmd_key,
                        value,
                    )

                    subidx = (cmd_key >> 8) & 255
                    idx = cmd_key >> 16
                    var = entity.node.sdo[idx]
                    if subidx:
                        var = var[subidx]
                    await var.aset_raw(value)
                except Exception as e:
                    logger.error("%s", e)
            else:
                m = NODE_CMD.match(message.topic.value)
                match m and m.groups():
                    case (node_id, "nmt", _):
                        cmd = int(message.payload.decode("utf-8"))
                        logger.info("sent nmt command %d to node %s", cmd, node_id)
                        can_network.send_message(0, [cmd, int(node_id, 16)])
                    case (node_id, "update", _):
                        node_id = int(node_id, 16)
                        node = can_network.get(node_id)
                        # TODO
                        # node.update_entity.disable_upload = True
                        await node.update_entity.publish_config(mqtt_client)
                        rev, path = FIRMWARE_MAP[node_id]
                        logger.info("firmware update, node_id: %s, rev: %s, path: %s", node_id, rev, path)
                        with open(path, "rb") as f:
                            asyncio.create_task(
                                firmware_upload(can_network, node_id, f.read())
                            )
                    case (node_id, "firmware", _):
                        asyncio.create_task(
                            firmware_upload(can_network, int(node_id, 16), message.payload)
                        )
                    case (node_id, "write", arg):
                        arg = arg[1:]
                        try:
                            node_id = int(node_id, 16)
                            dest = [int(i, 16) for i in arg.split(":")]
                            index = dest[0]
                            start_subidx = dest[1] if len(dest) > 1 else 0
                        except ValueError:
                            logger.warning("invalid write command: %s", message.payload)
                            continue
                        try:
                            data = [
                                int(v, 16) for v in re.split(b"[ ,]+", message.payload)
                            ]
                            logger.info(
                                f"write to node {node_id} at index: {index:04x}:{start_subidx:02x}, data: {data}"
                            )
                            for subidx, value in enumerate(data, start_subidx):
                                await can_network[node_id].sdo[index][subidx].aset_raw(
                                    value
                                )
                        except SdoAbortedError as e:
                            logger.error("sdo error: %s", e)
                    case _:
                        if m:
                            logger.warning("unknown command: %s", m)

def get_can2mqtt_status_topic(mqtt_topic_prefix):
    return f"{mqtt_topic_prefix}/can2mqtt/status"


async def publish_can2mqtt_status(mqtt_client, mqtt_topic_prefix, status):
    status_topic = get_can2mqtt_status_topic(mqtt_topic_prefix)
    await mqtt_client.publish(status_topic, payload=status, retain=False)


class FirmwareHandler(firmware_scanner.BaseFirmwareEventHandler):
    def __init__(self, can_network, mqtt_client):
        super().__init__()
        self.can_network = can_network
        self.mqtt_client = mqtt_client

    def publish_version(self, node_id, ver):
        node = self.can_network.get(node_id)
        if node and node.update_entity:
            asyncio.create_task(node.update_entity.publish_version(self.mqtt_client, ver))

    def on_delete_firmware(self, path):
        logger.info("remove firmware: %s", path)
        for node_id, (rev, _path) in FIRMWARE_MAP.items():
            if _path == path:
                return self.publish_version(node_id, None)

    def on_new_firmware(self, path, node_id, ver):
        logger.info("new_firmware: %s, node_id: %s, ver: %s", path, node_id, ver)
        _ver, _ = FIRMWARE_MAP[node_id]
        if not _ver or _ver < ver:
            FIRMWARE_MAP[node_id] = (ver, path)
        self.publish_version(node_id, ver)


async def start(
    mqtt_server='localhost',
    interface=None,
    channel=None,
    bitrate=125000,
    mqtt_topic_prefix = 'homeassistant',
    sdo_response_timeout=None,
    sdo_max_retries=None,
    firmware_dir=None,
    interface_opts_json=None,
    watchdog_timeout=60,
    **kwargs,
):
    global watchdog_timer
    watchdog_timer = WatchdogTimer(watchdog_timeout)

    mqtt_server, extra_auth = parse_mqtt_server_url(mqtt_server)
    will = aiomqtt.Will(
        get_can2mqtt_status_topic(mqtt_topic_prefix), b"offline", 1, retain=True
    )
    logger.info("server: %s, extra_auth: %s", mqtt_server, extra_auth)
    async with aiomqtt.Client(mqtt_server, will=will, **extra_auth) as mqtt_client:
        try:
            await publish_can2mqtt_status(mqtt_client, mqtt_topic_prefix, "online")
            can_network = canopen.Network()
            # can_network.listeners.append(lambda msg: logger.debug("%s", msg))
            loop = asyncio.get_running_loop()

            if interface_opts_json:
                can_kwargs = json.loads(interface_opts_json)
            else:
                can_kwargs = {}
            can_network.connect(
                loop=loop, interface=interface, channel=channel, bitrate=bitrate, **can_kwargs
            )

            if firmware_dir:
                firmware_scanner.init(loop, firmware_dir, FirmwareHandler(can_network, mqtt_client))

            await asyncio.gather(
                can_reader(
                    can_network,
                    mqtt_client,
                    mqtt_topic_prefix=mqtt_topic_prefix,
                    sdo_response_timeout=sdo_response_timeout,
                    sdo_max_retries=sdo_max_retries,
                ),
                mqtt_reader(
                    mqtt_client, can_network, mqtt_topic_prefix=mqtt_topic_prefix
                ),
            )
        except QuitException as e:
            logger.info("quitting: %s, exit_code: %d", e, e.exit_code)
            return e.exit_code
        finally:
            logger.info("publishing offline status")
            for node_id in can_network.scanner.nodes:
                node = can_network.get(node_id)
                if node and node.is_supported:
                    await mqtt_client.publish(
                        node.availability_topic, payload="offline"
                    )
            await publish_can2mqtt_status(mqtt_client, mqtt_topic_prefix, "offline")
