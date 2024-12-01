import machine

from ph4_sense_base.adapters import updateLogger
from ph4_sense_base.logger_mp import MpLogger
from ph4_sense_base.sensei_base import SenseiBase
from ph4_sense_base.support.uart_mp import UartMp

# import network
# from umqtt.robust import MQTTClient


# from ph4_sense_base.utils import try_fnc

# Set up your SPG30 sensor pin connections
# https://randomnerdtutorials.com/esp32-i2c-communication-arduino-ide/
# SPG30_SCL_PIN = 22
# SPG30_SDA_PIN = 21


# TODO: IMPLEMENT with mods
# TODO: mod for sensors, sensor set?
# Unfinished, missing integration with SensorsModMp
class SenseiMp(SenseiBase):
    def __init__(
        self,
        is_esp32=True,
        has_wifi=True,
        has_aht=True,
        has_sgp30=True,
        has_ccs811=True,
        has_scd4x=True,
        has_sps30=False,
        has_hdc1080=False,
        has_zh03b=False,
        has_sgp41=False,
        scl_pin=22,
        sda_pin=21,
    ):
        super().__init__(
            is_esp32=is_esp32,
            has_wifi=has_wifi,
            scl_pin=scl_pin,
            sda_pin=sda_pin,
        )

        updateLogger(MpLogger(self.log_fnc))

    def get_uart_builder(self, desc):
        if desc["type"] != "uart":
            raise ValueError("Only uart type is supported")

        def builder(**kwargs):
            return UartMp(machine.UART(desc["port"], **kwargs))

        return builder

    def publish_msg(self, topic: str, message: str):
        self.mqtt_client.publish(topic, message)
        self.print(f"Published {topic}:", message)


def main(**kwargs):
    sensei = SenseiMp(**kwargs)
    sensei.main()


# Run the main program
if __name__ == "__main__":
    main()
