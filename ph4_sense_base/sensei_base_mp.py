import machine
import network
from umqtt.robust import MQTTClient

from ph4_sense_base.adapters import sleep_ms, time, updateLogger
from ph4_sense_base.logger_mp import MpLogger
from ph4_sense_base.sensei_base import SenseiBase
from ph4_sense_base.support.uart_mp import UartMp
from ph4_sense_base.utils import try_fnc

# Set up your SPG30 sensor pin connections
# https://randomnerdtutorials.com/esp32-i2c-communication-arduino-ide/
# SPG30_SCL_PIN = 22
# SPG30_SDA_PIN = 21


# TODO: maybe define with modules. e.g., BusModule, WifiModule, MqttModule. Encapsulate also state inside.
class SenseiBaseMp(SenseiBase):
    def __init__(
        self,
        is_esp32=True,
        has_wifi=True,
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

    def log_fnc(self, level, msg, *args, **kwargs):
        if level < 20:  # do not log debug events
            return

        msg_use = msg if not args else msg % args
        self.print("log[{}]: {}".format(level, msg_use))

    def start_bus(self):
        self.i2c = machine.SoftI2C(scl=machine.Pin(self.scl_pin), sda=machine.Pin(self.sda_pin))
        self.i2c.start()

    def get_uart_builder(self, desc):
        if desc["type"] != "uart":
            raise ValueError("Only uart type is supported")

        def builder(**kwargs):
            return UartMp(machine.UART(desc["port"], **kwargs))

        return builder

    def connect_wifi(self, force=False):
        if not self.has_wifi:
            return

        if force:
            self.sta_if = None

        if not self.sta_if:
            self.sta_if = network.WLAN(network.STA_IF)
            self.sta_if.active(True)

        if not self.wifi_ssid:
            raise ValueError("WiFi is not configured")

        if not self.sta_if.isconnected():
            print("Not connected, scanning...")
            scan_res = self.sta_if.scan()
            if scan_res:
                for net in scan_res:
                    print(" - ", net)

            print("Connecting to WiFi: " + self.wifi_ssid)
            self.sta_if.connect(self.wifi_ssid, self.wifi_passphrase)
            while not self.sta_if.isconnected():
                sleep_ms(500)

            print("WiFi connected")

            # Set unlimited WiFi reconnect attempts
            self.sta_if.config(reconnects=-1)

        print("WiFi status:", self.sta_if.status())
        print("WiFi ifconfig:", self.sta_if.ifconfig())

    def check_wifi_ok(self):
        """
        Possible WiFi statuses:
            * ``STAT_IDLE`` -- no connection and no activity,
            * ``STAT_CONNECTING`` -- connecting in progress,
            * ``STAT_WRONG_PASSWORD`` -- failed due to incorrect password,
            * ``STAT_NO_AP_FOUND`` -- failed because no access point replied,
            * ``STAT_CONNECT_FAIL`` -- failed due to other problems,
            * ``STAT_GOT_IP`` -- connection successful.
        :return:
        """
        if not self.has_wifi:
            return

        try:
            if not self.sta_if.isconnected():
                raise ValueError("WiFi not connected")

            wifi_status = self.sta_if.status()
            is_connected = wifi_status == network.STAT_GOT_IP
            if is_connected:
                return

            t = time.time()
            is_connecting = wifi_status == network.STAT_CONNECTING
            if is_connecting and t - self.last_wifi_reconnect < self.wifi_reconnect_timeout:
                return

            try_fnc(lambda: self.sta_if.disconnect())

        except Exception as e:
            self.print("Network exception: ", e)

        # When control flow gets here - reconnect
        self.on_wifi_reconnect()

    def create_mqtt_client(self):
        # https://notebook.community/Wei1234c/Elastic_Network_of_Things_with_MQTT_and_MicroPython/notebooks/test/MQTT%20client%20test%20-%20MicroPython
        client = MQTTClient(
            f"esp32_client/{self.mqtt_sensor_id}",
            self.mqtt_broker,
            self.mqtt_port,
            keepalive=60,
            ssl=False,
            ssl_params={},
        )
        client.set_callback(self.mqtt_callback)
        client.connect()
        client.subscribe(self.mqtt_topic_sub)
        return client

    def publish_msg(self, topic: str, message: str):
        self.mqtt_client.publish(topic, message)
        self.print(f"Published {topic}:", message)
