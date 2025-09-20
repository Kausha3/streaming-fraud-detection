#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker &>/dev/null; then
  echo "docker not found in PATH" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/4] Starting core infrastructure..."
docker compose up -d zookeeper kafka redis postgres

echo "[2/4] Building and starting stream processor + API..."
docker compose up --build -d stream-processor api

echo "[3/4] Starting frontend dashboard..."
docker compose up --build -d frontend

echo "[4/4] Launching synthetic transaction generator (Ctrl+C to stop)..."
python3 src/generator/transaction_generator.py --broker localhost:9092 --topic transactions --tps 200
