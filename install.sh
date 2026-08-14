#!/bin/bash
set -e
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements-plugins.txt
./.venv/bin/pip install -r requirements.txt
echo "Готово. Запуск: ./run.sh"
