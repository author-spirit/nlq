#!/usr/bin/env bash
# Stop the NLQ Docker container started by ./bin/start.sh.
# Portable across Linux, macOS, and Windows (Git Bash / WSL).
#
# Usage:
#   ./bin/stop.sh           # stop and remove the container (volume kept)
#   ./bin/stop.sh --keep    # stop only; leave the container for docker start
#
# Env overrides: NLQ_CONTAINER (default nlq).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

NAME="${NLQ_CONTAINER:-nlq}"
KEEP=0

log()  { printf '%s\n' "$*"; }
err()  { printf 'error: %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --keep) KEEP=1 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      die "Unknown option: ${arg} (try --help)"
      ;;
  esac
done

command -v docker >/dev/null 2>&1 || die "'docker' is required but not found in PATH"
docker info >/dev/null 2>&1 || die "Cannot connect to the Docker daemon. Start Docker and retry."

if ! docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  log "No container named '${NAME}' — nothing to stop."
  exit 0
fi

if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  log "==> Stopping ${NAME}"
  docker stop "$NAME" >/dev/null
else
  log "Container '${NAME}' is already stopped."
fi

if (( KEEP )); then
  log "Container kept. Restart with: docker start ${NAME}  (or ./bin/start.sh)"
else
  log "==> Removing ${NAME}"
  docker rm "$NAME" >/dev/null
  log "Stopped. History volume 'nlq-history' is kept. Start again with ./bin/start.sh"
fi
