#!/bin/bash
# Run bot for 20 minutes, capture logs, then kill
LOGFILE="/root/RoyalTDN/logs/run_20min.log"
PIDFILE="/tmp/royaltdn_bot.pid"
mkdir -p /root/RoyalTDN/logs

echo "[$(date)] Starting bot..." | tee -a "$LOGFILE"

cd /root/RoyalTDN/src && PYTHONPATH="/root/RoyalTDN/src:$PYTHONPATH" \
  nohup /root/RoyalTDN/.venv/bin/python -m royaltdn.main \
  > "$LOGFILE" 2>&1 &

BOT_PID=$!
echo $BOT_PID > "$PIDFILE"
echo "[$(date)] Bot started, PID=$BOT_PID" | tee -a "$LOGFILE"

echo "[$(date)] Running for 20 minutes (1200s)..." | tee -a "$LOGFILE"
sleep 1200

echo "[$(date)] Time's up. Stopping bot..." | tee -a "$LOGFILE"
kill $BOT_PID 2>/dev/null
sleep 2
kill -0 $BOT_PID 2>/dev/null && kill -9 $BOT_PID 2>/dev/null

echo "[$(date)] Bot stopped. Log at $LOGFILE" | tee -a "$LOGFILE"
echo "--- LOG SIZE ---" >> "$LOGFILE"
wc -l "$LOGFILE" >> "$LOGFILE"
