from app.clipping import can_clip_violations, cap_aware_max_buy_value, quantity_for_value
from app.kill_switch import kill_switch_from_risk_payload, rejected_kill_switch_payload
from app.models import RiskCheckRequest, StandardResponse
from app.policy import MAX_MARGIN_MULTIPLIER, MAX_POSITION_PCT, MAX_TOTAL_EXPOSURE_PCT
from app.session_limits import check_session_limits
from app.sizing import calculate_position_size
from app.stock_limits import check_stock_limits
from app.strategy_bucket_gate import evaluate_strategy_bucket_gate

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

DEFAULT_REWARD_RISK_RATIO = 2.0


def _round_price(value: float) -> float:
    return round(float(value), 4)


def _reward_risk_ratio(payload: RiskCheckRequest) -> float:
    requested_ratio = payload.reward_risk_ratio or DEFAULT_REWARD_RISK_RATIO
    return max(float(requested_ratio), DEFAULT_REWARD_RISK_RATIO)


def _default_take_profit_price(payload: RiskCheckRequest, reward_risk_ratio: float) -> float:
    risk_per_share = abs(payload.entry_price - payload.protection_price)
    reward_distance = risk_per_share * reward_risk_ratio
    if payload.side == 'buy':
        return payload.entry_price + reward_distance
    return payload.entry_price - reward_distance


def _take_profit_price(payload: RiskCheckRequest, reward_risk_ratio: float) -> float:
    return payload.take_profit_price or _default_take_profit_price(payload, reward_risk_ratio)


def _actual_reward_risk_ratio(payload: RiskCheckRequest, take_profit_price: float) -> float:
    risk_per_share = abs(payload.entry_price - payload.protection_price)
    reward_per_share = abs(take_profit_price - payload.entry_price)
    if risk_per_share <= 0:
        return 0.0
    return reward_per_share / risk_per_share


def build_guard_plan(payload: RiskCheckRequest, quantity: float) -> dict:
    exit_side = 'sell' if payload.side == 'buy' else 'buy'
    reward_risk_ratio = _reward_risk_ratio(payload)
    take_profit_price = _take_profit_price(payload, reward_risk_ratio)
    actual_reward_risk_ratio = _actual_reward_risk_ratio(payload, take_profit_price)
    return {
        'account_id': payload.account_id,
        'symbol': payload.symbol,
        'side': exit_side,
        'quantity': quantity,
        'trigger_price': payload.protection_price,
        'take_profit_price': _round_price(take_profit_price),
        'reward_risk_ratio': round(actual_reward_risk_ratio, 4),
        'min_reward_risk_ratio': DEFAULT_REWARD_RISK_RATIO,
        'time_in_force': 'GTC',
        'trading_mode': payload.trading_mode,
        'asset_class': payload.asset_class,
    }


def missing_live_context_fields(payload: RiskCheckRequest) -> list[str]:
    provided_fields = getattr(payload, 'model_fields_set', set())
    return sorted(LIVE_REQUIRED_CONTEXT_FIELDS - provided_fields)


def _rejected_response(
    payload: RiskCheckRequest,
    violations: list[str],
    warnings: list[str],
    extra_data: dict | None = None,
) -> StandardResponse:
    data = {
        'approved': False,
        'approved_quantity': 0.0,
        'final_quantity': 0.0,
        'trading_mode': payload.trading_mode,
        'asset_class': payload.asset_class,
        'strategy_bucket': payload.strategy_bucket,
        'violations': violations,
        'warnings': warnings,
    }
    if extra_data:
        data.update(extra_data)
    return StandardResponse(status='rejected', data=data, error='risk_check_failed')


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _allocation_aware(payload: RiskCheckRequest) -> bool:
    return (
        payload.strategy_bucket != 'unassigned'
        or payload.target_weight is not None
        or payload.allocation_pct is not None
        or payload.target_value is not None
    )


def _strategy_bucket_gate(payload: RiskCheckRequest):
    provided_fields = getattr(payload, 'model_fields_set', set())
    allow_legacy_missing_bucket = (
        payload.trading_mode == 'PAPER'
        and 'strategy_bucket' not in provided_fields
    )
    return evaluate_strategy_bucket_gate(
        side=payload.side,
        strategy_bucket=payload.strategy_bucket,
        trading_mode=payload.trading_mode,
        bucket_confidence=payload.bucket_confidence,
        classification_status=payload.bucket_classification_status,
        classifier_version=payload.bucket_classifier_version,
        classification_reasons=payload.bucket_classification_reasons,
        require_metadata=False,
        allow_legacy_missing_bucket=allow_legacy_missing_bucket,
    )


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
    bucket_gate: dict,
) -> StandardResponse | None:
    if payload.side != 'buy' or not _allocation_aware(payload) or not can_clip_violations(violations):
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
            'strategy_bucket': payload.strategy_bucket,
            'strategy_bucket_gate': bucket_gate,
            'protection_required': True,
            'guard_plan': build_guard_plan(payload, clipped_quantity),
            'session_risk': session_metrics,
            'kill_switch_active': False,
            'stock_risk': {**stock_metrics, 'cap_clip_limits': cap_limits},
            'cap_clipped': True,
            'original_violations': violations,
            'violations': [],
            'warnings': clip_warnings,
        },
        error=None,
    )


def check_order(payload: RiskCheckRequest) -> StandardResponse:
    violations: list[str] = []
    warnings: list[str] = []
    bucket_gate_result = _strategy_bucket_gate(payload)
    bucket_gate = bucket_gate_result.as_dict()
    warnings.extend(bucket_gate_result.warnings)

    if payload.side == 'hold':
        return StandardResponse(
            status='approved',
            data={
                'approved': True,
                'approved_quantity': 0.0,
                'final_quantity': 0.0,
                'guard_plan': None,
                'strategy_bucket': payload.strategy_bucket,
                'strategy_bucket_gate': bucket_gate,
                'violations': [],
                'warnings': _dedupe(warnings),
                'kill_switch_active': False,
            },
        )

    if bucket_gate_result.violations:
        violations.extend(bucket_gate_result.violations)
        return _rejected_response(
            payload,
            _dedupe(violations),
            _dedupe(warnings),
            {'strategy_bucket_gate': bucket_gate},
        )

    if payload.trading_mode == 'LIVE':
        missing_context = missing_live_context_fields(payload)
        if missing_context:
            violations.append('live_context_required')
            return _rejected_response(
                payload,
                violations,
                _dedupe(warnings),
                {
                    'missing_context_fields': missing_context,
                    'strategy_bucket_gate': bucket_gate,
                },
            )

    kill_switch_active, session_violations, session_warnings, session_metrics = kill_switch_from_risk_payload(payload)
    if kill_switch_active:
        return StandardResponse(
            status='rejected',
            data={
                **rejected_kill_switch_payload(
                    trading_mode=payload.trading_mode,
                    asset_class=payload.asset_class,
                    violations=session_violations,
                    warnings=_dedupe(warnings + session_warnings),
                    metrics=session_metrics,
                ),
                'strategy_bucket': payload.strategy_bucket,
                'strategy_bucket_gate': bucket_gate,
            },
            error='risk_kill_switch_active',
        )

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
        bucket_gate=bucket_gate,
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
            'strategy_bucket': payload.strategy_bucket,
            'strategy_bucket_gate': bucket_gate,
            'protection_required': True,
            'guard_plan': guard_plan,
            'session_risk': session_metrics,
            'kill_switch_active': False,
            'stock_risk': stock_metrics,
            'violations': violations,
            'warnings': warnings,
        },
        error=None if approved else 'risk_check_failed',
    )
