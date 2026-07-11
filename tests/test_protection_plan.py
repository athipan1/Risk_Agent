import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.protection_plan import ProtectionPlanRequest, build_protection_plan


def test_value_position_gets_full_sl_tp_proposal():
    result = build_protection_plan(
        ProtectionPlanRequest(
            symbol='BKNG',
            side='long',
            quantity=51,
            entry_price=182.09,
            current_price=178.39,
            strategy_bucket='value_rebound',
            reward_risk_ratio=2.0,
        )
    )

    assert result['status'] == 'approved'
    assert result['symbol'] == 'BKNG'
    assert result['qty'] == 51
    assert result['stop_price'] == pytest.approx(169.47)
    assert result['take_profit_price'] == pytest.approx(196.23)
    assert result['calculation_method'] == 'bucket_fallback_distance'
    assert result['orders_submitted'] is False
    assert result['stop_price'] < result['reference_price'] < result['take_profit_price']


def test_valid_existing_stop_is_preserved():
    result = build_protection_plan(
        ProtectionPlanRequest(
            symbol='ACGL',
            quantity=151,
            entry_price=99.96,
            current_price=101.06,
            existing_stop_price=96.90,
            strategy_bucket='value_rebound',
        )
    )

    assert result['stop_price'] == 96.90
    assert result['take_profit_price'] == pytest.approx(109.38)
    assert result['calculation_method'] == 'preserve_valid_existing_stop'


def test_atr_plan_is_capped_by_max_distance():
    result = build_protection_plan(
        ProtectionPlanRequest(
            symbol='TEST',
            quantity=10,
            entry_price=100,
            current_price=100,
            atr=20,
            atr_multiplier=2,
            strategy_bucket='news_momentum',
        )
    )

    assert result['stop_price'] == 88.0
    assert result['risk_pct_of_reference'] == 0.12


def test_api_returns_standard_read_only_protection_contract():
    client = TestClient(app)
    response = client.post(
        '/risk/protection-plan',
        json={
            'symbol': 'CINF',
            'quantity': 86,
            'entry_price': 177.02,
            'current_price': 179.28,
            'strategy_bucket': 'value_rebound',
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'success'
    assert body['data']['purpose'] == 'protect_existing_position'
    assert body['data']['safety'] == 'read_only_risk_proposal_no_broker_mutation'
    assert body['metadata']['broker_mutation'] is False
