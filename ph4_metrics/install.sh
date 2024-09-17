#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# may exist already
sudo groupadd ph4metrics
sudo useradd -r -M -g ph4metrics -s /usr/sbin/nologin -c "System User for ph4metrics" ph4metrics
sudo usermod -aG i2c ph4metrics
sudo usermod -aG dialout ph4metrics
sudo usermod -aG audio ph4metrics

set -ex
cd "${SCRIPT_DIR}"
MDIR="/etc/ph4metrics"
mkdir -p "${MDIR}"

cp ph4metrics.sh "${MDIR}"
chmod 0755 "${MDIR}/ph4metrics.sh"

cp ph4_metrics/metrics.py /usr/local/bin/ph4-metrics
chmod 0755 "/usr/local/bin/ph4-metrics"
chown ph4metrics:ph4metrics "/usr/local/bin/ph4-metrics"

touch /var/log/ph4metrics.json
touch /var/log/ph4metrics.log
chown ph4metrics:ph4metrics /var/log/ph4metrics.json
chown ph4metrics:ph4metrics /var/log/ph4metrics.log

cp ph4metrics.service /etc/systemd/system/ph4metrics.service
systemctl daemon-reload

set +ex
echo "[+] DONE"

systemctl enable ph4metrics.service

# systemctl restart ph4metrics.service
# pip3.10 install -U . && systemctl restart ph4metrics.service
