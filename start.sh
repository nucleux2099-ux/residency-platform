#!/bin/bash
# Start both API and Web servers
# Ensure we are in the right directory
cd "$(dirname "$0")"

echo "Starting Residency Platform..."

# Check if pnpm is installed
if ! command -v pnpm &> /dev/null; then
    echo "pnpm could not be found. Please install it or use npm."
    # Fallback to npm if pnpm missing? The scripts use pnpm internally so it might fail anyway.
    exit 1
fi

# Start API in background
echo "Starting API on port 8000..."
# Use pnpm to run the script
pnpm run dev:api &
API_PID=$!

# Wait a moment for API to initialize
sleep 3

# Start Web
echo "Starting Web on port 3000..."
pnpm run dev:web

# When web stops, kill API
kill $API_PID
