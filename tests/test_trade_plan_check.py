from fastapi.testclient import TestClient

from app.main import app
from app.models import TradePlanRiskCheckRequest
from app.trade_plan_adapter import trade_plan_to_risk_check

client = TestClient(app)


def trade_plan_payload(**overrides):
    payload = {
        'trade_plan': {
            'plan_id': 'plan-1',
            'correlation_id': 'corr-1',
            'source': 'single_analysis',
            'status': 'risk_pending',
            'account_id': '1',
            'symbol': 'aapl',
            'side': 'buy',
            'order_type': 'market',
            'entry_price': 100,
            'quantity': 5,
            'final_quantity': 5,
            'time_in_force': 'GTC',
            'strategy': 'trend_pullback',
            'strategy_bucket': 'value_rebound',
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
            'exit': {
                'stop_loss': 95,
                'take_profit': 110,
            },
            'risk_approval_id': None,
            'manual_approval_required': True,
            'dry_run': False,
            'reasons': [],
            'guard_plan': {},
            'metadata': {},
        },
        'trading_mode': 'PAPER',
        'current_symbol_exposure': 0,
        'current_total_exposure': 0,
        'open_orders_exposure': 0,
        'margin_multiplier': 1,
        'session_risk_context': {
            'daily_realized_pnl': 0,
            'weekly_realized_pnl': 0,
            'consecutive_losses': 0,
            'trades_today': 0,
            'symbol_trades_today': 0,
            'minutes_since_last_loss': 120,
            'minutes_since_last_symbol_trade': 120,
            'emergency_halt': False,
        },
    }
    payload.update(overrides)
    return payload


def test_trade_plan_adapter_maps_to_existing_risk_check():
    request = TradePlanRiskCheckRequest.model_validate(trade_plan_payload())

    risk_payload = trade_plan_to_risk_check(request)

    assert risk_payload.account_id == 1
    assert risk_payload.symbol == 'AAPL'
    assert risk_payload.side == 'buy'
    assert risk_payload.entry_price == 100
    assert risk_payload.protection_price == 95
    assert risk_payload.requested_quantity == 5
    assert risk_payload.equity == 10000
    assert risk_payload.strategy_bucket == 'value_rebound'
    assert risk_payload.trades_today == 0


def test_trade_plan_check_approves_valid_plan():
    response = client.post('/risk/trade-plan-check', json=trade_plan_payload())
    body = response.json()

    assert response.status_code == 200
    assert body['status'] == 'approved'
    assert body['data']['approved'] is True
    assert body['data']['trade_plan_id'] == 'plan-1'
    assert body['data']['correlation_id'] == 'corr-1'
    assert body['data']['strategy_bucket'] == 'value_rebound'
    assert body['data']['trade_plan_validation'] == 'checked'
    assert body['data']['guard_plan']['trigger_price'] == 95


def test_trade_plan_check_rejects_missing_stop_loss():
    payload = trade_plan_payload()
    payload['trade_plan']['exit']['stop_loss'] = None

    response = client.post('/risk/trade-plan-check', json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert body['data']['approved'] is False
    assert 'invalid_trade_plan' in body['data']['violations']
    assert 'exit.stop_loss is required' in body['data']['reason']


def test_trade_plan_check_rejects_live_plan_without_context():
    payload = trade_plan_payload(trading_mode='LIVE', session_risk_context={})

    response = client.post('/risk/trade-plan-check', json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body['status'] == 'rejected'
    assert 'live_context_required' in body['data']['violations']
    assert body['data']['trade_plan_id'] == 'plan-1'
