from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def base_payload(**overrides):
    payload = {
        'account_id': 1,
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 95,
        'requested_quantity': 5,
        'equity': 10000,
        'current_symbol_exposure': 0,
        'current_total_exposure': 0,
        'open_orders_exposure': 0,
        'margin_multiplier': 1,
        'trading_mode': 'LIVE',
        'daily_realized_pnl': 0,
        'weekly_realized_pnl': 0,
        'consecutive_losses': 0,
        'trades_today': 0,
        'symbol_trades_today': 0,
        'minutes_since_last_loss': 120,
        'minutes_since_last_symbol_trade': 120,
        'emergency_halt': False,
    }
    payload.update(overrides)
    return payload


def assert_rejected_for(payload, violation):
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert body['data']['approved'] is False
    assert violation in body['data']['violations']
    assert body['data']['final_quantity'] == 0.0


def test_rejects_daily_loss_limit():
    assert_rejected_for(base_payload(daily_realized_pnl=-50), 'daily_loss_limit_exceeded')


def test_rejects_weekly_loss_limit():
    assert_rejected_for(base_payload(weekly_realized_pnl=-150), 'weekly_loss_limit_exceeded')


def test_rejects_max_consecutive_losses_and_cooldown():
    response = client.post('/risk/check', json=base_payload(consecutive_losses=3, minutes_since_last_loss=20))
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'max_consecutive_losses_exceeded' in body['data']['violations']
    assert 'loss_streak_cooldown_active' in body['data']['violations']


def test_rejects_max_trades_per_day():
    assert_rejected_for(base_payload(trades_today=5), 'max_trades_per_day_exceeded')


def test_rejects_symbol_trade_limit():
    assert_rejected_for(base_payload(symbol_trades_today=2), 'max_symbol_trades_per_day_exceeded')


def test_rejects_symbol_cooldown():
    assert_rejected_for(base_payload(minutes_since_last_symbol_trade=10), 'symbol_cooldown_active')


def test_rejects_emergency_halt():
    assert_rejected_for(base_payload(emergency_halt=True), 'emergency_halt_active')


def test_approves_when_session_limits_are_clear():
    response = client.post('/risk/check', json=base_payload())
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'approved'
    assert body['data']['approved'] is True
    assert body['data']['session_risk']['trades_today'] == 0
    assert body['data']['guard_plan']['side'] == 'sell'


def test_live_requires_session_context_fields():
    payload = base_payload()
    payload.pop('daily_realized_pnl')
    payload.pop('weekly_realized_pnl')
    payload.pop('consecutive_losses')
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'live_context_required' in body['data']['violations']
    assert 'daily_realized_pnl' in body['data']['missing_context_fields']
    assert 'weekly_realized_pnl' in body['data']['missing_context_fields']
    assert 'consecutive_losses' in body['data']['missing_context_fields']
