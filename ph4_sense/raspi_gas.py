import time
import board  # adafruit-blinka
import busio
import json
import adafruit_sgp30  # adafruit-circuitpython-sgp30
import adafruit_ahtx0  # adafruit-circuitpython-ahtx0
import paho.mqtt.client as mqtt  # paho-mqtt

# Initialize I2C bus
# i2c = busio.I2C(board.SCL7, board.SDA7)
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize sensors
sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)
aht21 = adafruit_ahtx0.AHTx0(i2c)

# Initialize sensor measurements
co2eq = 0
tvoc = 0

client = mqtt.Client("SGP30_sensor_office")
client.connect("10.0.1.103", 1883)

# Measure air quality
sgp30.set_iaq_relative_humidity(21, 0.45)
sgp30.set_iaq_baseline(0x8973, 0x8aae)
sgp30.iaq_init()

last_pub = 0
while True:
    t = time.time()
    temp = None
    humd = None
    try:
        temp = aht21.temperature
        humd = aht21.relative_humidity
        if temp and humd:
            sgp30.set_iaq_relative_humidity(temp, humd)

    except Exception as e:
        print(f'E: exc in temp {e}')

    sgp30.iaq_measure()
    co2eq, tvoc, eth, h2 = sgp30.eCO2, sgp30.TVOC, sgp30.Ethanol, sgp30.H2
    print("CO2eq: %4d ppm \t TVOC: %4d ppb, \t Eth: %5d, \t H2: %5d, temp: %4.2f, humd: %4.2f" % (co2eq, tvoc, eth, h2, temp or -1, humd or -1 ))

    if t - last_pub > 60:
        print(client.publish("sensors/sgp30_office", json.dumps({'eCO2': co2eq, 'TVOC': tvoc, 'Eth': eth, 'H2': h2, 'temp': temp, 'humidity': humd})))
        last_pub = t

    time.sleep(1)
