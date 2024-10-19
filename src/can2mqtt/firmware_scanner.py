from abc import abstractmethod
import asyncio
import datetime
import logging
import os
import re
import sys
from typing import Callable
from pathlib import Path

from awesomeversion import AwesomeVersion
import pyinotify


logger = logging.getLogger(__name__)

VER_RE = re.compile(rb"node_id: ([\da-f]{2}), ver: (\d{4}\.\d{1,1}\.\d{1,2}(?:-\w+)?.\d{4}\d{2}\d{2}\.\d{2}\d{2}\d{2})")

FIRMWARE_DIR = "firmwares"


def parse_fw(path):
    with open(path, 'rb') as fw:
        matched = VER_RE.search(fw.read())
        if matched:
            node_id, esp_rev = matched.groups()
            node_id = int(node_id, 16)
            esp_rev = AwesomeVersion(esp_rev.decode())
            return node_id, esp_rev
        else:
            logger.debug("cannot parse %s, skipping", path)


class BaseFirmwareEventHandler(pyinotify.ProcessEvent):

    def is_valid(self, event):
        return not event.dir and event.pathname.endswith(".bin")

    @abstractmethod
    def on_delete_firmware(self, path):
        pass

    @abstractmethod
    def on_new_firmware(self, path, node_id, rev):
        pass

    def process_IN_DELETE(self, event):
        if self.is_valid(event):
            self.on_delete_firmware(event.pathname)
            logger.info("removed %s", event.pathname)

    def process_IN_CLOSE_WRITE(self, event):
        if self.is_valid(event):
            parsed = parse_fw(event.pathname)
            if parsed:
                node_id, rev = parsed
                self.on_new_firmware(event.pathname, node_id, rev)
            else:
                logger.info("cannot parse firmware: %s", event.pathname)


class FirmwareDebugHandler(BaseFirmwareEventHandler):
    def on_delete_firmware(self, path):
        logger.debug("delete firmware: %s", path)

    def on_new_firmware(self, path, node_id, rev):
        logger.debug("new firmware: %s node_id: %s, ver: %s", path, node_id, rev)


def init(
    loop: asyncio.AbstractEventLoop,
    firmware_dir: str,
    event_handler: BaseFirmwareEventHandler,
) -> pyinotify.AsyncioNotifier:

    for path in Path(firmware_dir).rglob('*.bin'):
        parsed = parse_fw(path.absolute())
        if parsed:
            node_id, rev = parsed
            event_handler.on_new_firmware(path.absolute(), node_id, rev)

    wm = pyinotify.WatchManager()  # Watch Manager
    mask = pyinotify.IN_CLOSE_WRITE | pyinotify.IN_DELETE  # watched events
    notifier = pyinotify.AsyncioNotifier(wm, loop, default_proc_fun=event_handler)
    wdd = wm.add_watch(firmware_dir, mask, rec=True, auto_add=True)
    return notifier


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()

    notifier = init(loop, os.path.abspath(FIRMWARE_DIR), FirmwareDebugHandler())

    try:
        loop.run_forever()
    except:
        logger.info('\nshutting down...')

    loop.stop()
    notifier.stop()

