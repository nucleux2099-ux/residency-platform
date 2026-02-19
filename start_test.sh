#!/bin/bash
# Start Parallel Test Environment
# Frontend: Port 3002
# Backend: Port 8001
# Data: Same as main env (shared)

cd "$(dirname "$0")"

echo "Starting Residency Platform (TEST ENV)..."

# Check if pnpm is installed
if ! command -v pnpm &> /dev/null; then
    echo "pnpm could not be found. Please install it or use npm."
    exit 1
fi

# 1. Start API on Port 8001
echo "Starting API on port 8001..."
export API_PORT=8001
cd apps/api
# Run uvicorn directly to override the --port 8000 in package.json
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --reload-dir app --reload-exclude '.venv/*' --reload-exclude "**/__pycache__/*" &
API_PID=$!
cd ../..

# Wait for API
sleep 3

# 2. Start Web on Port 3002 pointing to API 8001
echo "Starting Web on port 3002 (Connected to API 8001)..."
# We export the env var so Next.js picks it up
export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8001"
export PORT=3002

pnpm --filter @residency/web dev

# Cleanup
kill $API_PID
