#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop is required. Install/open Docker Desktop, then run this file again."
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  open -a Docker 2>/dev/null || true
  echo "Docker Desktop is starting. Wait until it reports Running, then run this file again."
  exit 1
fi
if [ ! -f .env.iot ]; then
  umask 077
  POSTGRES_VALUE="$(openssl rand -hex 24)"
  SECRET_VALUE="$(openssl rand -hex 48)"
  ENCRYPTION_VALUE="$(openssl rand -base64 32 | tr '+/' '-_')"
  sed -e "s/generate-a-random-local-password/$POSTGRES_VALUE/" -e "s/generate-a-long-random-value/$SECRET_VALUE/" -e "s/generate-a-fernet-key/$ENCRYPTION_VALUE/" .env.iot.example > .env.iot
fi
./scripts/generate_iot_dev_certs.sh
docker compose --env-file .env.iot up -d --build db redis mqtt mailpit backend frontend
READY=0
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then READY=1; break; fi
  sleep 2
done
if [ "$READY" -ne 1 ]; then
  echo "GeoVision backend did not become healthy within 120 seconds."
  docker compose --env-file .env.iot logs --tail=100 backend
  exit 1
fi
docker compose --env-file .env.iot exec -T backend python scripts/seed_iot_demo.py
docker compose --env-file .env.iot --profile simulator up -d --build simulator
docker compose --env-file .env.iot exec -T backend sh -c 'cat /runtime/demo-login.txt'
open http://127.0.0.1:8001/login.html
echo "GeoVision IoT is running. Dashboard: http://127.0.0.1:8001  Mailpit: http://127.0.0.1:8025"
