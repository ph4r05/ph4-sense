import machine
import uasyncio as asyncio

from ph4_sense.sense_mod import SensorsModMp
from ph4_sense_base.adapters import sleep_ms, time, updateLogger
from ph4_sense_base.logger_mp import MpLogger
from ph4_sense_base.sensei_base import SenseiBase
from ph4_sense_base.support.sensor_helper import SensorHelper
from ph4_sense_base.support.typing import Dict, Optional
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

        self.sensor_helper: Optional[SensorHelper] = None
        self.sensor_board: Optional[SensorsModMp] = None
        updateLogger(MpLogger(self.log_fnc))

    def get_uart_builder(self, desc):
        if desc["type"] != "uart":
            raise ValueError("Only uart type is supported")

        def builder(**kwargs):
            return UartMp(machine.UART(desc["port"], **kwargs))

        return builder

    def get_sensor_helper(self) -> SensorHelper:
        if not self.sensor_helper:
            self.sensor_helper = SensorHelper(logger=self.logger)

        return self.sensor_helper

    def load_config(self) -> Dict:
        return super().load_config()

    def try_measure(self, fnc):
        for attempt in range(self.measure_attempts):
            try:
                return fnc()
            except Exception as e:
                if attempt + 1 >= self.measure_attempts:
                    self.logger.error(f"Could not measure sensor {fnc}, attempt {attempt}: {e}")
                    raise
                else:
                    self.logger.warn(f"Could not measure sensor {fnc}, attempt {attempt}: {e}")
                    sleep_ms(self.measure_timeout)

    def connect_sensors(self):
        self.print("\nConnecting sensors")
        try:
            self.sensor_board = SensorsModMp(i2c=self.mod_i2c.i2c, base=self, sensor_helper=self.get_sensor_helper())
            self.sensor_board.load_config(self.load_config_data())
            # self.try_connect_sensor(self.connect_sgp30)

            self.print("\nSensors connected")
        except Exception as e:
            self.print("Exception in sensor init: ", e)
            self.logger.debug("Exception in sensor init: {}".format(e), exc_info=e)
            raise

    def publish(self):
        self.publish_common()

    def publish_common(self):
        t = time.time()
        if t - self.last_pub <= self.readings_publish_timeout:
            return

        try:
            self.check_wifi_ok()
            self.maybe_reconnect_mqtt()

            self.last_pub = t
        except Exception as e:
            self.print("Error in pub:", e)

    def measure_loop_body(self):
        self.update_metrics()
        self.publish()

    def init_connections(self):
        self.post_start()

        self.connect_sensors()
        self.log_memory()

        self.publish_booted()
        self.log_memory()

    def main(self):
        self.init_connections()
        asyncio.run(self.amain())

    async def amain(self):
        while True:
            self.maybe_reconnect_mqtt()
            self.measure_loop_body()
            await asyncio.sleep(1000 * self.measure_loop_ms)


def main(**kwargs):
    sensei = SenseiMp(**kwargs)
    sensei.main()


# Run the main program
if __name__ == "__main__":
    main()
