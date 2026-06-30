from app.models import ProfitPlanGateRequest
from app.profit_plan_gate import check_profit_plan_gate


def make_payload(action: str = 'hold', quantity: float = 0.0, recommended_stop=None, current_r=0.4):
    return ProfitPlanGateRequest(
        position={
            'symbol': 'ACGL',
            'side': 'long',
            'quantity': 82,
            'entry_price': 96.79,
            'current_price': 98.39,
            'stop_loss': 92.94,
            'strategy_bucket': 'value_rebound',
        },
        profit_plan={
            'symbol': 'ACGL',
            'current_r_multiple': current_r,
            'unrealized_pl_pct': 0.0165,
            'primary_action': action,
            'actions': [
                {
                    'action': action,
                    'symbol': 'ACGL',
                    'quantity': quantity,
                    'recommended_stop': recommended_stop,
                    'reason': 'test action',
                    'confidence_score': 0.70,
                }
            ],
            'warnings': [],
            'metadata': {'advisory_only': True},
        },
        trading_mode='PAPER',
    )


def test_profit_plan_gate_approves_hold():
    response = check_profit_plan_gate(make_payload())
    assert response.status == 'approved'
    assert response.data['approved'] is True
    assert response.data['approved_actions'][0]['action'] == 'hold'
    assert response.data['orders_submitted'] is False


def test_profit_plan_gate_rejects_partial_exit_before_min_r():
    response = check_profit_plan_gate(make_payload(action='partial_exit', quantity=20, current_r=0.4))
    assert response.status == 'rejected'
    assert 'one_or_more_profit_actions_rejected' in response.data['violations']
    assert 'partial_exit_before_min_r' in response.data['rejected_actions'][0]['violations']


def test_profit_plan_gate_rejects_partial_exit_too_large():
    response = check_profit_plan_gate(make_payload(action='partial_exit', quantity=60, current_r=1.8))
    assert response.status == 'rejected'
    assert 'partial_exit_pct_exceeds_limit' in response.data['rejected_actions'][0]['violations']


def test_profit_plan_gate_approves_stop_tightening():
    response = check_profit_plan_gate(make_payload(action='move_stop', quantity=0, recommended_stop=96.79, current_r=1.2))
    assert response.status == 'approved'
    assert response.data['approved_actions'][0]['recommended_stop'] == 96.79


def test_profit_plan_gate_rejects_stop_loosening():
    response = check_profit_plan_gate(make_payload(action='move_stop', quantity=0, recommended_stop=91.0, current_r=1.2))
    assert response.status == 'rejected'
    assert 'move_stop_must_not_loosen_stop' in response.data['rejected_actions'][0]['violations']


def test_profit_plan_gate_rejects_exit_all_by_default():
    response = check_profit_plan_gate(make_payload(action='exit_all', quantity=82, current_r=2.0))
    assert response.status == 'rejected'
    assert 'exit_all_requires_manual_approval' in response.data['rejected_actions'][0]['violations']
