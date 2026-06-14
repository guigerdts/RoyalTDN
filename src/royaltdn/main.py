"""
RoyalTDN — Entry Point Principal (Fase 3)

Bot de Paper Trading con SMA Crossover + Risk Manager + TimescaleDB.

Comandos:
    check    Probar conexión Alpaca Paper
    run      Ejecutar bot con risk manager y alertas
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from royaltdn.risk_manager import (
    calculate_position_size,
    check_risk_limits,
    get_atr,
)
from royaltdn.alerts import notify_entry, notify_exit, notify_kill_switch, notify_error
from royaltdn.storage.db import Database

# ── Configuración ──────────────────────────────────────────────────────────────

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_SECRET_KEY")
SYMBOL = "SPY"
FAST_MA = 5
SLOW_MA = 20
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("royaltdn")


# ── Estado global del bot ──────────────────────────────────────────────────────

class BotState:
    """Estado compartido del bot entre ciclos."""

    def __init__(self):
        self.position: str | None = None  # 'long' | None
        self.position_qty: int = 0
        self.last_entry_price: float = 0.0
        self.last_entry_order_id: str | None = None
        self.last_entry_at = None  # datetime
        self.initial_equity: float = 0.0
        self.consecutive_losses: int = 0
        self.trades_count: int = 0
        self.killed: bool = False
        self.db: Database | None = None


state = BotState()


# ── Comando: check ─────────────────────────────────────────────────────────────

def cmd_check():
    """Prueba la conexión con Alpaca Paper (doc 04, 4.0.6)."""
    if not API_KEY or not API_SECRET:
        logger.error("ALPACA_API_KEY y ALPACA_SECRET_KEY deben estar en .env")
        sys.exit(1)

    client = TradingClient(API_KEY, API_SECRET, paper=True)
    account = client.get_account()

    logger.info("=== Conexión Alpaca Paper exitosa ===")
    logger.info(f"  Estado:       {account.status.value}")
    logger.info(f"  Capital:      ${float(account.equity):,.2f}")
    logger.info(f"  Poder compra: ${float(account.buying_power):,.2f}")
    logger.info(f"  PDT:          {account.pattern_day_trader}")
    return account


# ── Señal SMA ──────────────────────────────────────────────────────────────────

async def get_signal(data_client: StockHistoricalDataClient) -> int:
    """Calcula señal SMA crossover (doc 04, 4.1.2)."""
    end = datetime.now()
    start = end - timedelta(days=60)

    bars = data_client.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=SYMBOL,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed="iex",
        )
    )
    df = bars.df
    if isinstance(df.index, pd.MultiIndex):
        df = df.droplevel(0)

    df["SMA5"] = df["close"].rolling(FAST_MA).mean()
    df["SMA20"] = df["close"].rolling(SLOW_MA).mean()

    if len(df) < SLOW_MA:
        logger.warning(f"Pocos datos ({len(df)} bars) para SMA{SLOW_MA}")
        return 0

    if df["SMA5"].iloc[-1] > df["SMA20"].iloc[-1]:
        return 1
    return 0


# ── Posición actual ────────────────────────────────────────────────────────────

async def get_current_position(trading_client) -> tuple[str | None, int]:
    """Sincroniza posición real desde el broker."""
    try:
        pos = trading_client.get_open_position(SYMBOL)
        qty = float(pos.qty)
        if qty > 0:
            return "long", int(qty)
        elif qty < 0:
            return "short", int(abs(qty))
    except Exception:
        pass
    return None, 0


async def get_current_price(data_client) -> float:
    """Obtiene el último precio de cierre."""
    try:
        bars = data_client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=SYMBOL,
                timeframe=TimeFrame.Day,
                start=datetime.now() - timedelta(days=5),
                end=datetime.now(),
                feed="iex",
            )
        )
        df = bars.df
        if isinstance(df.index, pd.MultiIndex):
            df = df.droplevel(0)
        return float(df["close"].iloc[-1])
    except Exception:
        return 0.0


# ── Órdenes ────────────────────────────────────────────────────────────────────

async def submit_order(
    trading_client, side: OrderSide, qty: int, db: Database | None = None,
) -> object | None:
    """Envía orden de mercado y la registra en DB."""
    if qty <= 0:
        logger.warning(f"Qty {qty} inválida — orden cancelada")
        return None

    order = trading_client.submit_order(
        MarketOrderRequest(
            symbol=SYMBOL,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
    )
    logger.info(f"📤 Orden: {side.name} {qty} {SYMBOL} — ID: {order.id}")

    # Registrar en DB
    if db and db.is_connected:
        await db.insert_order({
            "order_id": order.id,
            "symbol": SYMBOL,
            "side": side.name,
            "qty": qty,
            "order_type": "market",
            "status": order.status if hasattr(order, 'status') else "new",
            "filled_price": float(order.filled_avg_price) if hasattr(order, 'filled_avg_price') and order.filled_avg_price else None,
            "filled_qty": int(order.filled_qty) if hasattr(order, 'filled_qty') and order.filled_qty else None,
            "created_at": datetime.now(),
        })

    return order


# ── Bucle principal ────────────────────────────────────────────────────────────

async def run_bot():
    """Bucle principal con risk manager + alertas (Fase 2)."""
    global state

    if not API_KEY or not API_SECRET:
        logger.error("ALPACA_API_KEY y ALPACA_SECRET_KEY deben estar en .env")
        sys.exit(1)

    trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
    data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

    # Inicializar DB (opcional — funciona sin TimescaleDB)
    if DATABASE_URL:
        state.db = Database(DATABASE_URL)
        connected = await state.db.connect()
        if not connected:
            logger.warning("TimescaleDB no disponible — trades solo en logs")
    else:
        logger.info("DATABASE_URL no configurada — saltando persistencia")

    # Sincronizar estado inicial
    account = trading_client.get_account()
    state.initial_equity = float(account.equity)
    pos, qty = await get_current_position(trading_client)
    state.position = pos
    state.position_qty = qty
    state.killed = False

    logger.info(f"Bot iniciado — Capital: ${state.initial_equity:,.2f}")
    logger.info(f"Posición inicial: {state.position} ({state.position_qty} acc)")

    while not state.killed:
        try:
            # ── Señal ──
            signal = await get_signal(data_client)

            # ── Risk check (pérdidas consecutivas) ──
            kill, reason = check_risk_limits(
                trading_client.get_account(),
                state.initial_equity,
                state.consecutive_losses,
            )
            if kill:
                notify_kill_switch(reason)
                logger.error(f"🛑 {reason}")

                # Cerrar posición si existe
                if state.position == "long" and state.position_qty > 0:
                    await submit_order(trading_client, OrderSide.SELL, state.position_qty)

                state.killed = True
                break

            # ── Lógica de trading ──
            logger.info(
                f"Señal: {signal} | Pos: {state.position} "
                f"({state.position_qty}) | Losses: {state.consecutive_losses}"
            )

            current_price = await get_current_price(data_client)

            if signal == 1 and state.position != "long":
                # ── ENTRADA LARGA ──
                # Calcular ATR y tamaño de posición
                atr = get_atr(data_client, SYMBOL)
                account = trading_client.get_account()
                qty = calculate_position_size(account, atr)

                if state.position == "short":
                    await submit_order(trading_client, OrderSide.BUY, state.position_qty)
                    await asyncio.sleep(2)

                entry_order = await submit_order(trading_client, OrderSide.BUY, qty, state.db)
                state.position = "long"
                state.position_qty = qty
                state.last_entry_price = current_price
                state.last_entry_order_id = entry_order.id if entry_order else None
                state.last_entry_at = datetime.now()

                if current_price > 0:
                    notify_entry(SYMBOL, "buy", qty, current_price)

            elif signal == 0 and state.position == "long":
                # ── SALIDA ──
                exit_order = await submit_order(trading_client, OrderSide.SELL, state.position_qty, state.db)

                # Calcular P&L
                pnl = (current_price - state.last_entry_price) * state.position_qty
                if current_price > 0:
                    notify_exit(SYMBOL, "sell", state.position_qty, current_price, pnl)

                # Registrar trade en DB
                if state.db and state.db.is_connected and state.last_entry_at:
                    await state.db.insert_trade({
                        "symbol": SYMBOL,
                        "side": "long",
                        "entry_price": state.last_entry_price,
                        "exit_price": current_price,
                        "qty": state.position_qty,
                        "pnl": pnl,
                        "entry_order_id": state.last_entry_order_id,
                        "exit_order_id": exit_order.id if exit_order else None,
                        "entry_at": state.last_entry_at,
                        "exit_at": datetime.now(),
                        "strategy": "sma_crossover",
                    })

                # Actualizar contador de pérdidas consecutivas
                if pnl < 0:
                    state.consecutive_losses += 1
                else:
                    state.consecutive_losses = 0

                state.trades_count += 1
                state.position = None
                state.position_qty = 0

            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Error en bucle principal: {e}", exc_info=True)
            notify_error(str(e))
            await asyncio.sleep(10)

    # ── Cerrar DB ──
    if state.db:
        await state.db.close()

    # ── Bot detenido ──
    account = trading_client.get_account()
    final_equity = float(account.equity)
    pnl_total = final_equity - state.initial_equity
    logger.info("=" * 50)
    logger.info("BOT DETENIDO")
    logger.info(f"  Capital inicial: ${state.initial_equity:,.2f}")
    logger.info(f"  Capital final:   ${final_equity:,.2f}")
    logger.info(f"  P&L total:       ${pnl_total:,.2f}")
    logger.info(f"  Trades:          {state.trades_count}")
    logger.info(f"  Losses seguidas: {state.consecutive_losses}")
    logger.info("=" * 50)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Uso: python -m royaltdn <check|run>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "check":
        cmd_check()
    elif command == "run":
        asyncio.run(run_bot())
    else:
        print(f"Comando desconocido: {command}")
        print("Usa: check | run")
        sys.exit(1)


if __name__ == "__main__":
    main()
