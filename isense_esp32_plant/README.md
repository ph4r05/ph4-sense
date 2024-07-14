# Local instance

Install
```shell
mpremote cp -r ph4_sense_base/ :
mpremote cp -r ph4_sense/ :
```

```shell
# UDP monitor
while true; do nc -ul 9998; done
```
