import logging
import json
import struct

import can

from . import consts

logger = logging.getLogger("can2mqtt.entities")


class Entity:
    def __init__(self, entity_id, mqtt_topic_prefix):
        self.entity_id = entity_id
        unique_id = "can_{:x}".format(entity_id)
        self._mqtt_topic_prefix = mqtt_topic_prefix

        self._properties = {
            "unique_id": unique_id,
            "object_id": unique_id,
        }

    def __repr__(self):
        return f"{self.__class__.__name__}(**{self._properties})"

    @property
    def type_name(self):
        return self.TYPE_ID[1]

    def update_properties(self, props):
        if hasattr(props, "items"):
            props = props.items()
        for k, v in props:
            if v is not None:
                self._properties[k] = v
            else:
                self._properties.pop(k, None)

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

    def get_config_topics_to_invalidate(self, supported_type_names):
        return [
            self.get_config_topic(type_name)
            for type_name in supported_type_names
            if type_name != self.type_name
        ]

    def send_can_cmd(self, can_bus, property_id, payload):
        arbitration_id = (self.entity_id << 4) | (property_id & 0xf)

        can_msg = can.Message(arbitration_id=arbitration_id, data=payload)
        logger.debug("send can msg: %r", can_msg)
        can_bus.send(can_msg)

    async def process_mqtt_command(self, cmd, payload, can_bus):
        pass


class EntityRegistry:
    _by_id = {}
    _by_name = {}

    def __init__(self, mqtt_topic_prefix):
        self._registry = {}
        self.mqtt_topic_prefix = mqtt_topic_prefix

    def get(self, entity_id) -> Entity:
        return self._registry.get(entity_id)

    def all_type_names(self):
        return self._by_name.keys()

    @classmethod
    def register(cls, entity_klass):
        _id, _name = entity_klass.TYPE_ID
        cls._by_id[_id] = entity_klass
        cls._by_name[_name] = entity_klass

    def mqtt_configure(self, type_name, entity_id, payload):
        entity = self._registry.get(entity_id)
        if entity is not None:
            logger.warning("entity %s is already configured, skipping", entity_id)
            return

        entity_klass = self._by_name.get(type_name)
        if entity_klass is None:
            logger.warning("entity type %s is not supported (yet)", type_name)
            return

        entity = self._registry[entity_id] = entity_klass(
            entity_id, self.mqtt_topic_prefix
        )
        entity.update_properties(json.loads(payload))

    def can_configure(self, type_id, entity_id, payload):
        entity_klass = self._by_id.get(type_id)
        if entity_klass is None:
            logger.warning("can entity id %s is not supported (yet)", type_id)
            return
        entity = self._registry[entity_id] = entity_klass(
            entity_id, self.mqtt_topic_prefix
        )
        return entity

@EntityRegistry.register
class Sensor(Entity):
    TYPE_ID = (consts.ENTITY_TYPE_SENSOR, "sensor")

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._properties.update(
            {"state_topic": self.state_topic}
        )

    async def process_can_frame(self, property_id, data, mqtt_client):
        if property_id == consts.PROPERTY_STATE0:
            if len(data) == 4:
                payload = str(struct.unpack_from("f", data)[0])
            elif len(data) == 8:
                payload = str(struct.unpack_from("d", data)[0])
            else:
                return
            await mqtt_client.publish(self.state_topic, payload=payload)


@EntityRegistry.register
class BinarySensor(Entity):
    TYPE_ID = (consts.ENTITY_TYPE_BINARY_SENSOR, "binary_sensor")

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._properties.update(
            {"state_topic": self.state_topic}
        )

    async def process_can_frame(self, property_id, data, mqtt_client):
        if property_id == consts.PROPERTY_STATE0:
            is_on = data and data[0]
            payload = is_on and "ON" or "OFF"
            await mqtt_client.publish(self.state_topic, payload=payload)


@EntityRegistry.register
class Switch(Entity):
    TYPE_ID = (consts.ENTITY_TYPE_SWITCH, "switch")

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._properties.update(
            {"assumed_state": False,
             "command_topic": self.command_topic,
             "state_topic": self.state_topic,
             }
        )

    async def process_mqtt_command(self, cmd, payload, can_bus):
        if cmd == "set":
            can_payload = b"\x01" if payload == b"ON" else b"\x00"
            self.send_can_cmd(can_bus, consts.PROPERTY_CMD0, can_payload)

    async def process_can_frame(self, property_id, data, mqtt_client):
        if property_id == consts.PROPERTY_STATE0:
            is_on = data and data[0]
            payload = is_on and "ON" or "OFF"
            await mqtt_client.publish(self.state_topic, payload=payload)


@EntityRegistry.register
class Cover(Entity):
    TYPE_ID = (consts.ENTITY_TYPE_COVER, "cover")

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._properties.update(
            {
                "command_topic": self.command_topic,
                "position_topic": self.position_topic,
                "set_position_topic": self.set_position_topic,
                "state_topic": self.state_topic,
                # "assumed_state": True,
                "position_closed": 0,
                "position_open": 100,
            }
        )

    CMDS = {
        b"OPEN": b"\x01",
        b"CLOSE": b"\x02",
        b"STOP": b"\x00",
    }

    async def process_mqtt_command(self, cmd, payload, can_bus):
        if cmd == "set":
            can_cmd = self.CMDS.get(payload)
            if can_cmd is not None:
                self.send_can_cmd(can_bus, consts.PROPERTY_CMD0, can_cmd)
            else:
                logger.warning("unknown MQTT command: %s", payload)
        elif cmd == "set_position":
            can_cmd = struct.pack("f", float(payload) / 100)
            self.send_can_cmd(can_bus, consts.PROPERTY_CMD1, can_cmd)

    STATES = {
        0: "open",
        1: "opening",
        2: "closed",
        3: "closing",
    }

    async def process_can_frame(self, property_id, data, mqtt_client):
        if property_id == consts.PROPERTY_STATE0:
            try:
                pos, state = struct.unpack_from("fb", data)
            except struct.error as e:
                logger.warning("unpack error: %s", e)
                return
            await mqtt_client.publish(self.state_topic, payload=self.STATES[state])
            await mqtt_client.publish(self.position_topic, payload=str(int(pos * 100)))

    @property
    def position_topic(self):
        return f"{self.topic}/position"

    @property
    def set_position_topic(self):
        return f"{self.topic}/set_position"
