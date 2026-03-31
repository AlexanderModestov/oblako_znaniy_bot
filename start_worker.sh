#!/bin/bash

echo "Running database migrations..."
alembic upgrade head
if [ $? -ne 0 ]; then
    echo "ERROR: Database migration failed! Check DATABASE_URL"
    exit 1
fi

echo "Starting bots..."
python -m src.main
