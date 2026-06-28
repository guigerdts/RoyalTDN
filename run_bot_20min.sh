#!/bin/bash
export PYTHONPATH="/root/RoyalTDN/src:$PYTHONPATH"
LOGFILE="/root/RoyalTDN/logs/run_20min_v4.log"
cd /root/RoyalTDN/src
/root/RoyalTDN/.venv/bin/python -m royaltdn.main > "$LOGFILE" 2>&1 &
BOT_PID=$!
echo $BOT_PID > /tmp/royaltdn_bot.pid
echo "Bot started PID=$BOT_PID at $(date)"
