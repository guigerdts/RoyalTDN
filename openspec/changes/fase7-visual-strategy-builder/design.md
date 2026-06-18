# Design: Fase 7 — Visual Strategy Builder

## Technical Approach

15 pandas-ta wrappers + 1 manual SmartMoneyFlowCloud. Recursive rule tree with depth-2 guard. DynamicStrategy(BaseStrategy) parsing JSON config. VectorBT + yfinance backtesting cached by SHA-256 hash. 3-column Streamlit page (30/40/30). 30s polling watcher in orchestrator legacy loop. `.active` symlink for hot-deploy.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Indicator library | pandas-ta + manual SMF | All manual / VectorBT-native | pandas-ta saves ~500 lines; SMF custom because no library has it |
| Rule evaluation | Recursive tree walker | Flat condition list | Supports 2-level nesting naturally; future-proof for deeper trees |
| Strategy persistence | JSON + `.tmp` atomic write | DB / pickle | Zero deps, debuggable, matches existing `logs/*.json` pattern |
| Backtesting cache | `@st.cache_data` by SHA-256 | No cache / Redis | Streamlit-native; hash changes on any param change = auto-invalidate |
| Watcher | Polling in legacy loop | asyncio task / Thread | Simplest, no thread safety issues; adds ~0.5ms every 30s |
| Builder state | `st.session_state` dict | Widget-based | Full control over serialization; survives reruns without widget binding |

## Data Flow

```
BUILDER PAGE (left col)             BACKTESTING (center col)        DEPLOY (right col)
┌─────────────────────┐            ┌─────────────────────┐         ┌──────────────────────┐
│ Indicator picker    │            │ yfinance.download()  │         │ JSON preview         │
│ → indicators_added │──────────→ │ → indicators.compute │────────→│ → Save .json         │
│ Rule tree editor   │            │ → rule_engine.eval() │         │ → Set .active symlink│
│ → rules            │            │ → VectorBT PF        │         └──────────────────────┘
│ Params sliders     │            │ → metrics dict       │                │
└─────────────────────┘            │ → @st.cache_data    │                ▼
                                  └─────────┬───────────┘         ORCHESTRATOR
                                            │                     (poll 30s)
                                            ▼                     ┌──────────────┐
                                     st.plotly_chart              │ get_active() │
                                     metrics table                │ from_file()  │
                                                                   │ validate()   │
                                                                   │ generate_signal()
```

## File Structure

```
src/royaltdn/strategy/
├── indicators.py          # 16 functions (15 pandas-ta + 1 SMF manual)
├── rule_engine.py         # evaluate() + validate_tree()
├── schema.py              # validate_config() for JSON v1
├── strategy_store.py      # save/load/list/get_active/set_active
├── dynamic.py             # DynamicStrategy(BaseStrategy)
└── backtesting.py         # BacktestEngine + yfinance + cache

src/royaltdn/frontend/pages/
└── builder.py             # 3-column strategy builder page

src/royaltdn/frontend/components/
├── builder_state.py       # st.session_state getters/setters
└── backtest_charts.py     # Builder-specific chart builders

user_strategies/            # Created on startup (gitignored)
└── .active                 # Symlink to deployed strategy
```

## Key Interfaces

### indicators.py
```python
def SMA(data, period=20, source="close") -> pd.Series
def EMA(data, period=20, source="close") -> pd.Series
def RSI(data, period=14, source="close") -> pd.Series
def MACD(data, fast=12, slow=26, signal=9, source="close") -> pd.DataFrame
def BollingerBands(data, period=20, std=2, source="close") -> pd.DataFrame
def ATR(data, period=14) -> pd.Series
def Volume(data) -> pd.Series
def Ichimoku(data, tenkan=9, kijun=26, senkou=52) -> pd.DataFrame
def SuperTrend(data, period=10, multiplier=3.0) -> pd.DataFrame
def VWAP(data, anchor="D") -> pd.Series
def ZScore(data, period=21, entry_threshold=2.0, exit_threshold=0.5) -> pd.Series
def ADX(data, period=14) -> pd.Series
def OBV(data) -> pd.Series
def Stochastic(data, k_period=14, d_period=3, slowing=3) -> pd.DataFrame
def ParabolicSAR(data, af=0.02, max_af=0.2) -> pd.Series
def SmartMoneyFlowCloud(data, trend_length=34, trend_engine="EMA", ...) -> pd.DataFrame
```

### rule_engine.py
```python
def evaluate(tree: dict, indicators: dict, data: pd.DataFrame) -> bool
def validate_tree(tree: dict) -> bool
```

### DynamicStrategy
```python
class DynamicStrategy(BaseStrategy):
    def __init__(self, config: dict)
    @classmethod def from_file(cls, path: str) -> DynamicStrategy
    def generate_signal(self, data: pd.DataFrame) -> dict | None
    def get_parameters(self) -> dict
    def validate(self) -> bool
```

### strategy_store.py
```python
def save_strategy(config: dict, name: str) -> Path
def load_strategy(path: str) -> dict
def list_strategies() -> list[Path]
def get_active() -> Path | None
def set_active(path: Path) -> None
```

### BacktestEngine
```python
class BacktestEngine:
    def __init__(self, config: dict)
    def run(self) -> dict
    @property def config_hash(self) -> str
```

## File Changes

| File | Action | Milestone |
|---|---|---|
| `src/royaltdn/strategy/indicators.py` | Create | H1 |
| `src/royaltdn/strategy/rule_engine.py` | Create | H1 |
| `src/royaltdn/strategy/schema.py` | Create | H1 |
| `src/royaltdn/strategy/strategy_store.py` | Create | H2 |
| `src/royaltdn/strategy/dynamic.py` | Create | H2 |
| `src/royaltdn/strategy/backtesting.py` | Create | H4 |
| `src/royaltdn/frontend/pages/builder.py` | Create | H3 |
| `src/royaltdn/frontend/components/builder_state.py` | Create | H3 |
| `src/royaltdn/frontend/components/backtest_charts.py` | Create | H4 |
| `src/royaltdn/orchestrator.py` | Modify | H5 |
| `src/royaltdn/frontend/app.py` | Modify | H5 |
| `requirements/fase7.txt` | Create | H5 |

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | indicators.py | 200-bar OHLCV fixture, assert all 16 produce correct shape |
| Unit | rule_engine.py | All operator categories + depth-2 guard + empty conditions |
| Unit | DynamicStrategy | Mock indicators, assert BUY/SELL/HOLD from rule trees |
| Unit | schema.py | Valid/invalid JSON examples; boundary conditions |
| Integration | BacktestEngine | Real yfinance SPY 1D data; assert metrics structure |
| Integration | strategy_store.py | Temp directory; save/load/list/set_active/get_active |

## Open Questions

None — all decisions resolved in proposal + specs + this design.

## Milestone Acceptance

- **Hito 1**: `python -c "from strategy.indicators import *; [f(200bar_df) for f in [SMA,EMA,RSI,...]]"` → no errors
- **Hito 2**: `DynamicStrategy.from_file("test.json").generate_signal(data)` → BUY/SELL/HOLD
- **Hito 3**: Builder page renders with 16 indicators, 2-level rule tree, JSON preview
- **Hito 4**: Backtesting shows equity curve + 8 metrics for any strategy config
- **Hito 5**: File in `user_strategies/` deploys within 60s; all Fase 6 pages unaffected
