"""Firmware upload on both update paths against a fake node on a python-can virtual bus (run: pytest tests/)."""

import asyncio
import hashlib
import os
import struct
import sys
import uuid
import zlib
from types import SimpleNamespace

import canopen
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from can2mqtt import can2mqtt as c2m  # noqa: E402
from can2mqtt import program_download  # noqa: E402

from fake_ota_node import CLEAR, START, STOP, FakeOtaNode  # noqa: E402

NODE_ID = 5
EDS = os.path.join(os.path.dirname(__file__), "..", "src", "can2mqtt", "eds", "esphome.eds")
# longer than a block, not a multiple of 7: the last segment is partial
IMAGE = bytes((i * 7 + 3) & 0xFF for i in range(1000))


class Bench:
    def __init__(self, **kwargs):
        self.channel = f"firmware-{uuid.uuid4()}"
        self.fake = FakeOtaNode(self.channel, NODE_ID, **kwargs)
        self.network = canopen.Network()

    async def __aenter__(self):
        self.fake.start()
        self.network.connect(interface="virtual", channel=self.channel, loop=asyncio.get_running_loop())
        self.node = self.network.add_node(NODE_ID, canopen.import_od(EDS))
        self.node.firmware_upload_running = False
        return self

    async def __aexit__(self, *exc):
        self.network.disconnect()
        self.fake.stop()


def run_bench(test, **kwargs):
    async def main():
        async with Bench(**kwargs) as bench:
            await test(bench)

    asyncio.run(main())


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"program_download": True}, True),
        ({"program_download": True, "legacy": True}, True),
        ({"program_download": False, "legacy": True}, False),
        ({"program_download": False}, False),
    ],
)
def test_supported(kwargs, expected):
    async def test(bench):
        assert await program_download.supported(bench.node) is expected

    run_bench(test, **kwargs)


def test_upload():
    async def test(bench):
        await program_download.upload(bench.node, IMAGE, bootup_timeout=5)
        assert bench.fake.staged == IMAGE
        assert bench.fake.commands == [STOP, CLEAR, START]
        # the block CRC-16 is requested, and no NMT state is asked for
        assert bench.fake.block_crc_seen
        assert bench.fake.nmt_frames == []

    run_bench(test)


def test_upload_replaces_an_earlier_session():
    async def test(bench):
        bench.fake.control = CLEAR
        bench.fake.cleared = True
        await program_download.upload(bench.node, IMAGE, bootup_timeout=5)
        assert bench.fake.staged == IMAGE

    run_bench(test)


@pytest.mark.parametrize("size", [1, 7, 8, 16 * 7, 16 * 7 + 1, 2 * 16 * 7])
def test_upload_sizes(size):
    async def test(bench):
        await program_download.upload(bench.node, IMAGE[:size], bootup_timeout=5)
        assert bench.fake.staged == IMAGE[:size]

    run_bench(test)


def test_crc_mismatch_is_not_started():
    async def test(bench):
        bench.fake.corrupt_crc = True
        with pytest.raises(program_download.ProgramDownloadError, match="CRC-32 mismatch"):
            await program_download.upload(bench.node, IMAGE, bootup_timeout=5)
        assert not bench.fake.started
        assert bench.fake.commands == [STOP, CLEAR, STOP]

    run_bench(test)


def test_flash_error_is_not_started():
    async def test(bench):
        bench.fake.flash_error_after_download = (5 << 1) | (0x83 << 16)
        with pytest.raises(program_download.ProgramDownloadError, match="error 5, backend 0x83"):
            await program_download.upload(bench.node, IMAGE, bootup_timeout=5)
        assert not bench.fake.started
        assert bench.fake.commands[-1] == STOP

    run_bench(test)


def test_aborted_download_is_stopped_and_reports_flash_status():
    async def test(bench):
        bench.fake.abort_download = True
        with pytest.raises(program_download.ProgramDownloadError, match="error 5, backend 0x83"):
            await program_download.upload(bench.node, IMAGE, bootup_timeout=5)
        assert not bench.fake.started
        assert bench.fake.commands[-1] == STOP

    run_bench(test)


def test_no_bootup_with_a_flash_error_raises():
    async def test(bench):
        bench.fake.bootup_after_start = False
        bench.fake.flash_status_after_start = (63 << 1) | (0x84 << 16)
        with pytest.raises(program_download.ProgramDownloadError, match="not started"):
            await program_download.upload(bench.node, IMAGE, bootup_timeout=0.3)

    run_bench(test)


def test_no_bootup_without_an_error_is_only_a_warning(caplog):
    async def test(bench):
        bench.fake.bootup_after_start = False
        await program_download.upload(bench.node, IMAGE, bootup_timeout=0.3)
        assert bench.fake.started
        assert "no boot-up" in caplog.text

    run_bench(test)


def network_of(bench):
    return {NODE_ID: bench.node}


@pytest.mark.parametrize("compress", [False, True])
def test_firmware_upload_program_download_path(compress):
    """Never compressed on this path, whatever the command topic says."""

    async def test(bench):
        bench.node.program_download = True
        await c2m.firmware_upload(network_of(bench), NODE_ID, IMAGE, compress=compress)
        assert bench.fake.staged == IMAGE
        assert bench.fake.legacy_writes == {}
        assert not bench.node.firmware_upload_running

    run_bench(test, legacy=True)


@pytest.mark.parametrize("compress", [False, True])
def test_firmware_upload_legacy_path(compress):
    async def test(bench):
        bench.node.program_download = False
        await c2m.firmware_upload(network_of(bench), NODE_ID, IMAGE, compress=compress)
        writes = bench.fake.legacy_writes
        assert struct.unpack("<I", writes[2])[0] == len(IMAGE)
        assert writes[3] == hashlib.md5(IMAGE).digest()
        assert writes[4] == (zlib.compress(IMAGE) if compress else IMAGE)
        assert bench.fake.commands == []
        assert not bench.node.firmware_upload_running

    run_bench(test, program_download=False, legacy=True)


def test_failed_upload_is_contained():
    """Logged, not raised: the task must not kill can2mqtt, and the log reader resumes."""

    async def test(bench):
        bench.node.program_download = True
        bench.fake.corrupt_crc = True
        bench.node.update_entity = SimpleNamespace()
        await c2m.firmware_upload(network_of(bench), NODE_ID, IMAGE)
        assert not bench.fake.started
        assert not bench.node.firmware_upload_running

    run_bench(test)
