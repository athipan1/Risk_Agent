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

# Stock-first controls. Defaults intentionally prefer long-only, no-leverage stock workflows.
ASSET_CLASS = os.getenv('ASSET_CLASS', 'stock').strip().lower()
STOCK_ONLY_MODE = _env_bool('STOCK_ONLY_MODE', True)
ALLOW_SHORT_SELLING = _env_bool('ALLOW_SHORT_SELLING', False)
ALLOW_FRACTIONAL_SHARES = _env_bool('ALLOW_FRACTIONAL_SHARES', False)
MAX_SINGLE_STOCK_PCT = _env_float('MAX_SINGLE_STOCK_PCT', 0.10)
MAX_SECTOR_EXPOSURE_PCT = _env_float('MAX_SECTOR_EXPOSURE_PCT', 0.25)
MIN_EQUITY_FOR_LIVE_STOCK = _env_float('MIN_EQUITY_FOR_LIVE_STOCK', 1000.0)

# Strategy bucket controls for the governed 50/30/20 core-satellite portfolio.
MAX_CORE_DIVIDEND_BUCKET_PCT = _env_float('MAX_CORE_DIVIDEND_BUCKET_PCT', 0.50)
MAX_VALUE_REBOUND_BUCKET_PCT = _env_float('MAX_VALUE_REBOUND_BUCKET_PCT', 0.30)
MAX_NEWS_MOMENTUM_BUCKET_PCT = _env_float('MAX_NEWS_MOMENTUM_BUCKET_PCT', 0.20)
MAX_CORE_DIVIDEND_SYMBOL_PCT = _env_float('MAX_CORE_DIVIDEND_SYMBOL_PCT', 0.10)
MAX_VALUE_REBOUND_SYMBOL_PCT = _env_float('MAX_VALUE_REBOUND_SYMBOL_PCT', 0.07)
MAX_NEWS_MOMENTUM_SYMBOL_PCT = _env_float('MAX_NEWS_MOMENTUM_SYMBOL_PCT', 0.03)

STRATEGY_BUCKET_LIMITS = {
    'core_dividend': {
        'max_bucket_pct': MAX_CORE_DIVIDEND_BUCKET_PCT,
        'max_symbol_pct': MAX_CORE_DIVIDEND_SYMBOL_PCT,
    },
    'value_rebound': {
        'max_bucket_pct': MAX_VALUE_REBOUND_BUCKET_PCT,
        'max_symbol_pct': MAX_VALUE_REBOUND_SYMBOL_PCT,
    },
    'news_momentum': {
        'max_bucket_pct': MAX_NEWS_MOMENTUM_BUCKET_PCT,
        'max_symbol_pct': MAX_NEWS_MOMENTUM_SYMBOL_PCT,
    },
}

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
    'asset_class': ASSET_CLASS,
    'stock_only_mode': STOCK_ONLY_MODE,
    'allow_short_selling': ALLOW_SHORT_SELLING,
    'allow_fractional_shares': ALLOW_FRACTIONAL_SHARES,
    'max_single_stock_pct': MAX_SINGLE_STOCK_PCT,
    'max_sector_exposure_pct': MAX_SECTOR_EXPOSURE_PCT,
    'min_equity_for_live_stock': MIN_EQUITY_FOR_LIVE_STOCK,
    'strategy_bucket_limits': STRATEGY_BUCKET_LIMITS,
    'max_daily_loss_pct': MAX_DAILY_LOSS_PCT,
    'max_weekly_loss_pct': MAX_WEEKLY_LOSS_PCT,
    'max_consecutive_losses': MAX_CONSECUTIVE_LOSSES,
    'cooldown_minutes_after_loss_streak': COOLDOWN_MINUTES_AFTER_LOSS_STREAK,
    'max_trades_per_day': MAX_TRADES_PER_DAY,
    'max_symbol_trades_per_day': MAX_SYMBOL_TRADES_PER_DAY,
    'symbol_cooldown_minutes': SYMBOL_COOLDOWN_MINUTES,
    'emergency_halt': EMERGENCY_HALT,
}
