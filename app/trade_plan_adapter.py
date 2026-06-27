from __future__ import annotations

from typing import Any

from app.checks import check_order
from app.models import RiskCheckRequest, StandardResponse, TradePlanRiskCheckRequest


def _session_value(context: dict[str, Any], key: str, default: Any) -> Any:
    return context.get(key, default)


def trade_plan_to_risk_check(payload: TradePlanRiskCheckRequest) -> RiskCheckRequest:
    """Convert a Manager TradePlan into the existing RiskCheckRequest contract."""
    plan = payload.trade_plan
    entry_price = plan.limit_price or plan.entry_price
    if entry_price is None:
        raise ValueError('trade_plan entry_price or limit_price is required')
    if plan.exit.stop_loss is None:
        raise ValueError('trade_plan exit.stop_loss is required for risk check')

    equity = payload.equity or plan.risk.account_equity
    if equity is None:
        raise ValueError('equity or trade_plan.risk.account_equity is required')

    quantity = plan.final_quantity or plan.quantity
    session = payload.session_risk_context or {}

    return RiskCheckRequest(
        account_id=int(plan.account_id),
        symbol=plan.symbol.upper(),
        side=plan.side,
        entry_price=entry_price,
        protection_price=plan.exit.stop_loss,
        requested_quantity=quantity,
        equity=equity,
        current_symbol_exposure=payload.current_symbol_exposure,
        current_total_exposure=payload.current_total_exposure,
        open_orders_exposure=payload.open_orders_exposure,
        margin_multiplier=payload.margin_multiplier,
        trading_mode=payload.trading_mode,
        asset_class=payload.asset_class,
        sector=payload.sector,
        owned_quantity=payload.owned_quantity,
        current_sector_exposure=payload.current_sector_exposure,
        strategy_bucket=plan.strategy_bucket,
        current_bucket_exposure=payload.current_bucket_exposure,
        target_weight=payload.target_weight,
        allocation_pct=payload.allocation_pct,
        target_value=payload.target_value,
        daily_realized_pnl=_session_value(session, 'daily_realized_pnl', 0.0),
        weekly_realized_pnl=_session_value(session, 'weekly_realized_pnl', 0.0),
        consecutive_losses=_session_value(session, 'consecutive_losses', 0),
        trades_today=_session_value(session, 'trades_today', 0),
        symbol_trades_today=_session_value(session, 'symbol_trades_today', 0),
        minutes_since_last_loss=session.get('minutes_since_last_loss'),
        minutes_since_last_symbol_trade=session.get('minutes_since_last_symbol_trade'),
        emergency_halt=_session_value(session, 'emergency_halt', False),
    )


def check_trade_plan(payload: TradePlanRiskCheckRequest) -> StandardResponse:
    """Validate a TradePlan by reusing the existing order risk engine."""
    try:
        risk_payload = trade_plan_to_risk_check(payload)
    except ValueError as exc:
        return StandardResponse(
            status='rejected',
            data={
                'approved': False,
                'approved_quantity': 0.0,
                'final_quantity': 0.0,
                'violations': ['invalid_trade_plan'],
                'warnings': [],
                'trade_plan_id': payload.trade_plan.plan_id,
                'reason': str(exc),
            },
            error='risk_check_failed',
        )

    response = check_order(risk_payload)
    data = dict(response.data or {})
    data.update(
        {
            'trade_plan_id': payload.trade_plan.plan_id,
            'correlation_id': payload.trade_plan.correlation_id,
            'strategy': payload.trade_plan.strategy,
            'strategy_bucket': payload.trade_plan.strategy_bucket,
            'source': payload.trade_plan.source,
            'risk_approval_id': payload.trade_plan.risk_approval_id,
            'trade_plan_validation': 'checked',
        }
    )
    return StandardResponse(status=response.status, data=data, error=response.error)
