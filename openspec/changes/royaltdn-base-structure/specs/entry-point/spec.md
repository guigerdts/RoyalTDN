# Entry Point Specification

## Purpose

Define el entry point principal `src/royaltdn/main.py` para Fase 0-1. Es un script simple (no un módulo complejo) con dos comandos: verificar conexión Alpaca y ejecutar paper trading con estrategia SMA crossover.

## Requirements

### Requirement: Simple CLI dispatch

`main.py` MUST usar `sys.argv` para dispatch de comandos — NO SHALL usar `argparse`, `click`, ni `typer`. MUST soportar `check` y `run`.

#### Scenario: Check command succeeds

- GIVEN un archivo `.env` con credenciales Alpaca Paper válidas
- WHEN se ejecuta `python -m src.royaltdn.main check`
- THEN el programa SHALL consultar `TradingClient.get_account()` y loguear estado, capital, y poder de compra

#### Scenario: Run command starts paper trading loop

- GIVEN un archivo `.env` con credenciales Alpaca Paper válidas
- WHEN se ejecuta `python -m src.royaltdn.main run`
- THEN el programa SHALL iniciar un bucle asyncio que evalúa señales SMA crossover cada 60 segundos

#### Scenario: Unknown command shows usage

- GIVEN la CLI ejecutada sin argumentos
- WHEN se ejecuta `python -m src.royaltdn.main`
- THEN SHALL imprimir mensaje de uso con comandos disponibles y salir con código 1

### Requirement: Paper trading loop with SMA crossover

El bucle `run` MUST implementar: obtener datos históricos de 60 días, calcular SMA rápida (5 períodos) y lenta (20 períodos), y generar señal de compra cuando SMA5 cruza arriba de SMA20. SHALL sincronizar posición real del broker al arrancar.

#### Scenario: Signal triggers buy on SMA crossover

- GIVEN una posición actual `None` y SMA5 > SMA20 en el último bar
- WHEN el bucle evalúa señal
- THEN SHALL enviar orden de compra `MARKET_DAY` por 1 acción de SPY

#### Scenario: Bot syncs position at startup

- GIVEN que el broker reporta una posición abierta de 10 SPY
- WHEN `run_bot()` inicia
- THEN `current_position` SHALL setearse a `"long"`

### Requirement: Graceful shutdown

El bucle `run` MUST manejar `SIGINT` y `SIGTERM` para detenerse ordenadamente. SHALL loguear "Bot detenido" antes de salir.

#### Scenario: SIGINT stops the loop

- GIVEN el bot ejecutándose en modo `run`
- WHEN el usuario presiona Ctrl+C
- THEN el bucle SHALL interrumpirse y loguear mensaje de cierre

### Requirement: Error resilience

El bucle `run` MUST capturar excepciones en cada iteración sin colapsar el bot. SHALL esperar 10 segundos y reintentar.

#### Scenario: Network error during data fetch

- GIVEN que Alpaca API no responde
- WHEN `get_signal()` lanza una excepción
- THEN el bucle SHALL loguear el error y continuar tras 10 segundos
