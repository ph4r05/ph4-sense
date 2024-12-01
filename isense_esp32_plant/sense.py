import uasyncio as asyncio
from machine import Pin

from ph4_sense_base.adapters import sleep_ms, time, updateLogger
from ph4_sense_base.logger_mp import MpLogger
from ph4_sense_base.mods_mp.mqtt import MqttModMp
from ph4_sense_base.sensei_base import SenseiBase
from ph4_sense_base.support.sensor_helper import SensorHelper
from ph4_sense_base.support.typing import Optional

try:
    from typing import List
except ImportError:
    pass


class MotorController:
    def __init__(self, pin_number, level_pin: Optional[int] = None):
        self.motor = Pin(pin_number, Pin.OUT)
        self.detect = Pin(level_pin, Pin.OUT) if level_pin else None
        self.task = None
        self.monitor_task = None
        self.running = False  # To track the motor state
        self.lock = asyncio.Lock()  # Lock to ensure thread safety

    async def _disable_after_timeout(self, timeout):
        await asyncio.sleep(timeout)
        self._stop_motor("Timeout reached")

    async def _monitor_water_level(self):
        while True:
            if self.detect.value() == 1:  # Water level high
                self._stop_motor("Water level high")
            await asyncio.sleep(0.1)  # Poll water level every 100ms

    def motor_on(self, timeout=1):
        """Turn the motor on and set a timeout to auto-disable."""
        async with self.lock:
            if self.running:
                return

            self._monitor_on()
            self.motor.value(1)  # Turn on the motor
            self.running = True

            # Cancel any existing auto-disable task
            if self.task:
                self.task.cancel()

            # Start a new auto-disable task
            self.task = asyncio.create_task(self._disable_after_timeout(timeout))

    def _monitor_on(self):
        self.monitor_task = asyncio.create_task(self._monitor_water_level())

    def _monitor_off(self):
        if self.monitor_task:
            self.monitor_task.cancel()
            self.monitor_task = None

    def motor_off(self):
        """Turn the motor off."""
        self._stop_motor("Manually turned off")

    def _stop_motor(self, reason):
        """Internal method to stop the motor with a reason."""
        async with self.lock:
            if self.running:
                self.motor.value(0)  # Turn off the motor
                self.running = False

            # Cancel the timeout task if running
            if self.task:
                self.task.cancel()
                self.task = None

            self._monitor_off()


class Sensei(SenseiBase):
    def __init__(
        self,
        is_esp32=True,
        has_wifi=True,
        scl_pin=22,
        sda_pin=21,
    ):
        super().__init__(is_esp32=is_esp32, has_wifi=has_wifi, scl_pin=scl_pin, sda_pin=sda_pin)
        self.set_sensor_id("default")

        self.measure_attempts = 5
        self.measure_timeout = 150
        self.measure_loop_ms = 2_000
        self.temp_sync_timeout = 180

        self.last_tsync = 0
        self.last_pub = time.time() + 30
        self.last_pub_sgp = time.time() + 30
        self.sensor_helper = None

        updateLogger(MpLogger(self.log_fnc))

    def init_mods(self):
        super().init_mods()
        self.mod_mqtt = MqttModMp(
            base=self, has_mqtt=True, callback=self.mqtt_callback, client_id="plant", topic_sub="plant"
        )

    def mqtt_callback(self, topic=None, msg=None):
        self.print("Received MQTT message:", topic, msg)

    def get_sensor_helper(self) -> SensorHelper:
        if not self.sensor_helper:
            self.sensor_helper = SensorHelper(logger=self.logger)

        return self.sensor_helper

    def load_config(self):
        js = super().load_config()

        if "sensors" in js:
            self.load_config_sensors(js["sensors"])

    def load_config_sensors(self, sensors: List[str]):
        for sensor in sensors:
            sensor = sensor.lower()
            pass

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
            await asyncio.sleep(100 * self.measure_loop_ms)


def main():
    sensei = Sensei()
    sensei.main()


# Run the main program
if __name__ == "__main__":
    main()
