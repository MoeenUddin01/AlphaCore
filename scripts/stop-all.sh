#!/bin/bash
# Stop all AlphaCore services

echo "Stopping AlphaCore services..."

pkill -f "main.py --mode api" 2>/dev/null && echo "API stopped" || echo "API not running"
pkill -f "main.py --mode trade" 2>/dev/null && echo "Scheduler stopped" || echo "Scheduler not running"
pkill -f "ngrok http" 2>/dev/null && echo "ngrok stopped" || echo "ngrok not running"

echo "All services stopped."
