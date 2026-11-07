"""The 'Remote log level' select: discovery config, registration, node_cmd_XXX/log_level (run: pytest tests/)."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from can2mqtt import can2mqtt as c2m  # noqa: E402
from can2mqtt import remote_logs  # noqa: E402
from can2mqtt.entities import RemoteLogLevelSelect  # noqa: E402

from fake_node import FakeLogs  # noqa: E402
from test_remote_logs import NODE_ID, Bench, node_log, wait_for  # noqa: E402, F401

PREFIX = "homeassistant"
CONFIG_TOPIC = f"{PREFIX}/select/can_{NODE_ID:03x}_remote_log_level/config"
STATE_TOPIC = f"{PREFIX}/node_state_{NODE_ID:03x}/log_level"
CMD_TOPIC = f"{PREFIX}/node_cmd_{NODE_ID:03x}/log_level"
LEVEL = remote_logs.ESPHOME_LOG_LEVELS.index


class FakeMqtt:
    def __init__(self, messages=()):
        self._messages = messages
        self.published = []

    async def subscribe(self, topic):
        pass

    async def publish(self, topic, payload=None, retain=False):
        self.published.append((topic, payload))

    def states(self):
        return [payload for topic, payload in self.published if topic == STATE_TOPIC]

    @asynccontextmanager
    async def messages(self):
        async def gen():
            for topic, payload in self._messages:
                yield SimpleNamespace(topic=SimpleNamespace(value=topic), payload=payload)

        yield gen()


class SelectBench(Bench):
    """Bench whose node has the attributes can_reader() adds."""

    async def __aenter__(self):
        await super().__aenter__()
        self.node.remote_log_level = None
        self.node.log_level_entity = None
        self.node.availability_topic = f"{PREFIX}/can_{NODE_ID:03x}/availability"
        self.node.sw_version = "1.0"
        self.node.hw_version = None
        return self


@pytest.fixture
def default_mode(monkeypatch):
    monkeypatch.setattr(c2m, "remote_log_mode", "NONE")


def test_select_config():
    node = SimpleNamespace(
        id=NODE_ID, availability_topic="a", device_name="test node", sw_version="1.0", hw_version=None
    )
    entity = RemoteLogLevelSelect(node, PREFIX)
    config = entity.get_mqtt_config()
    assert entity.get_mqtt_config_topic() == CONFIG_TOPIC
    assert config["unique_id"] == f"can_{NODE_ID:03x}_remote_log_level"
    assert config["name"] == "Remote log level"
    assert config["options"] == remote_logs.ESPHOME_LOG_LEVELS
    assert config["command_topic"] == CMD_TOPIC
    assert config["state_topic"] == STATE_TOPIC
    assert config["entity_category"] == "config"
    assert RemoteLogLevelSelect.BUILTIN


def test_default_registration_publishes_the_select_without_subscribing(default_mode):
    async def run():
        async with SelectBench(FakeLogs(default_level=3)) as bench:
            mqtt = FakeMqtt()
            await c2m.setup_remote_logs(mqtt, PREFIX, bench.node)
            await asyncio.sleep(0.1)
            assert bench.node.log_task is None
            assert bench.node.log_level == 0
            assert [t for t, _ in mqtt.published] == [CONFIG_TOPIC]
            await bench.node.log_level_entity.publish_state(mqtt)
            assert mqtt.states() == ["NONE"]
        # the node's boot buffer is left alone: it switches itself off after its Log Timeout
        assert bench.fake.level_writes == []

    asyncio.run(run())


def test_auto_mode_subscribes_at_the_node_level(monkeypatch):
    monkeypatch.setattr(c2m, "remote_log_mode", "AUTO")

    async def run():
        async with SelectBench(FakeLogs(default_level=3)) as bench:
            await c2m.setup_remote_logs(FakeMqtt(), PREFIX, bench.node)
            await wait_for(lambda: bench.fake.level_writes)
            assert bench.node.log_level == LEVEL("INFO")

    asyncio.run(run())


def test_chosen_level_survives_reboot_and_gets_the_boot_logs(node_log, default_mode):
    """Level chosen in HA, then the node restarts: the re-registration subscribes at once and uploads the lines
    the node buffered while booting."""

    async def run():
        async with SelectBench(FakeLogs(default_level=3)) as bench:
            await c2m.setup_remote_logs(FakeMqtt(), PREFIX, bench.node)
            await c2m.change_remote_log_level(FakeMqtt(), bench.node, "DEBUG")
            await wait_for(lambda: bench.fake.level_writes)

            # reboot: the reader stops (reload_node()), the node buffers its boot at its default level
            remote_logs.stop(bench.node)
            await wait_for(bench.node.log_task.done)
            bench.fake.reboot()
            bench.logs.level = 0
            for letter in "IWI":
                bench.add_line(letter)

            mqtt = FakeMqtt()
            await c2m.setup_remote_logs(mqtt, PREFIX, bench.node)  # re-registration
            await wait_for(lambda: len(node_log.lines) >= 3)
            await bench.node.log_level_entity.publish_state(mqtt)
            assert mqtt.states() == ["DEBUG"]
        assert node_log.lines == bench.expected
        assert bench.fake.level_writes[-1] == LEVEL("DEBUG")

    asyncio.run(run())


def test_select_none_switches_the_node_off(default_mode):
    async def run():
        async with SelectBench(FakeLogs(default_level=3)) as bench:
            await c2m.setup_remote_logs(FakeMqtt(), PREFIX, bench.node)
            mqtt = FakeMqtt()
            await c2m.change_remote_log_level(mqtt, bench.node, "VERBOSE")
            await wait_for(lambda: bench.fake.level_writes)
            await c2m.change_remote_log_level(mqtt, bench.node, "NONE")
            assert bench.node.log_task is None
            assert bench.node.remote_log_level == "NONE"
            assert mqtt.states() == ["VERBOSE", "NONE"]
        assert bench.fake.level_writes[0] == LEVEL("VERBOSE")
        assert bench.fake.level_writes[-1] == 0
        assert bench.logs.level == 0

    asyncio.run(run())


def test_node_without_remote_logs_has_no_select(default_mode):
    async def run():
        async with SelectBench(FakeLogs(), has_logs=False) as bench:
            mqtt = FakeMqtt()
            await c2m.setup_remote_logs(mqtt, PREFIX, bench.node)
            assert mqtt.published == []
            assert bench.node.log_level_entity is None

            # flashed without remote_logs: the select published before is removed
            bench.node.log_level_entity = RemoteLogLevelSelect(bench.node, PREFIX)
            await c2m.setup_remote_logs(mqtt, PREFIX, bench.node)
            assert mqtt.published == [(CONFIG_TOPIC, b"")]
            assert bench.node.log_level_entity is None

    asyncio.run(run())


def test_log_level_command_topic(default_mode):
    async def run():
        async with SelectBench(FakeLogs(default_level=3)) as bench:
            await c2m.setup_remote_logs(FakeMqtt(), PREFIX, bench.node)
            mqtt = FakeMqtt(
                [
                    (CMD_TOPIC, b"bogus"),  # ignored
                    (f"{PREFIX}/node_cmd_034/log_level", b"DEBUG"),  # unknown node, ignored
                    (CMD_TOPIC, b"debug"),
                ]
            )
            await c2m.mqtt_reader(mqtt, bench.network, PREFIX)
            await asyncio.gather(*c2m.background_tasks)
            await wait_for(lambda: bench.fake.level_writes)
            assert bench.node.remote_log_level == "DEBUG"
            assert mqtt.states() == ["DEBUG"]
        assert bench.fake.level_writes == [LEVEL("DEBUG")]

    asyncio.run(run())


def test_select_config_is_json_serializable():
    node = SimpleNamespace(id=1, availability_topic="a", device_name="n", sw_version=None, hw_version=None)
    json.dumps(RemoteLogLevelSelect(node, PREFIX).get_mqtt_config())
