# Local instance

```shell
sudo ./install.sh
sudo -u ph4sense /etc/ph4sense/ph4sense.sh

# Or in one go
sudo ./install.sh ; sudo -u ph4sense /etc/ph4sense/ph4sense.sh

# Start
systemctl restart ph4sense.service

# UDP monitor
while true; do nc -ul 9991; done
```
