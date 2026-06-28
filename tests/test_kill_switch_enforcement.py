import pytest

from app.checks import check_order
from app.models import PortfolioRiskCheckRequest, PortfolioRiskPosition, RiskCheckRequest, TradePlanRiskCheckRequest
from app.portfolio_checks import check_portfolio
from app.trade_plan_adapter import check_trade_plan


def base_risk_payload(**overrides):
    payload = {
        'account_id': 1,
        'symbol': 'AAPL',
        'side': 'buy',
        'entry_price': 100.0,
        'protection_price': 95.0,
        'equity': 100000.0,
        'requested_quantity': 10.0,
        'current_symbol_exposure': 0.0,
        'current_total_exposure': 0.0,
        'open_orders_exposure': 0.0,
        'margin_multiplier': 1.0,
        'trading_mode': 'PAPER',
        'asset_class': 'stock',
    }
    payload.update(overrides)
    return RiskCheckRequest(**payload)


def portfolio_position(symbol='AAPL'):
    return PortfolioRiskPosition(
        symbol=symbol,
        side='buy',
        entry_price=100.0,
        protection_price=95.0,
        requested_quantity=10.0,
        strategy_bucket='core_dividend',
        portfolio_context={'strategy_bucket': 'core_dividend'},
    )


def trade_plan_payload(session_context):
    return TradePlanRiskCheckRequest(
        trade_plan={
            'plan_id': 'plan-kill-switch',
            'correlation_id': 'corr-kill-switch',
            'account_id': 1,
            'symbol': 'AAPL',
            'side': 'buy',
            'order_type': 'market',
            'entry_price': 100.0,
            'quantity': 10.0,
            'final_quantity': 10.0,
            'strategy': 'test',
            'strategy_bucket': 'core_dividend',
            'final_verdict': 'buy',
            'confidence_score': 0.8,
            'risk': {
                'account_equity': 100000.0,
                'max_loss_amount': 50.0,
                'max_loss_pct': 0.0005,
            },
            'exit': {'stop_loss': 95.0},
        },
        equity=100000.0,
        trading_mode='PAPER',
        session_risk_context=session_context,
    )


@pytest.mark.parametrize(
    'field,value,violation',
    [
        ('emergency_halt', True, 'emergency_halt_active'),
        ('daily_realized_pnl', -500.0, 'daily_loss_limit_exceeded'),
        ('weekly_realized_pnl', -1500.0, 'weekly_loss_limit_exceeded'),
        ('consecutive_losses', 3, 'max_consecutive_losses_exceeded'),
        ('trades_today', 5, 'max_trades_per_day_exceeded'),
        ('symbol_trades_today', 2, 'max_symbol_trades_per_day_exceeded'),
    ],
)
def test_risk_check_kill_switch_rejects_before_approval(field, value, violation):
    payload = base_risk_payload(**{field: value})

    response = check_order(payload)

    assert response.status == 'rejected'
    assert response.error == 'risk_kill_switch_active'
    assert response.data['approved'] is False
    assert response.data['final_quantity'] == 0.0
    assert response.data['kill_switch_active'] is True
    assert violation in response.data['violations']
    assert violation in response.data['session_risk']['kill_switch_violations']
    assert response.data.get('guard_plan') is None


def test_trade_plan_check_propagates_kill_switch_rejection():
    response = check_trade_plan(trade_plan_payload({'emergency_halt': True}))

    assert response.status == 'rejected'
    assert response.error == 'risk_kill_switch_active'
    assert response.data['approved'] is False
    assert response.data['kill_switch_active'] is True
    assert 'emergency_halt_active' in response.data['violations']
    assert response.data['trade_plan_id'] == 'plan-kill-switch'


def test_portfolio_check_rejects_entire_batch_when_kill_switch_active():
    payload = PortfolioRiskCheckRequest(
        account_id=1,
        equity=100000.0,
        positions=[portfolio_position('AAPL'), portfolio_position('MSFT')],
        trading_mode='PAPER',
        asset_class='stock',
        session_risk_context={'emergency_halt': True},
    )

    response = check_portfolio(payload)

    assert response.status == 'rejected'
    assert response.error == 'risk_kill_switch_active'
    assert response.data['approved'] is False
    assert response.data['kill_switch_active'] is True
    assert response.data['approved_positions'] == 0
    assert response.data['rejected_positions'] == 2
    assert 'emergency_halt_active' in response.data['violations']
    assert all(not row['approved'] for row in response.data['risk_approvals'])
    assert all(row['scaling']['reason'] == 'portfolio_kill_switch_active' for row in response.data['risk_approvals'])


def test_near_daily_loss_warns_without_kill_switch():
    payload = base_risk_payload(daily_realized_pnl=-450.0)

    response = check_order(payload)

    assert response.status == 'approved'
    assert response.data['approved'] is True
    assert response.data['kill_switch_active'] is False
    assert 'daily_loss_near_limit' in response.data['warnings']
