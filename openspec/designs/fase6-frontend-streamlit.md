# Design: Fase 6 — Frontend Streamlit

## 1. Metadata

| Field | Value |
|-------|-------|
| **Change Name** | Fase 6 — Frontend Streamlit |
| **Author** | SDD Design Agent |
| **Date** | 2026-06-16 |
| **Status** | Draft |
| **Version** | 1.0 |
| **Spec Source** | `openspec/specs/fase6-frontend-streamlit.md` |
| **Proposal Source** | `openspec/proposals/fase6-frontend-streamlit.md` |

---

## 2. Frontend Component Architecture

### 2.1 File Tree

```
src/royaltdn/frontend/
├── __init__.py                     # Package marker
├── app.py                          # Entry point: st.navigation
├── pages/
│   ├── __init__.py
│   ├── dashboard.py                # 📊 Dashboard
│   ├── scanner.py                  # 🔍 Scanner
│   ├── estrategias.py              # ⚙️ Estrategias
│   ├── trades.py                   # 📈 Trades
│   └── logs.py                     # 📋 Logs
└── components/
    ├── __init__.py
    ├── loaders.py                  # JSON file readers
    └── charts.py                   # Plotly chart builders
```

### 2.2 Public Interfaces

#### `components/loaders.py` — All return `{}` on error, never raise

```python
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("royaltdn.frontend.loaders")

LOGS_DIR = Path("logs")

def load_json(path: Path) -> Optional[dict]:
    """Read and parse a JSON file safely.
    
    Returns:
        dict on success, None on any error (missing, corrupt, permission).
    """
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        return json.loads(raw)
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        logger.warning("Error reading %s: %s", path, e)
        return None

def load_status() -> dict:
    data = load_json(LOGS_DIR / "status.json")
    return data if data else {}

def load_equity() -> dict:
    data = load_json(LOGS_DIR / "equity.json")
    return data if data else {}

def load_positions() -> dict:
    data = load_json(LOGS_DIR / "positions.json")
    return data if data else {}

def load_signals() -> dict:
    data = load_json(LOGS_DIR / "signals.json")
    return data if data else {}

def load_scanner_results() -> dict:
    data = load_json(LOGS_DIR / "scanner_results.json")
    return data if data else {}

def load_strategies() -> dict:
    data = load_json(LOGS_DIR / "strategies.json")
    return data if data else {}

def load_trades() -> dict:
    data = load_json(LOGS_DIR / "trades.json")
    return data if data else {}

def is_stale(updated_at: str, max_age_minutes: int = 5) -> bool:
    """Check if a timestamp is older than max_age_minutes from now.
    
    Returns:
        True if stale or timestamp is unparseable.
    """
    if not updated_at:
        return True
    try:
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        delta = (datetime.now(timezone.utc) - ts).total_seconds()
        return delta > max_age_minutes * 60
    except (ValueError, TypeError):
        return True

def read_log_tail(path: Path = LOGS_DIR / "bot.log", max_lines: int = 1000) -> list[str]:
    """Read last max_lines lines from a text file efficiently.
    
    Uses deque with maxlen. Returns empty list on error.
    """
    from collections import deque
    try:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            return list(deque(f, maxlen=max_lines))
    except (OSError, PermissionError) as e:
        logger.warning("Error reading log %s: %s", path, e)
        return []
```

#### `components/charts.py` — All return `go.Figure`, never raise

```python
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Optional

EMPTY_CHART_LAYOUT = dict(
    xaxis=dict(visible=False),
    yaxis=dict(visible=False),
    annotations=[dict(
        text="No data available",
        xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=16, color="gray"),
    )],
)

def equity_curve_chart(equity_data: dict) -> go.Figure:
    """Plotly line chart from equity.json equity_curve[].
    
    Args:
        equity_data: dict with equity_curve key containing list of
                     {timestamp: str, equity: float}
    Returns:
        go.Figure with line chart or empty annotation.
    """
    curve = equity_data.get("equity_curve", [])
    if not curve:
        fig = go.Figure()
        fig.update_layout(**EMPTY_CHART_LAYOUT, title="Equity Curve")
        return fig
    
    df = pd.DataFrame(curve)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    fig = px.line(
        df, x="timestamp", y="equity",
        title="Equity Curve",
        labels={"equity": "Equity ($)", "timestamp": ""},
    )
    fig.update_traces(line=dict(color="#00cc96", width=2))
    fig.update_layout(
        hovermode="x unified",
        yaxis=dict(tickprefix="$", tickformat=","),
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig

def drawdown_chart(equity_data: dict) -> go.Figure:
    """Plotly filled area chart of drawdown from equity curve.
    
    Calculates drawdown as % below running maximum.
    """
    curve = equity_data.get("equity_curve", [])
    if not curve:
        fig = go.Figure()
        fig.update_layout(**EMPTY_CHART_LAYOUT, title="Drawdown")
        return fig
    
    df = pd.DataFrame(curve)
    df["peak"] = df["equity"].cummax()
    df["drawdown_pct"] = ((df["equity"] - df["peak"]) / df["peak"]) * 100
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(df["timestamp"]),
        y=df["drawdown_pct"],
        fill="tozeroy",
        line=dict(color="#ef553b", width=1),
        name="Drawdown",
        hovertemplate="%{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Drawdown",
        yaxis=dict(ticksuffix="%"),
        height=250,
        hovermode="x unified",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig

def distribution_chart(scanner_data: dict) -> go.Figure:
    """Bar chart of signal count per strategy."""
    signals = scanner_data.get("top_signals", [])
    if not signals:
        fig = go.Figure()
        fig.update_layout(**EMPTY_CHART_LAYOUT, title="Signals by Strategy")
        return fig
    
    from collections import Counter
    counts = Counter(s.get("strategy", "unknown") for s in signals)
    df = pd.DataFrame(counts.most_common(), columns=["Strategy", "Count"])
    
    fig = px.bar(
        df, x="Strategy", y="Count",
        title="Signals by Strategy",
        color="Strategy",
        color_discrete_sequence=px.colors.qualifier.Vivid,
    )
    fig.update_layout(
        height=300,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=False,
    )
    return fig

def pnl_bar_chart(trades: list[dict]) -> go.Figure:
    """Bar chart of P&L per trade, green for winning, red for losing."""
    if not trades:
        fig = go.Figure()
        fig.update_layout(**EMPTY_CHART_LAYOUT, title="P&L per Trade")
        return fig
    
    df = pd.DataFrame(trades)
    df["color"] = df["pnl"].apply(lambda x: "#00cc96" if x >= 0 else "#ef553b")
    df["label"] = df.apply(
        lambda r: f"{r.get('symbol', '?')} {r.get('side', '?')}", axis=1
    )
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=list(range(len(df))),
        y=df["pnl"],
        marker_color=df["color"],
        text=df["label"],
        hovertemplate="%{text}<br>P&L: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        title="P&L per Trade",
        yaxis=dict(tickprefix="$", tickformat=","),
        xaxis=dict(visible=False),
        height=300,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=False,
    )
    return fig

def pnl_histogram(trades: list[dict]) -> go.Figure:
    """Histogram of trade return distribution."""
    if not trades:
        fig = go.Figure()
        fig.update_layout(**EMPTY_CHART_LAYOUT, title="Return Distribution")
        return fig
    
    df = pd.DataFrame(trades)
    fig = px.histogram(
        df, x="pnl",
        title="Return Distribution",
        labels={"pnl": "P&L ($)"},
        nbins=20,
        color_discrete_sequence=["#636efa"],
    )
    fig.update_layout(
        height=250,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    # Vertical line at 0
    fig.add_vline(x=0, line_dash="dash", line_color="red")
    return fig
```

### 2.3 Data Flow Diagram

```
┌──────────────┐     poll every 60s      ┌──────────────────┐
│  Alpaca API  │ ◄────────────────────── │  Orchestrator    │
│  (Paper)     │     get_account()        │  _run_legacy_loop│
└──────────────┘                          │                  │
                                          │  _publish_status│
┌──────────────┐                          │  _atomic_write() │
│  Scanner     │     on scan cycle        └────────┬─────────┘
│  scan()      │ ──────────────────────────────►   │
│  _publish_   │                          writes   │
│  results()   │                                   ▼
└──────────────┘                          ┌──────────────────┐
                                          │  logs/*.json     │
                                          │  (7 files)       │
                                          └────────┬─────────┘
                                                   │ reads (poll 2-5s)
                                                   ▼
                                          ┌──────────────────┐
                                          │  loaders.py      │
                                          │  load_json()     │
                                          └────────┬─────────┘
                                                   │
                                          ┌────────┴────────┐
                                          │                 │
                                          ▼                 ▼
                                   ┌──────────┐     ┌──────────┐
                                   │ charts.py│     │ pages/*  │
                                   │ go.Figure│     │ st.*     │
                                   └──────────┘     └──────────┘
                                          │                 │
                                          └──────┬──────────┘
                                                 ▼
                                          ┌──────────────────┐
                                          │  app.py          │
                                          │  st.navigation   │
                                          └──────────────────┘
```

---

## 3. Orchestrator Design

### 3.1 `_atomic_write(path, data) -> bool`

Module-level function (static, in orchestrator.py or as a helper):

```python
import json
import os
from pathlib import Path
from typing import Optional

def _atomic_write(path: Path, data: dict) -> bool:
    """Write dict as JSON atomically via .tmp + os.replace.
    
    Process:
        1. Serialize data to JSON with indent=2, default=str
        2. Write to path.with_suffix('.tmp')
        3. os.replace(tmp_path, path) — atomic on Linux
    
    Returns:
        True on success, False on error (never raises).
    """
    try:
        tmp_path = path.with_suffix(".tmp")
        content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(path))
        return True
    except (OSError, TypeError, ValueError) as e:
        logger.warning("Error writing %s: %s", path, e)
        return False
```

### 3.2 `_get_current_equity() -> float`

```python
def _get_current_equity(self) -> float:
    """Fetch current equity from Alpaca account.
    
    Caches in self._last_known_equity. On error, returns cached value
    and sets self._equity_stale = True.
    
    Returns:
        float: current equity
    """
    try:
        account = self._trading.get_account()
        equity = float(account.equity)
        self._last_known_equity = equity
        self._equity_stale = False
        return equity
    except Exception as e:
        logger.warning("Error fetching equity: %s", e)
        self._equity_stale = True
        return self._last_known_equity
```

### 3.3 `_publish_status() -> None`

```python
def _publish_status(self) -> None:
    """Write all 7 JSON status files atomically to logs/.
    
    Order: equity → positions → signals → strategies → scanner_results → trades → status (LAST)
    status.json is written LAST so its presence and timestamp are the authoritative "ready" signal.
    """
    now = datetime.now(timezone.utc)
    uptime = int((now - self._start_time).total_seconds()) if hasattr(self, '_start_time') else 0
    
    # 1. equity.json
    equity_data = {
        "initial_equity": self._initial_equity,
        "current_equity": self._get_current_equity(),
        "pnl_day": self._current_equity - self._day_start_equity if hasattr(self, '_day_start_equity') else 0,
        "pnl_day_pct": 0.0,  # calculated from pnl_day / initial_equity * 100
        "drawdown": 0.0,
        "drawdown_pct": 0.0,
        "sharpe": self._calculate_sharpe() if hasattr(self, '_trades_count') and self._trades_count > 2 else None,
        "equity_curve": self._build_equity_curve(),
        "updated_at": now.isoformat(),
        "stale": getattr(self, '_equity_stale', False),
    }
    # Calculate P&L day %
    if equity_data["initial_equity"] > 0:
        equity_data["pnl_day_pct"] = round(
            (equity_data["current_equity"] - equity_data["initial_equity"]) 
            / equity_data["initial_equity"] * 100, 2
        )
    
    _atomic_write(LOGS_DIR / "equity.json", equity_data)
    
    # 2. positions.json
    positions_data = {
        "open_positions": self._build_positions_list(),
        "total_open": 1 if self._position else 0,
        "updated_at": now.isoformat(),
    }
    _atomic_write(LOGS_DIR / "positions.json", positions_data)
    
    # 3. signals.json
    signals_data = {
        "today_count": self._daily_signal_count,
        "last_signals": self._recent_signals[-20:] if hasattr(self, '_recent_signals') else [],
        "updated_at": now.isoformat(),
    }
    _atomic_write(LOGS_DIR / "signals.json", signals_data)
    
    # 4. strategies.json
    strategies_list = self._build_strategies_list()
    _atomic_write(LOGS_DIR / "strategies.json", {
        "strategies": strategies_list,
        "updated_at": now.isoformat(),
    })
    
    # 5. status.json (LAST — authoritative)
    status_data = {
        "bot_status": "KILLED" if self._killed else "ONLINE",
        "mode": "legacy" if self._use_legacy_fallback else "modular",
        "timestamp": now.isoformat(),
        "last_signal": self._last_signal_summary(),
        "last_error": self._last_error,
        "uptime_seconds": uptime,
        "symbols": [self.symbol],
        "scanner_enabled": self._scanner is not None,
        "version": "1.0.0",
    }
    _atomic_write(LOGS_DIR / "status.json", status_data)
```

Helper methods:

```python
def _build_equity_curve(self) -> list:
    """Build equity curve points, cap at 1000."""
    if not hasattr(self, '_equity_points'):
        self._equity_points = []
    
    now = datetime.now(timezone.utc)
    equity = getattr(self, '_last_known_equity', self._initial_equity)
    self._equity_points.append({
        "timestamp": now.isoformat(),
        "equity": equity,
    })
    # Cap at 1000 points
    if len(self._equity_points) > 1000:
        self._equity_points = self._equity_points[-1000:]
    return self._equity_points

def _build_positions_list(self) -> list:
    """Build open positions list from orchestrator state."""
    if not self._position:
        return []
    return [{
        "symbol": self.symbol,
        "side": self._position,
        "qty": self._position_qty,
        "entry_price": self._last_entry_price,
        "current_price": self._last_known_price if hasattr(self, '_last_known_price') else self._last_entry_price,
        "pnl_unrealized": self._calculate_unrealized_pnl(),
        "entry_at": self._last_entry_at.isoformat() if self._last_entry_at else None,
        "strategy": "sma_crossover",
    }]

def _build_strategies_list(self) -> list:
    """Build strategies status list from scanner + config."""
    strategies = []
    # If scanner is available, get strategies from there
    if self._scanner:
        for name, strategy in self._scanner.strategies.items():
            strategies.append({
                "name": name,
                "active": True,
                "params": strategy.get_parameters(),
                "validation": strategy.validate(),
                "last_signal": self._last_signal_by_strategy.get(name),
                "signal_count": self._signal_count_by_strategy.get(name, 0),
                "symbol": getattr(strategy, 'symbol', self.symbol),
                "timeframe": getattr(strategy, 'timeframe', '1d'),
            })
    else:
        # Fallback: only SMAStrategy
        strategies.append({
            "name": "sma_crossover",
            "active": True,
            "params": {"fast_period": self.sma_fast, "slow_period": self.sma_slow},
            "validation": True,
            "last_signal": self._last_action,
            "signal_count": self._trades_count,
            "symbol": self.symbol,
            "timeframe": "1d",
        })
    return strategies

def _last_signal_summary(self) -> Optional[dict]:
    """Return last signal summary or None."""
    if not hasattr(self, '_last_signal') or not self._last_signal:
        return None
    sig = self._last_signal
    return {
        "action": sig.get("action"),
        "price": sig.get("price"),
        "symbol": sig.get("symbol", self.symbol),
        "strategy": sig.get("strategy", "sma_crossover"),
        "timestamp": sig.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "metadata": sig.get("metadata", {}),
    }
```

### 3.4 `_append_trade(trade: dict) -> None`

```python
def _append_trade(self, trade: dict) -> None:
    """Append a completed trade to logs/trades.json.
    
    Reads existing trades.json, appends new trade, recalculates
    summary metrics, writes back atomically.
    """
    path = LOGS_DIR / "trades.json"
    
    # Read existing
    existing = {}
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            if raw.strip():
                existing = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        existing = {}
    
    trades = existing.get("trades", [])
    trades.append(trade)
    
    # Calculate summary metrics
    total = len(trades)
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    losses = total - wins
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    
    output = {
        "total_trades": total,
        "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "total_pnl": round(total_pnl, 2),
        "trades": trades,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    _atomic_write(path, output)
```

### 3.5 Scanner Publishing

In `src/royaltdn/scanner/scanner.py`, add after `_rank_signals()`:

```python
def _publish_scanner_results(self) -> None:
    """Write scanner results to logs/scanner_results.json."""
    path = Path("logs/scanner_results.json")
    
    # Build history
    if not hasattr(self, '_scan_history'):
        self._scan_history = []
    
    scan_entry = {
        "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols_scanned": self._last_symbols_scanned,
        "symbols_passed": self._last_symbols_passed,
        "total_signals": len(self._last_scan_results),
    }
    self._scan_history.append(scan_entry)
    if len(self._scan_history) > 10:
        self._scan_history = self._scan_history[-10:]
    
    data = {
        "scan_timestamp": scan_entry["scan_timestamp"],
        "symbols_scanned": self._last_symbols_scanned,
        "symbols_passed": self._last_symbols_passed,
        "total_signals": len(self._last_scan_results),
        "top_signals": self._last_scan_results[:SCANNER_TOP_N] if hasattr(self, '_last_scan_results') else [],
        "history": self._scan_history,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    _atomic_write(path, data)
```

And in `scan()`, store counts before returning and call `_publish_scanner_results()`:
```python
def scan(self) -> List[dict]:
    ...
    self._last_symbols_scanned = total_symbols
    self._last_symbols_passed = passed_count
    ...
    self._publish_scanner_results()
    return ranked
```

### 3.6 Insertion Points in Orchestrator

#### `_run_legacy_loop()` — end of each cycle

```python
while self._running and not self._killed:
    try:
        # ... existing scanner logic ...
        
        # ... existing SMA signal logic ...
        
        # NEW: Publish status at end of cycle
        self._publish_status()
        
    except asyncio.CancelledError:
        break
    except Exception as e:
        # ... existing error handling ...
    
    await asyncio.sleep(poll_interval)
```

#### `_execute_signal()` — SELL path, after P&L calculation

```python
# In the SELL path, after calculating P&L and slippage:
trade_record = {
    "symbol": self.symbol,
    "side": "long",
    "entry_price": self._last_entry_price,
    "exit_price": price,
    "qty": self._position_qty,
    "pnl": round(pnl, 2),
    "entry_at": self._last_entry_at.isoformat() if self._last_entry_at else None,
    "exit_at": datetime.now(timezone.utc).isoformat(),
    "strategy": "sma_crossover",  # TODO: extract from signal
    "slippage_bps": slippage_bps,
    "execution_method": exec_method,
}
self._append_trade(trade_record)  # ← NEW
```

Also, signal tracking for `signals.json`:
```python
# In _execute_signal or signal generation, after receiving signal:
if not hasattr(self, '_recent_signals'):
    self._recent_signals = []
self._recent_signals.append({
    "action": action,
    "symbol": signal.get("symbol", self.symbol),
    "price": price,
    "strategy": signal.get("strategy", "sma_crossover"),
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "metadata": signal.get("metadata", {}),
})
if len(self._recent_signals) > 20:
    self._recent_signals = self._recent_signals[-20:]

# Track signal count per day
if not hasattr(self, '_daily_signal_count'):
    self._daily_signal_count = 0
self._daily_signal_count += 1
```

#### `_setup()` — publish initial ONLINE status

```python
async def _setup(self) -> bool:
    # ... existing trading client init ...
    
    # NEW: Record start time
    self._start_time = datetime.now(timezone.utc)
    self._last_known_equity = self._initial_equity
    
    # NEW: Publish initial status
    self._publish_status()
    
    return True
```

#### `_shutdown()` — publish final OFFLINE status BEFORE closing

```python
async def _shutdown(self):
    # NEW: Publish final status FIRST (before connections close)
    self._publish_status()  # will have bot_status: OFFLINE if _running is False
    
    # ... existing cleanup ...
```

---

## 4. Frontend Pages Design

### 4.1 `app.py` — Entry Point

```python
import streamlit as st
from streamlit.navigation import page, navigation

st.set_page_config(
    page_title="RoyalTDN",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

dashboard = page("pages/dashboard.py", title="📊 Dashboard", default=True)
scanner = page("pages/scanner.py", title="🔍 Scanner")
estrategias = page("pages/estrategias.py", title="⚙️ Estrategias")
trades = page("pages/trades.py", title="📈 Trades")
logs = page("pages/logs.py", title="📋 Logs")

nav = navigation([dashboard, scanner, estrategias, trades, logs])
nav.run()
```

### 4.2 `pages/dashboard.py` — Layout

```python
import streamlit as st
import time
from datetime import datetime, timezone

from royaltdn.frontend.components.loaders import (
    load_status, load_equity, load_positions, load_signals, is_stale
)
from royaltdn.frontend.components.charts import (
    equity_curve_chart, drawdown_chart
)

# ── Layout ────────────────────────────────────────────────────
# 1. Title row
st.title("📊 Dashboard")

# 2. Metric cards (6-7 columns)
col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

equity = load_equity()
positions = load_positions()
signals = load_signals()
status = load_status()

with col1:
    capital = equity.get("current_equity")
    if capital is not None:
        st.metric("Capital", f"${capital:,.2f}")
    else:
        st.metric("Capital", "—")

with col2:
    pnl = equity.get("pnl_day")
    if pnl is not None:
        st.metric("P&L Day ($)", f"${pnl:+,.2f}", delta_color="normal")
    else:
        st.metric("P&L Day ($)", "—")

with col3:
    pnl_pct = equity.get("pnl_day_pct")
    if pnl_pct is not None:
        st.metric("P&L Day (%)", f"{pnl_pct:+.2f}%")
    else:
        st.metric("P&L Day (%)", "—")

with col4:
    dd = equity.get("drawdown_pct")
    if dd is not None:
        st.metric("Drawdown", f"{dd:.2f}%")
    else:
        st.metric("Drawdown", "—")

with col5:
    open_pos = positions.get("total_open", 0)
    st.metric("Open Positions", open_pos)

with col6:
    sig_count = signals.get("today_count", 0)
    st.metric("Signals Today", sig_count)

with col7:
    sharpe = equity.get("sharpe")
    if sharpe is not None:
        st.metric("Sharpe", f"{sharpe:.2f}")
    else:
        st.metric("Sharpe", "—")

# 3. Charts row
col_left, col_right = st.columns(2)
with col_left:
    fig_eq = equity_curve_chart(equity)
    st.plotly_chart(fig_eq, use_container_width=True)
with col_right:
    fig_dd = drawdown_chart(equity)
    st.plotly_chart(fig_dd, use_container_width=True)

# 4. Open positions table
st.subheader("Open Positions")
pos_list = positions.get("open_positions", [])
if pos_list:
    df_pos = pd.DataFrame(pos_list)
    # Calculate duration if entry_at is present
    if "entry_at" in df_pos.columns:
        df_pos["duration"] = df_pos["entry_at"].apply(
            lambda x: str(datetime.now(timezone.utc) - datetime.fromisoformat(x.replace("Z", "+00:00"))).split(".")[0]
            if x else "—"
        )
    st.dataframe(df_pos, use_container_width=True, hide_index=True)
else:
    st.info("No open positions")

# 5. Bot status
st.subheader("Bot Status")
is_stale_flag = is_stale(status.get("timestamp", ""))
bot_status = status.get("bot_status", "OFFLINE") if status else "OFFLINE"

if not status:
    st.warning("⏳ Waiting for bot to start...")
elif is_stale_flag:
    st.warning("⚠️ ⚠️ STALE — Bot data is older than 5 minutes")
elif bot_status == "ONLINE":
    st.success("● ONLINE")
elif bot_status == "KILLED":
    st.error("● KILLED")
else:
    st.error("● OFFLINE")

# Show mode
if status:
    st.caption(f"Mode: {status.get('mode', 'unknown')}")
    last_signal = status.get("last_signal")
    if last_signal:
        st.caption(f"Last signal: {last_signal.get('action')} @ {last_signal.get('price')}")
    if status.get("last_error"):
        st.error(f"Last error: {status['last_error']}")

# Auto-refresh
time.sleep(3)
st.rerun()
```

### 4.3 `pages/scanner.py` — Layout

```python
import streamlit as st
import time
import pandas as pd

from royaltdn.frontend.components.loaders import load_scanner_results
from royaltdn.frontend.components.charts import distribution_chart

st.title("🔍 Scanner")

scanner_data = load_scanner_results()

if not scanner_data or not scanner_data.get("top_signals"):
    st.info("Scanner not initialized or no scan completed yet")
    time.sleep(5)
    st.rerun()

# Config section
with st.expander("Scanner Configuration", expanded=False):
    st.selectbox("Universe", ["etfs", "sp500", "all"], key="scan_universe")
    st.number_input("Top N signals", min_value=1, max_value=20, value=5, key="scan_top_n")

# Signals table
st.subheader("Top Signals")
signals_df = pd.DataFrame(scanner_data.get("top_signals", []))
if not signals_df.empty:
    def color_row(row):
        if row.get("action") == "BUY":
            return ["background-color: #d4edda"] * len(row)
        elif row.get("action") == "SELL":
            return ["background-color: #f8d7da"] * len(row)
        elif row.get("action") == "RANK":
            return ["background-color: #cce5ff"] * len(row)
        return [""] * len(row)
    
    st.dataframe(
        signals_df.style.apply(color_row, axis=1),
        use_container_width=True,
        hide_index=True,
    )

# Distribution chart
st.subheader("Distribution by Strategy")
fig = distribution_chart(scanner_data)
st.plotly_chart(fig, use_container_width=True)

# Scan history
st.subheader("Scan History")
history = scanner_data.get("history", [])
if history:
    st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)

time.sleep(5)
st.rerun()
```

### 4.4 `pages/estrategias.py` — Layout

```python
import streamlit as st
import time
import pandas as pd

from royaltdn.frontend.components.loaders import load_strategies

st.title("⚙️ Estrategias")

strategies_data = load_strategies()
strategies = strategies_data.get("strategies", [])

if not strategies:
    st.info("No strategies loaded")
    time.sleep(5)
    st.rerun()

for s in strategies:
    with st.expander(f"{'✅' if s.get('active') else '⏸️'} {s.get('name', '?')}", expanded=True):
        cols = st.columns([1, 1, 1])
        with cols[0]:
            active = s.get("active", True)
            st.checkbox("Active", value=active, key=f"active_{s['name']}", disabled=True)
            st.caption(f"Symbol: {s.get('symbol', '—')}")
            st.caption(f"Timeframe: {s.get('timeframe', '—')}")
        with cols[1]:
            st.caption("Last signal")
            st.code(s.get("last_signal", "—") if s.get("last_signal") else "—")
            st.caption(f"Signal count: {s.get('signal_count', 0)}")
        with cols[2]:
            valid = s.get("validation", False)
            st.metric("Validation", "✅" if valid else "❌")
        
        # Parameters table
        params = s.get("params", {})
        if params:
            st.subheader("Parameters")
            params_df = pd.DataFrame([
                {"Parameter": k, "Value": v} for k, v in params.items()
            ])
            st.dataframe(params_df, hide_index=True, use_container_width=True)

time.sleep(5)
st.rerun()
```

### 4.5 `pages/trades.py` — Layout

```python
import streamlit as st
import time
import pandas as pd
from datetime import datetime, timedelta

from royaltdn.frontend.components.loaders import load_trades
from royaltdn.frontend.components.charts import pnl_bar_chart, pnl_histogram

st.title("📈 Trades")

trades_data = load_trades()
trades_list = trades_data.get("trades", [])

# Filters
col1, col2, col3, col4 = st.columns(4)
with col1:
    date_from = st.date_input("From", value=datetime.now() - timedelta(days=30))
with col2:
    date_to = st.date_input("To", value=datetime.now())
with col3:
    symbols = list(set(t.get("symbol", "") for t in trades_list)) if trades_list else []
    filter_symbol = st.selectbox("Symbol", ["All"] + symbols)
with col4:
    filter_result = st.radio("Result", ["All", "Win", "Loss"], horizontal=True)

# Filter logic
filtered = trades_list
if filter_symbol and filter_symbol != "All":
    filtered = [t for t in filtered if t.get("symbol") == filter_symbol]
if filter_result == "Win":
    filtered = [t for t in filtered if t.get("pnl", 0) > 0]
elif filter_result == "Loss":
    filtered = [t for t in filtered if t.get("pnl", 0) <= 0]

# Summary metrics
if filtered:
    total = len(filtered)
    wins = sum(1 for t in filtered if t.get("pnl", 0) > 0)
    total_pnl = sum(t.get("pnl", 0) for t in filtered)
    win_rate = wins / total * 100 if total > 0 else 0
    gross_profit = sum(t["pnl"] for t in filtered if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in filtered if t["pnl"] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_pnl = total_pnl / total if total > 0 else 0
    best = max(t.get("pnl", 0) for t in filtered) if filtered else 0
    worst = min(t.get("pnl", 0) for t in filtered) if filtered else 0
    
    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Total Trades", total)
    m2.metric("Win Rate", f"{win_rate:.1f}%")
    m3.metric("Profit Factor", f"{profit_factor:.2f}")
    m4.metric("Total P&L", f"${total_pnl:+,.2f}")
    m5.metric("Avg P&L", f"${avg_pnl:+,.2f}")
    m6.metric("Best", f"${best:+,.2f}")
    m7.metric("Worst", f"${worst:+,.2f}")

# Table
if filtered:
    df = pd.DataFrame(filtered)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Charts
    col_a, col_b = st.columns(2)
    with col_a:
        fig_pnl = pnl_bar_chart(filtered)
        st.plotly_chart(fig_pnl, use_container_width=True)
    with col_b:
        fig_hist = pnl_histogram(filtered)
        st.plotly_chart(fig_hist, use_container_width=True)
    
    # CSV export
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=f"trades_export_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
else:
    st.info("No trades executed this session" if not trades_list else "No trades match the filters")

time.sleep(5)
st.rerun()
```

### 4.6 `pages/logs.py` — Layout

```python
import streamlit as st
import time
from pathlib import Path

from royaltdn.frontend.components.loaders import read_log_tail

st.title("📋 Logs")

# Filters
col1, col2, col3, col4 = st.columns(4)
with col1:
    show_debug = st.checkbox("DEBUG", value=False)
    show_info = st.checkbox("INFO", value=True)
with col2:
    show_warning = st.checkbox("WARNING", value=True)
    show_error = st.checkbox("ERROR", value=True)
with col3:
    module_filter = st.text_input("Module filter", placeholder="e.g. scanner")
with col4:
    search_text = st.text_input("Search", placeholder="text to find")
    if st.button("Clear view"):
        st.session_state["log_buffer"] = []
        st.rerun()

# Initialize buffer
if "log_buffer" not in st.session_state:
    st.session_state["log_buffer"] = []

# Read log file
raw_lines = read_log_tail(Path("logs/bot.log"), max_lines=1000)

if not raw_lines:
    st.info("Log file not found at logs/bot.log")
    time.sleep(2)
    st.rerun()

# Apply filters
filtered = []
for line in raw_lines:
    # Level filter
    if not show_debug and " - DEBUG - " in line:
        continue
    if not show_info and " - INFO - " in line:
        continue
    if not show_warning and " - WARNING - " in line:
        continue
    if not show_error and " - ERROR - " in line:
        continue
    
    # Module filter
    if module_filter and module_filter.lower() not in line.lower():
        continue
    
    # Search
    if search_text and search_text.lower() not in line.lower():
        continue
    
    filtered.append(line)

# Display
st.session_state["log_buffer"] = filtered[-200:]  # keep last 200
st.code("".join(st.session_state["log_buffer"]), language="log", line_numbers=True)

time.sleep(2)
st.rerun()
```

---

## 5. Requirements Changes

Create `requirements/fase6.txt`:
```
streamlit>=1.28,<2.0
plotly>=5.18,<6.0
```

Add to `.env` (optional, for frontend):
```
# Streamlit Frontend (Fase 6)
STREAMLIT_PORT=8501
SCANNER_TOP_N=5
```

---

## 6. Implementation Plan with Milestones

### Hito 1: Publicación de estado (orchestrator + scanner)
**Archivos**: `src/royaltdn/orchestrator.py`, `src/royaltdn/scanner/scanner.py`
**Tareas**:
1. Add `_atomic_write()` module-level function
2. Add `_get_current_equity()` to Orchestrator
3. Add `_publish_status()` to Orchestrator
4. Add `_append_trade()` to Orchestrator
5. Add `_publish_scanner_results()` to Scanner
6. Add tracking of signal count, equity curve, recent signals to Orchestrator
7. Add `LOGS_DIR` constant and ensure `logs/` exists
8. Insert calls in `_run_legacy_loop()`, `_execute_signal()`, `_setup()`, `_shutdown()`
9. **Verificación**: `python -m royaltdn run` → `logs/` tiene los 7 archivos JSON válidos

### Hito 2: Loaders y Charts (frontend components)
**Archivos**: `frontend/__init__.py`, `frontend/components/__init__.py`, `loaders.py`, `charts.py`
**Tareas**:
1. Create `frontend/` package structure
2. Implement `loaders.py` with all 8 loader functions + `is_stale()` + `read_log_tail()`
3. Implement `charts.py` with all 5 chart functions
4. **Verificación**: `python -c "from royaltdn.frontend.components.loaders import *" && echo OK`

### Hito 3: Página Dashboard
**Archivos**: `frontend/pages/__init__.py`, `pages/dashboard.py`, `app.py`
**Tareas**:
1. Create `pages/` package
2. Implement `dashboard.py` with metric cards, charts, positions table, bot status
3. Implement `app.py` with `st.navigation`
4. Install streamlit + plotly
5. **Verificación**: `streamlit run src/royaltdn/frontend/app.py` abre Dashboard

### Hito 4: Páginas restantes
**Archivos**: `pages/scanner.py`, `pages/estrategias.py`, `pages/trades.py`, `pages/logs.py`
**Tareas**:
1. Implement Scanner page (signals table, distribution chart, history)
2. Implement Estrategias page (strategy expanders, params, validation)
3. Implement Trades page (filters, metrics, table, charts, CSV)
4. Implement Logs page (viewer, filters, search)
5. **Verificación**: Navegar entre las 5 páginas sin errores

### Hito 5: Integración completa
**Tareas**:
1. Run bot for 5+ cycles, verify all 7 JSON files are written and valid
2. Run frontend alongside bot, verify live data on all pages
3. Test empty states: delete a JSON file while frontend is running
4. Test stale detection: stop bot, verify frontend shows STALE/OFFLINE
5. Test trade recording: inject mock trade, verify it appears in frontend
6. Test CSV export downloads a valid file
7. **Verificación**: Checklist completo de acceptance criteria

---

## 7. Module Dependency Graph

```
DEPENDENCY ORDER (bottom-up):
1. requirements/fase6.txt
2. orchestrator.py (add _atomic_write, _publish_status, etc.)
3. scanner.py (add _publish_scanner_results)
4. frontend/__init__.py
5. frontend/components/__init__.py
6. frontend/components/loaders.py  (depends on: logs/*.json)
7. frontend/components/charts.py   (depends on: loaders)
8. frontend/pages/__init__.py
9. frontend/pages/dashboard.py     (depends on: loaders, charts)
10. frontend/pages/scanner.py      (depends on: loaders, charts)
11. frontend/pages/estrategias.py  (depends on: loaders)
12. frontend/pages/trades.py       (depends on: loaders, charts)
13. frontend/pages/logs.py         (depends on: loaders)
14. frontend/app.py                (depends on: pages)
```

---

## 8. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| File polling causes Streamlit rerender latency (full page reload) | Medium | Low | Use `st.cache_data` with TTL for file reads; files are small (<100KB) |
| `st.navigation` API changes in future Streamlit | High | Low | Pin `streamlit>=1.28,<2.0` |
| Atomic write fails on exotic filesystem (NFS, FUSE) | Low | Low | `os.replace()` is atomic on local filesystems; warn in docs |
| Log file grows unbounded (>1GB) | Low | Medium | Cap reads to 1000 lines with `deque`; log rotation planned for future |
| Orchestrator publish blocks the async loop | Low | Low | `_publish_status()` is sync but <200ms for 7 files; if latency appears, move to executor thread |

---

## 9. Open Questions

1. **Equity curve start**: ¿El primer punto de equity_curve debe ser al arranque del bot o al inicio del día? **Decisión**: Al arranque del bot (`self._initial_equity` en `_setup`). Por simplicidad.
2. **Scanner history persistence**: El historial de escaneos se acumula en memoria en `Scanner._scan_history`. Si el bot se reinicia, se pierde. ¿Debe persistirse? **Decisión**: Se pierde en restart — aceptable para MVP.
3. **signal_count tracking**: ¿El contador de señales debe reiniciarse cada día o es absoluto? **Decisión**: `today_count` por día se calcula filtrando señales de las últimas 24h; `signal_count` por estrategia es absoluto.
4. **Sharpe calculation**: ¿Cómo se calcula el Sharpe sin trades aún? **Decisión**: Si `trades_count < 3`, Sharpe se omite (None → "—" en frontend).
