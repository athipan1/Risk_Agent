from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.policy import MIN_PROTECTION_DISTANCE_PCT

ProtectionSide = Literal['long', 'short']
ProtectionBucket = Literal[
    'core_dividend',
    'value_rebound',
    'news_momentum',
    'unassigned',
]

PROTECTION_PLAN_POLICY_VERSION = 'risk-existing-position-protection-v1'


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


DEFAULT_DISTANCE_BY_BUCKET = {
    'core_dividend': _env_float('CORE_PROTECTION_DISTANCE_PCT', 0.04),
    'value_rebound': _env_float('VALUE_PROTECTION_DISTANCE_PCT', 0.05),
    'news_momentum': _env_float('MOMENTUM_PROTECTION_DISTANCE_PCT', 0.03),
    'unassigned': _env_float('DEFAULT_PROTECTION_DISTANCE_PCT', 0.04),
}
MAX_PROTECTION_DISTANCE_PCT = _env_float('MAX_PROTECTION_DISTANCE_PCT', 0.12)


class ProtectionPlanRequest(BaseModel):
    symbol: str = Field(min_length=1)
    side: ProtectionSide = 'long'
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    current_price: float = Field(gt=0)
    strategy_bucket: ProtectionBucket = 'unassigned'
    existing_stop_price: float | None = Field(default=None, gt=0)
    atr: float | None = Field(default=None, gt=0)
    atr_multiplier: float = Field(default=2.0, gt=0, le=10)
    reward_risk_ratio: float = Field(default=2.0, gt=0, le=10)

    @model_validator(mode='after')
    def validate_existing_stop_direction(self):
        if self.existing_stop_price is None:
            return self
        if self.side == 'long' and self.existing_stop_price >= self.current_price:
            raise ValueError('long existing_stop_price must be below current_price')
        if self.side == 'short' and self.existing_stop_price <= self.current_price:
            raise ValueError('short existing_stop_price must be above current_price')
        return self


def _round_price(value: float) -> float:
    return round(max(0.01, value), 2)


def _fallback_distance_pct(bucket: str) -> float:
    configured = DEFAULT_DISTANCE_BY_BUCKET.get(
        bucket,
        DEFAULT_DISTANCE_BY_BUCKET['unassigned'],
    )
    return min(
        MAX_PROTECTION_DISTANCE_PCT,
        max(MIN_PROTECTION_DISTANCE_PCT, configured),
    )


def build_protection_plan(payload: ProtectionPlanRequest) -> dict:
    reference = float(payload.current_price)
    min_distance = reference * max(MIN_PROTECTION_DISTANCE_PCT, 0.0001)

    if payload.existing_stop_price is not None:
        stop_price = float(payload.existing_stop_price)
        calculation_method = 'preserve_valid_existing_stop'
    elif payload.atr is not None:
        atr_distance = float(payload.atr) * float(payload.atr_multiplier)
        distance = max(min_distance, atr_distance)
        distance = min(distance, reference * MAX_PROTECTION_DISTANCE_PCT)
        stop_price = (
            reference - distance
            if payload.side == 'long'
            else reference + distance
        )
        calculation_method = 'atr_multiple_capped_by_policy'
    else:
        distance_pct = _fallback_distance_pct(payload.strategy_bucket)
        distance = max(min_distance, reference * distance_pct)
        stop_price = (
            reference - distance
            if payload.side == 'long'
            else reference + distance
        )
        calculation_method = 'bucket_fallback_distance'

    stop_price = _round_price(stop_price)
    risk_per_share = (
        reference - stop_price
        if payload.side == 'long'
        else stop_price - reference
    )
    if risk_per_share <= 0:
        raise ValueError('calculated stop price does not create positive protection distance')

    take_profit_price = (
        reference + (risk_per_share * payload.reward_risk_ratio)
        if payload.side == 'long'
        else reference - (risk_per_share * payload.reward_risk_ratio)
    )
    take_profit_price = _round_price(take_profit_price)

    direction_valid = (
        stop_price < reference < take_profit_price
        if payload.side == 'long'
        else take_profit_price < reference < stop_price
    )
    if not direction_valid:
        raise ValueError('calculated protection prices have an invalid direction')

    return {
        'status': 'approved',
        'purpose': 'protect_existing_position',
        'orders_submitted': False,
        'symbol': payload.symbol.strip().upper(),
        'side': payload.side,
        'qty': payload.quantity,
        'position_qty': payload.quantity,
        'entry_price': payload.entry_price,
        'reference_price': payload.current_price,
        'strategy_bucket': payload.strategy_bucket,
        'stop_price': stop_price,
        'take_profit_price': take_profit_price,
        'reward_risk_ratio': payload.reward_risk_ratio,
        'risk_per_share': round(risk_per_share, 6),
        'risk_pct_of_reference': round(risk_per_share / reference, 6),
        'calculation_method': calculation_method,
        'risk_policy_version': PROTECTION_PLAN_POLICY_VERSION,
        'safety': 'read_only_risk_proposal_no_broker_mutation',
    }
