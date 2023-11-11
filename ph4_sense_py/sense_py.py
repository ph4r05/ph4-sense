import argparse
import logging
import sys

import busio
import coloredlogs
import paho.mqtt.client as mqtt  # paho-mqtt
from ph4monitlib.utils import load_config_file

from ph4_sense.sense import Sensei
from ph4_sense.support.uart_mp import UartMp
from ph4_sense_py.support.uart import UartSerial

logger = logging.getLogger(__name__)
coloredlogs.install(level=logging.INFO)


class SenseiPy(Sensei):
    def __init__(
        self,
        is_esp32=False,
        has_wifi=False,
        has_aht=True,
        has_sgp30=True,
        has_ccs811=True,
        has_scd4x=True,
        has_sps30=False,
        has_hdc1080=False,
        has_zh03b=False,
        has_sgp41=False,
        scl_pin=None,
        sda_pin=None,
        config_file=None,
    ):
        super().__init__(
            is_esp32=is_esp32,
            has_wifi=has_wifi,
            has_aht=has_aht,
            has_sgp30=has_sgp30,
            has_ccs811=has_ccs811,
            has_scd4x=has_scd4x,
            has_sps30=has_sps30,
            has_hdc1080=has_hdc1080,
            has_zh03b=has_zh03b,
            has_sgp41=has_sgp41,
            scl_pin=scl_pin,
            sda_pin=sda_pin,
        )
        self.config_file = config_file
        self.args = None

    def load_config_data(self):
        cfile = self.config_file or "config.json"
        return load_config_file(cfile)

    def start_bus(self):
        self.i2c = busio.I2C(self.scl_pin, self.sda_pin)

    def get_uart_builder(self, desc):
        if desc["type"] == "uart":

            def builder(**kwargs):
                return UartMp(busio.UART(tx=desc["tx"] or 4, rx=desc["rx"] or 5, **kwargs))

            return builder

        elif desc["type"] == "serial":
            import serial

            def builder(**kwargs):
                return UartSerial(serial.Serial(desc["port"], **kwargs))

            return builder
        else:
            raise ValueError("Only uart and serial is supported")

    def connect_wifi(self, force=False):
        pass  # Not used for now

    def check_wifi_ok(self):
        pass  # Not used for now

    def create_mqtt_client(self):
        client = mqtt.Client(f"esp32_client/{self.mqtt_sensor_id}")
        client.on_message = self.mqtt_callback
        client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
        client.subscribe(self.mqtt_topic_sub)
        return client

    def publish_msg(self, topic: str, message: str):
        self.mqtt_client.publish(topic, message)
        self.print(f"Published {topic}:", message)

    def argparser(self):
        parser = argparse.ArgumentParser(description="Sensei")
        parser.add_argument("--debug", dest="debug", action="store_const", const=True, help="enables debug mode")
        parser.add_argument("-c", "--config", dest="config", help="Config file to load")
        return parser

    def main(self, sys_args=None):
        parser = self.argparser()
        self.args = parser.parse_args(sys_args)

        if self.args.debug:
            coloredlogs.install(level=logging.DEBUG)

        self.config_file = self.args.config
        super().main()


def main(*args, **kwargs):
    sensei = SenseiPy(**kwargs)
    sensei.main(*args)


# Run the main program
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
