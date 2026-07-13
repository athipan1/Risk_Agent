from app.models import PositionSizeRequest, StandardResponse
from app.policy import MAX_POSITION_PCT, MAX_TRADE_LOSS_PCT, MIN_PROTECTION_DISTANCE_PCT
from app.runtime_halt import is_emergency_halt_active


def has_bad_protection_direction(side: str, entry_price: float, protection_price: float) -> bool:
    if side == 'buy':
        return protection_price >= entry_price
    if side == 'sell':
        return protection_price <= entry_price
    return False


def calculate_position_size(payload: PositionSizeRequest) -> StandardResponse:
    if is_emergency_halt_active():
        return StandardResponse(
            status='rejected',
            data={
                'approved': False,
                'approved_quantity': 0.0,
                'violations': ['emergency_halt_active'],
            },
            error='emergency_halt_active',
        )

    if payload.side == 'hold':
        return StandardResponse(status='success', data={'approved_quantity': 0.0})

    if has_bad_protection_direction(payload.side, payload.entry_price, payload.protection_price):
        return StandardResponse(status='error', error='invalid_protection_direction')

    distance = abs(payload.entry_price - payload.protection_price)
    minimum_distance = payload.entry_price * MIN_PROTECTION_DISTANCE_PCT
    if distance < minimum_distance:
        return StandardResponse(status='error', error='protection_price_too_close')

    max_loss_amount = payload.equity * MAX_TRADE_LOSS_PCT
    quantity_by_loss = max_loss_amount / distance
    max_position_value = payload.equity * MAX_POSITION_PCT
    quantity_by_value = max_position_value / payload.entry_price
    approved_quantity = min(quantity_by_loss, quantity_by_value)

    return StandardResponse(
        status='success',
        data={
            'approved_quantity': round(approved_quantity, 8),
            'max_position_value': round(max_position_value, 2),
            'max_loss_amount': round(max_loss_amount, 2),
            'protection_distance': round(distance, 8),
        },
    )
