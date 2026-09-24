#!/usr/bin/env bash
# Run the RAPKP cloud API right on the phone (Termux) -> http://localhost:8000
cd "$(dirname "$0")" || exit 1
pip install -q skyfield numpy 2>/dev/null
[ -f de421.bsp ] || python3 -c "from skyfield.api import load; load('de421.bsp')"
echo "RAPKP v26 API at http://localhost:8000  (Ctrl-C to stop)"
PORT=8000 python3 server.py
