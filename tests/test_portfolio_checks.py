from app.models import PortfolioRiskCheckRequest, PortfolioRiskPosition
from app.portfolio_checks import check_portfolio


def _position(
    symbol,
    bucket,
    price=100,
    qty=10,
    allocation_pct=50.0,
    score=0.8,
    sector='Consumer Defensive',
    side='buy',
    confidence=0.86,
    status='classified',
):
    return PortfolioRiskPosition(
        symbol=symbol,
        side=side,
        entry_price=price,
        protection_price=round(price * (0.95 if side == 'buy' else 1.05), 2),
        requested_quantity=qty,
        strategy_bucket=bucket,
        bucket_confidence=confidence,
        bucket_classification_status=status,
        bucket_classification_reasons=['test_evidence'],
        bucket_classifier_version='manager-strategy-bucket-v2',
        portfolio_context={
            'bucket': bucket,
            'strategy_bucket': bucket,
            'bucket_confidence': confidence,
            'bucket_classification_status': status,
            'bucket_classification_reasons': ['test_evidence'],
            'bucket_classifier_version': 'manager-strategy-bucket-v2',
            'target_weight': allocation_pct / 100,
            'allocation_pct': allocation_pct,
            'target_value': 100000 * allocation_pct / 100,
        },
        scanner_candidate={'metadata': {'sector': sector}},
        score_breakdown={'final_opportunity_score': score},
        final_verdict='buy' if side == 'buy' else 'sell',
    )


def _payload(positions, **overrides):
    base = dict(
        account_id=1,
        equity=100000,
        positions=positions,
        trading_mode='PAPER',
        asset_class='stock',
        current_total_exposure=0,
        open_orders_exposure=0,
        margin_multiplier=1,
        allocation_plan={'policy_name': 'core_satellite_50_30_20'},
    )
    base.update(overrides)
    return PortfolioRiskCheckRequest(**base)


def test_portfolio_check_approves_selected_positions_with_allocation_context():
    payload = _payload([
        _position('KO', 'core_dividend', qty=10, allocation_pct=50.0),
        _position('ACGL', 'value_rebound', qty=5, allocation_pct=30.0),
        _position('NEWS', 'news_momentum', price=50, qty=10, allocation_pct=20.0, sector='Technology'),
    ])

    response = check_portfolio(payload)

    assert response.status == 'approved'
    assert response.data['mode'] == 'portfolio_allocation'
    assert response.data['approved_positions'] == 3
    assert [row['symbol'] for row in response.data['risk_approvals']] == ['KO', 'ACGL', 'NEWS']
    assert response.data['risk_approvals'][0]['strategy_bucket'] == 'core_dividend'
    assert response.data['risk_approvals'][0]['strategy_bucket_gate']['allowed'] is True
    assert response.data['risk_approvals'][0]['allocation_pct'] == 50.0


def test_portfolio_check_rejects_when_later_position_exceeds_bucket_exposure():
    payload = _payload([
        _position('KO', 'core_dividend', price=100, qty=100, allocation_pct=50.0),
        _position('JNJ', 'core_dividend', price=100, qty=100, allocation_pct=50.0),
        _position('PEP', 'core_dividend', price=100, qty=100, allocation_pct=50.0),
        _position('PG', 'core_dividend', price=100, qty=100, allocation_pct=50.0),
        _position('CL', 'core_dividend', price=100, qty=100, allocation_pct=50.0),
        _position('KMB', 'core_dividend', price=100, qty=100, allocation_pct=50.0),
    ])

    response = check_portfolio(payload)

    assert response.status == 'partial'
    assert response.data['approved_positions'] == 5
    assert response.data['rejected_positions'] == 1
    rejected = response.data['risk_approvals'][-1]
    assert rejected['symbol'] == 'KMB'
    assert rejected['approved'] is False
    assert 'bucket_exposure_limit_exceeded' in rejected['violations']


def test_portfolio_check_scales_quantity_to_news_bucket_limit():
    payload = _payload([
        _position('MSFT', 'news_momentum', price=100, qty=500, allocation_pct=20.0, sector='Technology'),
    ])

    response = check_portfolio(payload)

    approval = response.data['risk_approvals'][0]
    assert response.status == 'approved'
    assert approval['requested_quantity'] == 500
    assert approval['final_quantity'] == 30.0
    assert approval['approved_value'] == 3000.0
    assert 'portfolio_quantity_scaled_to_available_risk_budget' in approval['warnings']
    assert 'scaled_by_single_stock_exposure_limit' in approval['warnings']


def test_portfolio_check_rejects_unassigned_bucket():
    payload = _payload([
        _position(
            'AAPL',
            'unassigned',
            price=100,
            qty=1,
            allocation_pct=0.0,
            sector='Technology',
            confidence=None,
            status='unassigned',
        ),
    ])

    response = check_portfolio(payload)

    approval = response.data['risk_approvals'][0]
    assert response.status == 'rejected'
    assert approval['approved'] is False
    assert 'strategy_bucket_unassigned' in approval['violations']
    assert approval['strategy_bucket_gate']['allowed'] is False


def test_portfolio_check_rejects_low_confidence_bucket():
    payload = _payload([
        _position('AAPL', 'core_dividend', confidence=0.61),
    ])

    response = check_portfolio(payload)

    approval = response.data['risk_approvals'][0]
    assert response.status == 'rejected'
    assert 'strategy_bucket_confidence_below_minimum' in approval['violations']


def test_portfolio_check_rejects_conflicting_classification():
    payload = _payload([
        _position('AAPL', 'core_dividend', status='conflict'),
    ])

    response = check_portfolio(payload)

    approval = response.data['risk_approvals'][0]
    assert response.status == 'rejected'
    assert 'strategy_bucket_classification_conflict' in approval['violations']


def test_portfolio_check_prioritizes_core_before_news_when_total_exposure_is_tight():
    payload = _payload(
        [
            _position('MSFT', 'news_momentum', price=100, qty=100, allocation_pct=20.0, score=0.99, sector='Technology'),
            _position('KO', 'core_dividend', price=100, qty=100, allocation_pct=50.0, score=0.60),
        ],
        current_total_exposure=90000,
    )

    response = check_portfolio(payload)

    approvals = response.data['risk_approvals']
    assert [row['symbol'] for row in approvals] == ['KO', 'MSFT']
    assert approvals[0]['approved'] is True
    assert approvals[1]['approved'] is False
    assert 'portfolio_exposure_limit_exceeded' in approvals[1]['violations']


def test_portfolio_check_emergency_halt_rejects_all_positions():
    payload = _payload(
        [
            _position('KO', 'core_dividend', price=100, qty=10, allocation_pct=50.0),
            _position('ACGL', 'value_rebound', price=100, qty=10, allocation_pct=30.0),
        ],
        session_risk_context={'emergency_halt': True},
    )

    response = check_portfolio(payload)

    assert response.status == 'rejected'
    assert response.data['approved_positions'] == 0
    assert all('emergency_halt_active' in row['violations'] for row in response.data['risk_approvals'])


def test_portfolio_sell_with_unassigned_bucket_is_not_blocked_and_reduces_exposure():
    payload = _payload(
        [
            _position(
                'LEGACY',
                'unassigned',
                price=100,
                qty=10,
                allocation_pct=0,
                side='sell',
                confidence=None,
                status=None,
            ),
        ],
        current_total_exposure=5000,
    )

    response = check_portfolio(payload)

    approval = response.data['risk_approvals'][0]
    assert approval['strategy_bucket_gate']['allowed'] is True
    assert 'strategy_bucket_unassigned_exit_allowed' in approval['strategy_bucket_gate']['warnings']
    assert response.data['projected_total_exposure'] <= 5000
