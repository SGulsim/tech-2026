#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "▶ Bringing up Postgres + Redis…"
docker compose up -d

echo "▶ Waiting for services to be healthy…"
for svc in cache-postgres cache-redis; do
  for i in $(seq 1 30); do
    state=$(docker inspect -f '{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "starting")
    if [ "$state" = "healthy" ]; then
      echo "  $svc: healthy"
      break
    fi
    sleep 1
  done
done

echo "▶ Installing npm dependencies (if needed)…"
if [ ! -d node_modules ]; then
  npm install --silent
fi

echo "▶ Running benchmark (3 strategies × 3 scenarios)…"
npm run --silent benchmark | tee results/benchmark.log

echo
echo "▶ Running write-back buffer accumulation demo…"
npm run --silent writeback-demo | tee results/writeback-demo.log

echo
echo "✓ Done. Logs and JSON results are in results/"
