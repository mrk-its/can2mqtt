"""Remote ESPHome logs over CANopen (node OD 0x3100, see esphome-canopen OBJECT_DICTIONARY.md).

The node is a plain SDO server: we subscribe by writing a log level, poll Log Pending and upload Log Data,
which the node consumes. The node turns logging off by itself when nobody polls for its Log Timeout.
"""

import asyncio
import logging
import re

from canopen.sdo.client import BlockUploadStream
from canopen.sdo.exceptions import SdoAbortedError, SdoCommunicationError

logger = logging.getLogger("can2mqtt.logs")

LOGS_INDEX = 0x3100
LOG_DATA, LOG_PENDING, LOG_LEVEL, LOG_DROPPED, LOG_DEFAULT_LEVEL, LOG_TIMEOUT, LOG_BLOCK_SIZE = range(1, 8)

# ESPHome level names, the index is the value of Log Level
ESPHOME_LOG_LEVELS = [
    "NONE",
    "ERROR",
    "WARN",
    "INFO",
    "CONFIG",
    "DEBUG",
    "VERBOSE",
    "VERY_VERBOSE",
]
REMOTE_LOG_LEVEL_CHOICES = ["AUTO", *ESPHOME_LOG_LEVELS]

LINE_LEVELS = {
    "E": logging.ERROR,
    "W": logging.WARNING,
    "I": logging.INFO,
    "C": logging.INFO,
    "D": logging.DEBUG,
    "V": logging.DEBUG,
    "VV": logging.DEBUG,
}
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
LINE_LEVEL_RE = re.compile(r"^\[(E|W|I|C|D|VV|V)\]")

DEFAULT_TIMEOUT_MS = 30000
# block size when the node doesn't advertise one: the 3 TX mailboxes of the STM32 CAN controllers
DEFAULT_BLOCK_SIZE = 3
BLOCK_UPLOAD_MIN_SIZE = 64  # smaller amounts use a segmented / expedited upload
DRAIN_MAX_READS = 16
DROPPED_CHECK_INTERVAL = 30.0
ERROR_BACKOFF = 5.0


class LogUploadStream(BlockUploadStream):
    """Block upload with the block size the node advertises in Log Block Size (0x3100:7).

    The node sends a whole block back to back, so the block must fit its TX queue (without a software queue
    only the controller's 3 TX mailboxes). It must also be <= the node's sdo_block_transfer_size:
    canopen-stack caps a larger request silently and the initiate response can't tell us. canopen's
    BlockUploadStream requests its class attribute blksize (64) in the initiate request and every ack.
    """

    def __init__(self, sdo_client, index, subindex, blksize, **kwargs):
        self.blksize = blksize  # before super().__init__(), which sends the initiate request
        super().__init__(sdo_client, index, subindex, **kwargs)


def intervals(timeout_ms):
    """(keepalive, poll) in seconds; keepalive leaves room for two lost writes before the node times out."""
    if not timeout_ms:
        return 10.0, 1.0
    timeout = timeout_ms / 1000.0
    return min(10.0, timeout / 3), min(1.0, timeout / 3)


async def setup(node, mode):
    """Probe the node for remote logs and (re)start its log reader. mode: AUTO, NONE or an ESPHome level."""
    stop(node)
    if mode == "NONE":
        return
    try:
        await node.sdo.aupload(LOGS_INDEX, LOG_LEVEL)
    except SdoAbortedError:
        logger.debug("node %02x: no remote logs support", node.id)
        return
    default_level = await _read_u(node, LOG_DEFAULT_LEVEL, 0)
    timeout_ms = await _read_u(node, LOG_TIMEOUT, DEFAULT_TIMEOUT_MS)
    block_size = await _read_u(node, LOG_BLOCK_SIZE, 0)
    block_size_note = ""
    if not block_size:
        block_size = DEFAULT_BLOCK_SIZE
        block_size_note = " (default, node has no 0x3100:7)"
    level = default_level if mode == "AUTO" else ESPHOME_LOG_LEVELS.index(mode)
    if not level:
        logger.info("node %02x: remote logs available, not subscribed (level NONE)", node.id)
        return
    logger.info(
        "node %02x: subscribing to remote logs, level %s, node timeout %d ms, block size %d%s",
        node.id,
        ESPHOME_LOG_LEVELS[level],
        timeout_ms,
        block_size,
        block_size_note,
    )
    node.log_task = asyncio.create_task(log_reader(node, level, timeout_ms, block_size))


def stop(node):
    task = getattr(node, "log_task", None)
    if task:
        task.cancel()
    node.log_task = None


async def _read_u(node, subindex, default):
    try:
        return int.from_bytes(await node.sdo.aupload(LOGS_INDEX, subindex), "little")
    except SdoAbortedError:
        return default


async def _read_data(node, size, block_size):
    if size <= BLOCK_UPLOAD_MIN_SIZE:
        return await node.sdo.aupload(LOGS_INDEX, LOG_DATA)

    def read():
        with LogUploadStream(node.sdo, LOGS_INDEX, LOG_DATA, block_size, request_crc_support=False) as stream:
            return stream.readall()

    async with node.sdo.lock:  # the lock aupload() takes, one SDO transfer per node at a time
        return await asyncio.to_thread(read)


class LineDecoder:
    def __init__(self, node):
        self.node_logger = logging.getLogger(f"node.{node.device_name or f'{node.id:02x}'}")
        self.partial = b""

    def feed(self, data):
        # the node sends whole lines, partial is only for an aborted transfer that lost a line's start
        lines = (self.partial + data).split(b"\n")
        self.partial = lines.pop()
        for raw in lines:
            line = ANSI_RE.sub("", raw.decode("utf-8", errors="replace")).rstrip("\r\x00")
            if not line:
                continue
            m = LINE_LEVEL_RE.match(line)
            self.node_logger.log(LINE_LEVELS[m.group(1)] if m else logging.INFO, "%s", line)


async def log_reader(node, level, timeout_ms, block_size=DEFAULT_BLOCK_SIZE):
    keepalive_interval, poll_interval = intervals(timeout_ms)
    loop = asyncio.get_running_loop()
    decoder = LineDecoder(node)
    next_keepalive = 0.0
    next_dropped_check = loop.time() + DROPPED_CHECK_INTERVAL
    last_dropped = None
    while True:
        try:
            if getattr(node, "firmware_upload_running", False):
                # the node may time out meanwhile; after OTA it reboots, after a failed OTA the keepalive
                # below subscribes again
                await asyncio.sleep(poll_interval)
                continue
            now = loop.time()
            if now >= next_keepalive:
                # same level keeps the node's buffer, after a reboot / auto-off this subscribes again
                await node.sdo.adownload(LOGS_INDEX, LOG_LEVEL, bytes([level]))
                next_keepalive = now + keepalive_interval
            for _ in range(DRAIN_MAX_READS):
                pending = await _read_u(node, LOG_PENDING, 0)
                if not pending:
                    break
                decoder.feed(await _read_data(node, pending, block_size))
                await asyncio.sleep(0)
            if now >= next_dropped_check:
                dropped = await _read_u(node, LOG_DROPPED, 0)
                if last_dropped is not None and dropped > last_dropped:
                    logger.warning("node %02x: %d log lines dropped", node.id, dropped - last_dropped)
                last_dropped = dropped
                next_dropped_check = now + DROPPED_CHECK_INTERVAL
            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            raise
        except (SdoAbortedError, SdoCommunicationError) as e:
            logger.debug("node %02x: remote logs: %r", node.id, e)
            await asyncio.sleep(ERROR_BACKOFF)
        except Exception:
            logger.exception("node %02x: remote logs", node.id)
            await asyncio.sleep(ERROR_BACKOFF)
