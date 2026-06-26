from __future__ import annotations

import re
from typing import Tuple

from app.models import RiskCheckRequest
from app.policy import (
    ALLOW_FRACTIONAL_SHARES,
    ALLOW_SHORT_SELLING,
    ASSET_CLASS,
    MAX_SECTOR_EXPOSURE_PCT,
    MAX_SINGLE_STOCK_PCT,
    MIN_EQUITY_FOR_LIVE_STOCK,
    STOCK_ONLY_MODE,
    STRATEGY_BUCKET_LIMITS,
)

_STOCK_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(?:[.-][A-Z])?$")
_CRYPTO_HINTS = {"BTC", "ETH", "SOL", "DOGE", "USDT", "USDC", "BNB", "XRP", "ADA"}
_NON_TRADABLE_SYMBOLS = {"CASH", "USD", "USDT", "USDC"}
_VALID_STRATEGY_BUCKETS = set(STRATEGY_BUCKET_LIMITS)


def _is_stock_symbol(symbol: str) -> bool:
    symbol = str(symbol or "").strip().upper()
    if not symbol or "/" in symbol or ":" in symbol:
        return False
    if symbol in _NON_TRADABLE_SYMBOLS:
        return False
    if symbol in _CRYPTO_HINTS or symbol.startswith(tuple(_CRYPTO_HINTS)):
        return False
    if symbol in {"XAU", "XAUUSD", "GOLD", "GC"}:
        return False
    return bool(_STOCK_SYMBOL_RE.match(symbol))


def _strategy_bucket_limits(strategy_bucket: str) -> dict | None:
    bucket = str(strategy_bucket or "unassigned").strip().lower()
    return STRATEGY_BUCKET_LIMITS.get(bucket)


def _rebalance_position_value(payload: RiskCheckRequest, requested_position_value: float) -> tuple[float, float, bool]:
    """Return incremental buy value and projected symbol exposure.

    Portfolio allocation flows may send a full target value/quantity rather than a
    pure buy delta. For existing positions, adding that full target to current
    exposure double-counts exposure and causes false rejections. When target_value
    is present, treat the order as rebalance-aware and only count the positive
    delta above current symbol exposure.
    """
    if payload.side != 'buy' or payload.target_value is None:
        return requested_position_value, payload.current_symbol_exposure + requested_position_value, False

    target_value = float(payload.target_value or 0)
    incremental_value = max(0.0, target_value - payload.current_symbol_exposure)
    projected_symbol_exposure = max(payload.current_symbol_exposure, target_value)
    return incremental_value, projected_symbol_exposure, True


def check_stock_limits(payload: RiskCheckRequest) -> Tuple[list[str], list[str], dict]:
    violations: list[str] = []
    warnings: list[str] = []
    requested_position_value = payload.entry_price * payload.requested_quantity
    effective_position_value, projected_symbol_exposure, rebalance_aware = _rebalance_position_value(payload, requested_position_value)
    projected_sector_exposure = payload.current_sector_exposure + effective_position_value
    projected_bucket_exposure = payload.current_bucket_exposure + effective_position_value
    max_single_stock_value = payload.equity * MAX_SINGLE_STOCK_PCT
    max_sector_value = payload.equity * MAX_SECTOR_EXPOSURE_PCT

    bucket_limits = _strategy_bucket_limits(payload.strategy_bucket)
    bucket_max_symbol_value = None
    bucket_max_exposure_value = None
    if bucket_limits:
        bucket_max_symbol_value = payload.equity * bucket_limits['max_symbol_pct']
        bucket_max_exposure_value = payload.equity * bucket_limits['max_bucket_pct']
        max_single_stock_value = min(max_single_stock_value, bucket_max_symbol_value)

    if STOCK_ONLY_MODE:
        if payload.asset_class != 'stock' or ASSET_CLASS != 'stock':
            violations.append('stock_only_asset_class_required')
        if not _is_stock_symbol(payload.symbol):
            violations.append('stock_symbol_required')

    if payload.trading_mode == 'LIVE' and payload.equity < MIN_EQUITY_FOR_LIVE_STOCK:
        violations.append('minimum_live_stock_equity_required')

    if payload.side == 'sell' and not ALLOW_SHORT_SELLING and payload.requested_quantity > payload.owned_quantity:
        violations.append('short_selling_disabled')

    if not ALLOW_FRACTIONAL_SHARES and payload.requested_quantity != int(payload.requested_quantity):
        violations.append('fractional_shares_disabled')

    if payload.strategy_bucket != 'unassigned' and payload.strategy_bucket not in _VALID_STRATEGY_BUCKETS:
        violations.append('strategy_bucket_unknown')

    if projected_symbol_exposure > max_single_stock_value:
        violations.append('single_stock_exposure_limit_exceeded')

    if bucket_max_symbol_value is not None and projected_symbol_exposure > bucket_max_symbol_value:
        violations.append('bucket_symbol_exposure_limit_exceeded')

    if bucket_max_exposure_value is not None and projected_bucket_exposure > bucket_max_exposure_value:
        violations.append('bucket_exposure_limit_exceeded')

    if payload.sector and projected_sector_exposure > max_sector_value:
        violations.append('sector_exposure_limit_exceeded')

    if projected_symbol_exposure > max_single_stock_value * 0.80:
        warnings.append('near_single_stock_exposure_limit')

    if bucket_max_exposure_value is not None and projected_bucket_exposure > bucket_max_exposure_value * 0.80:
        warnings.append('near_bucket_exposure_limit')

    if payload.sector and projected_sector_exposure > max_sector_value * 0.80:
        warnings.append('near_sector_exposure_limit')

    metrics = {
        'asset_class': payload.asset_class,
        'stock_only_mode': STOCK_ONLY_MODE,
        'symbol_is_stock_like': _is_stock_symbol(payload.symbol),
        'allow_short_selling': ALLOW_SHORT_SELLING,
        'allow_fractional_shares': ALLOW_FRACTIONAL_SHARES,
        'owned_quantity': payload.owned_quantity,
        'sector': payload.sector,
        'strategy_bucket': payload.strategy_bucket,
        'rebalance_aware': rebalance_aware,
        'target_value': round(float(payload.target_value), 2) if payload.target_value is not None else None,
        'requested_position_value': round(requested_position_value, 2),
        'effective_position_value': round(effective_position_value, 2),
        'current_bucket_exposure': round(payload.current_bucket_exposure, 2),
        'projected_bucket_exposure': round(projected_bucket_exposure, 2),
        'max_bucket_exposure': round(bucket_max_exposure_value, 2) if bucket_max_exposure_value is not None else None,
        'bucket_max_symbol_exposure': round(bucket_max_symbol_value, 2) if bucket_max_symbol_value is not None else None,
        'current_sector_exposure': round(payload.current_sector_exposure, 2),
        'projected_sector_exposure': round(projected_sector_exposure, 2),
        'max_sector_exposure': round(max_sector_value, 2),
        'current_symbol_exposure': round(payload.current_symbol_exposure, 2),
        'projected_symbol_exposure': round(projected_symbol_exposure, 2),
        'max_single_stock_exposure': round(max_single_stock_value, 2),
        'min_equity_for_live_stock': MIN_EQUITY_FOR_LIVE_STOCK,
    }
    return violations, warnings, metrics
