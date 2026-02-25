#!/bin/bash
set -e

echo ">>> Pulling latest code"
git pull origin main

echo ">>> Building images"
docker compose -f docker-compose.prod.yml build

echo ">>> Running migrations"
docker compose -f docker-compose.prod.yml run --rm app \
  alembic upgrade head

echo ">>> Restarting services"
docker compose -f docker-compose.prod.yml up -d

echo ">>> Invalidating cache"
curl -s -X POST http://localhost:8000/admin/cache/invalidate \
  -H "X-Admin-Token: ${ADMIN_TOKEN}"

echo ">>> Done"
