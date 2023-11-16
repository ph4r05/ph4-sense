# Local instance

```shell
sudo ./install.sh
sudo /etc/ph4sense/ph4sense.sh

# Or in one go
sudo ./install.sh ; sudo -u ph4sense /etc/ph4sense/ph4sense.sh

# Start
systemctl restart ph4sense.service

# UDP monitor
while true; do nc -ul 9992; done
```


## `import board` problem

- https://forum.radxa.com/t/problem-using-adafruit-blinka-on-rock-4c/16802
- /usr/local/lib/python3.10/site-packages/adafruit_blinka/microcontroller/rockchip/rk3399/pin.py change back to:
- https://github.com/adafruit/Adafruit_Blinka/pull/677/files
