import pytest
from fastapi.testclient import TestClient

import app.runtime_halt as runtime_halt
from app.main import app
from app.runtime_halt import EmergencyHaltState


ADMIN_TOKEN = 'test-admin-token'


def risk_payload():
    return {
        'account_id': 1,
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 95,
        'requested_quantity': 5,
        'equity': 10000,
        'trading_mode': 'PAPER',
    }


def position_size_payload():
    return {
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100,
        'protection_price': 95,
        'equity': 10000,
    }


def trade_plan_payload():
    return {
        'trade_plan': {
            'plan_id': 'runtime-halt-plan',
            'correlation_id': 'runtime-halt-correlation',
            'source': 'single_analysis',
            'status': 'risk_pending',
            'account_id': 1,
            'symbol': 'AAPL',
            'side': 'buy',
            'order_type': 'market',
            'entry_price': 100,
            'quantity': 5,
            'final_quantity': 5,
            'strategy': 'trend_pullback',
            'strategy_bucket': 'value_rebound',
            'bucket_confidence': 0.86,
            'bucket_classification_status': 'classified',
            'bucket_classification_reasons': ['low_pe_ratio:12'],
            'bucket_classifier_version': 'manager-strategy-bucket-v2',
            'final_verdict': 'buy',
            'confidence_score': 0.7,
            'expected_r': 2.0,
            'risk': {
                'account_equity': 10000,
                'max_loss_amount': 25,
                'max_loss_pct': 0.0025,
                'risk_per_share': 5,
                'position_value': 500,
                'position_pct': 0.05,
                'reward_risk_ratio': 2.0,
            },
            'exit': {'stop_loss': 95, 'take_profit': 110},
            'manual_approval_required': True,
            'dry_run': False,
        },
        'trading_mode': 'PAPER',
        'session_risk_context': {'emergency_halt': False},
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    state = EmergencyHaltState(
        flag_path=tmp_path / 'emergency_halt.flag',
        default_active=False,
    )
    monkeypatch.setattr(runtime_halt, '_STATE', state)
    monkeypatch.setenv('ADMIN_TOKEN', ADMIN_TOKEN)
    with TestClient(app) as test_client:
        yield test_client


def admin_headers(token=ADMIN_TOKEN):
    return {'X-Admin-Token': token}


def test_trip_rejects_new_risk_decisions_and_clear_restores_service(client):
    trip = client.post(
        '/risk/halt',
        headers=admin_headers(),
        json={'reason': 'broker anomaly detected'},
    )

    assert trip.status_code == 200
    assert trip.json()['data']['active'] is True
    assert trip.json()['data']['reason'] == 'broker anomaly detected'
    assert trip.json()['data']['updated_at']
    assert client.get('/ready').json()['data']['ready'] is False
    assert client.get('/risk/policy').json()['data']['emergency_halt'] is True
    assert client.get('/risk/status').json()['data']['ready_for_trade_plan_check'] is False

    risk = client.post('/risk/check', json=risk_payload()).json()
    sizing = client.post('/risk/position-size', json=position_size_payload()).json()
    trade_plan = client.post('/risk/trade-plan-check', json=trade_plan_payload()).json()

    assert risk['status'] == 'rejected'
    assert risk['data']['approved'] is False
    assert risk['data']['final_quantity'] == 0.0
    assert 'emergency_halt_active' in risk['data']['violations']
    assert sizing['status'] == 'rejected'
    assert sizing['data']['approved_quantity'] == 0.0
    assert 'emergency_halt_active' in sizing['data']['violations']
    assert trade_plan['status'] == 'rejected'
    assert trade_plan['data']['approved'] is False
    assert trade_plan['data']['final_quantity'] == 0.0
    assert 'emergency_halt_active' in trade_plan['data']['violations']

    clear = client.post(
        '/risk/halt/clear',
        headers=admin_headers(),
        json={'reason': 'broker health verified', 'confirm': True},
    )

    assert clear.status_code == 200
    assert clear.json()['data']['active'] is False
    assert clear.json()['data']['reason'] == 'broker health verified'
    assert client.get('/ready').json()['data']['ready'] is True
    assert client.get('/risk/policy').json()['data']['emergency_halt'] is False
    assert client.post('/risk/check', json=risk_payload()).json()['status'] == 'approved'
    assert client.post('/risk/position-size', json=position_size_payload()).json()['status'] == 'success'
    assert client.post('/risk/trade-plan-check', json=trade_plan_payload()).json()['status'] == 'approved'

    caller_halt_payload = risk_payload() | {'emergency_halt': True}
    caller_halt = client.post('/risk/check', json=caller_halt_payload).json()
    assert caller_halt['status'] == 'rejected'
    assert 'emergency_halt_active' in caller_halt['data']['violations']


@pytest.mark.parametrize(
    'path,payload',
    [
        ('/risk/halt', {'reason': 'operator test'}),
        ('/risk/halt/clear', {'reason': 'operator test', 'confirm': True}),
    ],
)
def test_admin_endpoints_reject_missing_and_wrong_tokens(client, path, payload):
    missing = client.post(path, json=payload)
    wrong = client.post(path, headers=admin_headers('wrong-token'), json=payload)

    assert missing.status_code == 401
    assert wrong.status_code == 403


def test_clear_requires_explicit_confirmation_and_reason(client):
    no_confirmation = client.post(
        '/risk/halt/clear',
        headers=admin_headers(),
        json={'reason': 'operator test', 'confirm': False},
    )
    blank_reason = client.post(
        '/risk/halt/clear',
        headers=admin_headers(),
        json={'reason': '   ', 'confirm': True},
    )

    assert no_confirmation.status_code == 422
    assert blank_reason.status_code == 422


def test_admin_endpoints_fail_closed_when_admin_token_is_not_configured(client, monkeypatch):
    monkeypatch.delenv('ADMIN_TOKEN')

    response = client.post(
        '/risk/halt',
        headers=admin_headers(),
        json={'reason': 'operator test'},
    )

    assert response.status_code == 503


def test_halt_state_survives_restart_and_syncs_across_workers(tmp_path):
    flag_path = tmp_path / 'emergency_halt.flag'
    first_worker = EmergencyHaltState(flag_path=flag_path, default_active=False)
    second_worker = EmergencyHaltState(flag_path=flag_path, default_active=False)

    first_worker.trip('restart persistence test')

    restarted_worker = EmergencyHaltState(flag_path=flag_path, default_active=False)
    assert restarted_worker.is_active() is True
    assert restarted_worker.snapshot()['reason'] == 'restart persistence test'
    assert second_worker.is_active() is True

    first_worker.clear('restart persistence test complete', confirm=True)

    restarted_after_clear = EmergencyHaltState(flag_path=flag_path, default_active=True)
    assert restarted_after_clear.is_active() is False
    assert second_worker.is_active() is False
