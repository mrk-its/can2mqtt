from canopen.objectdictionary import datatypes
from collections import defaultdict
import logging
import json


logger = logging.getLogger(__name__)


def bool2onoff(value):
    return b"ON" if value else b"OFF"


def onoff2bool(value):
    return value == b"ON"

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

class Entity:
    _entities = {}
    NAME_PROP = 1
    TYPE_ID = None
    STATIC_PROPS = {}

    def __init__(self, node, entity_index, mqtt_topic_prefix):
        self.node = node
        self.entity_index = entity_index
        self.mqtt_topic_prefix = mqtt_topic_prefix

        # TODO: add some canbus id part to allow for many can busses
        self.unique_id = f"can_{self.node.id:03x}_{self.entity_index:02x}"
        self.props = {}
        self._entities[self.unique_id] = self

    @classmethod
    def entities(cls):
        return cls._entities.values()

    async def publish_config(self, mqtt_client):
        config_topic = self.get_mqtt_config_topic()
        config_payload = self.get_mqtt_config()
        logger.debug("mqtt config_topic: %r, payload: %r", config_topic, config_payload)
        await mqtt_client.publish(config_topic, payload=json.dumps(config_payload), retain=False)

    def set_property(self, key, value):
        self.props[key] = value

    def get_mqtt_config_topic(self):
        return f"{self.mqtt_topic_prefix}/{self.TYPE_NAME}/{self.unique_id}/config"

    def get_mqtt_config(self):
        cfg = {
            "object_id": self.unique_id,
            "entity_id": self.unique_id,
            "unique_id": self.unique_id,
        }
        cfg.update(self.STATIC_PROPS)
        cfg.update(self.props)
        return cfg

    def __str__(self):
        return f"{self.__class__.__name__}(node={self.node.id}, entity_index={self.entity_index})"

    def __repr__(self):
        args = []
        args.append(f"node_id={self.node.id}")
        args.append(f"entity_index={self.entity_index}")
        args.append(f"props={self.props}")
        args_str = ', '.join(args)
        return f"{self.__class__.__name__}({args_str})"


class EntityRegistry:
    _by_type = {}

    @classmethod
    def register(cls, entity_class):
        cls._by_type[entity_class.TYPE_ID] = entity_class

    @classmethod
    def create(cls, type_id, node, entity_index, mqtt_topic_prefix):
        return cls._by_type[type_id](node, entity_index, mqtt_topic_prefix)


@EntityRegistry.register
class Sensor(StateMixin, Entity):
    TYPE_ID = 1
    TYPE_NAME = "sensor"


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
    STATIC_PROPS = {
        "assumed_state": False
    }


@EntityRegistry.register
class Light(StateMixin, CommandMixin, Entity):
    TYPE_ID = 5
    TYPE_NAME = "light"

    STATES = [
        ("state_topic", bool2onoff, datatypes.UNSIGNED8),
        ("brightness_state_topic", str, datatypes.UNSIGNED8)
    ]

    COMMANDS = [
        ("command_topic", onoff2bool, datatypes.UNSIGNED8),
        ("brightness_command_topic", int, datatypes.UNSIGNED8),
    ]

    STATIC_PROPS = {
        "assumed_state": False
    }


@EntityRegistry.register
class Cover(StateMixin, CommandMixin, Entity):
    TYPE_ID = 4
    TYPE_NAME = "cover"

    STATIC_PROPS = {
        "position_closed": 0,
        "position_open": 100,
    }

    STATES = {
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
        ("state_topic", STATES.get, datatypes.UNSIGNED8),
        ("position_topic", lambda pos: pos * 100 // 255, datatypes.UNSIGNED8)
    ]

    COMMANDS = [
        ("command_topic", CMDS.get, datatypes.UNSIGNED8),
        ("set_position_topic", lambda pos: int(pos) * 255 // 100, datatypes.UNSIGNED8)
    ]
