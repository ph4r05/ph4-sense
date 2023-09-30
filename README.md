# Sensing library

Smart home sensing tools

## UdpLogger

Start UDP logger on the server side:

```bash
nc -ul 9998

# or to run repeatedly
while true; do nc -ul 9998; done
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
