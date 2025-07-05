#!/usr/bin/env bash

if [ -z "$1" ]; then
  echo "Usage: $0 <instance_name>"
  exit 1
fi

INSTANCE="$1"
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "${SCRIPT_DIR}"

if [ ! -d "4instances/${INSTANCE}" ]; then
  echo "Error: Directory '4instances/${INSTANCE}' does not exist."
  exit 1
fi

# may exist already
sudo groupadd ph4metrics
sudo useradd -r -M -g ph4metrics -s /usr/sbin/nologin -c "System User for ph4metrics" ph4metrics
sudo usermod -aG i2c ph4metrics
sudo usermod -aG dialout ph4metrics
sudo usermod -aG audio ph4metrics

set -ex
MDIR="/etc/ph4metrics"
mkdir -p "${MDIR}"

cp ph4metrics.sh "${MDIR}"
chmod 0755 "${MDIR}/ph4metrics.sh"

cp ph4_metrics/metrics.py /usr/local/bin/ph4-metrics
chmod 0755 "/usr/local/bin/ph4-metrics"
chown ph4metrics:ph4metrics "/usr/local/bin/ph4-metrics"

cp logrotate/ph4metrics /etc/logrotate.d/ph4metrics
cp "4instances/${INSTANCE}/ph4metrics.env" /etc/ph4metrics.env

touch /var/log/ph4metrics.json
touch /var/log/ph4metrics.log
chown ph4metrics:ph4metrics /var/log/ph4metrics.json
chown ph4metrics:ph4metrics /var/log/ph4metrics.log

echo 'ph4metrics ALL=(ALL) NOPASSWD: /usr/sbin/nvme smart-log /dev/nvme0 -o json' | sudo tee /etc/sudoers.d/ph4metrics-nvme > /dev/null
cp ph4metrics.service /etc/systemd/system/ph4metrics.service
systemctl daemon-reload

set +ex
echo "[+] DONE"

systemctl enable ph4metrics.service

# systemctl restart ph4metrics.service
# pip3.10 install -U . && systemctl restart ph4metrics.service
