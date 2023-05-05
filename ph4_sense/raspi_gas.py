import time
import board  # adafruit-blinka
import busio
import json
import adafruit_sgp30  # adafruit-circuitpython-sgp30
import adafruit_ahtx0  # adafruit-circuitpython-ahtx0
import adafruit_ccs811  # adafruit-circuitpython-ccs811
import adafruit_scd4x  # adafruit-circuitpython-scd4x
import paho.mqtt.client as mqtt  # paho-mqtt


class ExpAverage:
    def __init__(self, alpha):
        self.alpha = alpha
        self.average = None

    def update(self, value):
        if self.average is None:
            self.average = value
        else:
            self.average = self.alpha * value + (1 - self.alpha) * self.average
        return self.average


def try_fnc(x, msg=None):
    try:
        return x()
    except Exception as e:
        print(f'Err {msg or ""}: {e}')


# Initialize I2C bus
# i2c = busio.I2C(board.SCL7, board.SDA7)
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize sensors
sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)
aht21 = adafruit_ahtx0.AHTx0(i2c)
ccs811 = adafruit_ccs811.CCS811(i2c)
scd4x = adafruit_scd4x.SCD4X(i2c)

# Initialize sensor measurements
co2eq = 0
tvoc = 0

client = mqtt.Client("SGP30_sensor_office")
client.connect("10.0.1.103", 1883)

# Measure air quality
sgp30.set_iaq_relative_humidity(21, 0.45)
sgp30.set_iaq_baseline(0x8973, 0x8aae)
sgp30.iaq_init()
eavg = ExpAverage(0.1)
ccs811.drive_mode = adafruit_ccs811.DRIVE_MODE_250MS
scd4x.start_periodic_measurement()

last_ccs811_co2 = 0
last_ccs811_tvoc = 0
last_spg30_co2 = 0
last_spg30_tvoc = 0

last_pub = time.time() + 30
last_pub_spg = time.time() + 30
scd40_co2, scd40_temp, scd40_hum = None, None, None
while True:
    t = time.time()
    temp = None
    humd = None
    try:
        temp = try_fnc(lambda: aht21.temperature)
        humd = try_fnc(lambda: aht21.relative_humidity)
        if temp and humd and time.time() - last_pub > 3600:
            try_fnc(lambda: sgp30.set_iaq_relative_humidity(temp, humd))
            try_fnc(lambda: ccs811.set_environmental_data(int(humd), temp))
            print(f'Temp sync')

    except Exception as e:
        print(f'E: exc in temp {e}')

    try:
        sgp30.iaq_measure()
    except Exception as e:
        print(f'Exception measurement: {e}')
        time.sleep(1)
        continue

    ccs_co2, ccs_tvoc = 0, 0
    try:
        ccs811._update_data()
        nccs_co2, nccs_tvoc = ccs811._eco2, ccs811._tvoc
        if nccs_co2 and 100 < nccs_co2 < 30_000:
            last_ccs811_co2 = ccs_co2 = nccs_co2
        if nccs_tvoc and 0 <= nccs_tvoc < 30_000:
            last_ccs811_tvoc = ccs_tvoc = nccs_tvoc
        if ccs811.error:
            print(f'Err: {ccs811.error_code}')
    except Exception as e:
        print(f'CCS error: {e}')

    try:
        co2eq_1, tvoc, eth, h2 = sgp30.eCO2, sgp30.TVOC, sgp30.Ethanol, sgp30.H2
        if co2eq_1:
            last_spg30_co2 = co2eq_1
        if tvoc:
            last_spg30_tvoc = tvoc

        co2eq = eavg.update((last_spg30_co2 + last_ccs811_co2) / 2) if last_spg30_co2 and last_spg30_co2 else 0
    except Exception as e:
        print(f'SPG30 err: {e}')
        continue

    if scd4x.data_ready:
        try:
            scd40_co2, scd40_temp, scd40_hum = scd4x.CO2, scd4x.temperature, scd4x.relative_humidity
        except Exception as e:
            print(f'Err SDC40: {e}')

    print(
        "CO2eq: %4d (%4d) ppm, TVOC: %4d ppb, CO2: %4d, TVOC2: %4d, Eth: %5d, H2: %5d, %4.2f C, humd: %4.2f%%, SCD40: %4.2f, %4.2f C, %4.2f%%" % (
            co2eq, co2eq_1, tvoc, ccs_co2, ccs_tvoc, eth, h2, temp or -1, humd or -1, scd40_co2 or -1, scd40_temp or -1,
            scd40_hum or -1))

    if t - last_pub > 60:
        try:
            print(client.publish("sensors/sgp30_office", json.dumps(
                {'eCO2': co2eq, 'TVOC': tvoc, 'Eth': eth, 'H2': h2, 'temp': temp, 'humidity': humd})))

            print(client.publish("sensors/sgp30_raw_office", json.dumps(
                {'eCO2': last_spg30_co2, 'TVOC': last_spg30_tvoc})))

            print(client.publish("sensors/ccs811_raw_office", json.dumps(
                {'eCO2': last_ccs811_co2, 'TVOC': last_ccs811_tvoc})))

            last_pub = t
        except Exception as e:
            print(f'Error in pub: {e}')

    if t - last_pub_spg > 60 and scd40_co2 is not None and scd40_co2 > 0:
        try:
            print(client.publish("sensors/scd40_office", json.dumps(
                {'eCO2': scd40_co2, 'temp': scd40_temp, 'humidity': scd40_hum})))

            last_pub_spg = t
        except Exception as e:
            print(f'Error in pub: {e}')

    time.sleep(1)
