"""Number entities: limits for Home Assistant and scaled states / commands (run: pytest tests/)."""

import math
import os
import sys

import canopen
from canopen.objectdictionary import ODRecord

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from can2mqtt import entities  # noqa: E402

PREFIX = "homeassistant"
NODE_ID = 0x35


def make_entity(cls, entity_index, metadata):
    """An entity set up the way register_node() does it, with `metadata` as read over SDO."""
    node = canopen.RemoteNode(NODE_ID, canopen.ObjectDictionary())
    node.availability_topic = f"{PREFIX}/can_{NODE_ID:03x}/availability"
    node.device_name = "dimmer2"
    node.sw_version = node.hw_version = ""
    entity = cls(node, entity_index, mqtt_topic_prefix=PREFIX, caps=0)
    base_index = 0x2000 + entity_index * 16
    node.object_dictionary.add_object(ODRecord("states", base_index + 1))
    node.object_dictionary.add_object(ODRecord("cmds", base_index + 2))
    entity.setup_object_dictionary(node, base_index)
    for key, value in metadata.items():
        entity.set_metadata_property(key, value)
    return entity


def cmd_topic(entity):
    return entity.get_mqtt_command_topic(entity.command_map[0])


def test_number8_identity_encoding_with_limits():
    # vent_gear: size 1, encoding 0..254 (the byte is the value), the number itself 0..3
    entity = make_entity(
        entities.Number8,
        10,
        {1: b"vent_gear", 7: 0.0, 8: 254.0, 9: 0.0, 10: 3.0, 11: 1.0},
    )
    config = entity.get_mqtt_config()
    assert (config["min"], config["max"], config["step"]) == (0.0, 3.0, 1.0)
    assert "min_value" not in config and "max_value" not in config
    assert entity.get_can_cmd(cmd_topic(entity), b"2") == (entity.command_map[0], 2)
    assert entity.get_mqtt_state(entity.state_map[0], 2)[1] == "2.0"


def test_number16_scales_commands_and_states():
    # vent_party: size 2, encoding 0..720
    entity = make_entity(
        entities.Number16,
        11,
        {1: b"vent_party", 7: 0.0, 8: 720.0, 9: 0.0, 10: 720.0, 11: 1.0},
    )
    config = entity.get_mqtt_config()
    assert (config["min"], config["max"]) == (0.0, 720.0)
    _, wire = entity.get_can_cmd(cmd_topic(entity), b"360")
    assert wire == 32767  # round(65534 * 360 / 720)
    assert entity.get_can_cmd(cmd_topic(entity), b"720.0")[1] == 65534
    value = float(entity.get_mqtt_state(entity.state_map[0], 91)[1])
    assert round(value) == 1  # 91 * 720 / 65534 = 0.99995
    assert entity.get_mqtt_state(entity.state_map[0], 65535)[1] == ""  # NaN


def test_number8_without_limits_falls_back_to_the_encoding_range():
    # older firmware: no metadata 9..11
    entity = make_entity(entities.Number8, 3, {1: b"n", 7: 0.0, 8: 3.0})
    config = entity.get_mqtt_config()
    assert (config["min"], config["max"]) == (0.0, 3.0)
    assert "step" not in config
    # an encoding of 0..3 spreads the values over the byte
    assert entity.get_can_cmd(cmd_topic(entity), b"1")[1] == 85


def test_number_real32_limits():
    entity = make_entity(entities.Number, 4, {1: b"n", 9: -5.0, 10: 5.0, 11: 0.5})
    config = entity.get_mqtt_config()
    assert (config["min"], config["max"], config["step"]) == (-5.0, 5.0, 0.5)
    assert entity.get_can_cmd(cmd_topic(entity), b"1.5")[1] == 1.5


def test_number_real32_without_limits_uses_home_assistant_defaults():
    config = make_entity(entities.Number, 4, {1: b"n"}).get_mqtt_config()
    assert "min" not in config and "max" not in config


def test_sensor8_keeps_the_encoding_range_out_of_discovery():
    entity = make_entity(entities.Sensor8, 5, {1: b"t", 7: -40.0, 8: 85.0})
    config = entity.get_mqtt_config()
    assert not {"min", "max", "min_value", "max_value"} & config.keys()
    assert float(entity.get_mqtt_state(entity.state_map[0], 254)[1]) == 85.0
    assert math.isclose(float(entity.get_mqtt_state(entity.state_map[0], 0)[1]), -40.0)


def test_metadata_records_name_each_sub():
    entity = make_entity(entities.Number16, 11, {})
    record = entity.node.object_dictionary[0x2000 + 11 * 16]
    assert {sub: record[sub].name for sub in (7, 8, 9, 10, 11)} == {
        7: "meta_min_value",
        8: "meta_max_value",
        9: "meta_min",
        10: "meta_max",
        11: "meta_step",
    }
