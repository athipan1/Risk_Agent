from __future__ import annotations

from app.models import ManagerGateRequest, StandardResponse


APPROVED_DECISION = 'candidate_approved'
BLOCKED_DECISIONS = {'no_trade', 'rejected', 'blocked'}
REVIEW_DECISIONS = {'needs_review', 'manual_review', 'review'}


def _effective_multiplier(payload: ManagerGateRequest) -> float:
    context = payload.market_context
    candidates = [
        context.position_size_multiplier,
        context.risk_budget_multiplier,
        context.exposure_cap,
    ]
    if context.effective_size_multiplier is not None:
        candidates.append(context.effective_size_multiplier)
    return max(0.0, min(candidates))


def check_manager_gate(payload: ManagerGateRequest) -> StandardResponse:
    violations: list[str] = []
    warnings: list[str] = []
    notes = list(payload.market_context.decision_notes)

    decision = payload.decision.decision
    recommended_strategy = payload.decision.recommended_strategy
    best_strategy = payload.decision.backtest_best_strategy
    allowed_strategies = payload.market_context.allowed_strategies

    if decision in BLOCKED_DECISIONS:
        violations.append('manager_decision_blocks_trade')
    elif decision in REVIEW_DECISIONS:
        violations.append('manager_decision_requires_review')
    elif decision != APPROVED_DECISION:
        warnings.append('unknown_manager_decision')

    if payload.decision.confidence == 'low':
        violations.append('low_decision_confidence')

    if recommended_strategy and best_strategy and recommended_strategy != best_strategy:
        violations.append('strategy_mismatch')

    if allowed_strategies and recommended_strategy and recommended_strategy not in allowed_strategies:
        violations.append('strategy_not_allowed_by_market_context')

    exposure_cap = payload.market_context.exposure_cap
    projected_exposure_pct = (
        payload.account.current_exposure_pct
        + payload.account.open_orders_exposure_pct
        + payload.requested_position_pct
    )
    if projected_exposure_pct > exposure_cap:
        violations.append('market_exposure_cap_exceeded')

    effective_multiplier = _effective_multiplier(payload)
    max_position_pct = round(payload.requested_position_pct * effective_multiplier, 6)
    max_position_value = round(payload.account.equity * max_position_pct, 2)

    if max_position_pct <= 0:
        violations.append('zero_market_context_capacity')

    approved = not violations
    status = 'approved' if approved else 'rejected'

    return StandardResponse(
        status=status,
        data={
            'approved': approved,
            'symbol': payload.symbol.upper(),
            'trading_mode': payload.trading_mode,
            'decision': decision,
            'confidence': payload.decision.confidence,
            'recommended_strategy': recommended_strategy,
            'backtest_best_strategy': best_strategy,
            'effective_size_multiplier': effective_multiplier,
            'requested_position_pct': payload.requested_position_pct,
            'max_position_pct': max_position_pct,
            'max_position_value': max_position_value,
            'exposure_cap': exposure_cap,
            'current_exposure_pct': payload.account.current_exposure_pct,
            'open_orders_exposure_pct': payload.account.open_orders_exposure_pct,
            'projected_exposure_pct': round(projected_exposure_pct, 6),
            'allowed_strategies': allowed_strategies,
            'blocked_strategies': payload.market_context.blocked_strategies,
            'violations': violations,
            'warnings': warnings,
            'decision_notes': notes,
            'reason': 'Manager decision gate approved.' if approved else 'Manager decision gate rejected.',
        },
        error=None if approved else ','.join(violations),
    )
