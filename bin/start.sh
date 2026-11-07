#!/usr/bin/env bash
# Start the NLQ app in Docker (detached).
# Portable across Linux, macOS, and Windows (Git Bash / WSL).
#
# Usage:
#   ./bin/start.sh           # run image (build if missing)
#   ./bin/start.sh --build   # rebuild image, then run
#   ./bin/start.sh --fg      # run in the foreground (Ctrl+C stops)
#
# Env overrides: NLQ_IMAGE (default nlq), NLQ_CONTAINER (default nlq),
# NLQ_PORT (default 8000).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

IMAGE="${NLQ_IMAGE:-nlq}"
NAME="${NLQ_CONTAINER:-nlq}"
PORT="${NLQ_PORT:-8000}"
DO_BUILD=0
FOREGROUND=0

log()  { printf '%s\n' "$*"; }
err()  { printf 'error: %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --build) DO_BUILD=1 ;;
    --fg|--foreground) FOREGROUND=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      die "Unknown option: ${arg} (try --help)"
      ;;
  esac
done

command -v docker >/dev/null 2>&1 || die "'docker' is required but not found in PATH"
docker info >/dev/null 2>&1 || die "Cannot connect to the Docker daemon. Start Docker and retry."

[[ -f "${REPO_ROOT}/.env" ]] || die "Missing .env — copy env.template to .env and fill in the LLM settings"

if (( DO_BUILD )) || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  log "==> Building image ${IMAGE}"
  docker build -t "$IMAGE" .
fi

if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  log "NLQ already running as container '${NAME}' on port ${PORT}."
  log "Open http://127.0.0.1:${PORT}  ·  Stop: ./bin/stop.sh"
  exit 0
fi

# Drop a stopped leftover so --name stays unique.
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  log "==> Removing stopped container ${NAME}"
  docker rm "$NAME" >/dev/null
fi

# Persist imports on the host. Seed duckdb from the image on first run.
mkdir -p "${REPO_ROOT}/data/duckdb" "${REPO_ROOT}/hints"
if [[ ! -f "${REPO_ROOT}/data/duckdb/ecommerce.duckdb" ]]; then
  log "==> Seeding data/duckdb from image ${IMAGE}"
  seed_id="$(docker create "$IMAGE")"
  docker cp "${seed_id}:/app/data/duckdb/." "${REPO_ROOT}/data/duckdb/"
  docker rm "$seed_id" >/dev/null
fi
[[ -f "${REPO_ROOT}/data/datasets.json" ]] || echo '{}' > "${REPO_ROOT}/data/datasets.json"

log "==> Starting NLQ (${IMAGE}) on port ${PORT}"

RUN_ARGS=(
  run
  --name "$NAME"
  -p "127.0.0.1:${PORT}:8000"
  --env-file "${REPO_ROOT}/.env"
  --add-host=host.docker.internal:host-gateway
  -v nlq-history:/app/data/sqlite
  -v "${REPO_ROOT}/data/duckdb:/app/data/duckdb"
  -v "${REPO_ROOT}/data/datasets.json:/app/data/datasets.json"
  -v "${REPO_ROOT}/hints:/app/hints"
  -v "${REPO_ROOT}/recommendations:/app/recommendations"
  -v "${REPO_ROOT}/static:/app/static"
)

if (( FOREGROUND )); then
  RUN_ARGS+=(--rm)
  docker "${RUN_ARGS[@]}" "$IMAGE"
else
  RUN_ARGS+=(-d --restart unless-stopped)
  docker "${RUN_ARGS[@]}" "$IMAGE" >/dev/null
  log "Container ${NAME} is up."
  log "Open http://127.0.0.1:${PORT}"
  log "Logs:  docker logs -f ${NAME}"
  log "Stop:  ./bin/stop.sh"
fi
