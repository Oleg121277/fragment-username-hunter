#!/usr/bin/env bash
# Запуск Germes в *nix-окружении (git-bash / WSL).
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/python -m germes "$@"
