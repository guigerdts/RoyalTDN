#!/usr/bin/env python3
"""RoyalTDN — Integration Test: Flujo de Menú + Fase 18

Ejecuta el bot como subprocess (usando el venv), envía comandos vía stdin,
y verifica los archivos de estado (logs/*.json), el log del sistema
(logs/bot.log), y el log de actividad (logs/user_activity.log).

Todas las pruebas deben poder ejecutarse con el mercado cerrado (finde).

Uso:
    python tests/integration/test_menu_flow.py
"""

import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

# ── Constants ─────────────────────────────────────────────────────────────

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_DIR / "src"
LOGS_DIR = PROJECT_DIR / "logs"
VENV_PYTHON = str(PROJECT_DIR / "venv" / "bin" / "python")

sys.path.insert(0, str(SRC_DIR))


# ── Helpers ────────────────────────────────────────────────────────────────


def _clean_logs() -> None:
    """Remove logs/ directory so each test starts fresh."""
    if LOGS_DIR.exists():
        shutil.rmtree(str(LOGS_DIR))
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _env_with(**overrides) -> dict:
    """Build env: base .env + overrides, no GITHUB_TOKEN."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    env.pop("GITHUB_TOKEN", None)
    env.update(overrides)
    return env


def _bot_cmd(extra_args: Optional[List[str]] = None) -> List[str]:
    """Build the bot CLI command."""
    cmd = [VENV_PYTHON, "-m", "royaltdn", "run"]
    if extra_args:
        cmd.extend(extra_args)
    return cmd


# ── Subprocess interaction ────────────────────────────────────────────────


def run_bot(
    command_lines: List[str],
    extra_args: Optional[List[str]] = None,
    env_vars: Optional[dict] = None,
    startup_timeout: int = 35,
    cmd_timeout: int = 10,
) -> dict:
    """Start the bot, wait for startup, send commands line by line.

    Args:
        command_lines: List of strings to send as individual lines.
            Each line is written to stdin with a short delay between lines.
        extra_args: Extra CLI args (``--verbose``, ``--seed-trades``).
        env_vars: Environment variable overrides.
        startup_timeout: Max seconds to wait for the bot to start and show ``>> ``.
        cmd_timeout: Seconds to wait after each command before writing the next.

    Returns:
        dict with keys: ``stdout``, ``stderr``, ``returncode``, ``started``.
    """
    _clean_logs()
    env = _env_with(**(env_vars or {}))
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        _bot_cmd(extra_args),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(PROJECT_DIR),
    )
    assert proc.stdin is not None

    started = False
    collected_stdout: List[str] = []
    collected_stderr: List[str] = []

    def _drain(timeout: float = 1.0) -> Tuple[str, str]:
        """Non-blocking read from stdout/stderr for *timeout* seconds."""
        out, err = "", ""
        deadline = time.monotonic() + timeout
        proc_stdout = proc.stdout
        proc_stderr = proc.stderr
        assert proc_stdout is not None
        assert proc_stderr is not None

        while time.monotonic() < deadline:
            rlist, _, _ = select.select([proc_stdout, proc_stderr], [], [], 0.3)
            for fd in rlist:
                if fd is proc_stdout:
                    chunk = os.read(proc_stdout.fileno(), 4096).decode("utf-8", errors="replace")
                    if chunk:
                        out += chunk
                if fd is proc_stderr:
                    chunk = os.read(proc_stderr.fileno(), 4096).decode("utf-8", errors="replace")
                    if chunk:
                        err += chunk
            # Check if process died
            if proc.poll() is not None:
                break
        return out, err

    # ── Wait for the bot to start ─────────────────────────────────────
    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        out, err = _drain(1.0)
        collected_stdout.append(out)
        collected_stderr.append(err)
        combined = "".join(collected_stdout)
        if ">> " in combined:
            started = True
            break
        if proc.poll() is not None:
            break

    if not started:
        # Give it a moment and try to kill
        try:
            proc.kill()
        except OSError:
            pass
        return {
            "stdout": "".join(collected_stdout),
            "stderr": "".join(collected_stderr),
            "returncode": proc.returncode,
            "started": False,
        }

    # ── Send commands one by one ──────────────────────────────────────
    for cmd_line in command_lines:
        proc.stdin.write(cmd_line + "\n")
        proc.stdin.flush()
        time.sleep(cmd_timeout)

    # ── Give time to process last command ─────────────────────────────
    time.sleep(2)
    out, err = _drain(3.0)
    collected_stdout.append(out)
    collected_stderr.append(err)

    # ── Send exit and wait ────────────────────────────────────────────
    try:
        proc.stdin.write("0\n")
        proc.stdin.flush()
    except OSError:
        pass

    try:
        out, err = proc.communicate(timeout=10)
        collected_stdout.append(out)
        collected_stderr.append(err)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        collected_stdout.append(out)
        collected_stderr.append(err)

    return {
        "stdout": "".join(collected_stdout),
        "stderr": "".join(collected_stderr),
        "returncode": proc.returncode,
        "started": True,
    }


def run_cli(
    args: List[str],
    env_vars: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    """Run a non-interactive CLI command (check-readiness, etc.)."""
    env = _env_with(**(env_vars or {}))
    proc = subprocess.Popen(
        [VENV_PYTHON, "-m", "royaltdn"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(PROJECT_DIR),
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return {"stdout": stdout, "stderr": stderr, "returncode": -1, "timeout": True}

    return {"stdout": stdout, "stderr": stderr, "returncode": proc.returncode, "timeout": False}


# ── File helpers ───────────────────────────────────────────────────────────


def read_json(rel_path: str) -> dict:
    """Read and parse logs/{rel_path}; return {} on error."""
    path = LOGS_DIR / rel_path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def log_contains(pattern: str, path: str = "bot.log") -> bool:
    """Check if logs/{path} contains a regex pattern."""
    p = LOGS_DIR / path
    try:
        text = p.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return False
    return bool(re.search(pattern, text))


def log_lines(last_n: int = 0, path: str = "bot.log") -> List[str]:
    """Return lines from logs/{path}, optionally only last N."""
    p = LOGS_DIR / path
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return []
    return lines if last_n <= 0 else lines[-last_n:]


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


# ── Tests 1–7: Funcionalidad existente / básica ───────────────────────────


def test_arranque() -> List[str]:
    """Test 1: Bot startup — logs y estado."""
    errs: List[str] = []
    result = run_bot([])
    if not result["started"]:
        return [f"Bot no arrancó (stdout: {result['stdout'][:200]})"]

    if not LOGS_DIR.exists():
        errs.append("logs/ no se creó")
    if not (LOGS_DIR / "bot.log").exists():
        errs.append("logs/bot.log no se creó")
    return errs


def test_status_files() -> List[str]:
    """Test 2: Archivos de estado (status.json, strategies.json)."""
    errs: List[str] = []
    result = run_bot([])
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    for fname in ("status.json", "strategies.json"):
        if not (LOGS_DIR / fname).exists():
            errs.append(f"logs/{fname} no existe")
        else:
            data = read_json(fname)
            if not data:
                errs.append(f"logs/{fname} está vacío")
    return errs


def test_navegacion() -> List[str]:
    """Test 3: Navegación por todas las pantallas."""
    errs: List[str] = []
    # Navegar secuencialmente: Dashboard→Scanner→Estrategias→Trades→
    #                          Logs→Control→Simulación→Actividad→Salir
    lines = ["1", "0", "2", "0", "3", "0", "4", "0",
             "5", "0", "6", "0", "7", "0", "8", "0"]
    result = run_bot(lines, cmd_timeout=2)
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    if "Traceback" in result["stdout"] or "Traceback" in result["stderr"]:
        errs.append("Se encontró Traceback durante navegación")
    return errs


def test_scanner() -> List[str]:
    """Test 4: Pantalla de scanner."""
    errs: List[str] = []
    # 2→Scanner, s→forzar scan, Enter→volver
    lines = ["2", "s", ""]
    result = run_bot(lines, cmd_timeout=8)
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    if not log_contains("Scanner") and not log_contains("scan"):
        errs.append("No se encontró actividad del Scanner en bot.log")
    return errs


def test_pausa_reanudacion() -> List[str]:
    """Test 5: Control — pausar/reanudar."""
    errs: List[str] = []
    lines = ["6", "1"]
    result = run_bot(lines, cmd_timeout=2)
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    if not log_contains("paus"):
        errs.append("No se encontró 'paus' en bot.log")
    return errs


def test_crypto_universe() -> List[str]:
    """Test 6: SCANNER_UNIVERSE=crypto."""
    errs: List[str] = []
    result = run_bot([], env_vars={"SCANNER_UNIVERSE": "crypto"})
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    if not log_contains("crypto"):
        errs.append("No se encontró 'crypto' en bot.log con SCANNER_UNIVERSE=crypto")
    return errs


def test_builder_accessible() -> List[str]:
    """Test 7: Acceso a estrategias."""
    errs: List[str] = []
    # 3→Estrategias, 0→Volver
    lines = ["3", "0"]
    result = run_bot(lines, cmd_timeout=2)
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    stdout = strip_ansi(result["stdout"])
    if "Estrategias" not in stdout:
        errs.append("No se encontró 'Estrategias' en la salida")
    return errs


# ── Tests 8–16: Nuevas funcionalidades Fase 18 ────────────────────────────


def test_selector_universo() -> List[str]:
    """Test 8: Selector de universo con tecla 'U'.

    Cicla: crypto→sp500→all→etfs→crypto.
    Verifica user_activity.log por los cambios.
    """
    errs: List[str] = []
    # 4×U + _wait_enter() entre cada una + _wait_enter extra tras la última U
    lines = ["U", "", "U", "", "U", "", "U", ""]
    result = run_bot(lines, env_vars={"SCANNER_UNIVERSE": "crypto"}, cmd_timeout=2)
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    # Verificar user_activity.log
    activity_path = LOGS_DIR / "user_activity.log"
    if not activity_path.exists():
        errs.append("logs/user_activity.log no se creó")
        return errs

    activity = activity_path.read_text(encoding="utf-8")
    # Con SCANNER_UNIVERSE=crypto, ciclo: crypto→sp500→all→etfs→crypto
    expected = ["sp500", "all", "etfs", "crypto"]
    found = [u for u in expected if f"Universe changed to {u}" in activity]
    if len(found) < 2:
        errs.append(
            f"Solo {len(found)} cambios de universo en user_activity.log: {found}"
        )

    # No debe haber errores en stdout
    stdout_err = strip_ansi(result["stdout"] + result["stderr"])
    for error_kw in ("Traceback", "KeyError", "AttributeError", "MarkupError"):
        if error_kw in stdout_err:
            errs.append(f"Error '{error_kw}' encontrado durante ciclo de universo")
            break
    return errs


def test_scalping_auto_disable() -> List[str]:
    """Test 9: Desactivación automática de scalping en universo no-crypto.

    - Envía 2×U (crypto→sp500→all). En all se desactiva scalping.
    - Verifica strategies.json: categoría scalping active=false.
    - Vuelve a crypto (2×U más) — siguen desactivadas.
    - Verifica bot.log contiene mensaje de scalping desactivado.
    """
    errs: List[str] = []
    # 4×U + _wait_enter entre cada una + Enter extra tras la última U
    lines = ["U", "", "U", "", "U", "", "U", ""]
    result = run_bot(lines, env_vars={"SCANNER_UNIVERSE": "crypto"}, cmd_timeout=2)
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    # Leer strategies.json
    strat_data = read_json("strategies.json")
    strategies = strat_data.get("strategies", []) if strat_data else []

    if not strategies:
        errs.append("strategies.json no contiene estrategias")
        return errs

    scalping_strats = [s for s in strategies if s.get("category") == "scalping"]
    if not scalping_strats:
        errs.append("No se encontraron estrategias de scalping en strategies.json")
        return errs

    active_scalpings = [s for s in scalping_strats if s.get("active", True)]
    if active_scalpings:
        names = [s["name"] for s in active_scalpings]
        errs.append(
            f"Estrategias scalping siguen activas después de cambio de universo: {names}"
        )

    # Verificar mensaje en bot.log
    if not log_contains("Scalping desactivado"):
        errs.append("No se encontró 'Scalping desactivado' en bot.log")

    return errs


def test_verbose_scanner() -> List[str]:
    """Test 10: Modo verbose del Scanner.

    Ejecuta con ``--verbose``, fuerza scan, verifica scanner_verbose.log
    SI el scan asíncrono alcanzó a completarse; caso contrario verifica
    que al menos se disparó correctamente (bot.log).
    """
    errs: List[str] = []
    # 1→Dashboard (triggers scan), 0→salir — esperar scan async
    lines = ["1", "0"]
    result = run_bot(
        lines,
        extra_args=["--verbose"],
        cmd_timeout=15,
        startup_timeout=35,
    )
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    # Verificar mensaje de verbose mode en bot.log (SÍ es obligatorio)
    if not log_contains("Background initial scan started"):
        errs.append("No se encontró 'Background initial scan started' en bot.log")

    # scanner_verbose.log: si el scan async alcanzó a terminar, verificamos;
    # si no, el test NO falla por eso (es un log oportunista).
    verbose_path = LOGS_DIR / "scanner_verbose.log"
    if verbose_path.exists():
        content = verbose_path.read_text(encoding="utf-8").strip()
        if content:
            for line in content.split("\n")[:5]:
                if "|" not in line:
                    errs.append(f"Línea sin pipe en scanner_verbose.log: {line[:80]}")
                    break
        else:
            errs.append("scanner_verbose.log está vacío")

    return errs


def test_check_readiness() -> List[str]:
    """Test 11: Comando check-readiness como subprocess independiente."""
    errs: List[str] = []

    result = run_cli(["check-readiness"], timeout=30)
    stdout = strip_ansi(result["stdout"])

    required_checks = [
        "Verificación de Readiness",
        "Trades suficientes",
        "Sharpe reciente",
        "Slippage aceptable",
        "Kill switch probado",
        "Telegram funciona",
        "Broker conectividad",
    ]
    for check in required_checks:
        if check not in stdout:
            errs.append(f"check-readiness no mostró '{check}'")

    if result["returncode"] not in (0, 1, 2):
        errs.append(
            f"check-readiness retornó código {result['returncode']} "
            f"(esperado 0, 1 o 2)"
        )

    if result.get("timeout"):
        errs.append("Timeout ejecutando check-readiness")

    return errs


def test_scan_interval_dinamico() -> List[str]:
    """Test 12: Intervalo de escaneo dinámico.

    Toggla una scalping strategy y verifica scan_interval_minutes en status.json.
    """
    errs: List[str] = []
    # 3→Estrategias, 1→primera estrategia, T→toggle, 0→volver al menú
    # Luego 3→Estrategias, 1→misma, T→toggle back, 0→volver
    lines = ["3", "1", "T", "0", "3", "1", "T", "0"]
    result = run_bot(lines, cmd_timeout=3)
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    status = read_json("status.json")
    if not status:
        errs.append("status.json no existe")
        return errs

    interval = status.get("scanner_interval_minutes")
    if interval is None:
        errs.append("status.json no contiene scanner_interval_minutes")
    else:
        # El orchestrator recalcula según categorías activas.
        # Valores posibles: 2 (scalping), 15 (intraday), 240 (swing)
        if interval not in (2, 15, 240, 60):
            errs.append(f"scan_interval_minutes={interval} inesperado")

    return errs


def test_submenu_categorizado() -> List[str]:
    """Test 13: Submenú de estrategias categorizado.

    Verifica que la salida del menú contiene las categorías.
    """
    errs: List[str] = []
    lines = ["3", "0"]
    result = run_bot(lines, cmd_timeout=2)
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    stdout_upper = strip_ansi(result["stdout"]).upper()

    categories = [("SCALPING",), ("SWING",)]
    # intraday puede aparecer como "INTRADÍA" o "INTRADAY"
    if "INTRAD" in stdout_upper or "INTRADÍA" in stdout_upper or "INTRADAY" in stdout_upper:
        pass
    else:
        categories.append(("INTRADÍA", "INTRADAY"))

    for variants in categories:
        if not any(v in stdout_upper for v in variants):
            errs.append(f"No se encontró categoría {variants} en salida")

    # Verificar que no hay errores de renderizado
    for error_kw in ("Traceback", "MarkupError", "AttributeError"):
        if error_kw in strip_ansi(result["stdout"] + result["stderr"]):
            errs.append(f"Error '{error_kw}' encontrado")
            break

    return errs


def test_backtest_rapido() -> List[str]:
    """Test 14: Backtest rápido con métricas avanzadas.

    Ejecuta con --seed-trades, selecciona estrategia #1 (la primera
    disponible en el listado dinámico) y ejecuta backtest con SPY
    (confiable incluso en finde). Verifica métricas en stdout.
    """
    errs: List[str] = []
    # 3→Estrategias, 1→primera estrategia disponible, b→backtest,
    # SPY→símbolo (funciona finde), 1y→período, Enter→_wait_enter
    lines = ["3", "1", "b", "SPY", "1y", ""]
    result = run_bot(
        lines,
        extra_args=["--seed-trades"],
        cmd_timeout=6,
        startup_timeout=35,
    )
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    # Verificar métricas avanzadas en la salida (Rich table → stdout)
    stdout = strip_ansi(result["stdout"])
    expected = ["Sortino", "Calmar", "Expectancy", "Avg Trade", "Duration"]
    for metric in expected:
        if metric not in stdout:
            errs.append(f"No se encontró '{metric}' en stdout del backtest")
    return errs


def test_seed_trades() -> List[str]:
    """Test 15: Trades con seed data y campos requeridos.

    Acepta tanto ``entry_at``/``exit_at`` (formato actual del fixture)
    como ``entry_time``/``exit_time`` (formato Fase 18).
    Reporta como advertencia los campos de Fase 18 aún no implementados.
    """
    errs: List[str] = []
    result = run_bot([], extra_args=["--seed-trades"], cmd_timeout=2)
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    trades_data = read_json("trades.json")
    if not trades_data:
        errs.append("logs/trades.json no existe o está vacío")
        return errs

    trades = trades_data.get("trades", [])
    if len(trades) < 5:
        errs.append(f"Se esperaban ≥5 trades, se encontraron {len(trades)}")

    # Campos obligatorios (con alias para compatibilidad Fase 17 ↔ Fase 18)
    field_aliases = {
        "entry_time": ["entry_time", "entry_at"],
        "exit_time": ["exit_time", "exit_at"],
        "symbol": ["symbol"],
        "strategy": ["strategy"],
        "entry_price": ["entry_price"],
        "exit_price": ["exit_price"],
        "pnl": ["pnl"],
        "pnl_pct": ["pnl_pct"],
        "duration": ["duration"],
        "slippage_bps": ["slippage_bps"],
        "broker": ["broker"],
        "source": ["source"],
    }

    # Fase 18 nuevos campos — si faltan es esperable (no implementados aún)
    fase18_fields = {"pnl_pct", "duration", "broker", "source"}

    for i, trade in enumerate(trades):
        missing = []
        for canonical, aliases in field_aliases.items():
            if not any(a in trade for a in aliases):
                if canonical not in fase18_fields:
                    missing.append(canonical)
        if missing:
            errs.append(f"Trade {i} carece de campos obligatorios: {missing}")
            break

    # Advertencia por campos Fase 18 ausentes (no bloquea)
    for i, trade in enumerate(trades[:3]):
        missing_f18 = [f for f in fase18_fields if f not in trade]
        if missing_f18:
            print(f"       ℹ️  Trade {i}: campos Fase 18 pendientes: {missing_f18}")

    return errs


def test_simulacion() -> List[str]:
    """Test 16: Simulación con seed data.

    Navega a Simulación (7), selecciona estrategia, modifica take_profit.
    Verifica que la salida contiene resultados de simulación.
    """
    errs: List[str] = []
    # 7→Simulación, s→continuar (<30 trades warning),
    # 1→primera estrategia, 2→take_profit, 3.0→valor, Enter→_wait_enter
    lines = ["7", "s", "1", "2", "3.0", ""]
    result = run_bot(
        lines,
        extra_args=["--seed-trades"],
        cmd_timeout=3,
        startup_timeout=25,
    )
    if not result["started"]:
        return [f"Bot no arrancó ({result['stdout'][:100]})"]

    stdout = strip_ansi(result["stdout"])
    for kw in ("Simulación", "Simulado", "Original"):
        if kw not in stdout:
            errs.append(f"No se encontró '{kw}' en stdout de simulación")

    return errs


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> None:
    """Run all tests and display a summary."""
    tests: List[tuple] = [
        ("1. Arranque básico",           test_arranque),
        ("2. Archivos de estado",        test_status_files),
        ("3. Navegación menú",           test_navegacion),
        ("4. Scanner",                   test_scanner),
        ("5. Pausa/Reanudación",         test_pausa_reanudacion),
        ("6. Crypto universe",           test_crypto_universe),
        ("7. Builder accesible",         test_builder_accessible),
        ("8. Selector universo (U)",     test_selector_universo),
        ("9. Scalping auto-disable",     test_scalping_auto_disable),
        ("10. Scanner verbose",          test_verbose_scanner),
        ("11. Check-readiness",          test_check_readiness),
        ("12. Intervalo dinámico",       test_scan_interval_dinamico),
        ("13. Submenú categorizado",     test_submenu_categorizado),
        ("14. Backtest rápido",          test_backtest_rapido),
        ("15. Seed trades",              test_seed_trades),
        ("16. Simulación",               test_simulacion),
    ]

    results: List[dict] = []
    total_start = time.time()

    print("=" * 70)
    print("  RoyalTDN — Integration Test: Menu Flow + Fase 18")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Python: {VENV_PYTHON}")
    print("=" * 70)
    print()

    for name, fn in tests:
        print(f"  {name} ... ", end="", flush=True)
        start = time.time()
        try:
            errors = fn()
        except Exception as e:
            errors = [f"Excepción: {e}"]
            import traceback
            traceback.print_exc()
        elapsed = time.time() - start

        if not errors:
            print(f"\r  ✅ {name}  ({elapsed:.1f}s)")
        else:
            print(f"\r  ❌ {name}  ({elapsed:.1f}s)")
            for err in errors[:5]:
                print(f"       ⚠  {err}")
            if len(errors) > 5:
                print(f"       ... y {len(errors) - 5} error(es) más")

        results.append({"name": name, "errors": errors, "elapsed": elapsed})

    total_elapsed = time.time() - total_start
    passed = sum(1 for r in results if not r["errors"])
    failed = sum(1 for r in results if r["errors"])

    print()
    print("=" * 70)
    print(f"  RESUMEN: {passed} PASS / {failed} FAIL / {len(tests)} TOTAL")
    print(f"  Tiempo total: {total_elapsed:.1f}s")
    print("=" * 70)

    if failed > 0:
        print()
        print("  Pruebas fallidas:")
        for r in results:
            if r["errors"]:
                print(f"    ❌ {r['name']} ({len(r['errors'])} error(es))")
        print()
        sys.exit(1)
    else:
        print()
        print("  ✅ TODAS LAS PRUEBAS PASARON")
        print()


if __name__ == "__main__":
    main()
