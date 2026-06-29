from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def base_payload():
    return {
        'symbol': 'AAPL',
        'decision': {
            'decision': 'candidate_approved',
            'confidence': 'high',
            'recommended_strategy': 'trend_following',
            'backtest_best_strategy': 'trend_following',
            'reason': 'validated by manager',
        },
        'market_context': {
            'position_size_multiplier': 1.0,
            'risk_budget_multiplier': 0.8,
            'exposure_cap': 0.5,
            'effective_size_multiplier': 0.8,
            'allowed_strategies': ['trend_following', 'breakout', 'sma_crossover'],
            'blocked_strategies': ['mean_reversion'],
            'decision_notes': ['bull regime allows directional strategies'],
        },
        'account': {
            'equity': 100000,
            'current_exposure_pct': 0.20,
            'current_symbol_exposure_pct': 0.05,
            'open_orders_exposure_pct': 0.05,
        },
        'requested_position_pct': 0.10,
        'trading_mode': 'PAPER',
    }


def test_manager_gate_approves_valid_candidate():
    response = client.post('/risk/manager-gate', json=base_payload())
    body = response.json()

    assert response.status_code == 200
    assert body['status'] == 'approved'
    assert body['data']['approved'] is True
    assert body['data']['max_position_pct'] == 0.08
    assert body['data']['max_position_value'] == 8000
    assert body['data']['projected_exposure_pct'] == 0.35
    assert body['data']['violations'] == []


def test_manager_gate_rejects_review_decision():
    payload = base_payload()
    payload['decision']['decision'] = 'needs_review'

    response = client.post('/risk/manager-gate', json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert body['data']['approved'] is False
    assert 'manager_decision_requires_review' in body['data']['violations']


def test_manager_gate_rejects_strategy_mismatch():
    payload = base_payload()
    payload['decision']['backtest_best_strategy'] = 'mean_reversion'

    response = client.post('/risk/manager-gate', json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'strategy_mismatch' in body['data']['violations']


def test_manager_gate_rejects_exposure_cap_breach():
    payload = base_payload()
    payload['account']['current_exposure_pct'] = 0.45
    payload['account']['open_orders_exposure_pct'] = 0.05
    payload['requested_position_pct'] = 0.10

    response = client.post('/risk/manager-gate', json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'market_exposure_cap_exceeded' in body['data']['violations']


def test_manager_gate_rejects_strategy_not_allowed():
    payload = base_payload()
    payload['market_context']['allowed_strategies'] = ['breakout', 'sma_crossover']

    response = client.post('/risk/manager-gate', json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'strategy_not_allowed_by_market_context' in body['data']['violations']


def test_health_and_status_include_manager_gate_flags():
    health = client.get('/health').json()
    status = client.get('/risk/status').json()

    assert health['data']['manager_decision_gate'] is True
    assert status['data']['ready_for_manager_decision_gate'] is True
