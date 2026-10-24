"""remote_logs against a fake node on a python-can virtual bus (run: pytest tests/)."""

import asyncio
import logging
import os
import sys
import uuid

import canopen
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from can2mqtt import remote_logs  # noqa: E402

from fake_node import FakeLogs, FakeNode  # noqa: E402

NODE_ID = 5
EDS = os.path.join(os.path.dirname(__file__), "..", "src", "can2mqtt", "eds", "esphome.eds")


class Collect(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append((record.levelno, record.getMessage()))


@pytest.fixture
def node_log():
    handler = Collect()
    node_logger = logging.getLogger("node.test-node")
    node_logger.addHandler(handler)
    node_logger.setLevel(logging.DEBUG)
    yield handler
    node_logger.removeHandler(handler)


def esphome_line(n, letter="D"):
    text = f"[{letter}][test:{n:03d}]: line {n} " + "x" * (n % 23)
    return f"\x1b[0;36m{text}\x1b[0m\n".encode(), text


class Bench:
    """canopen client (can2mqtt side) and a FakeNode on their own virtual channel."""

    def __init__(self, logs, **node_kwargs):
        self.logs = logs
        self.expected = []
        self.count = 0
        channel = f"remote-logs-{uuid.uuid4()}"
        self.fake = FakeNode(channel, NODE_ID, logs, **node_kwargs)
        self.network = canopen.Network()
        self.channel = channel

    def add_line(self, letter="D"):
        raw, text = esphome_line(self.count, letter)
        self.count += 1
        self.logs.buf += raw
        level = remote_logs.LINE_LEVELS[letter]
        self.expected.append((level, text))

    async def __aenter__(self):
        self.fake.start()
        self.network.connect(interface="virtual", channel=self.channel, loop=asyncio.get_running_loop())
        self.node = self.network.add_node(NODE_ID, canopen.import_od(EDS))
        self.node.device_name = "test-node"
        self.node.log_task = None
        return self

    async def __aexit__(self, *exc):
        remote_logs.stop(self.node)
        await asyncio.sleep(0)
        self.network.disconnect()
        self.fake.stop()


async def wait_for(cond, timeout=10.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        assert loop.time() < end, "timeout"
        await asyncio.sleep(0.02)


@pytest.mark.parametrize(
    "advertised, buf_seg, expected",
    [
        (8, 16, 8),  # node with a TX queue: tx_queue_size 16
        (3, 63, 3),  # TX mailboxes only
        (None, 63, remote_logs.DEFAULT_BLOCK_SIZE),  # firmware without 0x3100:7
    ],
)
def test_block_upload_with_lines_logged_during_transfer(node_log, advertised, buf_seg, expected):
    async def run():
        logs = FakeLogs(default_level=3, block_size=advertised)
        # lines logged between blocks must not be eaten by the last block's Read(SegNum * 7)
        bench = Bench(logs, buf_seg=buf_seg, on_block=lambda n: bench.add_line() if n in (1, 3, 5) else None)
        async with bench:
            for letter in "WIC" + "D" * 12:  # > 64 bytes: block upload
                bench.add_line(letter)
            await remote_logs.setup(bench.node, "AUTO")
            await wait_for(lambda: len(node_log.lines) >= len(bench.expected))
            await asyncio.sleep(0.1)  # nothing extra
        assert node_log.lines == bench.expected
        assert bench.fake.level_writes[0] == 3  # AUTO: the node's default level
        assert "block" in bench.fake.log_data_uploads
        # the initiate request and every ack ask for the advertised block size
        assert set(bench.fake.requested_blksizes) == {expected}
        assert not logs.buf

    asyncio.run(run())


def test_small_amount_uses_segmented_upload(node_log):
    async def run():
        bench = Bench(FakeLogs())
        async with bench:
            await remote_logs.setup(bench.node, "DEBUG")
            await wait_for(lambda: bench.fake.level_writes)
            bench.add_line("E")
            await wait_for(lambda: node_log.lines)
        assert node_log.lines == bench.expected
        assert bench.fake.level_writes[0] == remote_logs.ESPHOME_LOG_LEVELS.index("DEBUG")
        assert bench.fake.log_data_uploads == ["segmented"]

    asyncio.run(run())


def test_empty_buffer_is_not_uploaded(node_log):
    async def run():
        bench = Bench(FakeLogs(timeout_ms=1500))  # poll interval 0.5 s
        async with bench:
            await remote_logs.setup(bench.node, "AUTO")
            await asyncio.sleep(1.2)
        assert bench.fake.level_writes
        assert bench.fake.log_data_uploads == []  # a size-0 upload would abort
        assert node_log.lines == []

    asyncio.run(run())


@pytest.mark.parametrize(
    "mode, default_level, has_logs, subscribed",
    [
        ("AUTO", 3, True, True),
        ("AUTO", 0, True, False),  # node has remote_logs: {level: NONE}
        ("NONE", 3, True, False),
        ("VERBOSE", 0, True, True),
        ("DEBUG", 3, False, False),  # old firmware without 0x3100
    ],
)
def test_subscription_mode(mode, default_level, has_logs, subscribed):
    async def run():
        bench = Bench(FakeLogs(default_level=default_level), has_logs=has_logs)
        async with bench:
            await remote_logs.setup(bench.node, mode)
            assert (bench.node.log_task is not None) == subscribed
            if subscribed:
                await wait_for(lambda: bench.fake.level_writes)
            await asyncio.sleep(0.1)
        if subscribed:
            expected = default_level if mode == "AUTO" else remote_logs.ESPHOME_LOG_LEVELS.index(mode)
            assert bench.fake.level_writes[0] == expected
        else:
            assert bench.fake.level_writes == []

    asyncio.run(run())


def test_intervals():
    assert remote_logs.intervals(30000) == (10.0, 1.0)
    assert remote_logs.intervals(3000) == (1.0, 1.0)
    assert remote_logs.intervals(0) == (10.0, 1.0)  # timeout: never
