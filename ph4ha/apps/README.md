# AppDaemon HA integration

- https://appdaemon.readthedocs.io/en/latest/APPGUIDE.html

## Deps
- https://github.com/AppDaemon/appdaemon/pull/360/files

## Deploy
```shell
rsync -avz -e ssh ph4ha/apps/blinds.py rock:/home/rock/blinds.py

# server
cp blinds.py ha-py/apps/blinds.py
```
