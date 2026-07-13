from __future__ import annotations

from app.models import ProfitPlanGateRequest, ProfitPlanAction, StandardResponse
from app.runtime_halt import is_emergency_halt_active

MOVE_STOP = 'move_stop'
PARTIAL_EXIT = 'partial_exit'
EXIT_ALL = 'exit_all'
HOLD = 'hold'
ALLOWED_ACTIONS = {MOVE_STOP, PARTIAL_EXIT, EXIT_ALL, HOLD}


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _action_name(action: ProfitPlanAction) -> str:
    return str(action.action).strip().lower()


def check_profit_plan_gate(payload: ProfitPlanGateRequest) -> StandardResponse:
    violations: list[str] = []
    warnings: list[str] = []
    approved_actions: list[dict] = []
    rejected_actions: list[dict] = []

    if is_emergency_halt_active():
        violations.append('emergency_halt_active')

    if payload.trading_mode == 'LIVE':
        warnings.append('live_mode_requires_external_manual_approval')

    if payload.position.quantity <= 0:
        violations.append('no_position_quantity')

    if payload.position.current_price <= 0 or payload.position.entry_price <= 0:
        violations.append('invalid_position_price')

    if payload.position.stop_loss is not None and payload.position.stop_loss <= 0:
        violations.append('invalid_stop_loss')

    current_r = payload.profit_plan.current_r_multiple
    if current_r is not None and current_r < -1.5:
        warnings.append('current_r_multiple_deeply_negative')

    for action in payload.profit_plan.actions:
        name = _action_name(action)
        action_errors: list[str] = []

        if name not in ALLOWED_ACTIONS:
            action_errors.append('unsupported_profit_action')

        if name == HOLD:
            if action.quantity not in (0, 0.0):
                action_errors.append('hold_quantity_must_be_zero')

        if name in {PARTIAL_EXIT, EXIT_ALL}:
            if action.quantity <= 0:
                action_errors.append('exit_quantity_must_be_positive')
            if action.quantity > payload.position.quantity:
                action_errors.append('exit_quantity_exceeds_position')

        if name == PARTIAL_EXIT:
            exit_pct = action.quantity / payload.position.quantity if payload.position.quantity > 0 else 0
            max_partial_exit_pct = payload.max_partial_exit_pct
            if exit_pct > max_partial_exit_pct:
                action_errors.append('partial_exit_pct_exceeds_limit')
            if current_r is not None and current_r < payload.min_partial_exit_r:
                action_errors.append('partial_exit_before_min_r')

        if name == EXIT_ALL and payload.require_manual_exit_all:
            action_errors.append('exit_all_requires_manual_approval')

        if name == MOVE_STOP:
            if action.recommended_stop is None or action.recommended_stop <= 0:
                action_errors.append('move_stop_requires_positive_recommended_stop')
            else:
                existing_stop = payload.position.stop_loss
                if existing_stop is not None and action.recommended_stop < existing_stop:
                    action_errors.append('move_stop_must_not_loosen_stop')
                if payload.position.side == 'long' and action.recommended_stop >= payload.position.current_price:
                    action_errors.append('long_stop_must_remain_below_current_price')
                if payload.position.side == 'short' and action.recommended_stop <= payload.position.current_price:
                    action_errors.append('short_stop_must_remain_above_current_price')

        record = {
            'action': name,
            'symbol': action.symbol.upper(),
            'quantity': action.quantity,
            'recommended_stop': action.recommended_stop,
            'reason': action.reason,
            'confidence_score': action.confidence_score,
            'violations': action_errors,
        }
        if action_errors:
            rejected_actions.append(record)
        else:
            approved_actions.append(record)

    if rejected_actions:
        violations.append('one_or_more_profit_actions_rejected')

    approved = not violations
    status = 'approved' if approved else 'rejected'

    return StandardResponse(
        status=status,
        data={
            'approved': approved,
            'symbol': payload.position.symbol.upper(),
            'trading_mode': payload.trading_mode,
            'advisory_only': True,
            'orders_submitted': False,
            'primary_action': payload.profit_plan.primary_action,
            'current_r_multiple': _round(current_r),
            'unrealized_pl_pct': _round(payload.profit_plan.unrealized_pl_pct),
            'approved_actions': approved_actions,
            'rejected_actions': rejected_actions,
            'violations': violations,
            'warnings': warnings,
            'risk_controls': {
                'max_partial_exit_pct': payload.max_partial_exit_pct,
                'min_partial_exit_r': payload.min_partial_exit_r,
                'require_manual_exit_all': payload.require_manual_exit_all,
            },
            'reason': 'Profit plan gate approved.' if approved else 'Profit plan gate rejected.',
        },
        error=None if approved else ','.join(violations),
    )
