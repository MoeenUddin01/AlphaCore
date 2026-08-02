#!/bin/bash
# AlphaCore auto-start script
# Add to crontab with: crontab -e
# Then add this line:
# @reboot /home/moeen/projects/AlphaCore/scripts/start-all.sh >> /home/moeen/projects/AlphaCore/logs/startup.log 2>&1

set -e

PROJECT_DIR="/home/moeen/projects/AlphaCore"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
API_LOG="$LOG_DIR/api.log"
SCHED_LOG="$LOG_DIR/scheduler.log"
SYNC_LOG="$LOG_DIR/sync.log"
NGROK_LOG="$LOG_DIR/ngrok.log"
STARTUP_LOCK="$LOG_DIR/.start-all.lock"

# Prevent concurrent invocations (flock exits if another instance holds the lock)
exec 200>"$STARTUP_LOCK"
if ! flock -n 200; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Another start-all.sh is already running — exiting"
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') === AlphaCore auto-start ==="

# Kill any existing processes and wait for them to exit
pkill -f "main.py --mode api" 2>/dev/null || true
pkill -f "main.py --mode trade" 2>/dev/null || true
pkill -f "main_real.py" 2>/dev/null || true
pkill -f "ngrok http" 2>/dev/null || true

# Wait up to 10s for processes to fully exit
for i in $(seq 1 10); do
    if ! pgrep -f "main.py --mode api" > /dev/null 2>&1 && \
       ! pgrep -f "main.py --mode trade" > /dev/null 2>&1 && \
       ! pgrep -f "main_real.py" > /dev/null 2>&1; then
        echo "All old processes exited"
        break
    fi
    sleep 1
done

# Final safety: kill any stragglers
pkill -9 -f "main.py --mode api" 2>/dev/null || true
pkill -9 -f "main.py --mode trade" 2>/dev/null || true
pkill -9 -f "main_real.py" 2>/dev/null || true
sleep 1

# Wait for network
echo "Waiting for network..."
for i in $(seq 1 30); do
    if ping -c 1 -W 1 google.com &>/dev/null; then
        echo "Network OK"
        break
    fi
    sleep 2
done

# Start API server
echo "Starting API server..."
cd "$PROJECT_DIR"
setsid "$VENV_PYTHON" main.py --mode api >> "$API_LOG" 2>&1 &
echo "API PID: $!"

# Wait for API to be ready
echo "Waiting for API..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/health &>/dev/null; then
        echo "API ready"
        break
    fi
    sleep 2
done

# Start scheduler
echo "Starting scheduler..."
cd "$PROJECT_DIR"
setsid "$VENV_PYTHON" main.py --mode trade >> "$SCHED_LOG" 2>&1 &
echo "Scheduler PID: $!"

# Start real-account sync daemon
echo "Starting real account sync daemon..."
cd "$PROJECT_DIR"
setsid "$VENV_PYTHON" main_real.py --mode daemon >> "$SYNC_LOG" 2>&1 &
echo "Sync PID: $!"

# Start ngrok
echo "Starting ngrok tunnel..."
setsid npx ngrok http --url=capably-relock-spirits.ngrok-free.dev 8000 >> "$NGROK_LOG" 2>&1 &
echo "ngrok PID: $!"

echo "$(date '+%Y-%m-%d %H:%M:%S') === All services started ==="
