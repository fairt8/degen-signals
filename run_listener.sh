#!/bin/bash
# Supervisor: restarts listener.py if it exits. Start: nohup ./run_listener.sh >> listener.log 2>&1 &
cd "$(dirname "$0")"
[ -n "${DEGEN_TELEGRAM_BOT_TOKEN:-}" ] || { echo "DEGEN_TELEGRAM_BOT_TOKEN not set"; exit 1; }
while true; do
  python3 -u listener.py; rc=$?
  [ $rc = 2 ] && { echo "wrong bot token, not restarting"; exit 2; }
  echo "$(date '+%F %T') listener exited ($?), restarting in 5s"; sleep 5
done
