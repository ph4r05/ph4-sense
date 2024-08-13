#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# may exist already
sudo groupadd ph4bark
sudo useradd -r -M -g ph4bark -s /usr/sbin/nologin -c "System User for ph4bark" ph4bark
sudo usermod -aG i2c ph4bark
sudo usermod -aG dialout ph4bark
sudo usermod -aG audio ph4bark

set -ex
cd "${SCRIPT_DIR}"
MDIR="/etc/ph4bark"
mkdir -p "${MDIR}"

cp ph4bark.sh "${MDIR}"
chmod 0755 "${MDIR}/ph4bark.sh"

cp ph4_bark/bark.py /usr/local/bin/ph4-bark
chmod 0755 "/usr/local/bin/ph4-bark"
chown ph4bark:ph4bark "/usr/local/bin/ph4-bark"

touch /var/log/ph4bark.json
touch /var/log/ph4bark.log
chown ph4bark:ph4bark /var/log/ph4bark.json
chown ph4bark:ph4bark /var/log/ph4bark.log

cp ph4bark.service /etc/systemd/system/ph4bark.service
systemctl daemon-reload

set +ex
echo "[+] DONE"

systemctl enable ph4bark.service

# systemctl restart ph4bark.service
# pip3.10 install -U . && systemctl restart ph4bark.service