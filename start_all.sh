#!/bin/bash

# Kill ports 8000 and 3000 to ensure clean start
echo "Cleaning up ports..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null

# Start API
echo "Starting Application Server..."
cd apps/api
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
cd ../..

# Wait for API
sleep 2

# Start Web (Dev mode for now as build takes time, but can be switched to start)
# Using dev mode is often safer for immediate local use without waiting for build
echo "Starting Interface..."
cd apps/web
pnpm dev &
WEB_PID=$!
cd ../..

echo "✅ System Online!"
echo "-----------------------------------"
echo "Web Interface: http://localhost:3000"
echo "API Server:    http://localhost:8000"
echo "-----------------------------------"
echo "To tunnel: 'cloudflared tunnel --url http://localhost:3000'"

# Trap Ctrl+C to kill both
trap "kill $API_PID $WEB_PID; exit" INT
wait
