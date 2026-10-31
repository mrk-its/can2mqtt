"""Fake esphome-canopen node with remote logs (OD 0x3100) on a python-can virtual bus.

canopen's SdoServer (LocalNode) answers a block upload with a regular one, so it can't exercise the block
path. This serves 0x3100 the way canopen-stack (src/service/cia301/co_ssdo.c) and components/canopen/logs.cpp
do:
- expedited / segmented / block upload of Log Data, block size capped at the node's CO_SDO_BUF_SEG
  (COSdoInitUploadBlock), without telling the client;
- Size() snapshots the pending bytes, the transfer sends exactly that many;
- every block calls Read(SegNum * 7), the last one too (COSdoUploadBlock), and Read never consumes more
  than the snapshot;
- an upload of an empty buffer aborts (COSdoGetSize: size 0).
canopen-stack has no CRC: it accepts a client's CRC request (0xA4) and answers without the server CRC bit (0xC2).
With server_crc the fake answers like CANopenNode (the hub's SDO server): the server CRC bit always set (0xC6), the
CRC-16 in the end frame only if the client requested it, 0 otherwise.
"""

import struct
import threading
import time

import can

LOGS_INDEX = 0x3100
ABORT_TOS = 0x06070010


def crc16_ccitt(data, crc=0):
    """The SDO block transfer CRC (CiA 301: CRC-16/XMODEM, polynomial 0x1021, initial value 0)."""
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


class FakeLogs:
    """Node state of 0x3100 (logs.cpp)."""

    def __init__(self, default_level=3, timeout_ms=30000, block_size=3):
        self.buf = bytearray()
        self.xfer = 0
        self.level = 0
        self.default_level = default_level
        self.timeout_ms = timeout_ms
        self.dropped = 0
        self.block_size = block_size  # 0x3100:7, None: firmware without it

    def size(self):
        self.xfer = len(self.buf)
        return self.xfer

    def read(self, n):
        k = min(n, self.xfer)
        data = bytes(self.buf[:k])
        del self.buf[:k]
        self.xfer -= k
        return data + bytes(n - k)


class FakeNode(threading.Thread):
    def __init__(
        self, channel, node_id, logs, has_logs=True, buf_seg=16, on_block=None, halt_at_block=None, server_crc=False
    ):
        super().__init__(daemon=True)
        self.bus = can.Bus(interface="virtual", channel=channel)
        self.node_id = node_id
        self.logs = logs
        self.has_logs = has_logs
        self.buf_seg = buf_seg
        self.on_block = on_block  # called with the block number before the block's Read
        self.halt_at_block = halt_at_block  # stop answering instead of sending this block (CPU halted)
        self.server_crc = server_crc
        self.halted = threading.Event()
        self.stopped = threading.Event()
        # what the client did, for assertions
        self.requested_blksizes = []  # initiate request + every block ack
        self.log_data_uploads = []  # "expedited" / "segmented" / "block"
        self.level_writes = []
        self.blocks = 0
        self.received = []  # (time.monotonic(), frame) of every request, also while halted
        self._seg = None
        self._blk = None

    def reboot(self):
        """The node comes back up: transfer state is gone, it answers again."""
        self._seg = None
        self._blk = None
        self.halted.clear()

    def stop(self):
        self.stopped.set()
        self.join(timeout=2)
        self.bus.shutdown()

    def send(self, data):
        self.bus.send(
            can.Message(
                arbitration_id=0x580 + self.node_id,
                data=bytes(data).ljust(8, b"\0"),
                is_extended_id=False,
            )
        )

    def abort(self, sub, code):
        self.send([0x80, *struct.pack("<HB", LOGS_INDEX, sub), *struct.pack("<I", code)])

    def value(self, sub):
        logs = self.logs
        if sub == 7:
            return None if logs.block_size is None else bytes([logs.block_size])
        return {
            2: lambda: struct.pack("<I", len(logs.buf)),
            3: lambda: bytes([logs.level]),
            4: lambda: struct.pack("<I", logs.dropped),
            5: lambda: bytes([logs.default_level]),
            6: lambda: struct.pack("<I", logs.timeout_ms),
        }[sub]()

    def run(self):
        while not self.stopped.is_set():
            msg = self.bus.recv(timeout=0.05)
            if msg is None or msg.arbitration_id != 0x600 + self.node_id:
                continue
            self.received.append((time.monotonic(), bytes(msg.data)))
            if not self.halted.is_set():
                self.handle(bytes(msg.data))

    def handle(self, d):
        cmd = d[0]
        index, sub = struct.unpack_from("<HB", d, 1)
        if cmd in (0x40, 0xA0, 0xA4) or cmd & 0xE0 == 0x20:
            if index != LOGS_INDEX or not self.has_logs:
                self.abort(sub, 0x06020000)  # object does not exist
                return
        if cmd == 0x40:  # initiate upload
            if sub != 1:
                v = self.value(sub)
                if v is None:
                    self.abort(sub, 0x06090011)  # subindex does not exist
                    return
                self.send([0x43 | ((4 - len(v)) << 2), *d[1:4], *v.ljust(4, b"\0")])
                return
            n = self.logs.size()
            if n == 0:
                self.abort(1, ABORT_TOS)
            elif n <= 4:
                self.log_data_uploads.append("expedited")
                self.send([0x43 | ((4 - n) << 2), *d[1:4], *self.logs.read(n).ljust(4, b"\0")])
            else:
                self.log_data_uploads.append("segmented")
                self._seg = n
                self.send([0x41, *d[1:4], *struct.pack("<I", n)])
        elif cmd & 0xE0 == 0x60 and self._seg:  # upload segment
            k = min(7, self._seg)
            self._seg -= k
            last = self._seg == 0
            self.send([(cmd & 0x10) | ((7 - k) << 1) | last, *self.logs.read(k)])
            if last:
                self._seg = None
        elif cmd & 0xE0 == 0x20:  # download (Log Level, expedited)
            self.logs.level = d[4]
            self.level_writes.append(d[4])
            self.send([0x60, *d[1:4], 0, 0, 0, 0])
        elif cmd in (0xA0, 0xA4):  # initiate block upload
            self.requested_blksizes.append(d[4])
            n = self.logs.size()
            if n == 0:
                self.abort(1, ABORT_TOS)
                return
            self.log_data_uploads.append("block")
            self._blk = {"len": n, "segnum": min(d[4], self.buf_seg)}
            self._blk["crc"] = 0 if self.server_crc and cmd == 0xA4 else None
            self.send([0xC6 if self.server_crc else 0xC2, *d[1:4], *struct.pack("<I", n)])
        elif cmd == 0xA3 and self._blk:  # start upload
            self.send_block()
        elif cmd == 0xA2 and self._blk:  # block ack
            ackseq, blksize = d[1], d[2]
            self.requested_blksizes.append(blksize)
            assert ackseq == self._blk["sent"], (ackseq, self._blk["sent"])
            if self._blk["len"] == 0:
                crc = self._blk["crc"] or 0
                self.send([0xC1 | ((7 - self._blk["last_valid"]) << 2), *struct.pack("<H", crc)])
            else:
                self._blk["segnum"] = min(blksize, self.buf_seg)
                self.send_block()
        elif cmd == 0xA1:  # end ack
            self._blk = None

    def send_block(self):
        blk = self._blk
        if self.blocks == self.halt_at_block:
            self.halted.set()
            return
        if self.on_block:
            self.on_block(self.blocks)
        self.blocks += 1
        data = self.logs.read(blk["segnum"] * 7)
        pos = 0
        for seq in range(1, blk["segnum"] + 1):
            k = min(7, blk["len"])
            blk["len"] -= k
            last = blk["len"] == 0
            self.send([seq | (0x80 if last else 0), *data[pos : pos + k]])
            pos += k
            blk["sent"], blk["last_valid"] = seq, k
            if blk.get("crc") is not None:
                blk["crc"] = crc16_ccitt(data[pos - k : pos], blk["crc"])
            if last:
                break
