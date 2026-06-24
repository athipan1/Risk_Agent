from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.checks import check_order
from app.models import PortfolioRiskCheckRequest, PortfolioRiskPosition, RiskCheckRequest, StandardResponse


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
        strategy_bucket=bucket if bucket in {'core_dividend', 'value_rebound', 'news_momentum'} else 'unassigned',
        current_bucket_exposure=bucket_exposure,
        target_weight=_target_weight(position),
        allocation_pct=position.portfolio_context.get('allocation_pct'),
        target_value=position.portfolio_context.get('target_value'),
        daily_realized_pnl=float(session.get('daily_realized_pnl', 0.0)),
        weekly_realized_pnl=float(session.get('weekly_realized_pnl', 0.0)),
        consecutive_losses=int(session.get('consecutive_losses', 0)),
        trades_today=int(session.get('trades_today', 0)),
        symbol_trades_today=int(session.get('symbol_trades_today', 0)),
        minutes_since_last_loss=session.get('minutes_since_last_loss'),
        minutes_since_last_symbol_trade=session.get('minutes_since_last_symbol_trade'),
        emergency_halt=bool(session.get('emergency_halt', False)),
    )


def check_portfolio(payload: PortfolioRiskCheckRequest) -> StandardResponse:
    decisions: list[dict[str, Any]] = []
    projected_total = float(payload.current_total_exposure)
    bucket_exposures = defaultdict(float)
    for bucket, value in payload.current_bucket_exposures.items():
        bucket_exposures[str(bucket)] = float(value or 0.0)

    for position in payload.positions:
        symbol = str(position.symbol).upper()
        bucket = _bucket_from_position(position)
        position_value = position.entry_price * position.requested_quantity
        risk_payload = _build_risk_request(
            payload=payload,
            position=position,
            current_total_exposure=projected_total,
            bucket_exposure=bucket_exposures[bucket],
        )
        response = check_order(risk_payload)
        data = response.data or {}
        approved = bool(data.get('approved'))
        final_quantity = float(data.get('final_quantity') or 0.0)
        approved_value = position.entry_price * final_quantity

        if approved:
            projected_total += approved_value
            bucket_exposures[bucket] += approved_value

        decisions.append(
            {
                'symbol': symbol,
                'approved': approved,
                'status': response.status,
                'strategy_bucket': bucket,
                'target_weight': risk_payload.target_weight,
                'allocation_pct': risk_payload.allocation_pct,
                'target_value': risk_payload.target_value,
                'requested_quantity': position.requested_quantity,
                'final_quantity': final_quantity,
                'requested_value': round(position_value, 2),
                'approved_value': round(approved_value, 2),
                'risk_response': data,
                'violations': data.get('violations', []),
                'warnings': data.get('warnings', []),
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
            'risk_approvals': decisions,
        },
        error=None if rejected_count == 0 else 'portfolio_risk_check_failed',
    )
