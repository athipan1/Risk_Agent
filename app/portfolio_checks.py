from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from app.checks import check_order
from app.kill_switch import rejected_kill_switch_payload
from app.models import PortfolioRiskCheckRequest, PortfolioRiskPosition, RiskCheckRequest, StandardResponse
from app.policy import (
    ALLOW_FRACTIONAL_SHARES,
    MAX_POSITION_PCT,
    MAX_SECTOR_EXPOSURE_PCT,
    MAX_TOTAL_EXPOSURE_PCT,
    STRATEGY_BUCKET_LIMITS,
)

BUCKET_PRIORITY = {
    'core_dividend': 0,
    'quality_growth': 1,
    'value_rebound': 2,
    'news_momentum': 3,
    'unassigned': 99,
}


def _context_float(context: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = context.get(key, default)
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _bucket_from_position(position: PortfolioRiskPosition) -> str:
    context_bucket = position.portfolio_context.get('strategy_bucket') or position.portfolio_context.get('bucket')
    return str(context_bucket or position.strategy_bucket or 'unassigned')


def _sector_from_position(position: PortfolioRiskPosition) -> str | None:
    scanner = position.scanner_candidate or {}
    metadata = scanner.get('metadata') or {}
    return metadata.get('sector') or scanner.get('sector')


def _target_weight(position: PortfolioRiskPosition) -> float | None:
    value = position.portfolio_context.get('target_weight')
    if value is None and position.portfolio_context.get('allocation_pct') is not None:
        value = _context_float(position.portfolio_context, 'allocation_pct') / 100.0
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _max_bucket_pct(bucket: str) -> float | None:
    limits = STRATEGY_BUCKET_LIMITS.get(bucket)
    if not limits:
        return None
    return float(limits['max_bucket_pct'])


def _max_bucket_symbol_pct(bucket: str) -> float | None:
    limits = STRATEGY_BUCKET_LIMITS.get(bucket)
    if not limits:
        return None
    return float(limits['max_symbol_pct'])


def _quantity_for_value(value: float, price: float) -> float:
    if price <= 0 or value <= 0:
        return 0.0
    quantity = value / price
    return quantity if ALLOW_FRACTIONAL_SHARES else float(math.floor(quantity))


def _scale_position_to_limits(
    *,
    payload: PortfolioRiskCheckRequest,
    position: PortfolioRiskPosition,
    projected_total: float,
    bucket_exposure: float,
) -> tuple[PortfolioRiskPosition | None, list[str], list[str], dict[str, Any]]:
    symbol = str(position.symbol).upper()
    bucket = _bucket_from_position(position)
    sector = _sector_from_position(position)
    warnings: list[str] = []
    violations: list[str] = []

    if bucket not in STRATEGY_BUCKET_LIMITS:
        return None, ['strategy_bucket_unassigned'], warnings, {
            'symbol': symbol,
            'strategy_bucket': bucket,
            'requested_quantity': position.requested_quantity,
            'requested_value': round(position.entry_price * position.requested_quantity, 2),
            'max_allowed_value': 0.0,
            'scaling_reason': 'strategy_bucket_unassigned',
        }

    requested_value = position.entry_price * position.requested_quantity
    current_symbol_exposure = float(payload.current_symbol_exposures.get(symbol, 0.0))
    current_sector_exposure = float(payload.current_sector_exposures.get(sector or '', 0.0))

    max_total_value = payload.equity * MAX_TOTAL_EXPOSURE_PCT
    max_global_symbol_value = payload.equity * MAX_POSITION_PCT
    max_bucket_value = payload.equity * (_max_bucket_pct(bucket) or 0.0)
    max_bucket_symbol_value = payload.equity * (_max_bucket_symbol_pct(bucket) or 0.0)
    max_symbol_value = min(max_global_symbol_value, max_bucket_symbol_value)
    max_sector_value = payload.equity * MAX_SECTOR_EXPOSURE_PCT

    allowed_by_total = max_total_value - payload.open_orders_exposure - projected_total
    allowed_by_symbol = max_symbol_value - current_symbol_exposure
    allowed_by_bucket = max_bucket_value - bucket_exposure
    allowed_by_sector = max_sector_value - current_sector_exposure if sector else requested_value

    limits = {
        'portfolio_exposure_limit': allowed_by_total,
        'single_stock_exposure_limit': allowed_by_symbol,
        'bucket_exposure_limit': allowed_by_bucket,
        'sector_exposure_limit': allowed_by_sector,
    }
    max_allowed_value = min(limits.values())

    if max_allowed_value <= 0:
        for name, allowed in limits.items():
            if allowed <= 0:
                violations.append(f'{name}_exceeded')
        return None, violations, warnings, {
            'symbol': symbol,
            'strategy_bucket': bucket,
            'requested_quantity': position.requested_quantity,
            'requested_value': round(requested_value, 2),
            'max_allowed_value': round(max(0.0, max_allowed_value), 2),
            'limits': {name: round(value, 2) for name, value in limits.items()},
        }

    final_quantity = position.requested_quantity
    if requested_value > max_allowed_value:
        final_quantity = _quantity_for_value(max_allowed_value, position.entry_price)
        warnings.append('portfolio_quantity_scaled_to_available_risk_budget')
        for name, allowed in limits.items():
            if requested_value > allowed:
                warnings.append(f'scaled_by_{name}')

    if final_quantity <= 0:
        violations.append('scaled_quantity_below_minimum')
        return None, violations, warnings, {
            'symbol': symbol,
            'strategy_bucket': bucket,
            'requested_quantity': position.requested_quantity,
            'requested_value': round(requested_value, 2),
            'max_allowed_value': round(max_allowed_value, 2),
            'limits': {name: round(value, 2) for name, value in limits.items()},
        }

    scaled_position = position.model_copy(update={'requested_quantity': final_quantity})
    return scaled_position, violations, warnings, {
        'symbol': symbol,
        'strategy_bucket': bucket,
        'requested_quantity': position.requested_quantity,
        'scaled_quantity': final_quantity,
        'requested_value': round(requested_value, 2),
        'scaled_value': round(position.entry_price * final_quantity, 2),
        'max_allowed_value': round(max_allowed_value, 2),
        'limits': {name: round(value, 2) for name, value in limits.items()},
    }


def _build_risk_request(
    *,
    payload: PortfolioRiskCheckRequest,
    position: PortfolioRiskPosition,
    current_total_exposure: float,
    bucket_exposure: float,
) -> RiskCheckRequest:
    session = payload.session_risk_context or {}
    symbol = str(position.symbol).upper()
    bucket = _bucket_from_position(position)
    return RiskCheckRequest(
        account_id=payload.account_id,
        symbol=symbol,
        side=position.side,
        entry_price=position.entry_price,
        protection_price=position.protection_price,
        equity=payload.equity,
        requested_quantity=position.requested_quantity,
        current_symbol_exposure=float(payload.current_symbol_exposures.get(symbol, 0.0)),
        current_total_exposure=current_total_exposure,
        open_orders_exposure=payload.open_orders_exposure,
        margin_multiplier=payload.margin_multiplier,
        trading_mode=payload.trading_mode,
        asset_class=payload.asset_class,
        sector=_sector_from_position(position),
        current_sector_exposure=float(payload.current_sector_exposures.get(_sector_from_position(position) or '', 0.0)),
        strategy_bucket=bucket if bucket in STRATEGY_BUCKET_LIMITS else 'unassigned',
        current_bucket_exposure=bucket_exposure,
        target_weight=_target_weight(position),
        allocation_pct=position.portfolio_context.get('allocation_pct'),
        target_value=None,
        daily_realized_pnl=float(session.get('daily_realized_pnl', 0.0)),
        weekly_realized_pnl=float(session.get('weekly_realized_pnl', 0.0)),
        consecutive_losses=int(session.get('consecutive_losses', 0)),
        trades_today=int(session.get('trades_today', 0)),
        symbol_trades_today=int(session.get('symbol_trades_today', 0)),
        minutes_since_last_loss=session.get('minutes_since_last_loss'),
        minutes_since_last_symbol_trade=session.get('minutes_since_last_symbol_trade'),
        emergency_halt=bool(session.get('emergency_halt', False)),
    )


def _portfolio_kill_switch_payload(payload: PortfolioRiskCheckRequest) -> RiskCheckRequest | None:
    if not payload.positions:
        return None
    first_position = payload.positions[0]
    return _build_risk_request(
        payload=payload,
        position=first_position,
        current_total_exposure=float(payload.current_total_exposure),
        bucket_exposure=float(payload.current_bucket_exposures.get(_bucket_from_position(first_position), 0.0)),
    )


def _rejected_decision(
    *,
    position: PortfolioRiskPosition,
    violations: list[str],
    warnings: list[str],
    scaling: dict[str, Any],
) -> dict[str, Any]:
    symbol = str(position.symbol).upper()
    bucket = _bucket_from_position(position)
    requested_value = position.entry_price * position.requested_quantity
    return {
        'symbol': symbol,
        'approved': False,
        'status': 'rejected',
        'strategy_bucket': bucket,
        'target_weight': _target_weight(position),
        'allocation_pct': position.portfolio_context.get('allocation_pct'),
        'target_value': position.portfolio_context.get('target_value'),
        'requested_quantity': position.requested_quantity,
        'final_quantity': 0.0,
        'requested_value': round(requested_value, 2),
        'approved_value': 0.0,
        'risk_response': {'approved': False, 'violations': violations, 'warnings': warnings, 'scaling': scaling},
        'violations': violations,
        'warnings': warnings,
        'scaling': scaling,
    }


def check_portfolio(payload: PortfolioRiskCheckRequest) -> StandardResponse:
    kill_switch_payload = _portfolio_kill_switch_payload(payload)
    if kill_switch_payload is not None:
        kill_response = check_order(kill_switch_payload)
        kill_data = kill_response.data or {}
        if kill_data.get('kill_switch_active'):
            violations = kill_data.get('violations') or []
            warnings = kill_data.get('warnings') or []
            session_risk = kill_data.get('session_risk') or {}
            return StandardResponse(
                status='rejected',
                data={
                    **rejected_kill_switch_payload(
                        trading_mode=payload.trading_mode,
                        asset_class=payload.asset_class,
                        violations=violations,
                        warnings=warnings,
                        metrics=session_risk,
                        extra={'mode': 'portfolio_allocation'},
                    ),
                    'total_positions': len(payload.positions),
                    'approved_positions': 0,
                    'rejected_positions': len(payload.positions),
                    'projected_total_exposure': round(float(payload.current_total_exposure), 2),
                    'projected_bucket_exposures': {},
                    'projected_sector_exposures': {},
                    'risk_approvals': [
                        _rejected_decision(
                            position=position,
                            violations=violations,
                            warnings=warnings,
                            scaling={'reason': 'portfolio_kill_switch_active'},
                        )
                        for position in payload.positions
                    ],
                },
                error='risk_kill_switch_active',
            )

    decisions: list[dict[str, Any]] = []
    projected_total = float(payload.current_total_exposure)
    bucket_exposures = defaultdict(float)
    sector_exposures = defaultdict(float)
    for bucket, value in payload.current_bucket_exposures.items():
        bucket_exposures[str(bucket)] = float(value or 0.0)
    for sector, value in payload.current_sector_exposures.items():
        sector_exposures[str(sector)] = float(value or 0.0)

    ordered_positions = sorted(
        list(payload.positions),
        key=lambda pos: (BUCKET_PRIORITY.get(_bucket_from_position(pos), 99), -float((pos.score_breakdown or {}).get('final_opportunity_score') or 0.0)),
    )

    for position in ordered_positions:
        symbol = str(position.symbol).upper()
        bucket = _bucket_from_position(position)
        sector = _sector_from_position(position)

        scaled_position, pre_violations, pre_warnings, scaling = _scale_position_to_limits(
            payload=payload,
            position=position,
            projected_total=projected_total,
            bucket_exposure=bucket_exposures[bucket],
        )
        if scaled_position is None:
            decisions.append(_rejected_decision(position=position, violations=pre_violations, warnings=pre_warnings, scaling=scaling))
            continue

        position_value = position.entry_price * position.requested_quantity
        risk_payload = _build_risk_request(
            payload=payload,
            position=scaled_position,
            current_total_exposure=projected_total,
            bucket_exposure=bucket_exposures[bucket],
        )
        response = check_order(risk_payload)
        data = response.data or {}
        approved = bool(data.get('approved'))
        final_quantity = float(data.get('final_quantity') or 0.0)
        approved_value = position.entry_price * final_quantity
        warnings = list(dict.fromkeys(pre_warnings + (data.get('warnings', []) or [])))
        violations = data.get('violations', []) or []

        if approved:
            projected_total += approved_value
            bucket_exposures[bucket] += approved_value
            if sector:
                sector_exposures[sector] += approved_value

        decisions.append(
            {
                'symbol': symbol,
                'approved': approved,
                'status': response.status,
                'strategy_bucket': bucket,
                'target_weight': risk_payload.target_weight,
                'allocation_pct': risk_payload.allocation_pct,
                'target_value': position.portfolio_context.get('target_value'),
                'requested_quantity': position.requested_quantity,
                'final_quantity': final_quantity,
                'requested_value': round(position_value, 2),
                'approved_value': round(approved_value, 2),
                'risk_response': {**data, 'warnings': warnings, 'scaling': scaling},
                'violations': violations,
                'warnings': warnings,
                'scaling': scaling,
            }
        )

    approved_count = sum(1 for row in decisions if row['approved'])
    rejected_count = len(decisions) - approved_count
    return StandardResponse(
        status='approved' if rejected_count == 0 else 'partial' if approved_count else 'rejected',
        data={
            'approved': rejected_count == 0,
            'mode': 'portfolio_allocation',
            'total_positions': len(decisions),
            'approved_positions': approved_count,
            'rejected_positions': rejected_count,
            'projected_total_exposure': round(projected_total, 2),
            'projected_bucket_exposures': {bucket: round(value, 2) for bucket, value in bucket_exposures.items()},
            'projected_sector_exposures': {sector: round(value, 2) for sector, value in sector_exposures.items()},
            'risk_approvals': decisions,
            'kill_switch_active': False,
        },
        error=None if rejected_count == 0 else 'portfolio_risk_check_failed',
    )
