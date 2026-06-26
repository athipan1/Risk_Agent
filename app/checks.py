from app.clipping import can_clip_violations, cap_aware_max_buy_value, quantity_for_value
from app.models import RiskCheckRequest, StandardResponse
from app.policy import MAX_MARGIN_MULTIPLIER, MAX_POSITION_PCT, MAX_TOTAL_EXPOSURE_PCT
from app.session_limits import check_session_limits
from app.sizing import calculate_position_size
from app.stock_limits import check_stock_limits

LIVE_REQUIRED_CONTEXT_FIELDS = {
    'current_symbol_exposure',
    'current_total_exposure',
    'open_orders_exposure',
    'margin_multiplier',
    'daily_realized_pnl',
    'weekly_realized_pnl',
    'consecutive_losses',
    'trades_today',
    'symbol_trades_today',
    'emergency_halt',
}


def build_guard_plan(payload: RiskCheckRequest, quantity: float) -> dict:
    exit_side = 'sell' if payload.side == 'buy' else 'buy'
    return {
        'account_id': payload.account_id,
        'symbol': payload.symbol,
        'side': exit_side,
        'quantity': quantity,
        'trigger_price': payload.protection_price,
        'time_in_force': 'GTC',
        'trading_mode': payload.trading_mode,
        'asset_class': payload.asset_class,
    }


def missing_live_context_fields(payload: RiskCheckRequest) -> list[str]:
    provided_fields = getattr(payload, 'model_fields_set', set())
    return sorted(LIVE_REQUIRED_CONTEXT_FIELDS - provided_fields)


def _rejected_response(payload: RiskCheckRequest, violations: list[str], warnings: list[str], extra_data: dict | None = None) -> StandardResponse:
    data = {
        'approved': False,
        'approved_quantity': 0.0,
        'final_quantity': 0.0,
        'trading_mode': payload.trading_mode,
        'asset_class': payload.asset_class,
        'violations': violations,
        'warnings': warnings,
    }
    if extra_data:
        data.update(extra_data)
    return StandardResponse(status='rejected', data=data, error='risk_check_failed')


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _cap_clipped_response(
    *,
    payload: RiskCheckRequest,
    violations: list[str],
    warnings: list[str],
    stock_metrics: dict,
    session_metrics: dict,
    max_position_value: float,
    max_total: float,
    position_value: float,
    projected_total: float,
    sizing_approved_quantity: float,
) -> StandardResponse | None:
    if payload.side != 'buy' or not can_clip_violations(violations):
        return None

    max_allowed_value, cap_limits = cap_aware_max_buy_value(payload)
    clipped_quantity = min(
        payload.requested_quantity,
        sizing_approved_quantity,
        quantity_for_value(max_allowed_value, payload.entry_price),
    )
    if clipped_quantity <= 0:
        return None

    clipped_value = payload.entry_price * clipped_quantity
    clipped_projected_total = payload.current_total_exposure + payload.open_orders_exposure + clipped_value
    clip_warnings = _dedupe(warnings + ['quantity_clipped_to_risk_cap'])
    risk_score = 1.0 if max_position_value == 0 else min(1.0, clipped_value / max_position_value)

    return StandardResponse(
        status='approved',
        data={
            'approved': True,
            'risk_score': round(risk_score, 4),
            'approved_quantity': sizing_approved_quantity,
            'final_quantity': clipped_quantity,
            'requested_quantity': payload.requested_quantity,
            'requested_value': round(position_value, 2),
            'approved_value': round(clipped_value, 2),
            'max_position_value': round(max_position_value, 2),
            'max_total_exposure': round(max_total, 2),
            'position_value': round(clipped_value, 2),
            'unclipped_position_value': round(position_value, 2),
            'current_symbol_exposure': round(payload.current_symbol_exposure, 2),
            'current_total_exposure': round(payload.current_total_exposure, 2),
            'open_orders_exposure': round(payload.open_orders_exposure, 2),
            'projected_total_exposure': round(clipped_projected_total, 2),
            'unclipped_projected_total_exposure': round(projected_total, 2),
            'trading_mode': payload.trading_mode,
            'asset_class': payload.asset_class,
            'protection_required': True,
            'guard_plan': build_guard_plan(payload, clipped_quantity),
            'session_risk': session_metrics,
            'stock_risk': {**stock_metrics, 'cap_clip_limits': cap_limits},
            'cap_clipped': True,
            'original_violations': violations,
            'violations': [],
            'warnings': clip_warnings,
        },
        error=None,
    )


def check_order(payload: RiskCheckRequest) -> StandardResponse:
    violations = []
    warnings = []

    if payload.side == 'hold':
        return StandardResponse(status='approved', data={'approved': True, 'approved_quantity': 0.0, 'guard_plan': None, 'violations': [], 'warnings': []})

    if payload.trading_mode == 'LIVE':
        missing_context = missing_live_context_fields(payload)
        if missing_context:
            violations.append('live_context_required')
            return _rejected_response(payload, violations, warnings, {'missing_context_fields': missing_context})

    session_violations, session_warnings, session_metrics = check_session_limits(payload)
    stock_violations, stock_warnings, stock_metrics = check_stock_limits(payload)
    violations.extend(session_violations)
    violations.extend(stock_violations)
    warnings.extend(session_warnings)
    warnings.extend(stock_warnings)

    position_value = payload.entry_price * payload.requested_quantity
    max_position_value = payload.equity * MAX_POSITION_PCT
    if position_value > max_position_value:
        violations.append('position_size_limit_exceeded')

    projected_total = payload.current_total_exposure + payload.open_orders_exposure + position_value
    max_total = payload.equity * MAX_TOTAL_EXPOSURE_PCT
    if projected_total > max_total:
        violations.append('portfolio_exposure_limit_exceeded')

    if payload.margin_multiplier > MAX_MARGIN_MULTIPLIER:
        violations.append('margin_multiplier_limit_exceeded')

    sizing = calculate_position_size(payload)
    approved_quantity = 0.0
    if sizing.status == 'error':
        violations.append(sizing.error or 'position_sizing_error')
    else:
        approved_quantity = sizing.data['approved_quantity']
        if payload.requested_quantity > approved_quantity:
            warnings.append('requested_quantity_above_safe_size')

    violations = _dedupe(violations)
    warnings = _dedupe(warnings)

    clipped = _cap_clipped_response(
        payload=payload,
        violations=violations,
        warnings=warnings,
        stock_metrics=stock_metrics,
        session_metrics=session_metrics,
        max_position_value=max_position_value,
        max_total=max_total,
        position_value=position_value,
        projected_total=projected_total,
        sizing_approved_quantity=approved_quantity,
    )
    if clipped is not None:
        return clipped

    approved = len(violations) == 0
    risk_score = 1.0 if max_position_value == 0 else min(1.0, position_value / max_position_value)
    final_quantity = min(payload.requested_quantity, approved_quantity) if approved else 0.0
    guard_plan = build_guard_plan(payload, final_quantity) if approved and final_quantity > 0 else None

    return StandardResponse(
        status='approved' if approved else 'rejected',
        data={
            'approved': approved,
            'risk_score': round(risk_score, 4),
            'approved_quantity': approved_quantity,
            'final_quantity': final_quantity,
            'max_position_value': round(max_position_value, 2),
            'max_total_exposure': round(max_total, 2),
            'position_value': round(position_value, 2),
            'current_symbol_exposure': round(payload.current_symbol_exposure, 2),
            'current_total_exposure': round(payload.current_total_exposure, 2),
            'open_orders_exposure': round(payload.open_orders_exposure, 2),
            'projected_total_exposure': round(projected_total, 2),
            'trading_mode': payload.trading_mode,
            'asset_class': payload.asset_class,
            'protection_required': True,
            'guard_plan': guard_plan,
            'session_risk': session_metrics,
            'stock_risk': stock_metrics,
            'violations': violations,
            'warnings': warnings
        },
        error=None if approved else 'risk_check_failed',
    )
