import asyncio
import logging
import time
import queue
import can
import asyncio_mqtt as aiomqtt

from can2mqtt.utils import parse_mqtt_server_url

logger = logging.getLogger(__name__)


async def run(mqtt_server_url, bus):
    host_name, extra_auth = parse_mqtt_server_url(mqtt_server_url)

    async with aiomqtt.Client(host_name, **extra_auth) as client:
        bus.client = client
        await client.subscribe("from-canbus/#")
        async with client.messages() as messages:
            async for message in messages:
                can_msg = can.Message(
                    arbitration_id=int(message.topic.value.split("/")[1], 16),
                    is_extended_id=False,
                    data=message.payload,
                )
                logger.info("received %s %s, can_msg: %r", message.topic, message.payload, can_msg)
                bus.queue.put(can_msg, block=True)


class MqttCan(can.bus.BusABC):
    def __init__(self, channel, **kwargs):
        logger.info("channel: %s", channel)
        self.client = None
        self.queue = queue.Queue(1000)
        self.channel_info = 'mqtt'
        asyncio.create_task(run(channel, self))

    def send(self, msg):
        logger.debug("send %r", msg)
        can_id = msg.arbitration_id
        asyncio.create_task(self.client.publish(f"to-canbus/{can_id:x}", payload=msg.data, retain=False))

    def _recv_internal(self, timeout=None):
        try:
            msg = self.queue.get(timeout=timeout)
        except queue.Empty:
            msg = None
        logger.debug("recv %r", msg)
        return msg


