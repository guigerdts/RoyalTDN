import json
from pathlib import Path

log_path = Path("logs/trading.log")
if not log_path.exists():
    print("No hay datos de trading.log")
    exit(1)

trades = []
with open(log_path, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        if event.get("type") == "position" and event.get("status") in ("close", "closed"):
            trades.append(event)

if not trades:
    print("No hay trades cerrados aún.")
    exit(0)

total_pnl = sum(t["pnl"] for t in trades)
wins = [t for t in trades if t["pnl"] > 0]
losses = [t for t in trades if t["pnl"] <= 0]
win_rate = len(wins) / len(trades) * 100 if trades else 0
gross_profit = sum(t["pnl"] for t in wins)
gross_loss = abs(sum(t["pnl"] for t in losses))
profit_factor = gross_profit / gross_loss if gross_loss else float("inf")

print(f"Total trades cerrados: {len(trades)}")
print(f"P&L total: ${total_pnl:.2f}")
print(f"Win Rate: {win_rate:.1f}%")
print(f"Profit Factor: {profit_factor:.2f}")
print(f"Ganancias: ${gross_profit:.2f}")
print(f"Pérdidas: ${gross_loss:.2f}")
