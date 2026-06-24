from app.models import PortfolioRiskCheckRequest, PortfolioRiskPosition
from app.portfolio_checks import check_portfolio


def _position(symbol, bucket, price=100, qty=10, allocation_pct=50.0):
    return PortfolioRiskPosition(
        symbol=symbol,
        side='buy',
        entry_price=price,
        protection_price=95,
        requested_quantity=qty,
        strategy_bucket=bucket,
        portfolio_context={
            'bucket': bucket,
            'strategy_bucket': bucket,
            'target_weight': allocation_pct / 100,
            'allocation_pct': allocation_pct,
            'target_value': 100000 * allocation_pct / 100,
        },
        scanner_candidate={'metadata': {'sector': 'Consumer Defensive'}},
        score_breakdown={'final_opportunity_score': 0.8},
        final_verdict='buy',
    )


def test_portfolio_check_approves_selected_positions_with_allocation_context():
    payload = PortfolioRiskCheckRequest(
        account_id=1,
        equity=100000,
        positions=[
            _position('KO', 'core_dividend', qty=10, allocation_pct=50.0),
            _position('ACGL', 'value_rebound', qty=5, allocation_pct=30.0),
            _position('NEWS', 'news_momentum', price=50, qty=10, allocation_pct=20.0),
        ],
        trading_mode='PAPER',
        asset_class='stock',
        current_total_exposure=0,
        open_orders_exposure=0,
        margin_multiplier=1,
        allocation_plan={'policy_name': 'core_satellite_50_30_20'},
    )

    response = check_portfolio(payload)

    assert response.status == 'approved'
    assert response.data['mode'] == 'portfolio_allocation'
    assert response.data['approved_positions'] == 3
    assert [row['symbol'] for row in response.data['risk_approvals']] == ['KO', 'ACGL', 'NEWS']
    assert response.data['risk_approvals'][0]['strategy_bucket'] == 'core_dividend'
    assert response.data['risk_approvals'][0]['allocation_pct'] == 50.0


def test_portfolio_check_rejects_when_later_position_exceeds_bucket_exposure():
    payload = PortfolioRiskCheckRequest(
        account_id=1,
        equity=100000,
        positions=[
            _position('COREA', 'core_dividend', price=100, qty=400, allocation_pct=50.0),
            _position('COREB', 'core_dividend', price=100, qty=200, allocation_pct=50.0),
        ],
        trading_mode='PAPER',
        asset_class='stock',
        current_total_exposure=0,
        open_orders_exposure=0,
        margin_multiplier=1,
        allocation_plan={'policy_name': 'core_satellite_50_30_20'},
    )

    response = check_portfolio(payload)

    assert response.status == 'partial'
    assert response.data['approved_positions'] == 1
    assert response.data['rejected_positions'] == 1
    rejected = response.data['risk_approvals'][1]
    assert rejected['approved'] is False
    assert 'bucket_exposure_limit_exceeded' in rejected['violations']
