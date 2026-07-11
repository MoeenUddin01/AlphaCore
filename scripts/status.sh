#!/bin/bash
# Check AlphaCore service status

echo "=== AlphaCore Service Status ==="
echo ""

# API
if pgrep -f "main.py --mode api" > /dev/null; then
    echo "API:       RUNNING (PID $(pgrep -f 'main.py --mode api'))"
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "  Health:  OK"
    else
        echo "  Health:  UNREACHABLE"
    fi
else
    echo "API:       STOPPED"
fi

# Scheduler
if pgrep -f "main.py --mode trade" > /dev/null; then
    echo "Scheduler: RUNNING (PID $(pgrep -f 'main.py --mode trade'))"
else
    echo "Scheduler: STOPPED"
fi

# ngrok
if pgrep -f "ngrok http" > /dev/null; then
    echo "ngrok:     RUNNING (PID $(pgrep -f 'ngrok http'))"
    if curl -s https://capably-relock-spirits.ngrok-free.dev/health -H "ngrok-skip-browser-warning: true" > /dev/null 2>&1; then
        echo "  Tunnel:  OK"
    else
        echo "  Tunnel:  UNREACHABLE"
    fi
else
    echo "ngrok:     STOPPED"
fi

echo ""
echo "Crontab:"
crontab -l 2>/dev/null || echo "  (none)"
