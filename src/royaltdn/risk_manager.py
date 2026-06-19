"""
RoyalTDN — Gestor de Riesgos (Fase 2)

Basado en documento 05_ruta_implementacion_fase2_fase3.md, sección 5.2.3.

Funciones:
- calculate_position_size: Tamaño de posición por riesgo fijo (% capital / ATR)
- check_risk_limits: Kill switches (drawdown diario, pérdidas consecutivas)
- get_atr: Cálculo de ATR(14) desde datos Alpaca
"""

import json
from datetime import datetime, timedelta

from loguru import logger
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


def get_atr(
    data_client: StockHistoricalDataClient,
    symbol: str,
    period: int = 14,
) -> float:
    """
    Calcula ATR(14) desde datos de velas diarias Alpaca (feed IEX).

    ATR = media del True Range en los últimos `period` días.
    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))

    Returns:
        float: Valor ATR actual. 0.0 si no hay datos suficientes.
    """
    end = datetime.now()
    start = end - timedelta(days=period * 3)  # folio holgado

    bars = data_client.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed="iex",
        )
    )
    df = bars.df
    if isinstance(df.index, pd.MultiIndex):
        df = df.droplevel(0)

    if len(df) < period + 1:
        logger.warning(f"Pocos datos ({len(df)}) para ATR({period})")
        return 0.0

    df["prev_close"] = df["close"].shift(1)
    df["tr"] = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["prev_close"]).abs(),
            (df["low"] - df["prev_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = df["tr"].rolling(period).mean().iloc[-1]
    logger.info(f"ATR({period}) {symbol}: {atr:.2f}")
    return float(atr)


def calculate_position_size(
    account,
    atr_value: float,
    risk_pct: float = 0.02,
    stop_multiplier: float = 2.0,
) -> int:
    """
    Calcula tamaño de posición según riesgo fijo.

    Regla (doc 05, 5.2.3):
      risk_amount = equity * risk_pct       (ej: 100k * 2% = $2,000)
      stop_distance = atr * stop_multiplier  (ej: $2.50 * 2 = $5.00)
      shares = risk_amount / stop_distance   (ej: 2000 / 5.0 = 400)

    Args:
        account: Cuenta Alpaca (con .equity, .buying_power).
        atr_value: ATR actual del símbolo.
        risk_pct: Porcentaje del capital a arriesgar (default 2%).
        stop_multiplier: Multiplicador de ATR para stop loss (default 2).

    Returns:
        int: Número de acciones (entero, redondeado hacia abajo).
    """
    equity = float(account.equity)
    buying_power = float(account.buying_power)

    if atr_value <= 0 or equity <= 0:
        logger.warning("ATR o equity inválidos — usando 1 acción")
        return 1

    risk_amount = equity * risk_pct
    stop_distance = atr_value * stop_multiplier
    shares = int(risk_amount / stop_distance)

    # No usar más del 95% del poder de compra
    price_est = float(account.last_equity or equity) / 100  # fallback burdo
    max_by_bp = int(buying_power * 0.95 / max(price_est, 1))

    shares = min(shares, max_by_bp, 10_000)
    shares = max(shares, 1)  # mínimo 1 acción

    logger.info(
        f"Position size: {shares} acc | "
        f"Equity=${equity:.0f} | "
        f"Risk=${risk_amount:.0f} | "
        f"StopDist=${stop_distance:.2f} | "
        f"ATR={atr_value:.2f}"
    )
    return shares


def check_risk_limits(
    account,
    initial_equity: float,
    consecutive_losses: int,
    max_daily_loss_pct: float = 0.03,
    max_consecutive_losses: int = 5,
) -> tuple[bool, str]:
    """
    Evalúa kill switches antes de cada operación.

    Reglas (doc 05, 5.2.3):
      1. Drawdown diario > max_daily_loss_pct (default 3%) → KILL
      2. Pérdidas consecutivas > max_consecutive_losses (default 5) → KILL

    Lee ``logs/alert_thresholds.json`` al inicio para sobreescribir los
    valores por defecto si el archivo existe y tiene las claves esperadas.

    Args:
        account: Cuenta Alpaca (con .equity).
        initial_equity: Capital al inicio de la sesión.
        consecutive_losses: Contador de pérdidas consecutivas.
        max_daily_loss_pct: Máxima pérdida diaria permitida (default 3%).
        max_consecutive_losses: Máximo de pérdidas seguidas (default 5).

    Returns:
        tuple[bool, str]: (kill_activated, reason).
        kill_activated=True → el bot debe cerrar todo y detenerse.
    """
    # ── Read user-configured thresholds if available ─────────────────
    try:
        with open("logs/alert_thresholds.json", "r") as _f:
            _thresholds = json.load(_f)
        if "max_daily_drawdown_pct" in _thresholds:
            max_daily_loss_pct = float(_thresholds["max_daily_drawdown_pct"]) / 100.0
        if "max_consecutive_losses" in _thresholds:
            max_consecutive_losses = int(_thresholds["max_consecutive_losses"])
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    current_equity = float(account.equity)
    daily_loss_pct = (initial_equity - current_equity) / initial_equity

    logger.info(
        f"Risk check — Equity: ${current_equity:.0f} | "
        f"DD diario: {daily_loss_pct*100:.2f}% | "
        f"Losses seguidas: {consecutive_losses}"
    )

    if daily_loss_pct > max_daily_loss_pct:
        reason = (
            f"KILL SWITCH — Drawdown diario {daily_loss_pct*100:.1f}% "
            f"excede límite {max_daily_loss_pct*100:.0f}%"
        )
        logger.error(reason)
        return True, reason

    if consecutive_losses >= max_consecutive_losses:
        reason = (
            f"KILL SWITCH — {consecutive_losses} pérdidas consecutivas "
            f"alcanzó límite {max_consecutive_losses}"
        )
        logger.error(reason)
        return True, reason

    return False, "OK"
