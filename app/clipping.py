from __future__ import annotations

import math
from typing import Any

from app.models import RiskCheckRequest
from app.policy import (
    ALLOW_FRACTIONAL_SHARES,
    MAX_POSITION_PCT,
    MAX_SECTOR_EXPOSURE_PCT,
    MAX_TOTAL_EXPOSURE_PCT,
    STRATEGY_BUCKET_LIMITS,
)

CAP_CLIPPABLE_VIOLATIONS = {
    'position_size_limit_exceeded',
    'portfolio_exposure_limit_exceeded',
    'single_stock_exposure_limit_exceeded',
    'bucket_symbol_exposure_limit_exceeded',
    'bucket_exposure_limit_exceeded',
    'sector_exposure_limit_exceeded',
}


def quantity_for_value(value: float, price: float) -> float:
    if price <= 0 or value <= 0:
        return 0.0
    quantity = value / price
    return quantity if ALLOW_FRACTIONAL_SHARES else float(math.floor(quantity))


def bucket_limits(strategy_bucket: str) -> dict[str, Any] | None:
    return STRATEGY_BUCKET_LIMITS.get(str(strategy_bucket or 'unassigned'))


def cap_aware_max_buy_value(payload: RiskCheckRequest) -> tuple[float, dict[str, float]]:
    """Return the maximum incremental buy value allowed by exposure caps."""
    max_position_value = payload.equity * MAX_POSITION_PCT
    max_total_value = payload.equity * MAX_TOTAL_EXPOSURE_PCT
    max_sector_value = payload.equity * MAX_SECTOR_EXPOSURE_PCT

    limits = {
        'position_size_limit': max_position_value,
        'portfolio_exposure_limit': max_total_value - payload.current_total_exposure - payload.open_orders_exposure,
        'single_stock_exposure_limit': max_position_value - payload.current_symbol_exposure,
    }

    bucket = bucket_limits(payload.strategy_bucket)
    if bucket:
        bucket_symbol_limit = payload.equity * float(bucket['max_symbol_pct'])
        bucket_total_limit = payload.equity * float(bucket['max_bucket_pct'])
        limits['bucket_symbol_exposure_limit'] = bucket_symbol_limit - payload.current_symbol_exposure
        limits['bucket_exposure_limit'] = bucket_total_limit - payload.current_bucket_exposure
        limits['single_stock_exposure_limit'] = min(limits['single_stock_exposure_limit'], bucket_symbol_limit - payload.current_symbol_exposure)

    if payload.sector:
        limits['sector_exposure_limit'] = max_sector_value - payload.current_sector_exposure

    max_allowed_value = min(limits.values()) if limits else 0.0
    return max(0.0, max_allowed_value), {key: round(value, 2) for key, value in limits.items()}


def can_clip_violations(violations: list[str]) -> bool:
    return bool(violations) and all(violation in CAP_CLIPPABLE_VIOLATIONS for violation in violations)
