#!/usr/bin/env bash
# QuantatraderAI — redeploy script
# Run this every time you push changes: qai-deploy
set -euo pipefail

APP_DIR="/opt/quantatraderai"
cd "$APP_DIR"

echo "==> Pulling latest code"
git pull origin main

echo "==> Building Docker image"
docker compose build --no-cache

echo "==> Running DB migrations (run manually: cd ui && npx prisma migrate deploy)"
echo "==> Restarting container"
docker compose up -d --remove-orphans

echo "==> Waiting for health check"
sleep 25
docker compose ps

echo "==> Done — API status:"
curl -sf http://localhost:8000/api/status | python3 -m json.tool || echo "(not ready yet — wait 10s and retry)"
