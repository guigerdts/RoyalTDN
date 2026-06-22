"""
RoyalTDN — Entry Point Principal (Fase 4+)

Arquitectura modular: DataIngestor + SMAStrategy + Orchestrator.

Comandos:
    check                Probar conexión Alpaca Paper
    run                  Iniciar bot + consola interactiva
    status               Mostrar estado actual del bot
    logs                 Mostrar últimas líneas de log
    pause                Pausar el bot
    resume               Reanudar el bot
    scanner              Disparar scanner manual
"""

import asyncio
import os
import sys
import threading
from typing import Dict

from dotenv import load_dotenv
from loguru import logger

from alpaca.trading.client import TradingClient

from royaltdn.brokers.alpaca import AlpacaBroker
from royaltdn.brokers.base import BaseBroker
from royaltdn.brokers.binance import BinanceBroker
from royaltdn.frontend.console.loguru_config import setup_logging
from royaltdn.orchestrator import Orchestrator

# ── Configuración ──────────────────────────────────────────────────────────

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_SECRET_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "")
SYMBOL = "SPY"
AUTO_EXECUTE = os.getenv("AUTO_EXECUTE", "false").lower() == "true"
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "5"))


# ── Comando: check ─────────────────────────────────────────────────────────

def cmd_check():
    """Prueba la conexión con Alpaca Paper."""
    setup_logging()
    if not API_KEY or not API_SECRET:
        logger.error("ALPACA_API_KEY y ALPACA_SECRET_KEY deben estar en .env")
        sys.exit(1)

    client = TradingClient(API_KEY, API_SECRET, paper=True)
    account = client.get_account()

    logger.info("=== Conexión Alpaca Paper exitosa ===")
    logger.info("  Estado:       {}", account.status.value)
    logger.info("  Capital:      ${:.2f}", float(account.equity))
    logger.info("  Poder compra: ${:.2f}", float(account.buying_power))
    logger.info("  PDT:          {}", account.pattern_day_trader)
    return account


# ── Comando: status ────────────────────────────────────────────────────────

def cmd_status():
    """One-shot dashboard render from JSON files using inline Rich components."""
    from rich import print as rprint
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from royaltdn.frontend.console.components.state import StateLoader
    from royaltdn.frontend.console.log_handler import LogBuffer

    loader = StateLoader()
    state = loader.load_all()
    status = state.get("status", {})
    account = state.get("account", {})
    signals = state.get("signals", [])
    trades = state.get("trades", {})

    # ── Bot status block ──────────────────────────────────────────────
    status_table = Table.grid(padding=(0, 2))
    status_table.add_column(style="bold cyan")
    status_table.add_column(style="white")
    status_table.add_row("Bot Status", status.get("bot_status", "OFFLINE"))
    status_table.add_row("Mode", status.get("mode", "paper"))
    status_table.add_row("Uptime", status.get("uptime", "0:00:00"))
    status_table.add_row("Last Scan", str(status.get("last_scan", "\u2014")))
    if account:
        status_table.add_row("Capital", f"${account.get('equity', 0):,.2f}")
        status_table.add_row("Buying Power", f"${account.get('buying_power', 0):,.2f}")

    # ── Recent signals ────────────────────────────────────────────────
    if isinstance(signals, list) and signals:
        sig_table = Table(title="Recent Signals", box=None, padding=(0, 1))
        sig_table.add_column("Symbol", style="cyan")
        sig_table.add_column("Signal", style="yellow")
        sig_table.add_column("Confidence", style="green")
        for s in signals[:5]:
            sig_table.add_row(
                s.get("symbol", "?"),
                s.get("signal", "?"),
                str(s.get("confidence", "\u2014")),
            )
    else:
        sig_table = None

    # ── Recent trades ─────────────────────────────────────────────────
    trade_list = trades.get("trades", [])
    if isinstance(trade_list, list) and trade_list:
        tr_table = Table(title="Recent Trades (last 5)", box=None, padding=(0, 1))
        tr_table.add_column("Symbol", style="cyan")
        tr_table.add_column("Side", style="yellow")
        tr_table.add_column("Qty", style="white")
        tr_table.add_column("Price", style="green")
        tr_table.add_column("P&L", style="bold")
        for t in trade_list[-5:]:
            pnl = t.get("pnl", 0)
            pnl_str = f"${pnl:+.2f}" if isinstance(pnl, (int, float)) else "\u2014"
            tr_table.add_row(
                t.get("symbol", "?"),
                t.get("side", "?"),
                str(t.get("qty", "\u2014")),
                f"${t.get('price', 0):,.2f}" if t.get("price") else "\u2014",
                pnl_str,
            )
    else:
        tr_table = None

    # ── Assemble ──────────────────────────────────────────────────────
    elements = [Panel(status_table, title="Status", border_style="blue")]
    if sig_table:
        elements.append(sig_table)
    if tr_table:
        elements.append(tr_table)

    rprint(Group(*elements))

    bot_status = status.get("bot_status", "OFFLINE")
    if bot_status == "OFFLINE":
        sys.exit(1)


# ── Comando: logs ──────────────────────────────────────────────────────────

def cmd_logs():
    """Show last 50 lines of bot.log with syntax highlighting."""
    from rich.console import Console
    from pathlib import Path

    log_file = Path("logs/bot.log")
    if not log_file.exists():
        print("No hay logs aún.")
        return

    console = Console()
    lines = log_file.read_text().splitlines()
    for line in lines[-50:]:
        styled = line
        if "CRITICAL" in line:
            styled = f"[bold red]{line}[/]"
        elif "ERROR" in line:
            styled = f"[red]{line}[/]"
        elif "WARNING" in line or "WARN" in line:
            styled = f"[yellow]{line}[/]"
        elif "INFO" in line:
            styled = f"[green]{line}[/]"
        elif "DEBUG" in line:
            styled = f"[dim]{line}[/]"
        console.print(styled)


# ── Comando: pause ─────────────────────────────────────────────────────────

def cmd_pause():
    """Send pause signal to the bot."""
    from royaltdn.frontend.console.commands import pause_bot
    pause_bot()
    print("✅ Señal de pausa enviada. El bot se pausará en el próximo ciclo.")


# ── Comando: resume ────────────────────────────────────────────────────────

def cmd_resume():
    """Send resume signal to the bot."""
    from royaltdn.frontend.console.commands import resume_bot
    resume_bot()
    print("✅ Señal de reanudación enviada.")


# ── Comando: scanner ───────────────────────────────────────────────────────

def cmd_scanner():
    """Trigger scanner manually."""
    from royaltdn.frontend.console.commands import trigger_scanner
    trigger_scanner()
    print("✅ Scanner disparado. Los resultados aparecerán en el próximo ciclo.")

def _load_seed_trades() -> None:
    """Copy mock trades from tests/fixtures/ into logs/trades.json."""
    import json
    from pathlib import Path

    src = Path("tests/fixtures/mock_trades.json")
    dst = Path("logs/trades.json")
    if not src.exists():
        logger.warning("Seed trades no encontrado en {}", src)
        return
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Seed trades cargados: {} trades sintéticos en {}", data.get("total_trades", 0), dst)
    except Exception as e:
        logger.warning("Error cargando seed trades: {}", e)


# ── Comando: check-readiness ──────────────────────────────────────────────


def cmd_check_readiness():
    """6 independent checks for real-money readiness.

    Uses StateLoader for JSON reads, Alpaca/Binance clients directly.
    Exits with code 0 (READY), 1 (CASI LISTO), or 2 (NO RECOMENDADO).
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from royaltdn.frontend.console.components.state import StateLoader

    console = Console(color_system="standard")
    loader = StateLoader()
    checks: list[dict] = []

    # 1. Trades suficientes
    try:
        trades_data = loader.load_trades()
        trades_list = trades_data.get("trades", [])
        n_trades = len(trades_list)
        passed = n_trades >= 50
        checks.append({
            "name": "Trades suficientes",
            "passed": passed,
            "detail": f"{n_trades}/50 trades",
            "severity": "critical",
        })
    except Exception as e:
        checks.append({
            "name": "Trades suficientes",
            "passed": False,
            "detail": f"Error: {e}",
            "severity": "critical",
        })

    # 2. Sharpe reciente
    try:
        equity_data = loader._load_file("equity.json", {})
        sharpe = float(equity_data.get("sharpe", 0))
        passed = sharpe > 0.5
        checks.append({
            "name": "Sharpe reciente",
            "passed": passed,
            "detail": f"Sharpe={sharpe:.2f} {'> 0.5' if passed else '<= 0.5'}",
            "severity": "critical",
        })
    except Exception as e:
        checks.append({
            "name": "Sharpe reciente",
            "passed": False,
            "detail": f"Error: {e}",
            "severity": "critical",
        })

    # 3. Slippage aceptable
    try:
        trades_data = loader.load_trades()
        trades_list = trades_data.get("trades", [])
        slippages = []
        for t in trades_list:
            s = t.get("slippage_bps", None)
            if s is not None:
                slippages.append(float(s))
        avg_slippage = sum(slippages) / len(slippages) if slippages else 0
        passed = avg_slippage < 50 if slippages else True
        checks.append({
            "name": "Slippage aceptable",
            "passed": passed,
            "detail": f"{avg_slippage:.1f} bps promedio {'< 50' if passed else '>= 50'}",
            "severity": "critical",
        })
    except Exception as e:
        checks.append({
            "name": "Slippage aceptable",
            "passed": False,
            "detail": f"Error: {e}",
            "severity": "critical",
        })

    # 4. Kill switch probado
    try:
        from pathlib import Path
        log_text = Path("logs/bot.log").read_text(encoding="utf-8")
        found = "KILL SWITCH" in log_text or "drawdown >" in log_text
        checks.append({
            "name": "Kill switch probado",
            "passed": found,
            "detail": "Encontrado en bot.log" if found else "No encontrado en bot.log",
            "severity": "critical",
        })
    except Exception as e:
        checks.append({
            "name": "Kill switch probado",
            "passed": False,
            "detail": f"Error: {e}",
            "severity": "critical",
        })

    # 5. Telegram funciona
    try:
        from pathlib import Path
        log_text = Path("logs/bot.log").read_text(encoding="utf-8")
        found = "Telegram enviado" in log_text
        checks.append({
            "name": "Telegram funciona",
            "passed": found,
            "detail": "Encontrado en bot.log" if found else "No encontrado en bot.log",
            "severity": "warning",
        })
    except Exception as e:
        checks.append({
            "name": "Telegram funciona",
            "passed": False,
            "detail": f"Error: {e}",
            "severity": "warning",
        })

    # 6. Broker conectividad
    alpaca_ok = False
    binance_ok = False
    try:
        from alpaca.trading.client import TradingClient
        tc = TradingClient(API_KEY, API_SECRET, paper=True)
        tc.get_account()
        alpaca_ok = True
    except Exception as e:
        alpaca_detail = f"Alpaca: {e}"
    try:
        binance_key = os.getenv("BINANCE_API_KEY", "")
        binance_secret = os.getenv("BINANCE_SECRET_KEY", "")
        if binance_key:
            from royaltdn.brokers.binance import BinanceBroker
            bb = BinanceBroker(binance_key, binance_secret, testnet=True)
            bb.get_account_balance()
            binance_ok = True
        else:
            binance_ok = True  # No Binance configured = OK (not needed)
    except Exception as e:
        binance_detail = f"Binance: {e}"

    detail_parts = []
    if alpaca_ok:
        detail_parts.append("Alpaca OK")
    else:
        detail_parts.append(alpaca_detail)
    if binance_ok:
        detail_parts.append("Binance OK")
    else:
        detail_parts.append(binance_detail)

    checks.append({
        "name": "Broker conectividad",
        "passed": alpaca_ok,
        "detail": " | ".join(detail_parts),
        "severity": "critical",
    })

    # ── Render panel ─────────────────────────────────────────────────
    n_critical_fail = sum(1 for c in checks if not c["passed"] and c["severity"] == "critical")
    n_warning_fail = sum(1 for c in checks if not c["passed"] and c["severity"] == "warning")

    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold white")
    for c in checks:
        icon = "✅" if c["passed"] else "❌"
        name_style = "green" if c["passed"] else "red"
        detail_text = f"\n  [dim]{c['detail']}[/]" if not c["passed"] else ""
        table.add_row(
            Text.assemble(
                (f"{icon} ", ""),
                (c["name"], name_style),
                (detail_text, ""),
            )
        )

    if n_critical_fail == 0 and n_warning_fail == 0:
        verdict = Text("✅ READY — Todas las verificaciones OK", style="bold green")
        exit_code = 0
    elif n_critical_fail == 0:
        verdict = Text(f"⚠️ CASI LISTO — {n_warning_fail} pendiente(s)", style="bold yellow")
        exit_code = 1
    else:
        verdict = Text("❌ NO RECOMENDADO — Pruebas insuficientes", style="bold red")
        exit_code = 2

    console.print()
    console.print(Panel(table, title="🔍 Verificación de Readiness", border_style="white"))
    console.print()
    console.print(verdict)
    sys.exit(exit_code)


# ── Comando: run ───────────────────────────────────────────────────────────


def cmd_run():
    """Arranca el bot con arquitectura modular + consola interactiva."""
    setup_logging()

    # ── Parse extra flags ────────────────────────────────────────────
    seed_trades = "--seed-trades" in sys.argv[2:]
    if seed_trades:
        _load_seed_trades()
    verbose = "--verbose" in sys.argv[2:]

    if not API_KEY or not API_SECRET:
        logger.error("ALPACA_API_KEY y ALPACA_SECRET_KEY deben estar en .env")
        sys.exit(1)

    logger.info("=" * 50)
    logger.info("RoyalTDN — Arquitectura Modular (Fase 4)")
    logger.info("  Símbolo:     {}", SYMBOL)
    logger.info("  Estrategia:  SMA5/SMA20")
    logger.info("  Broker:      Alpaca Paper (IEX)")
    logger.info("  Redis:       {}", REDIS_URL)
    logger.info("  TimescaleDB: {}", "SÍ" if DATABASE_URL else "NO")
    logger.info("  Seed trades: {}", "SÍ" if seed_trades else "NO")
    logger.info("=" * 50)

    # ── Reconfigurar Loguru: stderr solo WARNING+ para no ensuciar el menú ──
    logger.remove()  # quitar todos los sinks (file + stderr)
    logger.add(
        "logs/bot.log", rotation="10 MB", retention="7 days",
        level="INFO", encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss,SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
    )
    logger.add(
        sys.stderr, colorize=True, level="WARNING",
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<level>{message}</level>"
        ),
    )

    from royaltdn.frontend.menu.app import run_menu

    # ── Brokers: Alpaca (stocks) + Binance (crypto) ──
    alpaca_broker = AlpacaBroker(API_KEY, API_SECRET, paper=True)
    brokers: Dict[str, BaseBroker] = {"stocks": alpaca_broker}

    binance_api_key = os.getenv("BINANCE_API_KEY", "")
    binance_secret = os.getenv("BINANCE_SECRET_KEY", "")
    binance_testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    if binance_api_key:
        binance_broker = BinanceBroker(binance_api_key, binance_secret, testnet=binance_testnet)
        brokers["crypto"] = binance_broker
        logger.info("BinanceBroker configurado para crypto (testnet={})", binance_testnet)

    # ── Scanner: inicializar antes del Orchestrator ──
    scanner = None
    try:
        from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
        from royaltdn.scanner import AssetUniverse, LiquidityFilter, Scanner
        from royaltdn.strategy.sma_strategy import SMAStrategy
        from royaltdn.strategy.bollinger_rsi import BollingerRSIStrategy
        from royaltdn.strategy.momentum_atr import MomentumATRStrategy
        from royaltdn.strategy.factor_rotation import FactorRotationStrategy
        from royaltdn.strategy.scalping_momentum import ScalpingMomentumStrategy
        from royaltdn.strategy.scalping_breakout import ScalpingBreakoutStrategy
        from royaltdn.strategy.scalping_reversion import ScalpingReversionStrategy
        from royaltdn.strategy.scalping_orderflow import ScalpingOrderFlowStrategy
        from royaltdn.strategy.scalping_spread import ScalpingSpreadStrategy
        from royaltdn.strategy.intraday_trend import IntradayTrendStrategy
        from royaltdn.strategy.intraday_vwap import IntradayVWAPStrategy
        from royaltdn.strategy.intraday_volume_breakout import IntradayVolumeBreakoutStrategy
        from royaltdn.strategy.intraday_support_resistance import IntradaySupportResistanceStrategy
        from royaltdn.strategy.intraday_macd_divergence import IntradayMACDDivergenceStrategy
        from royaltdn.strategy.swing_trend_following import SwingTrendFollowingStrategy
        from royaltdn.strategy.swing_reversion import SwingReversionStrategy
        from royaltdn.strategy.swing_breakout import SwingBreakoutStrategy

        data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
        crypto_client = CryptoHistoricalDataClient(API_KEY, API_SECRET)
        broker_type = "binance" if os.getenv("BINANCE_API_KEY") else "alpaca"
        universe = AssetUniverse(
            API_KEY, API_SECRET,
            universe_type=os.getenv("SCANNER_UNIVERSE", "all"),
            broker_type=broker_type,
        )
        # Crypto universe needs laxer defaults — low-price pairs, no spread data
        _crypto_mode = os.getenv("SCANNER_UNIVERSE", "all") == "crypto"
        liquidity_filter = LiquidityFilter(
            min_volume=int(os.getenv(
                "SCANNER_MIN_VOLUME", "1000" if _crypto_mode else "100000",
            )),
            min_price=float(os.getenv(
                "SCANNER_MIN_PRICE", "1.0" if _crypto_mode else "5.0",
            )),
            max_spread_pct=float(os.getenv(
                "SCANNER_MAX_SPREAD_PCT", "999" if _crypto_mode else "1.0",
            )),
            brokers=brokers,
        )
        strategies = {}
        strategies_enabled = os.getenv(
            "STRATEGIES_ENABLED", "sma_crossover,bollinger_rsi,momentum_atr,factor_rotation,scalping_momentum,scalping_breakout,scalping_reversion,scalping_orderflow,scalping_spread,intraday_trend,intraday_vwap,intraday_volume_breakout,intraday_support_resistance,intraday_macd_divergence,swing_trend_following,swing_reversion,swing_breakout"
        ).split(",")
        if "sma_crossover" in strategies_enabled:
            strategies["sma_crossover"] = SMAStrategy()
        if "bollinger_rsi" in strategies_enabled:
            strategies["bollinger_rsi"] = BollingerRSIStrategy()
        if "momentum_atr" in strategies_enabled:
            strategies["momentum_atr"] = MomentumATRStrategy()
        if "factor_rotation" in strategies_enabled:
            strategies["factor_rotation"] = FactorRotationStrategy()
        if "scalping_momentum" in strategies_enabled:
            strategies["scalping_momentum"] = ScalpingMomentumStrategy()
        if "scalping_breakout" in strategies_enabled:
            strategies["scalping_breakout"] = ScalpingBreakoutStrategy()
        if "scalping_reversion" in strategies_enabled:
            strategies["scalping_reversion"] = ScalpingReversionStrategy()
        if "scalping_orderflow" in strategies_enabled:
            strategies["scalping_orderflow"] = ScalpingOrderFlowStrategy()
        if "scalping_spread" in strategies_enabled:
            strategies["scalping_spread"] = ScalpingSpreadStrategy()
        if "intraday_trend" in strategies_enabled:
            strategies["intraday_trend"] = IntradayTrendStrategy()
        if "intraday_vwap" in strategies_enabled:
            strategies["intraday_vwap"] = IntradayVWAPStrategy()
        if "intraday_volume_breakout" in strategies_enabled:
            strategies["intraday_volume_breakout"] = IntradayVolumeBreakoutStrategy()
        if "intraday_support_resistance" in strategies_enabled:
            strategies["intraday_support_resistance"] = IntradaySupportResistanceStrategy()
        if "intraday_macd_divergence" in strategies_enabled:
            strategies["intraday_macd_divergence"] = IntradayMACDDivergenceStrategy()
        if "swing_trend_following" in strategies_enabled:
            strategies["swing_trend_following"] = SwingTrendFollowingStrategy()
        if "swing_reversion" in strategies_enabled:
            strategies["swing_reversion"] = SwingReversionStrategy()
        if "swing_breakout" in strategies_enabled:
            strategies["swing_breakout"] = SwingBreakoutStrategy()

        scanner = Scanner(
            universe, liquidity_filter, strategies, data_client,
            crypto_data_client=crypto_client,
            brokers=brokers,
        )
        scanner.verbose = verbose
        logger.info(
            "Scanner inicializado desde main — universo={} estrategias={}",
            os.getenv("SCANNER_UNIVERSE", "all"),
            list(strategies.keys()),
        )
    except Exception as e:
        logger.warning("Scanner no disponible desde main ({})", e)

    if scanner is not None:
        from royaltdn.frontend.menu.app import set_universe_setter, set_scanner
        set_universe_setter(lambda ut: setattr(scanner.universe, 'universe_type', ut))
        set_scanner(scanner)

    orch = Orchestrator(
        api_key=API_KEY,
        secret_key=API_SECRET,
        redis_url=REDIS_URL,
        db_url=DATABASE_URL,
        symbol=SYMBOL,
        scanner=scanner,
        auto_execute=AUTO_EXECUTE,
        max_positions=MAX_POSITIONS,
        brokers=brokers,
    )

    def _run_orchestrator():
        asyncio.run(orch.start())

    t = threading.Thread(target=_run_orchestrator, daemon=True)
    t.start()

    try:
        run_menu()
    finally:
        orch.stop()
        logger.info("🛑 Bot detenido.")


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    load_dotenv()

    if len(sys.argv) < 2:
        print("Uso: python -m royaltdn <comando>")
        print("")
        print("Comandos:")
        print("  run         Iniciar bot + consola interactiva")
        print("  status      Mostrar estado actual del bot")
        print("  logs        Mostrar últimas líneas de log")
        print("  pause       Pausar el bot")
        print("  resume      Reanudar el bot")
        print("  scanner     Disparar scanner manual")
        print("  check            Verificar configuración")
        print("  check-readiness  Verificar preparación para dinero real")
        sys.exit(1)

    cmd = sys.argv[1]
    commands = {
        "run": cmd_run,
        "status": cmd_status,
        "logs": cmd_logs,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "scanner": cmd_scanner,
        "check": cmd_check,
        "check-readiness": cmd_check_readiness,
    }

    if cmd not in commands:
        print(f"Comando desconocido: {cmd}")
        print("Use: python -m royaltdn <comando>")
        sys.exit(1)

    commands[cmd]()


if __name__ == "__main__":
    main()
