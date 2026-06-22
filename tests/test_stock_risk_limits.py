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
        'trading_mode': 'PAPER',
        'asset_class': 'stock',
        'sector': 'Technology',
        'owned_quantity': 0,
        'current_sector_exposure': 0,
    }
    payload.update(overrides)
    return payload


def test_risk_status_exposes_stock_policy():
    response = client.get('/risk/status')
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'success'
    assert body['data']['stock_only_mode'] is True
    assert body['data']['allow_short_selling'] is False


def test_stock_only_mode_blocks_crypto_like_symbol():
    response = client.post('/risk/check', json=base_payload(symbol='BTCUSD'))
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'stock_symbol_required' in body['data']['violations']


def test_stock_only_mode_blocks_gold_symbol():
    response = client.post('/risk/check', json=base_payload(symbol='XAUUSD'))
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'stock_symbol_required' in body['data']['violations']


def test_long_only_blocks_sell_more_than_owned_quantity():
    response = client.post('/risk/check', json=base_payload(side='sell', requested_quantity=5, owned_quantity=2, protection_price=105))
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'short_selling_disabled' in body['data']['violations']


def test_allows_sell_owned_position_when_not_shorting():
    response = client.post('/risk/check', json=base_payload(side='sell', requested_quantity=5, owned_quantity=5, protection_price=105))
    body = response.json()
    assert response.status_code == 200
    assert 'short_selling_disabled' not in body['data']['violations']


def test_blocks_fractional_shares_by_default():
    response = client.post('/risk/check', json=base_payload(requested_quantity=1.5))
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'fractional_shares_disabled' in body['data']['violations']


def test_blocks_sector_exposure_limit_when_sector_context_present():
    response = client.post('/risk/check', json=base_payload(requested_quantity=5, current_sector_exposure=2450))
    body = response.json()
    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'sector_exposure_limit_exceeded' in body['data']['violations']
    assert body['data']['stock_risk']['projected_sector_exposure'] == 2950
