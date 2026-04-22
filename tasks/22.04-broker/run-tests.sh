#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Colors ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ─── Argument ────────────────────────────────────────────────────────────────
# Usage: ./run-tests.sh [all|basic|size|rate]
EXPERIMENT="${1:-all}"

# ─── Pre-flight ──────────────────────────────────────────────────────────────
command -v docker   >/dev/null 2>&1 || error "docker not found"
command -v docker-compose >/dev/null 2>&1 || COMPOSE_CMD="docker compose"
COMPOSE_CMD="${COMPOSE_CMD:-docker-compose}"

# ─── Start brokers ───────────────────────────────────────────────────────────
info "Starting brokers..."
$COMPOSE_CMD up -d

info "Waiting for RabbitMQ to be healthy..."
for i in $(seq 1 30); do
  if $COMPOSE_CMD exec -T rabbitmq rabbitmq-diagnostics ping >/dev/null 2>&1; then
    info "RabbitMQ is ready"
    break
  fi
  sleep 2
  if [ "$i" -eq 30 ]; then error "RabbitMQ did not start in time"; fi
done

info "Waiting for Redis to be healthy..."
for i in $(seq 1 15); do
  if $COMPOSE_CMD exec -T redis redis-cli ping >/dev/null 2>&1; then
    info "Redis is ready"
    break
  fi
  sleep 1
  if [ "$i" -eq 15 ]; then error "Redis did not start in time"; fi
done

# ─── Install deps ────────────────────────────────────────────────────────────
if [ ! -d "node_modules" ]; then
  info "Installing dependencies..."
  npm install
else
  info "node_modules already present, skipping install"
fi

mkdir -p results

# ─── Run benchmark ───────────────────────────────────────────────────────────
info "Running experiment: $EXPERIMENT"
echo ""

npx ts-node src/benchmark.ts "$EXPERIMENT"

echo ""
info "All done! Results are in ./results/"
info "Docker containers are still running. To stop them: $COMPOSE_CMD down"
