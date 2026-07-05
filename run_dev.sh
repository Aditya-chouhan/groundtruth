#!/bin/bash

# Groundtruth Startup Script
# Starts backend and frontend local servers

echo "=== Starting Groundtruth Dev Servers ==="

# Check if Postgres is running
if ! pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    echo "ERROR: Postgres is not running on localhost:5432"
    echo "Please start PostgreSQL before running dev servers."
    exit 1
fi
echo "✓ Postgres is running"

# Get current script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Start Backend API
echo "Starting Backend API on http://localhost:8000..."
cd "$DIR/app/backend"
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start Frontend
echo "Starting Next.js Frontend on http://localhost:3000..."
cd "$DIR/app/frontend"
npm run dev &
FRONTEND_PID=$!

# Handle shutdown cleanly
trap "echo 'Stopping dev servers...'; kill $BACKEND_PID; kill $FRONTEND_PID; exit" INT TERM
wait
