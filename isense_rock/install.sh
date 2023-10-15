#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# may exist already
sudo groupadd ph4sense
sudo useradd -r -M -g ph4sense -s /usr/sbin/nologin -c "System User for ph4sense" ph4sense
sudo usermod -aG i2c ph4sense

set -ex
cd "${SCRIPT_DIR}"
MDIR="/etc/ph4sense"
mkdir -p "${MDIR}"

cp config.yaml "${MDIR}/config.yaml"
chmod 0640 "${MDIR}/config.yaml"
chown ph4sense:ph4sense "${MDIR}/config.yaml"

cp ph4sense.sh "${MDIR}"
chmod 0755 "${MDIR}/ph4sense.sh"

cp ph4sense.py /usr/local/bin/ph4-sensei-loc
chmod 0755 "/usr/local/bin/ph4-sensei-loc"
chown ph4sense:ph4sense "/usr/local/bin/ph4-sensei-loc"

touch /var/log/ph4sense.json
touch /var/log/ph4sense.log
chown ph4sense:ph4sense /var/log/ph4sense.json
chown ph4sense:ph4sense /var/log/ph4sense.log

cp ph4sense.service /etc/systemd/system/ph4sense.service
systemctl daemon-reload

set +ex
echo "[+] DONE"

systemctl enable ph4sense.service

# systemctl restart ph4sense.service
# pip install -U . && systemctl restart ph4sense.service
