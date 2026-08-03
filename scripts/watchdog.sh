#!/bin/bash
# AlphaCore watchdog — restarts services if they died OR hung
# Runs every minute via crontab

PROJECT_DIR="/home/moeen/projects/AlphaCore"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
API_LOG="$PROJECT_DIR/logs/api.log"
SCHED_LOG="$PROJECT_DIR/logs/scheduler.log"
REAL_LOG="$PROJECT_DIR/logs/real_daemon.log"
NGROK_LOG="$PROJECT_DIR/logs/ngrok.log"
HEARTBEAT_FILE="$PROJECT_DIR/data_cache/.trade_heartbeat.json"

# Max age of heartbeat / cycle running before we treat trade process as hung
# (must stay in sync with src/utils/heartbeat.py: HEARTBEAT_MAX_AGE_S, CYCLE_MAX_DURATION_S)
HB_MAX_AGE=900
CYCLE_MAX_RUN=600

# Helper: print the PID that owns the (fresh) heartbeat file, or 0 if
# the heartbeat is missing/unreadable/stale. A healthy, actively
# heartbeating process is authoritative and must never be killed in
# favour of an older zombie/defunct process.
heartbeat_owner_pid() {
    "$VENV_PYTHON" - "$HEARTBEAT_FILE" "$HB_MAX_AGE" <<'PYEOF'
import json, os, sys
path, hb_max_age = sys.argv[1], int(sys.argv[2])
try:
    with open(path) as fh:
        data = json.load(fh)
except Exception:
    sys.exit(0)
now = __import__("time").time()
age = now - float(data.get("last_activity", 0))
if age > hb_max_age:
    sys.exit(0)
pid = data.get("pid", 0)
if isinstance(pid, int) and pid > 0:
    print(pid)
PYEOF
}

# Helper: 0 (alive) if the PID exists in the process table AND is not a
# zombie/defunct process (state Z in /proc/<pid>/stat). A dead-but-
# unreaped zombie still "exists" for pgrep/kill purposes, so state must
# be checked explicitly.
pid_is_zombie() {
    local pid="$1"
    [ -r "/proc/$pid/stat" ] || return 1
    # state is the char right after the closing paren of the comm field
    local state
    state=$(sed -n 's/^.*) \([A-Z]\).*$/\1/p' "/proc/$pid/stat" 2>/dev/null)
    [ "$state" = "Z" ]
}

# Helper: kill all but the healthiest instance of a process pattern.
# Uses the heartbeat file to identify the authoritative process for the
# trade scheduler; for other patterns (no heartbeat) it keeps the oldest
# non-zombie PID. A zombie/defunct process is NEVER preferred over a
# healthy one, regardless of PID age.
kill_extras() {
    local pattern="$1"
    local use_heartbeat="${2:-0}"
    local pids
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    local count
    count=$(printf '%s\n' "$pids" | grep -c . 2>/dev/null)
    count=${count:-0}
    if [ "$count" -gt 1 ]; then
        local keep=""
        # 1) The actively-heartbeating process is authoritative (never a zombie).
        if [ "$use_heartbeat" = "1" ] && [ -f "$HEARTBEAT_FILE" ]; then
            local hb_pid
            hb_pid=$(heartbeat_owner_pid)
            if [ -n "$hb_pid" ] \
                && echo "$pids" | grep -qx "$hb_pid" \
                && ! pid_is_zombie "$hb_pid"; then
                keep="$hb_pid"
            fi
        fi
        # 2) Otherwise keep the oldest NON-zombie instance (never a zombie).
        if [ -z "$keep" ]; then
            for pid in $pids; do
                if ! pid_is_zombie "$pid"; then
                    keep="$pid"
                    break
                fi
            done
        fi
        # 3) Only if EVERY instance is a zombie do we keep one (to avoid
        #    killing everything); the zombie will be reaped and restarted.
        if [ -z "$keep" ]; then
            keep=$(echo "$pids" | head -1)
        fi
        local extras=""
        for pid in $pids; do
            if [ "$pid" != "$keep" ]; then
                extras="$extras $pid"
            fi
        done
        echo "$(date '+%Y-%m-%d %H:%M:%S') WARNING: $count instances of '$pattern' running — keeping PID $keep, killing: $extras"
        for pid in $extras; do
            kill "$pid" 2>/dev/null || true
        done
    fi
}

# Kill extras for each service type (trade uses the heartbeat to decide
# which instance is authoritative; real-account daemon has no heartbeat).
kill_extras "main.py --mode trade" 1
kill_extras "main_real.py" 0

# Helper: detect a hung (frozen but alive) trade process via heartbeat.
# Returns 0 (hung) if:
#   - heartbeat file exists and last_activity is older than HB_MAX_AGE, OR
#   - cycle_state=running and it started more than CYCLE_MAX_RUN ago.
# A missing heartbeat file is NOT treated as hung (process may be mid-start).
trade_is_hung() {
    [ -f "$HEARTBEAT_FILE" ] || return 1
    "$VENV_PYTHON" - "$HEARTBEAT_FILE" "$HB_MAX_AGE" "$CYCLE_MAX_RUN" <<'PYEOF'
import json, os, sys
path, hb_max_age, cycle_max_run = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
try:
    with open(path) as fh:
        data = json.load(fh)
except Exception:
    sys.exit(1)
now = __import__("time").time()
age = now - float(data.get("last_activity", 0))
if age > hb_max_age:
    print(f"HUNG: heartbeat stale {int(age)}s (> {hb_max_age}s)", file=sys.stderr)
    sys.exit(0)
if data.get("cycle_state") == "running":
    cycle_age = now - float(data.get("cycle_started", 0))
    if cycle_age > cycle_max_run:
        print(f"HUNG: cycle running {int(cycle_age)}s (> {cycle_max_run}s)", file=sys.stderr)
        sys.exit(0)
sys.exit(1)
PYEOF
}

# Check API
if ! pgrep -f "main.py --mode api" > /dev/null 2>&1; then
    cd "$PROJECT_DIR"
    setsid "$VENV_PYTHON" main.py --mode api >> "$API_LOG" 2>&1 &
    sleep 5
fi

# Check scheduler (only start if API is running)
if pgrep -f "main.py --mode api" > /dev/null 2>&1 && ! pgrep -f "main.py --mode trade" > /dev/null 2>&1; then
    cd "$PROJECT_DIR"
    setsid "$VENV_PYTHON" main.py --mode trade >> "$SCHED_LOG" 2>&1 &
    echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: trade process was dead — restarted"
else
    # Trade process is alive — check whether it is hung (frozen but running)
    if pgrep -f "main.py --mode trade" > /dev/null 2>&1; then
        if trade_is_hung; then
            TRADE_PID=$(pgrep -f "main.py --mode trade" | head -1)
            echo "$(date '+%Y-%m-%d %H:%M:%S') WARNING: trade process $TRADE_PID hung (stale heartbeat) — restarting"
            kill -9 "$TRADE_PID" 2>/dev/null || true
            # wait for process to die
            for i in $(seq 1 20); do
                if ! kill -0 "$TRADE_PID" 2>/dev/null; then
                    break
                fi
                sleep 1
            done
            cd "$PROJECT_DIR"
            setsid "$VENV_PYTHON" main.py --mode trade >> "$SCHED_LOG" 2>&1 &
            echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: trade process restarted after hang detection"
        fi
    fi
fi

# Check real-account sync daemon (only start if API is running)
if pgrep -f "main.py --mode api" > /dev/null 2>&1 && ! pgrep -f "main_real.py" > /dev/null 2>&1; then
    cd "$PROJECT_DIR"
    setsid "$VENV_PYTHON" main_real.py --mode daemon >> "$REAL_LOG" 2>&1 &
fi

# Check ngrok (only start if API is running)
if pgrep -f "main.py --mode api" > /dev/null 2>&1 && ! pgrep -f "ngrok http" > /dev/null 2>&1; then
    setsid npx ngrok http --url=capably-relock-spirits.ngrok-free.dev 8000 >> "$NGROK_LOG" 2>&1 &
fi
