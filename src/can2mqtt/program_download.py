"""Firmware upload on the CiA 302-3 program download objects (`ota: - platform: canopen` of the esphome-canopen hub).

Stop, clear, block download of the image, check the node's status and CRC-32, start. The node isn't told the expected
CRC, so the check before "start" is the only place a damaged image is caught on platforms without their own image
validation: it isn't optional here. No NMT state is required: the node keeps running during the upload.
"""

import logging
import zlib

from canopen.nmt import NmtError
from canopen.sdo.exceptions import SdoAbortedError, SdoCommunicationError

logger = logging.getLogger(__name__)

CONTROL_STOP = 0
CONTROL_START = 1
CONTROL_CLEAR = 3

# 0x1F57:1: bit 0 in progress, bits 1-7 error, bits 16-23 the backend's OTAResponseTypes
FLASH_ERROR_MASK = 0xFF
BOOTUP_TIMEOUT = 60.0  # end() and reboot on the node, then e.g. an MCUboot swap


class ProgramDownloadError(Exception):
    pass


def _objects(node):
    return (
        node.sdo["Program Control"][1],
        node.sdo["Program Data"][1],
        node.sdo["Program Identification"][1],
        node.sdo["Flash Status"][1],
    )


async def supported(node) -> bool:
    """Whether the node has the objects. Other SDO problems are raised, not taken for "no"."""
    try:
        await node.sdo["Program Control"][1].aget_raw()
        return True
    except SdoAbortedError:
        return False


def _describe_flash_status(status: int) -> str:
    return f"0x{status:08x} (error {(status >> 1) & 0x7F}, backend {(status >> 16) & 0xFF:#04x})"


async def upload(node, payload: bytes, bootup_timeout: float = BOOTUP_TIMEOUT) -> None:
    """Raises on any failure, after dropping what the node received: the old firmware keeps running."""
    control, data, identification, flash_status = _objects(node)
    expected_crc = zlib.crc32(payload)
    try:
        await control.aset_raw(CONTROL_STOP)
        await control.aset_raw(CONTROL_CLEAR)
        logger.info("node %02x: writing program data (block transfer), CRC-32 0x%08x", node.id, expected_crc)
        try:
            await data.aset_data(payload, block_transfer=True)
        except SdoAbortedError as e:
            raise ProgramDownloadError(
                f"download aborted: {e}, flash status {_describe_flash_status(await flash_status.aget_raw())}"
            ) from e
        status = await flash_status.aget_raw()
        if status & FLASH_ERROR_MASK:
            raise ProgramDownloadError(f"flash status {_describe_flash_status(status)}")
        received_crc = await identification.aget_raw()
        if received_crc != expected_crc:
            raise ProgramDownloadError(f"CRC-32 mismatch: node 0x{received_crc:08x}, image 0x{expected_crc:08x}")
        await control.aset_raw(CONTROL_START)
    except Exception:
        try:
            await control.aset_raw(CONTROL_STOP)
        except (SdoAbortedError, SdoCommunicationError) as e:
            logger.warning("node %02x: can't stop the failed upload: %r", node.id, e)
        raise
    logger.info("node %02x: image verified and started, waiting for boot-up", node.id)
    await _wait_for_bootup(node, flash_status, bootup_timeout)


async def _wait_for_bootup(node, flash_status, timeout: float) -> None:
    try:
        await node.nmt.await_for_bootup(timeout)
        return
    except NmtError:
        pass
    # "start" is acknowledged before the node's final OTA step, whose error only shows here
    status = await flash_status.aget_raw()
    if status & FLASH_ERROR_MASK:
        raise ProgramDownloadError(f"not started, flash status {_describe_flash_status(status)}")
    # e.g. `reboot: false` on the node
    logger.warning("node %02x: no boot-up within %.0f s, image staged", node.id, timeout)
