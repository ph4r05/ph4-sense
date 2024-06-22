# Shelly scripts

## Hallway switch

KVS `HA_PARAMS`, for HA webhook
```json
{ "url": "http://ha.local:8123/api/webhook/shelly_cor", "token": "secret token" }
```

For AppDaemon webhook
```json
{ "url": "http://ha.local:5050/api/appdaemon/shelly_cor", "token": "secret token" }
```

### Updating KVS

```
curl -X POST -d '{"id":1,"method":"KVS.Set","params":{"key":"HA_PARAMS","value":"{\"url\": \"http://ha.local:5050/api/appdaemon/shelly_cor\", \"token\": \"secret token\" }"}}' http://${SHELLY}/rpc
```
