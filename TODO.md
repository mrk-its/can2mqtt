# TODO

## Firmware updates (CAN OTA) for Zephyr / MCUboot nodes

can2mqtt already works with MCUboot-signed images (`zephyr.signed.bin`): the version string is found,
the node reports no compression via 0x3000:5, and the MD5 matches. Possible improvements:

- **Skip unsigned twins.** `zephyr.bin` (unsigned) contains the same `node_id: xx, ver: ...` string as
  `zephyr.signed.bin`. If both end up in the firmware directory, they register as the same node and version,
  and whichever is scanned last wins. `firmware_scanner.py` could skip a `.bin` that has a `*.signed.bin` next to it
  (or prefer files that start with the MCUboot magic `3d b8 f3 96`). The node rejects unsigned images anyway,
  but only after the transfer has started.
- **Surface upload errors in Home Assistant.** `firmware_upload()` only logs failures (e.g. the SDO abort a node
  sends for a non-MCUboot image) and re-enables the update entity, so HA shows no error. Publish the failure
  reason in the update entity state (e.g. `release_summary`) or clear `in_progress` with an error.
- **Report progress after retransmissions.** In the SDO client (`mrk-its/canopen-asyncio`,
  `canopen/sdo/client.py`), `BlockDownloadStream._block_ack()` calls `progress()` only when the
  whole block was acknowledged (`ackseq == blksize`). On a partial ack it goes through `_retransmit()`
  and returns early, so no progress is reported. If frames are lost in every block (seen with
  block size 32/63 when only ~16 frames per burst got through), HA shows no upload progress at all,
  even though the transfer slowly moves on. Call `self.sdo_client.progress(self.pos, self.size)` on
  the retransmit path as well (e.g. after `_retransmit()` in `_block_ack()`).
- **Show retransmissions at INFO.** `_retransmit()` logs `... Will start retransmission` at DEBUG,
  so a transfer that is slow because of lost frames looks normal in the default log. Logging it
  (or a per-transfer retransmission count) at INFO would make the problem visible.
