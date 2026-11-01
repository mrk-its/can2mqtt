"""NMT buttons (discovery config) and the node_cmd_XXX/nmt command topic (run: pytest tests/)."""

import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import can
import canopen
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from can2mqtt import can2mqtt as c2m  # noqa: E402
from can2mqtt.entities import NMT_BUTTONS, NMTButton, NMTStateSensor, Sensor, Update  # noqa: E402

PREFIX = "homeassistant"


def fake_node(node_id):
    return SimpleNamespace(
        id=node_id,
        availability_topic=f"{PREFIX}/can_{node_id:03x}/availability",
        device_name="test node",
        sw_version="1.0",
        hw_version=None,
    )


def test_restart_button_config():
    config = NMTButton(fake_node(0x12), "restart", PREFIX).get_mqtt_config()
    assert config["unique_id"] == "can_012_nmt_restart"
    assert config["name"] == "Restart"
    assert config["command_topic"] == f"{PREFIX}/node_cmd_012/nmt"
    assert config["payload_press"] == "129"
    assert config["device_class"] == "restart"
    assert config["entity_category"] == "config"
    assert "enabled_by_default" not in config
    assert config["device"]["identifiers"] == ["canopen_node_18"]


@pytest.mark.parametrize("key", ["start", "stop", "pre_operational"])
def test_other_nmt_buttons_disabled_by_default(key):
    config = NMTButton(fake_node(0x12), key, PREFIX).get_mqtt_config()
    assert config["enabled_by_default"] is False
    assert "device_class" not in config
    assert config["payload_press"] == str(NMT_BUTTONS[key][1])


def test_builtin_entities_are_not_removed_as_stale():
    assert NMTButton.BUILTIN and NMTStateSensor.BUILTIN and Update.BUILTIN
    assert not Sensor.BUILTIN


@pytest.mark.parametrize(
    "payload, cmd",
    [
        (b"129", 0x81),
        (b"0x81", 0x81),
        (b"1", 0x01),
        (b"RESET", 0x81),
        (b"reset_communication", 0x82),
        (b"pre_operational", 0x80),
        (b"PRE-OPERATIONAL", 0x80),
        (b"stopped", 0x02),
    ],
)
def test_parse_nmt_command(payload, cmd):
    assert c2m.parse_nmt_command(payload) == cmd


@pytest.mark.parametrize("payload", [b"", b"foo", b"256", b"-1"])
def test_parse_nmt_command_invalid(payload):
    with pytest.raises(ValueError):
        c2m.parse_nmt_command(payload)


class FakeMqtt:
    def __init__(self, messages):
        self._messages = messages
        self.published = []

    async def subscribe(self, topic):
        pass

    async def publish(self, topic, payload=None, retain=False):
        self.published.append((topic, payload))

    @asynccontextmanager
    async def messages(self):
        async def gen():
            for topic, payload in self._messages:
                yield SimpleNamespace(topic=SimpleNamespace(value=topic), payload=payload)

        yield gen()


def run_mqtt_reader(messages, node_ids=()):
    """Feed messages to mqtt_reader(), return the NMT frames sent and the network."""

    async def run():
        channel = f"nmt-{uuid.uuid4()}"
        network = canopen.Network()
        network.connect(interface="virtual", channel=channel, loop=asyncio.get_running_loop())
        for node_id in node_ids:
            network.add_node(node_id, canopen.ObjectDictionary())
        bus = can.Bus(interface="virtual", channel=channel)
        try:
            await c2m.mqtt_reader(FakeMqtt(messages), network, PREFIX)
            frames = []
            while (msg := bus.recv(timeout=0.1)) is not None:
                frames.append((msg.arbitration_id, list(msg.data)))
            return frames, network
        finally:
            bus.shutdown()
            network.disconnect()

    return asyncio.run(run())


def test_restart_button_press_sends_nmt_reset_and_updates_state():
    frames, network = run_mqtt_reader([(f"{PREFIX}/node_cmd_012/nmt", b"129")], [0x12])
    assert frames == [(0, [0x81, 0x12])]
    assert network[0x12].nmt.state == "INITIALISING"


def test_nmt_command_to_unknown_node_and_broadcast():
    frames, _ = run_mqtt_reader(
        [
            (f"{PREFIX}/node_cmd_034/nmt", b"STOPPED"),
            (f"{PREFIX}/node_cmd_000/nmt", b"RESET"),
        ]
    )
    assert frames == [(0, [0x02, 0x34]), (0, [0x81, 0x00])]


def test_invalid_nmt_command_is_ignored():
    frames, _ = run_mqtt_reader(
        [(f"{PREFIX}/node_cmd_012/nmt", b"bogus"), (f"{PREFIX}/node_cmd_012/nmt", b"1")], [0x12]
    )
    assert frames == [(0, [0x01, 0x12])]
