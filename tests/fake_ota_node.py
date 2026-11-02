"""Fake node with firmware update objects on a python-can virtual bus: the hub's program download (program_download.h
of esphome-canopen: 0x1F50, 0x1F51, 0x1F56, 0x1F57), the 0x3000 objects, or both. Answers expedited and segmented
SDO, and block downloads the way CANopenNode does (asks for block_size segments, checks the client's CRC-16)."""

import struct
import threading
import zlib

import can

from fake_node import crc16_ccitt

ABORT_NOT_EXIST = 0x06020000
ABORT_HW = 0x06060000
ABORT_NO_DATA = 0x08000024
ABORT_CRC = 0x05040004

STOP, START, CLEAR = 0, 1, 3


class FakeOtaNode(threading.Thread):
    def __init__(self, channel, node_id, program_download=True, legacy=False, flags=0, block_size=16):
        super().__init__(daemon=True)
        self.bus = can.Bus(interface="virtual", channel=channel)
        self.node_id = node_id
        self.program_download = program_download
        self.legacy = legacy
        self.flags = flags
        self.block_size = block_size
        self.stopped = threading.Event()
        # 0x1F5x state
        self.control = START
        self.cleared = False
        self.image_ready = False
        self.flash_status = 0
        self.program_id = 0
        self.image = bytearray()
        # what the client did, for assertions
        self.commands = []
        self.nmt_frames = []
        self.started = False
        self.staged = None  # the image at "start"
        self.block_crc_seen = False
        # 0x3000 state
        self.legacy_writes = {}
        # faults
        self.corrupt_crc = False
        self.flash_error_after_download = 0
        self.abort_download = False
        self.bootup_after_start = True
        self.flash_status_after_start = 0
        self._blk = None
        self._seg = None

    def stop(self):
        self.stopped.set()
        self.join(timeout=2)
        self.bus.shutdown()

    def send(self, data, can_id=None):
        self.bus.send(
            can.Message(
                arbitration_id=0x580 + self.node_id if can_id is None else can_id,
                data=bytes(data).ljust(8, b"\0"),
                is_extended_id=False,
            )
        )

    def abort(self, index, sub, code):
        self.send([0x80, *struct.pack("<HB", index, sub), *struct.pack("<I", code)])

    def run(self):
        while not self.stopped.is_set():
            msg = self.bus.recv(0.02)
            if msg is None:
                continue
            if msg.arbitration_id == 0:
                self.nmt_frames.append(bytes(msg.data))
            elif msg.arbitration_id == 0x600 + self.node_id:
                self.handle(bytes(msg.data).ljust(8, b"\0"))

    def has(self, index):
        if index in (0x1F50, 0x1F51, 0x1F56, 0x1F57):
            return self.program_download
        return index == 0x3000 and self.legacy

    def read_value(self, index, sub):
        if sub == 0:
            return struct.pack("<B", 5 if index == 0x3000 else 1)
        if index == 0x1F51 and sub == 1:
            return struct.pack("<B", self.control)
        if index == 0x1F56 and sub == 1:
            return struct.pack("<I", self.program_id)
        if index == 0x1F57 and sub == 1:
            return struct.pack("<I", self.flash_status)
        if index == 0x3000 and sub == 5:
            return struct.pack("<I", self.flags)
        return None

    def handle(self, d):
        if self._blk is not None:
            self.block_frame(d)
            return
        cmd = d[0]
        if cmd == 0x80:
            self._seg = None
            return
        if self._seg is not None and cmd & 0xE0 == 0x00:
            self.segment(d)
            return
        index, sub = struct.unpack_from("<HB", d, 1)
        if not self.has(index):
            self.abort(index, sub, ABORT_NOT_EXIST)
        elif cmd == 0x40:
            value = self.read_value(index, sub)
            if value is None:
                self.abort(index, sub, ABORT_NOT_EXIST)
            else:
                self.send([0x43 | ((4 - len(value)) << 2), *d[1:4], *value.ljust(4, b"\0")])
        elif cmd & 0xE0 == 0x20:
            if cmd & 0x02:  # expedited
                n = 4 - ((cmd >> 2) & 3) if cmd & 0x01 else 4
                self.write(index, sub, d[4:4 + n])
            else:
                self._seg = {"index": index, "sub": sub, "data": bytearray()}
                self.send([0x60, *d[1:4]])
        elif cmd & 0xE0 == 0xC0:  # initiate block download
            self.block_crc_seen = bool(cmd & 0x04)
            if index == 0x1F50 and (self.abort_download or not self.cleared):
                self.flash_status = (4 << 1) if not self.cleared else (5 << 1) | (0x83 << 16)
                self.abort(index, sub, ABORT_HW)
                return
            self._blk = {"index": index, "sub": sub, "data": bytearray(), "seq": 0, "ended": False}
            self.send([0xA4, *d[1:4], self.block_size])
        else:
            self.abort(index, sub, ABORT_HW)

    def segment(self, d):
        cmd = d[0]
        n = 7 - ((cmd >> 1) & 7)
        self._seg["data"] += d[1:1 + n]
        self.send([0x20 | (cmd & 0x10)])
        if cmd & 1:
            seg, self._seg = self._seg, None
            self.legacy_writes[seg["sub"]] = bytes(seg["data"])

    def write(self, index, sub, value):
        if index == 0x1F51:
            result = self.control_write(value[0])
            if result:
                self.abort(index, sub, result)
                return
        elif index == 0x3000:
            self.legacy_writes[sub] = bytes(value)
        self.send([0x60, *struct.pack("<HB", index, sub)])

    def control_write(self, value):
        self.commands.append(value)
        if value == STOP:
            self.control = STOP
            self.cleared = False
            self.image_ready = False
            self.program_id = 0
            self.image = bytearray()
        elif value == CLEAR:
            if self.control != STOP:
                return ABORT_NO_DATA
            self.control = CLEAR
            self.cleared = True
            self.flash_status = 0
        elif value == START:
            if self.cleared and not self.image_ready:
                return ABORT_NO_DATA
            self.control = START
            if self.image_ready:
                self.started = True
                self.staged = bytes(self.image)
                self.flash_status = self.flash_status_after_start
                if self.bootup_after_start:
                    threading.Timer(0.05, lambda: self.send([0], can_id=0x700 + self.node_id)).start()
        return 0

    def block_frame(self, d):
        blk = self._blk
        if blk["ended"] or d[0] & 0xE3 == 0xC1 and blk["seq"] == 0 and blk.get("data_done"):
            # end of the transfer: bytes without data in the last segment, CRC
            unused = (d[0] >> 2) & 7
            if unused:
                del blk["data"][-unused:]
            crc = struct.unpack_from("<H", d, 1)[0]
            if self.block_crc_seen and crc != crc16_ccitt(bytes(blk["data"])):
                self.abort(blk["index"], blk["sub"], ABORT_CRC)
                self._blk = None
                return
            self.block_done(blk)
            self.send([0xA1])
            self._blk = None
            return
        last = bool(d[0] & 0x80)
        blk["seq"] = d[0] & 0x7F
        blk["data"] += d[1:8]
        if last or blk["seq"] == self.block_size:
            self.send([0xA2, blk["seq"], self.block_size])
            blk["seq"] = 0
            blk["data_done"] = last

    def block_done(self, blk):
        data = bytes(blk["data"])
        if blk["index"] == 0x1F50:
            self.image = bytearray(data)
            self.cleared = False
            self.image_ready = True
            self.control = STOP
            self.flash_status = self.flash_error_after_download
            self.program_id = zlib.crc32(data) ^ (1 if self.corrupt_crc else 0)
        else:
            self.legacy_writes[blk["sub"]] = data
