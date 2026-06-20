# Rate Limiting — Specification

## Purpose

Protect the Alpaca API from excessive requests by implementing a token bucket rate limiter (200 requests per minute, matching the standard Alpaca plan). Add exponential backoff retry logic for transient errors (HTTP 429, 503, timeouts) and abort on authentication failures (HTTP 401/403).

## Requirements

### REQ-RATE-LIMIT — Token bucket rate limiter para API calls

The system MUST implement a token bucket rate limiter with:
- Initial capacity: 200 tokens
- Refill rate: 200 tokens per minute (1 token every 0.3s)
- Each `get_latest_bar` call consumes 1 token.
- Each `get_stock_bars` batch call consumes 1 token (regardless of batch size).
- When the bucket is empty, the caller MUST block until a token is available.
- The rate limiter SHALL be applied in `LiquidityFilter.filter()` for `get_latest_bar` calls.

#### Scenario: Token bucket empieza con 200 tokens

- GIVEN a freshly initialized token bucket
- WHEN `get_available_tokens()` is queried
- THEN the result is exactly 200

#### Scenario: Refill rate: 200 tokens por minuto

- GIVEN the bucket has 0 tokens at T=0
- WHEN the system waits 60 seconds
- THEN `get_available_tokens()` returns exactly 200 at T=60

#### Scenario: get_latest_bar en LiquidityFilter pasa por rate limiter

- GIVEN `LiquidityFilter.filter()` is processing 50 symbols
- WHEN each symbol calls `data_client.get_latest_bar()`
- THEN every call acquires 1 token from the bucket
- AND no call proceeds if the bucket is empty

#### Scenario: Rate limiter bloquea hasta tener tokens disponibles

- GIVEN the token bucket is empty
- WHEN a `get_latest_bar()` call is attempted
- THEN the call blocks until at least 1 token is available
- AND the call proceeds immediately once a token is acquired

#### Scenario: Burst de requests consume tokens hasta vaciar el bucket

- GIVEN the token bucket has 200 tokens
- WHEN 200 `get_latest_bar()` calls are made sequentially
- THEN the first 200 calls succeed without blocking
- AND the 201st call blocks until a token is refilled

#### Scenario: Bucket vacío — espera hasta refill

- GIVEN the token bucket has 0 tokens
- WHEN a `get_latest_bar()` call is made
- THEN the call blocks for at most ~0.3s
- AND then proceeds with the acquired token

#### Scenario: Refill después de 60 segundos

- GIVEN exactly 200 tokens were consumed at T=0
- WHEN the system waits 60 seconds
- THEN the bucket has exactly 200 tokens available at T=60
- AND any calls between T=0 and T=60 block or proceed at the refill rate

### REQ-RETRY — Exponential backoff para errores de API

The system MUST retry failed API calls with exponential backoff:
- Backoff sequence: 1s, 2s, 4s, 8s (doubling each attempt).
- Maximum retries per call: 5.
- HTTP 429 (rate limit), 503 (service unavailable), and network timeouts SHALL trigger retry.
- HTTP 401 and 403 SHALL log the error and abort the entire scan.
- After the 5th failed retry, SHALL log a warning and skip the symbol.

#### Scenario: HTTP 429 retry con backoff 1s, 2s, 4s, 8s

- GIVEN a `get_latest_bar(symbol="SPY")` call returns HTTP 429
- WHEN the retry logic executes
- THEN it waits 1s before the 1st retry
- AND waits 2s before the 2nd retry (if still failing)
- AND waits 4s before the 3rd retry
- AND waits 8s before the 4th retry

#### Scenario: Máximo 5 reintentos para un request

- GIVEN a `get_stock_bars()` call consistently returns HTTP 429
- WHEN the retry logic executes
- THEN exactly 5 retries are attempted
- AND after the 5th failure, the symbol/batch is skipped
- AND a warning is logged: `"Rate limit: max retries reached for {symbol}"`

#### Scenario: HTTP 401 loguea error y aborta el scan

- GIVEN any API call returns HTTP 401
- WHEN the retry logic evaluates the status code
- THEN no retry is attempted
- AND an error is logged: `"Auth error (401): credenciales inválidas — abortando scan"`
- AND the scan stops immediately

#### Scenario: HTTP 403 loguea error y aborta el scan

- GIVEN any API call returns HTTP 403
- WHEN the retry logic evaluates the status code
- THEN no retry is attempted
- AND an error is logged: `"Auth error (403): acceso denegado — abortando scan"`
- AND the scan stops immediately

#### Scenario: Timeout de conexión — retry con backoff

- GIVEN a `get_latest_bar()` call times out after 10s
- WHEN the retry logic executes
- THEN it retries with the same backoff sequence (1s, 2s, 4s, 8s)
- AND logs each timeout: `"Timeout en {symbol}: {error} — reintento {n}/5"`

#### Scenario: 5to retry fallido — loguea warning, salta el símbolo

- GIVEN all 5 retries fail for a given symbol
- WHEN the retry logic gives up
- THEN a warning is logged: `"Rate limit: max retries (5) reached para {symbol}"`
- AND the symbol is skipped (not added to the passed list)

#### Scenario: Éxito en el 3er reintento — continúa normalmente

- GIVEN a call fails twice with HTTP 429
- WHEN the 3rd retry succeeds
- THEN no warning is logged
- AND the symbol is added to the passed list normally
- AND the total retry count is reset for the next symbol

#### Scenario: get_stock_bars batch consume 1 token (no 100)

- GIVEN a batch of 100 symbols is ready for `get_stock_bars()`
- WHEN the API call is made through the rate limiter
- THEN exactly 1 token is consumed from the bucket (not 100)
- AND the batch proceeds normally
