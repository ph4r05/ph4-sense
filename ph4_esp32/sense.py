import machine
import time
import ujson as json
from umqtt.robust import MQTTClient

from athx0 import AHTx0
from ccs811 import CCS811Custom
from scd4x import SCD4X
from spg30 import SGP30

# Set up your Wi-Fi connection details
WIFI_SSID = None
WIFI_PASSWORD = None

# Set up your MQTT broker details
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_SENSOR_SUFFIX = "_bed"
MQTT_TOPIC_SUB = "sensors/esp32_bed_sub"
MQTT_TOPIC = "sensors/esp32_bed_gas"

HAS_AHT = True
HAS_SGP30 = True
HAS_CCS811 = True
HAS_SCD4X = True

# Set up your SPG30 sensor pin connections
# https://randomnerdtutorials.com/esp32-i2c-communication-arduino-ide/
SPG30_SCL_PIN = 22
SPG30_SDA_PIN = 21


def load_config():
    global WIFI_SSID, WIFI_PASSWORD, MQTT_BROKER
    with open("config.json") as fh:
        js = json.load(fh)

    WIFI_SSID = js["wifi"]["ssid"]
    WIFI_PASSWORD = js["wifi"]["passphrase"]
    MQTT_BROKER = js["mqtt"]["host"]


# Define the MQTT callback function
def mqtt_callback(topic, msg):
    print("Received MQTT message:", topic, msg)


# Connect to Wi-Fi
def connect_wifi():
    import network

    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(True)

    if not WIFI_SSID:
        raise ValueError("WiFi is not configured")

    if not sta_if.isconnected():
        print("Not connected, scanning...")
        sta_if.scan()

        print("Connecting to WiFi: " + WIFI_SSID)
        sta_if.connect(WIFI_SSID, WIFI_PASSWORD)
        while not sta_if.isconnected():
            time.sleep(0.5)
    print("WiFi connected:", sta_if.ifconfig())


# Connect to MQTT broker
def connect_mqtt():
    # https://notebook.community/Wei1234c/Elastic_Network_of_Things_with_MQTT_and_MicroPython/notebooks/test/MQTT%20client%20test%20-%20MicroPython
    client = MQTTClient(
        "esp32_client/gas",
        MQTT_BROKER,
        MQTT_PORT,
        keepalive=60,
        ssl=False,
        ssl_params={},
    )
    client.set_callback(mqtt_callback)
    client.connect()
    client.subscribe(MQTT_TOPIC_SUB)
    return client


# Main program loop
def main():
    print("Starting bus")
    i2c = machine.SoftI2C(
        scl=machine.Pin(SPG30_SCL_PIN), sda=machine.Pin(SPG30_SDA_PIN)
    )
    i2c.start()

    print("Loading config")
    load_config()

    print("\nConnecting WiFi")
    #connect_wifi()

    print("\nConnecting MQTT")
    #mqtt_client = connect_mqtt()
    mqtt_client = None

    print("\nConnecting sensors")
    try:
        #print(" - Connecting SGP30")
        #sgp30 = SGP30(i2c) if HAS_SGP30 else None

        #print("\n - Connecting AHT21")
        #aht21 = AHTx0(i2c) if HAS_AHT else None

        print("\n - Connecting CCS811")
        ccs811 = CCS811Custom(i2c) if HAS_CCS811 else None

        print("\n - Connecting SCD40")
        scd4x = SCD4X(i2c) if HAS_SCD4X else None

        print("\n Sensors connected")
    except Exception as e:
        print("Excepion in sensor init: ", e)

    return
    while True:
        # Read data from SPG30 sensor
        # i2c.writeto(0x58, b'\x20\x03')
        # time.sleep(0.5)
        # data = i2c.readfrom(0x58, 6)
        # tvoc = data[0] * 256 + data[1]
        # Publish data to MQTT broker
        payload = json.dumps({"tvoc": 0})
        print(payload)
        print(mqtt_client.publish(MQTT_TOPIC, payload))
        # Wait for some time before taking the next reading
        time.sleep(10)


# Run the main program
if __name__ == "__main__":
    main()
