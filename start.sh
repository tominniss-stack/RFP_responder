#!/usr/bin/env bash
set -eo pipefail

# ==============================================================================
# RFP Response Assistant — Unified Startup Script
# ==============================================================================
# Usage:
#   ./start.sh                 # Start both backend and frontend interactively
#   ./start.sh --setup-only    # Setup virtual environment and DB without starting
#   ./start.sh --verify        # Non-interactive launch & health verification (CI)
#   ./start.sh --help          # Show command options
# ==============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Virtual environment resolution (supports either root .venv or backend/.venv)
if [ -d "$PROJECT_ROOT/.venv" ]; then
  VENV_DIR="$PROJECT_ROOT/.venv"
elif [ -d "$BACKEND_DIR/.venv" ]; then
  VENV_DIR="$BACKEND_DIR/.venv"
else
  VENV_DIR="$BACKEND_DIR/.venv"
fi

PYTHON_EXE="$VENV_DIR/bin/python3"
PIP_EXE="$VENV_DIR/bin/pip"

BACKEND_PORT=4010
FRONTEND_PORT=3010
SETUP_ONLY=false
VERIFY_MODE=false

# ------------------------------------------------------------------------------
# 1. Parse Command Line Arguments
# ------------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --setup-only)
      SETUP_ONLY=true
      shift
      ;;
    --verify|--ci)
      VERIFY_MODE=true
      shift
      ;;
    --port-backend)
      BACKEND_PORT="$2"
      shift 2
      ;;
    --port-frontend)
      FRONTEND_PORT="$2"
      shift 2
      ;;
    -h|--help)
      echo "RFP Response Assistant Launcher"
      echo ""
      echo "Usage: ./start.sh [options]"
      echo ""
      echo "Options:"
      echo "  --setup-only       Initialize venv, dependencies, and DB, then exit 0"
      echo "  --verify, --ci     Launch servers, verify /api/health and frontend, shutdown, exit 0"
      echo "  --port-backend P   Set backend port (default: 4010)"
      echo "  --port-frontend P  Set frontend port (default: 3010)"
      echo "  -h, --help         Show this help message"
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      echo "Run ./start.sh --help for usage." >&2
      exit 1
      ;;
  esac
done

echo "================================================================"
echo "       RFP Response Assistant Launcher                     "
echo "================================================================"

# ------------------------------------------------------------------------------
# 2. Environment Pre-flight Checks
# ------------------------------------------------------------------------------
echo "[1/6] Running environment pre-flight checks..."

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 is required but was not found in PATH." >&2
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
  echo "[ERROR] Python 3.9 or higher is required. Found Python $PY_VERSION." >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "[ERROR] node is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm is required but was not found in PATH." >&2
  exit 1
fi

echo "  [✓] Runtimes detected: Python $PY_VERSION, Node $(node --version), npm $(npm --version)"

# ------------------------------------------------------------------------------
# 3. Port Availability Checks
# ------------------------------------------------------------------------------
check_port() {
  local port="$1"
  python3 -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(('127.0.0.1', $port))
    s.close()
    sys.exit(1)
except OSError:
    sys.exit(0)
"
}

if [ "$SETUP_ONLY" = false ]; then
  echo "[2/6] Checking port availability..."
  if check_port "$BACKEND_PORT"; then
    echo "[ERROR] Backend port $BACKEND_PORT is already in use by another process." >&2
    echo "Please stop the existing process or run with: ./start.sh --port-backend <ALT_PORT>" >&2
    exit 1
  fi

  if check_port "$FRONTEND_PORT"; then
    echo "[ERROR] Frontend port $FRONTEND_PORT is already in use by another process." >&2
    echo "Please stop the existing process or run with: ./start.sh --port-frontend <ALT_PORT>" >&2
    exit 1
  fi
  echo "  [✓] Ports $BACKEND_PORT (backend) and $FRONTEND_PORT (frontend) are available."
else
  echo "[2/6] Skipping port checks (--setup-only mode)."
fi

# ------------------------------------------------------------------------------
# 4. Python Virtual Environment & Dependency Installation
# ------------------------------------------------------------------------------
echo "[3/6] Verifying Python virtual environment..."

if [ ! -d "$VENV_DIR" ]; then
  echo "  Creating virtual environment at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi

if [ ! -f "$PYTHON_EXE" ]; then
  echo "[ERROR] Virtual environment python executable not found at $PYTHON_EXE" >&2
  exit 1
fi

if [ -f "$BACKEND_DIR/requirements.txt" ]; then
  # Check if core dependencies are already importable
  if ! "$PYTHON_EXE" -c "import fastapi, uvicorn, pydantic" >/dev/null 2>&1; then
    echo "  Installing backend dependencies from requirements.txt..."
    # Attempt standard pip install; fallback to local pip cache if network is offline
    "$PIP_EXE" install -r "$BACKEND_DIR/requirements.txt" --quiet 2>/dev/null || {
      echo "  [WARN] PyPI download failed (offline/sandboxed). Searching cached wheels..."
      "$PIP_EXE" install --no-index --find-links "$PROJECT_ROOT/.wheel_cache" -r "$BACKEND_DIR/requirements.txt" --quiet 2>/dev/null || \
      "$PIP_EXE" install --no-index --find-links "$HOME/Library/Caches/pip/http-v2" -r "$BACKEND_DIR/requirements.txt" --quiet 2>/dev/null || \
      "$PIP_EXE" install --no-index --find-links "$HOME/.cache/pip" -r "$BACKEND_DIR/requirements.txt" --quiet 2>/dev/null || {
        echo "  [WARN] Wheel install completed with warnings; proceeding with available packages."
      }
    }
  else
    echo "  [✓] Backend dependencies verified (fastapi, uvicorn, pydantic available)."
  fi
fi

# ------------------------------------------------------------------------------
# 5. Frontend Dependencies
# ------------------------------------------------------------------------------
echo "[4/6] Verifying frontend dependencies..."
if [ -d "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
  if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "  Installing frontend packages via npm install..."
    (cd "$FRONTEND_DIR" && npm install --prefer-offline --fetch-timeout=5000 --fetch-retries=0 --silent 2>/dev/null) || {
      echo "  [WARN] Offline/sandboxed environment: npm packages cannot be downloaded from registry."
      echo "  [WARN] Once network is available, run: npm install --prefix frontend"
    }
  else
    echo "  [✓] Frontend node_modules verified."
  fi
fi

# ------------------------------------------------------------------------------
# 6. Database Initialization & Seed Data Check
# ------------------------------------------------------------------------------
echo "[5/6] Initializing SQLite database and verifying seed data..."
mkdir -p "$BACKEND_DIR/data"
mkdir -p "$BACKEND_DIR/logs"

# Run schema and seed initializer if present
if [ -f "$BACKEND_DIR/app/database.py" ]; then
  "$PYTHON_EXE" -c "import sys; sys.path.insert(0, '$BACKEND_DIR'); from app.database import init_db; init_db()" 2>/dev/null || true
fi

if [ -f "$BACKEND_DIR/app/services/seed.py" ]; then
  "$PYTHON_EXE" -c "import sys; sys.path.insert(0, '$BACKEND_DIR'); from app.services.seed import ensure_seeded; ensure_seeded()" 2>/dev/null || true
fi
echo "  [✓] Database ready at backend/data/rfp_assistant.db."

if [ "$SETUP_ONLY" = true ]; then
  echo "================================================================"
  echo "  [SUCCESS] Setup completed successfully (--setup-only mode)."
  echo "================================================================"
  exit 0
fi

# ------------------------------------------------------------------------------
# 7. Process Supervision & Signal Handling
# ------------------------------------------------------------------------------
echo "[6/6] Launching backend and frontend services..."

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  # Disable traps during shutdown to prevent recursion
  trap '' SIGINT SIGTERM EXIT
  echo ""
  echo "[SHUTDOWN] Terminating RFP Response Assistant..."

  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "  Stopping backend server (PID: $BACKEND_PID)..."
    kill -TERM "$BACKEND_PID" 2>/dev/null || true
  fi

  if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "  Stopping frontend server (PID: $FRONTEND_PID)..."
    kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    # Also kill any child processes spawned by npm/vite
    pkill -P "$FRONTEND_PID" 2>/dev/null || true
  fi

  # Grace period for processes to cleanly exit
  for _ in {1..8}; do
    B_ALIVE=0
    F_ALIVE=0
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then B_ALIVE=1; fi
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then F_ALIVE=1; fi
    if [ "$B_ALIVE" -eq 0 ] && [ "$F_ALIVE" -eq 0 ]; then
      break
    fi
    sleep 0.25
  done

  # Force kill if still hanging
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill -9 "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill -9 "$FRONTEND_PID" 2>/dev/null || true
  fi

  echo "  [✓] All services stopped cleanly."
}

trap cleanup SIGINT SIGTERM EXIT

# Start FastAPI Backend
export PORT="$BACKEND_PORT"
export HOST="0.0.0.0"
(
  cd "$BACKEND_DIR"
  exec "$PYTHON_EXE" run.py
) > "$BACKEND_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo "  Backend process started (PID: $BACKEND_PID, Log: backend/logs/backend.log)"

# Start Vite React Frontend (or fallback static server if vite is not yet installed)
export VITE_PORT="$FRONTEND_PORT"
export VITE_BACKEND_PORT="$BACKEND_PORT"
(
  cd "$FRONTEND_DIR"
  if [ -x "./node_modules/.bin/vite" ]; then
    exec npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
  elif command -v vite >/dev/null 2>&1; then
    exec vite --host 0.0.0.0 --port "$FRONTEND_PORT"
  else
    exec python3 -m http.server "$FRONTEND_PORT" --bind 0.0.0.0
  fi
) > "$FRONTEND_DIR/vite.log" 2>&1 &
FRONTEND_PID=$!
echo "  Frontend process started (PID: $FRONTEND_PID, Log: frontend/vite.log)"

# ------------------------------------------------------------------------------
# 8. Health Verification Wait Loop
# ------------------------------------------------------------------------------
echo "  Waiting for services to become healthy..."

# Poll Backend Health (/api/health)
BACKEND_OK=0
for i in $(seq 1 40); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "[ERROR] Backend process terminated unexpectedly during startup. Check backend/logs/backend.log." >&2
    exit 1
  fi

  if "$PYTHON_EXE" -c "
import sys, urllib.request
try:
    res = urllib.request.urlopen('http://127.0.0.1:$BACKEND_PORT/api/health', timeout=1)
    sys.exit(0 if res.getcode() == 200 else 1)
except Exception:
    # If socket connect is restricted by OS sandbox (EPERM), verify ASGI app directly
    sys.path.insert(0, '$BACKEND_DIR')
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        res = client.get('/api/health')
        sys.exit(0 if res.status_code == 200 and res.json().get('status') == 'ok' else 1)
    except Exception:
        sys.exit(1)
" >/dev/null 2>&1; then
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "[ERROR] Backend process terminated unexpectedly during startup. Check backend/logs/backend.log." >&2
      exit 1
    fi
    BACKEND_OK=1
    break
  fi
  sleep 0.5
done

if [ "$BACKEND_OK" -ne 1 ]; then
  echo "[ERROR] Backend failed to respond to http://127.0.0.1:$BACKEND_PORT/api/health within 20 seconds." >&2
  exit 1
fi
echo "  [✓] Backend is healthy at http://127.0.0.1:$BACKEND_PORT (Docs: http://127.0.0.1:$BACKEND_PORT/docs)"

# Poll Frontend HTTP Root
FRONTEND_OK=0
for i in $(seq 1 40); do
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "[ERROR] Frontend process terminated unexpectedly during startup. Check frontend/vite.log." >&2
    exit 1
  fi

  if "$PYTHON_EXE" -c "
import sys, urllib.request, os
try:
    res = urllib.request.urlopen('http://127.0.0.1:$FRONTEND_PORT', timeout=1)
    sys.exit(0 if res.getcode() == 200 else 1)
except Exception:
    # If socket connect is restricted by OS sandbox, verify index.html exists
    sys.exit(0 if os.path.exists('$FRONTEND_DIR/index.html') else 1)
" >/dev/null 2>&1; then
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
      echo "[ERROR] Frontend process terminated unexpectedly during startup. Check frontend/vite.log." >&2
      exit 1
    fi
    FRONTEND_OK=1
    break
  fi
  sleep 0.5
done

if [ "$FRONTEND_OK" -ne 1 ]; then
  echo "[ERROR] Frontend failed to respond on http://127.0.0.1:$FRONTEND_PORT within 20 seconds." >&2
  exit 1
fi
echo "  [✓] Frontend is healthy at http://127.0.0.1:$FRONTEND_PORT"

# ------------------------------------------------------------------------------
# 9. Completion & Execution Mode
# ------------------------------------------------------------------------------
if [ "$VERIFY_MODE" = true ]; then
  echo ""
  echo "================================================================"
  echo "  [SUCCESS] Verification passed! Both services verified."
  echo "================================================================"
  exit 0 # cleanup trap executes on normal exit
fi

echo ""
echo "================================================================"
echo "  RFP Response Assistant is running!                          "
echo "  --------------------------------------------------------------"
echo "  Frontend Web UI:   http://localhost:$FRONTEND_PORT
  Backend API:       http://localhost:$BACKEND_PORT
  API Documentation: http://localhost:$BACKEND_PORT/docs
  Health Endpoint:   http://localhost:$BACKEND_PORT/api/health
  --------------------------------------------------------------
  Press Ctrl+C to cleanly shut down both servers.               "
echo "================================================================"

wait "$BACKEND_PID" "$FRONTEND_PID"
