
import time
import board  # adafruit-blinka
import busio
import json
import adafruit_sgp30  # adafruit-circuitpython-sgp30
import adafruit_ahtx0  # adafruit-circuitpython-ahtx0
import adafruit_scd4x  # adafruit-circuitpython-scd4x
import paho.mqtt.client as mqtt  # paho-mqtt

# Initialize I2C bus
i2c = busio.I2C(board.SCL7, board.SDA7)

# Initialize sensors
sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)
aht21 = adafruit_ahtx0.AHTx0(i2c)
scd4x = adafruit_scd4x.SCD4X(i2c)

# Initialize sensor measurements
co2eq = 0
tvoc = 0

client = mqtt.Client("SGP30_sensor")
client.connect("127.0.0.1", 1883)

# Measure air quality
sgp30.set_iaq_relative_humidity(21, 0.45)
sgp30.set_iaq_baseline(0x8973, 0x8aae)
sgp30.iaq_init()
scd4x.start_periodic_measurement()

last_pub = 0
scd40_co2, scd40_temp, scd40_hum = None, None, None
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

    if scd4x.data_ready:
        scd40_co2, scd40_temp, scd40_hum = scd4x.CO2, scd4x.temperature, scd4x.relative_humidity

    print("CO2eq: %4d ppm \t TVOC: %4d ppb, \t Eth: %5d, \t H2: %5d, temp: %4.2f, humd: %4.2f, SCD40: %4.2f, %4.2f C, %4.2f%%" % (co2eq, tvoc, eth, h2, temp or -1, humd or -1, scd40_co2 or -1, scd40_temp or -1, scd40_hum or -1))

    if t - last_pub > 60:
        print(client.publish("sensors/sgp30", json.dumps({'eCO2': co2eq, 'TVOC': tvoc, 'Eth': eth, 'H2': h2, 'temp': temp, 'humidity': humd})))
        if scd40_co2 is not None and scd40_co2 > 0:
            print(client.publish("sensors/scd40", json.dumps({'eCO2': scd40_co2, 'temp': scd40_temp, 'humidity': scd40_hum})))
        last_pub = t


    time.sleep(1)

