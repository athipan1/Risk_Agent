from __future__ import annotations

from typing import Any

from app.checks import check_order
from app.models import RiskCheckRequest, StandardResponse, TradePlanRiskCheckRequest
from app.strategy_bucket_gate import (
    classification_fields_from_mapping,
    evaluate_strategy_bucket_gate,
)

SESSION_CONTEXT_FIELDS = {
    'daily_realized_pnl',
    'weekly_realized_pnl',
    'consecutive_losses',
    'trades_today',
    'symbol_trades_today',
    'minutes_since_last_loss',
    'minutes_since_last_symbol_trade',
    'emergency_halt',
}


def _session_value(context: dict[str, Any], key: str, default: Any) -> Any:
    return context[key] if key in context else default


def _mark_live_session_fields_as_unset_if_missing(
    *,
    risk_payload: RiskCheckRequest,
    session_context: dict[str, Any],
) -> None:
    """Preserve existing LIVE behavior when TradePlan session context is missing."""
    provided = getattr(risk_payload, 'model_fields_set', None)
    if not isinstance(provided, set):
        return
    for field_name in SESSION_CONTEXT_FIELDS:
        if field_name not in session_context:
            provided.discard(field_name)


def _trade_plan_classification_fields(plan) -> dict[str, Any]:
    metadata = plan.metadata or {}
    portfolio_context = metadata.get('portfolio_context')
    portfolio_context = portfolio_context if isinstance(portfolio_context, dict) else {}
    metadata_fields = classification_fields_from_mapping(metadata)
    portfolio_fields = classification_fields_from_mapping(portfolio_context)
    return {
        'bucket_confidence': (
            plan.bucket_confidence
            if plan.bucket_confidence is not None
            else metadata_fields['bucket_confidence']
            if metadata_fields['bucket_confidence'] is not None
            else portfolio_fields['bucket_confidence']
        ),
        'classification_status': (
            plan.bucket_classification_status
            or metadata_fields['classification_status']
            or portfolio_fields['classification_status']
        ),
        'classifier_version': (
            plan.bucket_classifier_version
            or metadata_fields['classifier_version']
            or portfolio_fields['classifier_version']
        ),
        'classification_reasons': (
            plan.bucket_classification_reasons
            or metadata_fields['classification_reasons']
            or portfolio_fields['classification_reasons']
        ),
    }


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
    classification = _trade_plan_classification_fields(plan)

    risk_payload = RiskCheckRequest(
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
        bucket_confidence=classification['bucket_confidence'],
        bucket_classification_status=classification['classification_status'],
        bucket_classifier_version=classification['classifier_version'],
        bucket_classification_reasons=classification['classification_reasons'],
        current_bucket_exposure=payload.current_bucket_exposure,
        target_weight=payload.target_weight,
        allocation_pct=payload.allocation_pct,
        target_value=payload.target_value,
        take_profit_price=plan.exit.take_profit,
        reward_risk_ratio=plan.risk.reward_risk_ratio or plan.expected_r,
        daily_realized_pnl=_session_value(session, 'daily_realized_pnl', 0.0),
        weekly_realized_pnl=_session_value(session, 'weekly_realized_pnl', 0.0),
        consecutive_losses=_session_value(session, 'consecutive_losses', 0),
        trades_today=_session_value(session, 'trades_today', 0),
        symbol_trades_today=_session_value(session, 'symbol_trades_today', 0),
        minutes_since_last_loss=session.get('minutes_since_last_loss'),
        minutes_since_last_symbol_trade=session.get('minutes_since_last_symbol_trade'),
        emergency_halt=_session_value(session, 'emergency_halt', False),
    )
    if payload.trading_mode == 'LIVE':
        _mark_live_session_fields_as_unset_if_missing(
            risk_payload=risk_payload,
            session_context=session,
        )
    return risk_payload


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

    bucket_gate_result = evaluate_strategy_bucket_gate(
        side=risk_payload.side,
        strategy_bucket=risk_payload.strategy_bucket,
        trading_mode=risk_payload.trading_mode,
        bucket_confidence=risk_payload.bucket_confidence,
        classification_status=risk_payload.bucket_classification_status,
        classifier_version=risk_payload.bucket_classifier_version,
        classification_reasons=risk_payload.bucket_classification_reasons,
        require_metadata=risk_payload.side == 'buy',
    )
    bucket_gate = bucket_gate_result.as_dict()
    if bucket_gate_result.violations:
        return StandardResponse(
            status='rejected',
            data={
                'approved': False,
                'approved_quantity': 0.0,
                'final_quantity': 0.0,
                'violations': list(bucket_gate_result.violations),
                'warnings': list(bucket_gate_result.warnings),
                'trade_plan_id': payload.trade_plan.plan_id,
                'correlation_id': payload.trade_plan.correlation_id,
                'strategy': payload.trade_plan.strategy,
                'strategy_bucket': payload.trade_plan.strategy_bucket,
                'strategy_bucket_gate': bucket_gate,
                'source': payload.trade_plan.source,
                'risk_approval_id': payload.trade_plan.risk_approval_id,
                'trade_plan_validation': 'bucket_gate_rejected',
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
            'strategy_bucket_gate': data.get('strategy_bucket_gate') or bucket_gate,
            'source': payload.trade_plan.source,
            'risk_approval_id': payload.trade_plan.risk_approval_id,
            'trade_plan_validation': 'checked',
        }
    )
    return StandardResponse(status=response.status, data=data, error=response.error)
