#!/bin/bash
# AlphaCore watchdog — restarts services if they died
# Runs every minute via crontab

PROJECT_DIR="/home/moeen/projects/AlphaCore"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
API_LOG="$PROJECT_DIR/logs/api.log"
SCHED_LOG="$PROJECT_DIR/logs/scheduler.log"
NGROK_LOG="$PROJECT_DIR/logs/ngrok.log"

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
fi

# Check ngrok (only start if API is running)
if pgrep -f "main.py --mode api" > /dev/null 2>&1 && ! pgrep -f "ngrok http" > /dev/null 2>&1; then
    setsid npx ngrok http --url=capably-relock-spirits.ngrok-free.dev 8000 >> "$NGROK_LOG" 2>&1 &
fi
