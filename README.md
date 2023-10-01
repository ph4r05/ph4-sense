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
