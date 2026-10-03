#!/usr/bin/env bash
# One-command demo bootstrap.
#
#   ./scripts/demo.sh             # full boot: clean → backend → seed → frontend
#   ./scripts/demo.sh --no-seed   # skip sourcing-workflow seed
#   ./scripts/demo.sh --no-fe     # backend + seed only (skip frontend)
#   ./scripts/demo.sh --keep-state  # resume the last snapshot in .data/ (no reset, no seed)
#   ./scripts/demo.sh stop        # stop everything
#   ./scripts/demo.sh status      # show what's running
#   ./scripts/demo.sh logs        # tail all logs
#   ./scripts/demo.sh seed        # re-run sourcing seeder against live backend
#
# Outputs:
#   .logs/{backend,frontend,seed}.log     (gitignored)
#   .pids/{backend,frontend}.pid          (gitignored)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$ROOT/.logs"
PID_DIR="$ROOT/.pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"
VENV_PY="$ROOT/.venv/bin/python"

# Auto-source .env if present. Lets users set DEEPSEEK_API_KEY, etc.
# without exporting in every shell. Variables are auto-exported so child
# processes (uvicorn, next dev) see them.
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

# ---------------------------------------------------------------- helpers ----

c_grn() { printf "\033[32m%s\033[0m" "$1"; }
c_ylw() { printf "\033[33m%s\033[0m" "$1"; }
c_red() { printf "\033[31m%s\033[0m" "$1"; }
c_dim() { printf "\033[2m%s\033[0m" "$1"; }

step() { echo "$(c_grn '==>') $*"; }
warn() { echo "$(c_ylw 'WARN') $*" >&2; }
fail() { echo "$(c_red 'FAIL') $*" >&2; exit 1; }

# Kill a process and all of its descendants. `npm run dev` forks
# `next dev` → `next-server`; killing only the npm pid orphans the server,
# which keeps the port and serves a stale .next on the next boot.
kill_tree() {
  local pid=$1 sig=${2:-TERM} child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child" "$sig"
  done
  kill -"$sig" "$pid" 2>/dev/null || true
}

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "  killing existing process on :$port (pid $pids)"
    kill $pids 2>/dev/null || true
    sleep 1
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    [[ -n "$pids" ]] && kill -9 $pids 2>/dev/null || true
  fi
}

wait_for_url() {
  local url=$1
  local timeout=${2:-30}
  local i=0
  while ! curl -sf -o /dev/null --max-time 2 "$url"; do
    i=$((i+1))
    if [[ $i -gt $timeout ]]; then
      return 1
    fi
    sleep 1
  done
  return 0
}

# ---------------------------------------------------------------- actions ----

cleanup() {
  step "cleaning up stale processes"
  stop_pid backend
  stop_pid frontend
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
}

reset_state() {
  # The backend restores its last snapshot from .data/ on boot. Seeding on top
  # of a restored snapshot duplicates every PR/RFQ/PO, so a full boot starts
  # from a clean slate.
  if [[ -d "$ROOT/.data" ]]; then
    step "resetting demo state (.data/)"
    rm -rf "$ROOT/.data"
  fi
}

# A stale server left on the port would answer our readiness check while the
# fresh one dies with EADDRINUSE, so refuse to start over it.
ensure_port_free() {
  local port=$1
  if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/"; then
    fail "port $port is still held by an old process — stop it (e.g. pkill -f next-server / serve_with_hydro) and retry"
  fi
}

start_backend() {
  step "starting backend on :$BACKEND_PORT"
  ensure_port_free "$BACKEND_PORT"
  [[ -x "$VENV_PY" ]] || fail "venv python not found at $VENV_PY — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  (
    cd "$ROOT"
    BACKEND_PORT="$BACKEND_PORT" nohup "$VENV_PY" -m fixtures.hydro.serve_with_hydro \
      > "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$PID_DIR/backend.pid"
  )
  if ! wait_for_url "http://127.0.0.1:$BACKEND_PORT/api/health" 30; then
    warn "backend failed to come up — last 20 lines of log:"
    tail -20 "$LOG_DIR/backend.log" >&2 || true
    fail "backend startup timed out"
  fi
  echo "  backend ready (pid $(cat "$PID_DIR/backend.pid"))"
}

seed_sourcing() {
  step "seeding sourcing workflow (PRs → RFQs → Quotes → Awards → POs)"
  (
    cd "$ROOT"
    SEED_API_BASE="http://127.0.0.1:$BACKEND_PORT" \
      "$VENV_PY" -m fixtures.seed_sourcing > "$LOG_DIR/seed.log" 2>&1
  )
  sed -n '/=== final tally/,$p' "$LOG_DIR/seed.log" | sed 's/^/  /'
}

start_frontend() {
  step "starting frontend on :$FRONTEND_PORT"
  ensure_port_free "$FRONTEND_PORT"
  [[ -d "$ROOT/frontend/node_modules" ]] || (
    step "installing frontend dependencies (first run)"
    cd "$ROOT/frontend" && npm install
  )
  (
    cd "$ROOT/frontend"
    NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-http://127.0.0.1:$BACKEND_PORT}" \
      nohup npm run dev -- -p "$FRONTEND_PORT" \
      > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"
  )
  if ! wait_for_url "http://127.0.0.1:$FRONTEND_PORT/" 60; then
    warn "frontend failed to come up — last 20 lines of log:"
    tail -20 "$LOG_DIR/frontend.log" >&2 || true
    fail "frontend startup timed out"
  fi
  echo "  frontend ready (pid $(cat "$PID_DIR/frontend.pid"))"
}

print_status() {
  local back="$(c_red 'down')"
  local front="$(c_red 'down')"
  curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$BACKEND_PORT/api/health" && back="$(c_grn 'up')"
  curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$FRONTEND_PORT/" && front="$(c_grn 'up')"
  echo "$(c_grn '==>') demo status"
  echo "  backend  $back   http://127.0.0.1:$BACKEND_PORT/api/health"
  echo "  frontend $front  http://127.0.0.1:$FRONTEND_PORT/"
  if [[ -f "$PID_DIR/backend.pid" ]]; then
    echo "$(c_dim "  backend pid : $(cat "$PID_DIR/backend.pid")")"
  fi
  if [[ -f "$PID_DIR/frontend.pid" ]]; then
    echo "$(c_dim "  frontend pid: $(cat "$PID_DIR/frontend.pid")")"
  fi
  echo
  echo "$(c_dim "  logs : $LOG_DIR/backend.log, frontend.log, seed.log")"
  echo "$(c_dim "  stop : ./scripts/demo.sh stop")"
}

stop_pid() {
  local name=$1
  local pidfile="$PID_DIR/$name.pid"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      echo "  stopping $name (pid $pid)"
      kill_tree "$pid"
      sleep 1
      kill -0 "$pid" 2>/dev/null && kill_tree "$pid" KILL
    fi
    rm -f "$pidfile"
  fi
}

stop_all() {
  step "stopping demo"
  stop_pid backend
  stop_pid frontend
  # belt + braces — kill any straggler that lost its pid file
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
  echo "  done"
}

# ---------------------------------------------------------------- dispatch ----

CMD=""
NO_SEED=0
NO_FE=0
KEEP_STATE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    stop|status|logs|seed) CMD="$1" ;;
    --no-seed)             NO_SEED=1 ;;
    --no-fe|--no-frontend) NO_FE=1 ;;
    --keep-state)          KEEP_STATE=1; NO_SEED=1 ;;
    -h|--help)
      sed -n '2,18p' "$0" | sed 's/^# //; s/^#//'
      exit 0
      ;;
    *) fail "unknown arg: $1" ;;
  esac
  shift
done

case "$CMD" in
  stop)   stop_all ;;
  status) print_status ;;
  logs)   exec tail -F "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log" "$LOG_DIR/seed.log" 2>/dev/null ;;
  seed)   seed_sourcing ;;
  "")
    cleanup
    [[ "$KEEP_STATE" -eq 0 ]] && reset_state
    start_backend
    [[ "$NO_SEED" -eq 0 ]] && seed_sourcing
    [[ "$NO_FE"   -eq 0 ]] && start_frontend
    print_status
    ;;
esac
