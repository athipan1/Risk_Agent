from app.checks import check_order
from app.models import RiskCheckRequest


def _payload(**overrides):
    data = {
        'account_id': 1,
        'symbol': 'ACGL',
        'side': 'buy',
        'entry_price': 100.0,
        'protection_price': 95.0,
        'equity': 100000.0,
        'requested_quantity': 340.0,
        'current_symbol_exposure': 0.0,
        'current_total_exposure': 0.0,
        'open_orders_exposure': 0.0,
        'margin_multiplier': 1.0,
        'trading_mode': 'PAPER',
        'asset_class': 'stock',
        'sector': 'Financial Services',
        'current_sector_exposure': 0.0,
        'strategy_bucket': 'value_rebound',
        'current_bucket_exposure': 0.0,
    }
    data.update(overrides)
    return RiskCheckRequest(**data)


def test_check_order_clips_oversized_bucket_symbol_quantity():
    response = check_order(_payload())

    assert response.status == 'approved'
    data = response.data
    assert data['approved'] is True
    assert data['cap_clipped'] is True
    assert data['final_quantity'] == 70.0
    assert data['approved_value'] == 7000.0
    assert 'bucket_symbol_exposure_limit_exceeded' in data['original_violations']
    assert data['violations'] == []
    assert 'quantity_clipped_to_risk_cap' in data['warnings']
    assert data['guard_plan']['quantity'] == 70.0


def test_check_order_clips_to_remaining_symbol_budget_for_existing_exposure():
    response = check_order(_payload(current_symbol_exposure=6500.0, requested_quantity=100.0))

    assert response.status == 'approved'
    data = response.data
    assert data['cap_clipped'] is True
    assert data['final_quantity'] == 5.0
    assert data['approved_value'] == 500.0
    assert data['stock_risk']['cap_clip_limits']['bucket_symbol_exposure_limit'] == 500.0


def test_check_order_does_not_clip_when_no_risk_budget_remains():
    response = check_order(_payload(current_symbol_exposure=7000.0, requested_quantity=10.0))

    assert response.status == 'rejected'
    assert response.data['approved'] is False
    assert response.data['final_quantity'] == 0.0
    assert 'single_stock_exposure_limit_exceeded' in response.data['violations']


def test_check_order_kill_switch_rejects_before_cap_clipping():
    response = check_order(_payload(emergency_halt=True))

    assert response.status == 'rejected'
    assert response.error == 'risk_kill_switch_active'
    assert response.data['approved'] is False
    assert response.data['kill_switch_active'] is True
    assert response.data['final_quantity'] == 0.0
    assert 'emergency_halt_active' in response.data['violations']
    assert response.data.get('guard_plan') is None
