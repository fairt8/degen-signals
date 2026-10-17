#!/bin/bash
# Supervisor: restarts listener.py if it exits. Start: nohup ./run_listener.sh >> listener.log 2>&1 &
cd "$(dirname "$0")"
while true; do
  python3 -u listener.py
  echo "$(date '+%F %T') listener exited ($?), restarting in 5s"; sleep 5
done
