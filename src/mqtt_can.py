import asyncio
import logging
import time
import queue
import can
import aiomqtt

from can2mqtt.utils import parse_mqtt_server_url

logger = logging.getLogger(__name__)


async def run(mqtt_server_url, bus):
    host_name, extra_auth = parse_mqtt_server_url(mqtt_server_url)

    async with aiomqtt.Client(host_name, **extra_auth) as client:
        bus.client = client
        await client.subscribe("canbus/#")
        async with client.messages() as messages:
            async for message in messages:
                _, src, can_id = message.topic.value.split("/")
                if src == '2048':
                    continue
                can_msg = can.Message(
                    arbitration_id=int(can_id),
                    is_extended_id=False,
                    data=message.payload,
                )
                logger.debug("received %s %s, can_msg: %r", message.topic, message.payload, can_msg)
                bus.queue.put(can_msg, block=True)


class MqttCan(can.bus.BusABC):
    def __init__(self, channel, **kwargs):
        logger.info("channel: %s", channel)
        self.client = None
        self.queue = queue.Queue(1000)
        self.channel_info = 'mqtt'
        self.loop = asyncio.get_running_loop()
        self.loop.create_task(run(channel, self))

    def send(self, msg):
        logger.debug("send %r", msg)
        can_id = msg.arbitration_id
        self.loop.create_task(self.client.publish(f"canbus/2048/{can_id}", payload=msg.data, retain=False))

    def _recv_internal(self, timeout=None):
        try:
            msg = self.queue.get(timeout=timeout)
        except queue.Empty:
            msg = None
        logger.debug("recv %r", msg)
        return msg, True


