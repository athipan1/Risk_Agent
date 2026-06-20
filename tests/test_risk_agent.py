from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_position_size_uses_safe_limit():
    payload = {
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 95,
        'equity': 10000,
    }
    response = client.post('/risk/position-size', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'success'
    assert body['data']['approved_quantity'] == 10
    assert body['data']['max_position_value'] == 1000
    assert body['data']['max_loss_amount'] == 100


def test_rejects_large_position():
    payload = {
        'account_id': 1,
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 95,
        'requested_quantity': 200,
        'equity': 10000,
        'current_symbol_exposure': 0,
        'current_total_exposure': 0,
        'open_orders_exposure': 0,
        'margin_multiplier': 1,
        'trading_mode': 'PAPER',
    }
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'position_size_limit_exceeded' in body['data']['violations']


def test_rejects_bad_protection_direction():
    payload = {
        'account_id': 1,
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 105,
        'requested_quantity': 5,
        'equity': 10000,
        'current_symbol_exposure': 0,
        'current_total_exposure': 0,
        'open_orders_exposure': 0,
        'margin_multiplier': 1,
        'trading_mode': 'PAPER',
    }
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'invalid_protection_direction' in body['data']['violations']


def test_live_rejects_missing_context_fields():
    payload = {
        'account_id': 1,
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 95,
        'requested_quantity': 5,
        'equity': 10000,
        'trading_mode': 'LIVE',
    }
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert body['data']['approved'] is False
    assert 'live_context_required' in body['data']['violations']
    assert body['data']['missing_context_fields'] == [
        'current_symbol_exposure',
        'current_total_exposure',
        'margin_multiplier',
        'open_orders_exposure',
    ]


def test_live_allows_explicit_zero_context_fields():
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
    }
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert 'live_context_required' not in body['data']['violations']
    assert body['data']['trading_mode'] == 'LIVE'
    assert body['data']['current_total_exposure'] == 0
    assert body['data']['open_orders_exposure'] == 0


def test_paper_keeps_default_context_backward_compatible():
    payload = {
        'account_id': 1,
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 95,
        'requested_quantity': 5,
        'equity': 10000,
        'trading_mode': 'PAPER',
    }
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert 'live_context_required' not in body['data']['violations']
    assert body['data']['projected_total_exposure'] == 500


def test_open_orders_exposure_counts_toward_portfolio_limit():
    payload = {
        'account_id': 1,
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 95,
        'requested_quantity': 5,
        'equity': 10000,
        'current_symbol_exposure': 0,
        'current_total_exposure': 9500,
        'open_orders_exposure': 600,
        'margin_multiplier': 1,
        'trading_mode': 'LIVE',
    }
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'portfolio_exposure_limit_exceeded' in body['data']['violations']
    assert body['data']['projected_total_exposure'] == 10600
    assert body['data']['trading_mode'] == 'LIVE'


def test_accepts_manager_payload_fields_when_within_limits():
    payload = {
        'account_id': 1,
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 95,
        'requested_quantity': 5,
        'equity': 10000,
        'current_symbol_exposure': 100,
        'current_total_exposure': 1000,
        'open_orders_exposure': 200,
        'margin_multiplier': 1,
        'trading_mode': 'PAPER',
    }
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'approved'
    assert body['data']['open_orders_exposure'] == 200
    assert body['data']['projected_total_exposure'] == 1700
    assert body['data']['guard_plan']['trading_mode'] == 'PAPER'
