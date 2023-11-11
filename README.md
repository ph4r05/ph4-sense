# Sensing library

Smart home sensing tools

## UdpLogger

Start UDP logger on the server side:

```bash
nc -ul 9998

# or to run repeatedly
while true; do nc -ul 9998; done
```

## Alternative python installation

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev
wget https://www.python.org/ftp/python/3.10.12/Python-3.10.12.tgz
tar -xf Python-3.10.*.tgz
cd Python-3.10.*/
./configure --prefix=/usr/local --enable-optimizations --enable-shared LDFLAGS="-Wl,-rpath /usr/local/lib"
make -j $(nproc)
sudo make altinstall

python3.10 --version
```

## Circuitry

Note that SPS30 is 5V sensor while others are 3.3V. Directly attaching SPS30 to I2C won't work due to operating voltage difference.
(Also note that I2C and UART on ESP32 and Rpi are 3.3V). A [level shifter](https://cdn-shop.adafruit.com/datasheets/an97055.pdf) is needed for 3.3V and 5V sensors to operate on the same I2C bus.

## Dependencies

Repository has directly included Sensirion gas index algorithm for ease of deployment to ESP32: https://github.com/ph4r05/ph4-sensirion-gas-index-algorithm-py

## Development

Install pre-commit hooks defined by `.pre-commit-config.yaml`

```shell
pip3 install -U pre-commit
pre-commit install
```

Auto fix
```shell
pre-commit run --all-files
```

Plugin version update
```shell
pre-commit autoupdate
```
