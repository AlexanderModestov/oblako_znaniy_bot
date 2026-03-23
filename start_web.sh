#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting web server..."
uvicorn src.web.app:app --host 0.0.0.0 --port ${PORT:-8000}
