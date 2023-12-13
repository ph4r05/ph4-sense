from umqtt.robust import MQTTClient

from ph4_sense_base.mods.mqtt import MqttMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.consts import Const
from ph4_sense_base.support.typing import Callable, Optional
from ph4_sense_base.utils import try_exec_method_cb


class MqttModMp(MqttMod):
    def __init__(
        self,
        client_id: str,
        broker_host: str,
        broker_port: int = 1883,
        topic_sub: Optional[str] = None,
        callback: Optional[Callable] = None,
        base: Optional[SenseiIface] = None,
        has_mqtt: bool = True,
        mqtt_reconnect_timeout: int = 60 * 3,
        last_reconnect: Optional[int] = None,
    ):
        super().__init__(base, has_mqtt, mqtt_reconnect_timeout, last_reconnect)
        self.client_id = client_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic_sub = topic_sub
        self.callback = callback

    def create_mqtt_client(self):
        # https://notebook.community/Wei1234c/Elastic_Network_of_Things_with_MQTT_and_MicroPython/notebooks/test/MQTT%20client%20test%20-%20MicroPython
        client = MQTTClient(
            self.client_id,
            self.broker_host,
            self.broker_port,
            keepalive=60,
            ssl=False,
            ssl_params={},
        )
        if self.callback:
            client.set_callback(self.callback)

        client.connect()

        if self.topic_sub:
            client.subscribe(self.topic_sub)

        return client

    def publish_msg(self, topic: str, message: str):
        self.mqtt_client.publish(topic, message)
        try_exec_method_cb(self.base, Const.PRINT, f"Published {topic}:", message)
