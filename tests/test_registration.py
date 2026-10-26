"""Parallel node registration (registration_task) and heartbeat tracking (run: pytest tests/)."""

import asyncio
import os
import sys
import time
import uuid
from types import SimpleNamespace

import can
import canopen
import pytest
from canopen.sdo.exceptions import SdoCommunicationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from can2mqtt import can2mqtt as c2m  # noqa: E402

PREFIX = "homeassistant"


class FakeMqtt:
    def __init__(self):
        self.published = []

    async def publish(self, topic, payload=None, retain=False):
        self.published.append((topic, payload))


def fake_node(node_id):
    """A RemoteNode with the attributes can_reader() adds, as far as registration uses them."""
    return SimpleNamespace(
        id=node_id,
        is_initialized=False,
        is_supported=False,
        register_task=None,
        reload_count=0,
        last_heartbeat_time=time.time(),
        prod_heartbeat_time=5000,
        availability=None,
        availability_topic=f"{PREFIX}/can_{node_id:03x}/availability",
        ntm_state_entity=None,
        log_stop=None,
        tpdo=SimpleNamespace(map={}),
    )


async def register_all(mqtt, nodes, semaphore):
    """Start registrations the way can_reader() does and wait for them."""
    for node in nodes:
        node.register_task = asyncio.create_task(
            c2m.registration_task(mqtt, PREFIX, None, node, semaphore)
        )
    await asyncio.gather(*(node.register_task for node in nodes))


@pytest.fixture
def watchdog(monkeypatch):
    timer = c2m.WatchdogTimer(60)
    monkeypatch.setattr(c2m, "watchdog_timer", timer)
    return timer


def availability_of(mqtt, node):
    return [payload for topic, payload in mqtt.published if topic == node.availability_topic]


def test_registers_nodes_in_parallel_up_to_the_limit(monkeypatch):
    running = 0
    max_running = 0

    async def register_node(mqtt_client, mqtt_topic_prefix, can_network, node):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.05)
        running -= 1
        node.is_supported = True
        node.is_initialized = True

    monkeypatch.setattr(c2m, "register_node", register_node)
    mqtt = FakeMqtt()
    nodes = [fake_node(i) for i in range(1, 11)]

    async def run():
        t0 = time.monotonic()
        await register_all(mqtt, nodes, asyncio.Semaphore(4))
        return time.monotonic() - t0

    elapsed = asyncio.run(run())
    assert max_running == 4
    assert elapsed < 10 * 0.05  # not serial
    for node in nodes:
        assert node.is_initialized and node.register_task is None
        assert availability_of(mqtt, node) == ["online"]


def test_reboot_during_registration_registers_again(monkeypatch):
    async def register_node(mqtt_client, mqtt_topic_prefix, can_network, node):
        await asyncio.sleep(0.01)
        c2m.reload_node(node)  # boot-up heartbeat arrives meanwhile
        node.is_supported = True
        node.is_initialized = True

    monkeypatch.setattr(c2m, "register_node", register_node)
    mqtt = FakeMqtt()
    node = fake_node(5)
    asyncio.run(register_all(mqtt, [node], asyncio.Semaphore(4)))
    assert not node.is_initialized  # can_reader() starts a new registration
    assert node.register_task is None
    assert availability_of(mqtt, node) == []


def test_failed_registration_is_retried_later(monkeypatch):
    async def register_node(mqtt_client, mqtt_topic_prefix, can_network, node):
        raise SdoCommunicationError("No SDO response received")

    monkeypatch.setattr(c2m, "register_node", register_node)
    mqtt = FakeMqtt()
    node = fake_node(5)
    asyncio.run(register_all(mqtt, [node], asyncio.Semaphore(4)))
    assert not node.is_initialized
    assert node.register_task is None
    assert availability_of(mqtt, node) == []


def test_heartbeat_tracked_before_registration(watchdog):
    node = fake_node(5)
    node.last_heartbeat_time = 0
    watchdog._time = 0
    on_heartbeat = c2m.get_heartbeat_cb(FakeMqtt(), node)

    on_heartbeat(5)  # OPERATIONAL
    assert time.time() - node.last_heartbeat_time < 1
    assert not watchdog.passed()
    assert node.reload_count == 0

    on_heartbeat(0)  # boot-up
    assert node.reload_count == 1
    assert not node.is_initialized


def test_availability_after_registration_uses_earlier_heartbeats(monkeypatch, watchdog):
    """A node registered within a few seconds isn't reported offline (2026-10-25 startup log)."""
    node = fake_node(5)
    node.last_heartbeat_time = time.time() - 30  # created long ago, e.g. while others registered
    on_heartbeat = c2m.get_heartbeat_cb(FakeMqtt(), node)
    on_heartbeat(5)  # heartbeat before registration starts

    async def register_node(mqtt_client, mqtt_topic_prefix, can_network, node):
        node.is_supported = True
        node.is_initialized = True

    monkeypatch.setattr(c2m, "register_node", register_node)
    mqtt = FakeMqtt()
    asyncio.run(register_all(mqtt, [node], asyncio.Semaphore(4)))
    assert availability_of(mqtt, node) == ["online"]


def test_can_reader_registers_nodes_seen_on_the_bus(monkeypatch, watchdog):
    """can_reader() on a virtual bus: heartbeats -> nodes created -> registered in parallel."""
    node_ids = [0x11, 0x22, 0x33]
    registered = []

    async def register_node(mqtt_client, mqtt_topic_prefix, can_network, node):
        await asyncio.sleep(0.05)
        node.is_supported = True
        node.is_initialized = True
        registered.append(node.id)

    monkeypatch.setattr(c2m, "register_node", register_node)

    async def run():
        channel = f"registration-{uuid.uuid4()}"
        network = canopen.Network()
        network.connect(interface="virtual", channel=channel, loop=asyncio.get_running_loop())
        bus = can.Bus(interface="virtual", channel=channel)
        mqtt = FakeMqtt()
        reader = asyncio.create_task(c2m.can_reader(network, mqtt, PREFIX, asyncio.Semaphore(2)))
        try:
            loop = asyncio.get_running_loop()
            end = loop.time() + 10
            while len(registered) < len(node_ids):
                assert loop.time() < end, "timeout"
                for node_id in node_ids:  # heartbeat, OPERATIONAL
                    bus.send(can.Message(arbitration_id=0x700 + node_id, data=[5], is_extended_id=False))
                await asyncio.sleep(0.2)
            await asyncio.sleep(0.1)
            return network, mqtt
        finally:
            reader.cancel()
            bus.shutdown()
            network.disconnect()

    network, mqtt = asyncio.run(run())
    assert sorted(registered) == node_ids
    for node_id in node_ids:
        node = network[node_id]
        assert node.is_initialized and node.register_task is None
        assert availability_of(mqtt, node) == ["online"]
