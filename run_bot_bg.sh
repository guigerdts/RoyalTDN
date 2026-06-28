#!/bin/bash
LOGFILE="/root/RoyalTDN/logs/run_20min_v3.log"
echo "[$(date)] Iniciando bot 20 min (S+R fix)..." > "$LOGFILE"
cd /root/RoyalTDN/src
PYTHONPATH="/root/RoyalTDN/src:$PYTHONPATH"
export PYTHONPATH
nohup /root/RoyalTDN/.venv/bin/python -m royaltdn.main >> "$LOGFILE" 2>&1 &
BOT_PID=$!
echo $BOT_PID > /tmp/royaltdn_bot.pid
echo "[$(date)] Bot PID=$BOT_PID" >> "$LOGFILE"

# Wait 20 minutes then kill
sleep 1200
echo "[$(date)] Time's up. Killing bot PID=$BOT_PID..." >> "$LOGFILE"
kill $BOT_PID 2>/dev/null
sleep 2
kill -0 $BOT_PID 2>/dev/null && kill -9 $BOT_PID 2>/dev/null
echo "[$(date)] Bot stopped." >> "$LOGFILE"
echo "--- LOG SIZE: $(wc -l < "$LOGFILE") lines ---" >> "$LOGFILE"
