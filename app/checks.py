from app.models import RiskCheckRequest, StandardResponse
from app.policy import MAX_MARGIN_MULTIPLIER, MAX_POSITION_PCT, MAX_TOTAL_EXPOSURE_PCT
from app.sizing import calculate_position_size


def check_order(payload: RiskCheckRequest) -> StandardResponse:
    violations = []
    warnings = []

    if payload.side == 'hold':
        return StandardResponse(
            status='approved',
            data={'approved': True, 'approved_quantity': 0.0, 'violations': [], 'warnings': []},
        )

    position_value = payload.entry_price * payload.requested_quantity
    max_position_value = payload.equity * MAX_POSITION_PCT
    if position_value > max_position_value:
        violations.append('position_size_limit_exceeded')

    projected_total = payload.current_total_exposure + position_value
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

    approved = len(violations) == 0
    if max_position_value == 0:
        risk_score = 1.0
    else:
        risk_score = min(1.0, position_value / max_position_value)

    return StandardResponse(
        status='approved' if approved else 'rejected',
        data={
            'approved': approved,
            'risk_score': round(risk_score, 4),
            'approved_quantity': approved_quantity,
            'max_position_value': round(max_position_value, 2),
            'max_total_exposure': round(max_total, 2),
            'position_value': round(position_value, 2),
            'protection_required': True,
            'violations': violations,
            'warnings': warnings,
        },
        error=None if approved else 'risk_check_failed',
    )
