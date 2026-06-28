#!/bin/bash
LOGFILE="/root/RoyalTDN/logs/run_20min_v2.log"
PIDFILE="/tmp/royaltdn_bot.pid"

echo "[$(date)] Esperando 20 minutos..." >> "$LOGFILE"
sleep 1200

if [ -f "$PIDFILE" ]; then
    BOT_PID=$(cat "$PIDFILE")
    echo "[$(date)] Time's up. Stopping bot (PID=$BOT_PID)..." | tee -a "$LOGFILE"
    kill $BOT_PID 2>/dev/null
    sleep 2
    kill -0 $BOT_PID 2>/dev/null && kill -9 $BOT_PID 2>/dev/null
    echo "[$(date)] Bot stopped." | tee -a "$LOGFILE"
    echo "--- LOG SIZE ---" >> "$LOGFILE"
    wc -l "$LOGFILE" >> "$LOGFILE"
fi
