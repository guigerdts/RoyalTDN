"""Configuration models with validation for the RoyalTDN trading bot.

Provides a validated schema for ``config.yaml`` using dataclasses with
manual type-checking (M3 — YAML validation). Designed so that migrating
to Pydantic ``BaseModel`` later is a drop-in replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class ConfigValidationError(ValueError):
    """Raised when config validation fails."""


# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------


@dataclass
class OptimizationConfig:
    """Periodic optimization settings."""

    interval_days: int = 30
    metric: str = "sharpe"
    trials: int = 100

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptimizationConfig:
        """Parse and validate an optimization config block."""
        return cls(
            interval_days=_as_int(data, "interval_days", 30, ge=1),
            metric=_as_str(data, "metric", "sharpe"),
            trials=_as_int(data, "trials", 100, ge=1),
        )


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------


@dataclass
class BotConfig:
    """Validated RoyalTDN configuration."""

    broker: str = "paper"
    testnet: bool = True
    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    strategies_dir: str = "cells/templates/"
    initial_capital: float = 100_000.0
    max_positions: int = 10
    max_drawdown: float = 0.20
    telegram_token: str = ""
    telegram_chat_id: str = ""
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)

    # Derived
    strategies_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.strategies_path = Path(__file__).resolve().parent / self.strategies_dir

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BotConfig:
        """Parse and validate a raw YAML dict into a ``BotConfig``.

        Args:
            data: Raw dict from ``yaml.safe_load``.

        Returns:
            Validated ``BotConfig`` instance.

        Raises:
            ConfigValidationError: On any type or constraint violation.
        """
        errors: list[str] = []
        _validate_dict(data, errors, root="config")

        try:
            return cls(
                broker=_as_str(data, "broker", "paper"),
                testnet=_as_bool(data, "testnet", True),
                symbols=_as_str_list(data, "symbols", []),
                strategies_dir=_as_str(data, "strategies_dir", "cells/templates/"),
                initial_capital=_as_float(data, "initial_capital", 100_000.0, ge=0),
                max_positions=_as_int(data, "max_positions", 10, ge=1),
                max_drawdown=_as_float(data, "max_drawdown", 0.20, ge=0.0, le=1.0),
                telegram_token=_as_str(data, "telegram_token", ""),
                telegram_chat_id=_as_str(data, "telegram_chat_id", ""),
                optimization=OptimizationConfig.from_dict(
                    _as_dict(data, "optimization", {})
                ),
            )
        except (ConfigValidationError, TypeError, ValueError) as exc:
            errors.append(str(exc))

        if errors:
            raise ConfigValidationError(
                "Config validation failed:\n  - " + "\n  - ".join(errors)
            )

    def to_dict(self) -> dict[str, Any]:
        """Export validated config back to a plain dict."""
        return {
            "broker": self.broker,
            "testnet": self.testnet,
            "symbols": list(self.symbols),
            "strategies_dir": self.strategies_dir,
            "initial_capital": self.initial_capital,
            "max_positions": self.max_positions,
            "max_drawdown": self.max_drawdown,
            "telegram_token": self.telegram_token,
            "telegram_chat_id": self.telegram_chat_id,
            "optimization": {
                "interval_days": self.optimization.interval_days,
                "metric": self.optimization.metric,
                "trials": self.optimization.trials,
            },
        }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_dict(data: Any, errors: list[str], root: str = "config") -> None:
    if not isinstance(data, dict):
        errors.append(f"{root}: expected a dict, got {type(data).__name__}")


def _as_int(
    data: dict,
    key: str,
    default: int,
    ge: int | None = None,
) -> int:
    val = data.get(key, default)
    if not isinstance(val, int) or isinstance(val, bool):
        raise ConfigValidationError(
            f"'{key}': expected int, got {type(val).__name__} ({val!r})"
        )
    if ge is not None and val < ge:
        raise ConfigValidationError(f"'{key}': must be >= {ge}, got {val}")
    return val


def _as_float(
    data: dict,
    key: str,
    default: float,
    ge: float | None = None,
    le: float | None = None,
) -> float:
    val = data.get(key, default)
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise ConfigValidationError(
            f"'{key}': expected float, got {type(val).__name__} ({val!r})"
        )
    val = float(val)
    if ge is not None and val < ge:
        raise ConfigValidationError(f"'{key}': must be >= {ge}, got {val}")
    if le is not None and val > le:
        raise ConfigValidationError(f"'{key}': must be <= {le}, got {val}")
    return val


def _as_str(data: dict, key: str, default: str) -> str:
    val = data.get(key, default)
    if not isinstance(val, str):
        raise ConfigValidationError(
            f"'{key}': expected str, got {type(val).__name__} ({val!r})"
        )
    return val


def _as_bool(data: dict, key: str, default: bool) -> bool:
    val = data.get(key, default)
    # yaml bools arrive as Python bools
    if not isinstance(val, bool):
        raise ConfigValidationError(
            f"'{key}': expected bool, got {type(val).__name__} ({val!r})"
        )
    return val


def _as_str_list(data: dict, key: str, default: list[str]) -> list[str]:
    val = data.get(key, default)
    if not isinstance(val, list):
        raise ConfigValidationError(
            f"'{key}': expected list, got {type(val).__name__} ({val!r})"
        )
    result: list[str] = []
    for i, item in enumerate(val):
        if not isinstance(item, str):
            raise ConfigValidationError(
                f"'{key}[{i}]': expected str, got {type(item).__name__} ({item!r})"
            )
        result.append(item)
    return result


def _as_dict(data: dict, key: str, default: dict) -> dict:
    val = data.get(key, default)
    if not isinstance(val, dict):
        raise ConfigValidationError(
            f"'{key}': expected dict, got {type(val).__name__} ({val!r})"
        )
    return val
