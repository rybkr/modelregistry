#!/usr/bin/env bash

set -e

echo "Installing dependencies..."
python3 -m pip install --upgrade pip

if python3 -m pip install -e ".[dev]" 2>/dev/null; then
    echo "install ok"
    exit 0
fi

if [ -f "requirements.txt" ]; then
    python3 -m pip install -r requirements.txt
else
    python3 -m pip install pytest pytest-cov
fi

echo "install ok"
