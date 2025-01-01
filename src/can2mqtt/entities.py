from canopen.objectdictionary import datatypes
from collections import defaultdict
from functools import cached_property
import logging
import json
import math
from canopen.objectdictionary import ODVariable, ODRecord
from canopen.node import RemoteNode


class OctetString(ODVariable):
    def __init__(self, name, index, subindex):
        super().__init__(name, index, subindex)
        self.data_type = datatypes.OCTET_STRING

logger = logging.getLogger(__name__)


def bool2onoff(value):
    return b"ON" if value else b"OFF"


def onoff2bool(value):
    return value == b"ON"


def scale_to_wire(value: float|str, min_val: float, max_val: float, max_int: int) -> int:
    value = float(value)
    if math.isnan(value):
        return max_int
    result = round((max_int - 1) * (value - min_val) / (max_val - min_val))
    return max(0, min(max_int - 1, int(result)))


def scale_from_wire(value: int, min_val: float, max_val: float, max_int: int) -> float:
    if value == max_int:
        return math.nan
    return value * (max_val - min_val) / (max_int - 1) + min_val


def percentage_to_wire(value: float|str):
    return scale_to_wire(value, 0.0, 100.0, 255)


def percentage_from_wire(value: int):
    return scale_from_wire(value, 0.0, 100.0, 255)


def color_temp_to_wire(value: float|str) -> int:
  value = float(value)
  return scale_to_wire(value, 100.0, 1000.0, 255)


def color_temp_from_wire(value: int) -> float:
  # round to int, floats are not expected on mqtt state topic
  return int(scale_from_wire(value, 100.0, 1000.0, 255))


def brightness_to_wire(brightness: float|str):
    return scale_to_wire(brightness, 0, 254, 255)


def brightness_from_wire(value):
    return scale_from_wire(value, 0, 254, 255)

class StateMixin:
    _node_state_key_2_entity = defaultdict(dict)

    STATES = [
        ("state_topic", str, datatypes.UNSIGNED8),
    ]

    state_map = None

    @classmethod
    def get_entity_by_node_state_key(cls, node_id, state_key):
        return cls._node_state_key_2_entity[node_id].get(state_key)

    def setup_state_topics(self, state_map):
        self.state_map = state_map
        logger.debug("setup state topics for %s, %s", self, state_map)
        for state_key in self.state_map:
            self._node_state_key_2_entity[self.node.id][state_key] = self

    def get_mqtt_config(self):
        config = super(StateMixin, self).get_mqtt_config()
        assert len(self.STATES) == len(self.state_map)
        for (topic, *_), state_key in zip(self.STATES, self.state_map):
            config[topic] = self.get_mqtt_state_topic(state_key)
        return config

    def get_mqtt_state_topic(self, state_key):
        return f"{self.mqtt_topic_prefix}/can_state_{self.node.id:03x}_{state_key:08x}"

    def get_mqtt_state(self, state_key, value):
        index = self.state_map.index(state_key)
        return self.get_mqtt_state_topic(state_key), self.STATES[index][1](value)

    def setup_object_dictionary(self, node, base_index):
        super().setup_object_dictionary(node, base_index)
        state_map = []
        index = base_index + 1
        for sub, (_, _, _type) in enumerate(self.STATES, 1):
            v = ODVariable("state", index, sub)
            v.data_type = _type
            node.object_dictionary[index].add_member(v)
            state_map.append((index << 16) | (sub << 8))
        self.setup_state_topics(state_map)

    async def mqtt_initial_publish(self, mqtt_client):
        for state_key in self.state_map:
            value = await self.node.sdo[state_key>>16][(state_key >> 8) & 0xff].aget_raw()
            topic, mqtt_value = self.get_mqtt_state(state_key, value)
            await mqtt_client.publish(topic, mqtt_value, retain=False)


class CommandMixin:
    _mqtt_cmd_topic2entity = dict()

    COMMANDS = [
        ("command_topic", int, datatypes.UNSIGNED8),
    ]
    command_map = None
    _topic2cmdkey = None

    @classmethod
    def get_entity_by_cmd_topic(cls, cmd_topic):
        return cls._mqtt_cmd_topic2entity.get(cmd_topic)

    def setup_command_topics(self, command_map):
        self.command_map = command_map
        self._topic2cmdkey = {}
        for cmd_key in self.command_map:
            topic = self.get_mqtt_command_topic(cmd_key)
            self._mqtt_cmd_topic2entity[topic] = self
            self._topic2cmdkey[topic] = cmd_key

    def get_mqtt_config(self):
        config = super(CommandMixin, self).get_mqtt_config()
        assert len(self.COMMANDS) == len(self.command_map)
        for (topic, *_), cmd_key in zip(self.COMMANDS, self.command_map):
            config[topic] = self.get_mqtt_command_topic(cmd_key)
        return config

    def get_mqtt_command_topic(self, cmd_key):
        return f"{self.mqtt_topic_prefix}/can_cmd_{self.node.id:03x}_{cmd_key:08x}"

    def get_can_cmd(self, topic, value):
        cmd_key = self._topic2cmdkey and self._topic2cmdkey.get(topic)
        if not cmd_key:
            raise ValueError(f"topic {topic} is not recognized")
        index = self.command_map.index(cmd_key)
        return cmd_key, self.COMMANDS[index][1](value)

    def setup_object_dictionary(self, node, base_index):
        super().setup_object_dictionary(node, base_index)
        cmd_map = []
        index = base_index + 2
        for sub, (_, _, _type) in enumerate(self.COMMANDS, 1):
            v = ODVariable("cmd", index, sub)
            v.data_type = _type
            node.object_dictionary[index].add_member(v)
            cmd_map.append((index << 16) | (sub << 8))

        self.setup_command_topics(cmd_map)


class Entity:
    _entities = {}
    NAME_PROP = 1
    TYPE_ID = None
    VERSION = 0
    PROPS = {}

    @cached_property
    def METADATA_PROPERTIES(self):
        return dict(self.get_metadata_properties())

    def get_metadata_properties(self):
        yield 1, "name"
        yield 2, "device_class"

    def __init__(self, node, entity_index, mqtt_topic_prefix, caps):
        self.node = node
        self.entity_index = entity_index
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.caps = caps

        # TODO: add some canbus id part to allow for many can busses
        self.unique_id = f"can_{self.node.id:03x}_{self.entity_index:02x}"
        self.props = {}
        self._entities[self.unique_id] = self

    @classmethod
    def entities(cls):
        return list(cls._entities.values())

    @classmethod
    def remove_entity(cls, unique_id):
        cls._entities.pop(unique_id, None)

    async def publish_config(self, mqtt_client):
        config_topic = self.get_mqtt_config_topic()
        config_payload = self.get_mqtt_config()
        logger.debug("mqtt config_topic: %r, payload: %r", config_topic, config_payload)
        await mqtt_client.publish(
            config_topic, payload=json.dumps(config_payload), retain=False
        )

    async def delete_config(self, mqtt_client):
        config_topic = self.get_mqtt_config_topic()
        logger.debug("delete mqtt config_topic: %r", config_topic)
        await mqtt_client.publish(
            config_topic, payload=None, retain=False
        )

    async def remove_config(self, mqtt_client):
        config_topic = self.get_mqtt_config_topic()
        await mqtt_client.publish(
            config_topic, payload=b'', retain=False
        )

    def set_property(self, key, value):
        self.props[key] = value

    def get_mqtt_config_topic(self):
        return f"{self.mqtt_topic_prefix}/{self.TYPE_NAME}/{self.unique_id}/config"

    def get_mqtt_config(self):
        cfg = {
            # "object_id": self.unique_id,
            "unique_id": self.unique_id,
            "availability": [
                {
                    "topic": self.node.availability_topic,
                },
                {
                    "topic": f"{self.mqtt_topic_prefix}/can2mqtt/status",
                },
            ],
            "availability_mode": "all",
            "device": {
                "identifiers": [f"canopen_node_{self.node.id}"],
                "name": self.node.device_name,
                "sw_version": self.node.sw_version or "",
                "hw_version": self.node.hw_version or "",
                "manufacturer": "mrk",
                "model": "esphome-canopen",
            },
        }
        cfg.update(self.PROPS)
        cfg.update(self.props)
        return cfg

    def __str__(self):
        return f"{self.__class__.__name__}(node={self.node.id}, entity_index={self.entity_index})"

    def __repr__(self):
        args = []
        args.append(f"node_id={self.node.id}")
        args.append(f"entity_index={self.entity_index}")
        args.append(f"props={self.props}")
        args_str = ", ".join(args)
        return f"{self.__class__.__name__}({args_str})"

    def setup_object_dictionary(self, node: RemoteNode, base_index):
        node.object_dictionary.add_object(ODRecord(f"node {node.id:02x} metadata", base_index))
        node.object_dictionary[base_index].add_member(OctetString("name", base_index, 1))
        node.object_dictionary[base_index].add_member(OctetString("device_class", base_index, 2))


    def set_metadata_property(self, key, value):
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        name = self.METADATA_PROPERTIES.get(key)
        if name:
            logger.debug("\t%s %s: %s", name, key, value)
            self.set_property(name, value)
        else:
            logger.warning("\tunknown metadata property %s: %s", key, value)

    async def mqtt_initial_publish(self, _mqtt_client):
        pass

class EntityRegistry:
    _by_type = {}

    @classmethod
    def register(cls, entity_class):
        cls._by_type[(entity_class.TYPE_ID, entity_class.VERSION)] = entity_class
        return entity_class

    @classmethod
    def create(cls, type_id, node, entity_index, mqtt_topic_prefix):
        version = (type_id >> 8) & 0xff
        caps = (type_id >> 16) & 0xffff
        type_id = type_id & 0xff
        logger.info("type_id: %s, version: %s, caps: %s", type_id, version, caps)

        return cls._by_type[(type_id, version)](node, entity_index, mqtt_topic_prefix, caps)


@EntityRegistry.register
class Update(Entity):
    TYPE_ID = 255
    TYPE_NAME = "update"
    STATES = [
        ("state_topic", str, str),
    ]

    disable_upload = False

    def get_state_topic(self):
        return f"{self.mqtt_topic_prefix}/node_state_{self.node.id:03x}/update"

    def get_command_topic(self):
        return f"{self.mqtt_topic_prefix}/node_cmd_{self.node.id:03x}/update"

    def get_mqtt_config(self):
        config = super().get_mqtt_config()
        config["state_topic"] = self.get_state_topic()

        config["device_class"] = "firmware"
        config["name"] = "Update"
        config["icon"] = "mdi:file-download-outline"
        if not self.disable_upload:
            config["command_topic"] = self.get_command_topic()
        config["payload_install"] = "install"
        return config

    async def publish_version(self, mqtt_client, ver):
        state_topic = self.get_state_topic()
        payload = json.dumps({
            "installed_version": self.node.sw_version,
            "latest_version": ver or self.node.sw_version
        })
        logger.info("publish_version: %s", payload)
        await mqtt_client.publish(state_topic, payload=payload, retain=False)

    async def mqtt_initial_publish(self, mqtt_client):
        await self.publish_version(mqtt_client, None)


@EntityRegistry.register
class NMTStateSensor(Entity):
    TYPE_ID = 0
    TYPE_NAME = "sensor"
    STATES = [
        ("state_topic", str, datatypes.UNSIGNED8),
    ]

    def get_state_topic(self):
        return f"{self.mqtt_topic_prefix}/can_state_{self.node.id:03x}_nmt_state"

    def get_mqtt_config(self):
        config = super().get_mqtt_config()
        config["state_topic"] = self.get_state_topic()
        return config


def float_to_str(value):
    return not math.isnan(value) and str(value) or ''


@EntityRegistry.register
class Sensor(StateMixin, Entity):
    TYPE_ID = 1
    TYPE_NAME = "sensor"
    STATES = [
        ("state_topic", float_to_str, datatypes.REAL32),
    ]

    def get_metadata_properties(self):
        yield from super().get_metadata_properties()
        yield 3, "unit_of_measurement"
        yield 4, "state_class"

    def setup_object_dictionary(self, node: RemoteNode, base_index):
        super().setup_object_dictionary(node, base_index)
        logger.info("sensor, setup od")
        node.object_dictionary[base_index].add_member(OctetString("unit_of_measurement", base_index, 3))
        node.object_dictionary[base_index].add_member(OctetString("state_class", base_index, 4))


class MinMaxValueMixin:

    def get_metadata_properties(self):
        yield from super().get_metadata_properties()
        yield 7, "min_value"
        yield 8, "max_value"

    def setup_object_dictionary(self, node, base_index):
        super().setup_object_dictionary(node, base_index)
        logger.info("min max, setup od")
        v = ODVariable("meta_min_value", base_index, 7)
        v.data_type = datatypes.REAL32
        node.object_dictionary[base_index].add_member(v)
        v = ODVariable("meta_min_value", base_index, 8)
        v.data_type = datatypes.REAL32
        node.object_dictionary[base_index].add_member(v)

    def get_mqtt_state(self, state_key, value):
        if value == self.N_LEVELS:
            value2 = math.nan
        else:
            min_val = self.props.get("min_value", 0)
            max_val = self.props.get("max_value", self.N_LEVELS - 1)
            value2 = scale_from_wire(value, min_val, max_val, self.N_LEVELS)
        return super().get_mqtt_state(state_key, value2)

    # TODO: add scaling for commands in get_can_cmd


@EntityRegistry.register
class Sensor8(MinMaxValueMixin, Sensor):
    TYPE_ID = 6
    TYPE_NAME = "sensor"
    STATES = [
        ("state_topic", float_to_str, datatypes.UNSIGNED8),
    ]
    N_LEVELS = 255


@EntityRegistry.register
class Sensor16(MinMaxValueMixin, Sensor):
    TYPE_ID = 7
    TYPE_NAME = "sensor"
    STATES = [
        ("state_topic", float_to_str, datatypes.UNSIGNED16),
    ]
    N_LEVELS = 65535


@EntityRegistry.register
class BinarySensor(StateMixin, Entity):
    TYPE_ID = 2
    TYPE_NAME = "binary_sensor"

    STATES = [
        ("state_topic", bool2onoff, datatypes.UNSIGNED8),
    ]


@EntityRegistry.register
class Switch(StateMixin, CommandMixin, Entity):
    TYPE_ID = 3
    TYPE_NAME = "switch"

    STATES = [
        ("state_topic", bool2onoff, datatypes.UNSIGNED8),
    ]
    COMMANDS = [
        ("command_topic", onoff2bool, datatypes.UNSIGNED8),
    ]
    PROPS = {"assumed_state": False}


@EntityRegistry.register
class Light(StateMixin, CommandMixin, Entity):
    TYPE_ID = 5
    TYPE_NAME = "light"

    STATES = [
        ("state_topic", bool2onoff, datatypes.UNSIGNED8),
        ("brightness_state_topic", brightness_from_wire, datatypes.UNSIGNED8),
        ("color_temp_state_topic", color_temp_from_wire, datatypes.UNSIGNED8),
    ]

    COMMANDS = [
        ("command_topic", onoff2bool, datatypes.UNSIGNED8),
        ("brightness_command_topic", brightness_to_wire, datatypes.UNSIGNED8),
        ("color_temp_command_topic", color_temp_to_wire, datatypes.UNSIGNED8),
    ]

    PROPS = {
        "assumed_state": False,
        "supported_color_modes": ["color_temp"]
    }

    def get_metadata_properties(self):
        yield from super().get_metadata_properties()
        yield 7, "min_mireds"
        yield 8, "max_mireds"

    def setup_object_dictionary(self, node, base_index):
        super().setup_object_dictionary(node, base_index)
        # let's reuse 7 and 8 indices for min/max mireds
        v = ODVariable("min_mireds", base_index, 7)
        v.data_type = datatypes.REAL32
        node.object_dictionary[base_index].add_member(v)
        v = ODVariable("max_mireds", base_index, 8)
        v.data_type = datatypes.REAL32
        node.object_dictionary[base_index].add_member(v)


@EntityRegistry.register
class LightV1(StateMixin, CommandMixin, Entity):
    TYPE_ID = 5
    VERSION = 1
    TYPE_NAME = "light"

    def get_states(self):
        yield ("state_topic", bool2onoff, datatypes.UNSIGNED8)
        if self.supports_brightness():
            yield ("brightness_state_topic", brightness_from_wire, datatypes.UNSIGNED8)
        if self.supports_color_temp():
            yield ("color_temp_state_topic", color_temp_from_wire, datatypes.UNSIGNED8)

    def get_commands(self):
        yield ("command_topic", onoff2bool, datatypes.UNSIGNED8)
        if self.supports_brightness():
            yield ("brightness_command_topic", brightness_to_wire, datatypes.UNSIGNED8)
        if self.supports_color_temp():
            yield ("color_temp_command_topic", color_temp_to_wire, datatypes.UNSIGNED8)

    def get_metadata_properties(self):
        yield from super().get_metadata_properties()
        if self.supports_color_temp():
            yield 7, "min_mireds"
            yield 8, "max_mireds"

    def get_props(self):
        color_modes = {
            1: "onoff",
            2: "brightness",
            4: "color_temp",
        }

        supported_color_modes = [
            v
            for k, v in color_modes.items()
            if self.caps & k
        ]

        yield "supported_color_modes", supported_color_modes


    @cached_property
    def STATES(self):
        return list(self.get_states())

    @cached_property
    def COMMANDS(self):
        return list(self.get_commands())

    @cached_property
    def PROPS(self):
        return dict(self.get_props())

    def supports_brightness(self):
        return self.caps & (4 | 2)

    def supports_color_temp(self):
        return self.caps & 4

    def setup_object_dictionary(self, node, base_index):
        super().setup_object_dictionary(node, base_index)
        # let's reuse 7 and 8 indices for min/max mireds
        v = ODVariable("min_mireds", base_index, 7)
        v.data_type = datatypes.REAL32
        node.object_dictionary[base_index].add_member(v)
        v = ODVariable("max_mireds", base_index, 8)
        v.data_type = datatypes.REAL32
        node.object_dictionary[base_index].add_member(v)



@EntityRegistry.register
class Cover(StateMixin, CommandMixin, Entity):
    TYPE_ID = 4
    TYPE_NAME = "cover"

    PROPS = {
        "position_closed": 0,
        "position_open": 100,
    }

    STATES_DICT = {
        0: "open",
        1: "opening",
        2: "closed",
        3: "closing",
    }

    CMDS = {
        b"STOP": 0,
        b"OPEN": 1,
        b"CLOSE": 2,
    }

    STATES = [
        ("state_topic", STATES_DICT.get, datatypes.UNSIGNED8),
        ("position_topic", percentage_from_wire, datatypes.UNSIGNED8),
    ]

    COMMANDS = [
        ("command_topic", CMDS.get, datatypes.UNSIGNED8),
        ("set_position_topic", percentage_to_wire, datatypes.UNSIGNED8),
    ]


@EntityRegistry.register
class CoverV1(StateMixin, CommandMixin, Entity):
    TYPE_ID = 4
    VERSION = 1
    TYPE_NAME = "cover"


    def get_props(self):
        if self.caps & 1:
            yield "position_closed", 0
            yield "position_open", 100

    @cached_property
    def PROPS(self):
        return dict(self.get_props())

    STATES_DICT = {
        0: "open",
        1: "opening",
        2: "closed",
        3: "closing",
    }

    CMDS = {
        b"STOP": 0,
        b"OPEN": 1,
        b"CLOSE": 2,
    }

    def get_states(self):
        yield ("state_topic", self.STATES_DICT.get, datatypes.UNSIGNED8)
        if self.caps & 1:
            yield ("position_topic", percentage_from_wire, datatypes.UNSIGNED8)
        if self.caps & 2:
            yield ("tilt_status_topic", percentage_from_wire, datatypes.UNSIGNED8)

    @cached_property
    def STATES(self):
        return list(self.get_states())

    def get_commands(self):
        yield ("command_topic", self.CMDS.get, datatypes.UNSIGNED8)
        if self.caps & 1:
            yield ("set_position_topic", percentage_to_wire, datatypes.UNSIGNED8)
        if self.caps & 2:
            yield ("tilt_command_topic", percentage_to_wire, datatypes.UNSIGNED8)

    @cached_property
    def COMMANDS(self):
        return list(self.get_commands())


@EntityRegistry.register
class Number(StateMixin, CommandMixin, Entity):
    TYPE_ID = 8
    TYPE_NAME = "number"
    STATES = [
        ("state_topic", float_to_str, datatypes.REAL32),
    ]
    COMMANDS = [
        ("command_topic", float, datatypes.REAL32)
    ]

@EntityRegistry.register
class Number8(MinMaxValueMixin, StateMixin, CommandMixin, Entity):
    TYPE_ID = 9
    TYPE_NAME = "number"
    STATES = [
        ("state_topic", float_to_str, datatypes.UNSIGNED8),
    ]
    COMMANDS = [
        ("command_topic", int, datatypes.UNSIGNED8),
    ]
    N_LEVELS = 255


@EntityRegistry.register
class Number16(MinMaxValueMixin, StateMixin, CommandMixin, Entity):
    TYPE_ID = 10
    TYPE_NAME = "number"
    STATES = [
        ("state_topic", float_to_str, datatypes.UNSIGNED16),
    ]
    COMMANDS = [
        ("command_topic", int, datatypes.UNSIGNED16),
    ]
    N_LEVELS = 65535


ALARM_COMMANDS = {
    b"DISARM": 0,
    b"ARM_AWAY": 1,
    b"ARM_HOME": 2,
    b"ARM_NIGHT": 3,
    b"ARM_VACATION": 4,
    b"ARM_CUSTOM_BYPASS": 5,
    b"TRIGGER": 127,
}

ALARM_STATES = {
    0: b"disarmed",
    1: b"armed_home",
    2: b"armed_away",
    3: b"armed_night",
    4: b"armed_vacation",
    5: b"armed_custom_bypass",
    6: b"pending",
    7: b"arming",
    8: b"disarming",
    9: b"triggered",
}


@EntityRegistry.register
class Alarm(StateMixin, CommandMixin, Entity):
    TYPE_ID = 16
    TYPE_NAME = "alarm_control_panel"

    STATES = [
        ("state_topic", ALARM_STATES.get, datatypes.UNSIGNED8),
    ]
    COMMANDS = [
        ("command_topic", ALARM_COMMANDS.get, datatypes.UNSIGNED8),
    ]
    PROPS = {
        "assumed_state": False,
        "code_arm_required": False,
        "code_disarm_requried": False,
        "code_trigger_required": False,
    }
