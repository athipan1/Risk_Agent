import os


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


MAX_POSITION_PCT = _env_float('MAX_POSITION_PCT', 0.10)
MAX_TRADE_LOSS_PCT = _env_float('MAX_TRADE_LOSS_PCT', 0.01)
MAX_TOTAL_EXPOSURE_PCT = _env_float('MAX_TOTAL_EXPOSURE_PCT', 1.00)
MAX_MARGIN_MULTIPLIER = _env_float('MAX_MARGIN_MULTIPLIER', 1.00)
MIN_PROTECTION_DISTANCE_PCT = _env_float('MIN_PROTECTION_DISTANCE_PCT', 0.002)

# Session / circuit-breaker controls. Defaults are intentionally conservative
# enough for early tiny-live workflows while remaining paper-trading friendly.
MAX_DAILY_LOSS_PCT = _env_float('MAX_DAILY_LOSS_PCT', 0.005)
MAX_WEEKLY_LOSS_PCT = _env_float('MAX_WEEKLY_LOSS_PCT', 0.015)
MAX_CONSECUTIVE_LOSSES = _env_int('MAX_CONSECUTIVE_LOSSES', 3)
COOLDOWN_MINUTES_AFTER_LOSS_STREAK = _env_int('COOLDOWN_MINUTES_AFTER_LOSS_STREAK', 60)
MAX_TRADES_PER_DAY = _env_int('MAX_TRADES_PER_DAY', 5)
MAX_SYMBOL_TRADES_PER_DAY = _env_int('MAX_SYMBOL_TRADES_PER_DAY', 2)
SYMBOL_COOLDOWN_MINUTES = _env_int('SYMBOL_COOLDOWN_MINUTES', 30)
EMERGENCY_HALT = _env_bool('EMERGENCY_HALT', False)

POLICY = {
    'max_position_pct': MAX_POSITION_PCT,
    'max_trade_loss_pct': MAX_TRADE_LOSS_PCT,
    'max_total_exposure_pct': MAX_TOTAL_EXPOSURE_PCT,
    'max_margin_multiplier': MAX_MARGIN_MULTIPLIER,
    'min_protection_distance_pct': MIN_PROTECTION_DISTANCE_PCT,
    'max_daily_loss_pct': MAX_DAILY_LOSS_PCT,
    'max_weekly_loss_pct': MAX_WEEKLY_LOSS_PCT,
    'max_consecutive_losses': MAX_CONSECUTIVE_LOSSES,
    'cooldown_minutes_after_loss_streak': COOLDOWN_MINUTES_AFTER_LOSS_STREAK,
    'max_trades_per_day': MAX_TRADES_PER_DAY,
    'max_symbol_trades_per_day': MAX_SYMBOL_TRADES_PER_DAY,
    'symbol_cooldown_minutes': SYMBOL_COOLDOWN_MINUTES,
    'emergency_halt': EMERGENCY_HALT,
}
