#!/bin/zsh

python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

# install deps into a folder that you'll zip and upload
pip install -r requirements.txt -t src/

cp -r haaska/*.py haaska/*.json src/

cd src/ && zip -r ../function.zip .
