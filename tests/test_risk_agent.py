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
        'margin_multiplier': 1,
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
        'margin_multiplier': 1,
    }
    response = client.post('/risk/check', json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'invalid_protection_direction' in body['data']['violations']
