from app.models import RiskCheckRequest
from app.stock_limits import check_stock_limits


def _payload(**overrides):
    data = {
        'account_id': 1,
        'symbol': 'ACGL',
        'side': 'buy',
        'entry_price': 100.0,
        'protection_price': 95.0,
        'equity': 100000.0,
        'requested_quantity': 10.0,
        'asset_class': 'stock',
        'trading_mode': 'PAPER',
    }
    data.update(overrides)
    return RiskCheckRequest(**data)


def test_core_dividend_allows_up_to_ten_percent_per_symbol():
    payload = _payload(strategy_bucket='core_dividend', requested_quantity=100.0)

    violations, warnings, metrics = check_stock_limits(payload)

    assert 'bucket_symbol_exposure_limit_exceeded' not in violations
    assert metrics['strategy_bucket'] == 'core_dividend'
    assert metrics['bucket_max_symbol_exposure'] == 10000.0
    assert metrics['max_bucket_exposure'] == 50000.0


def test_value_rebound_rejects_above_seven_percent_symbol_weight():
    payload = _payload(strategy_bucket='value_rebound', requested_quantity=80.0)

    violations, warnings, metrics = check_stock_limits(payload)

    assert 'bucket_symbol_exposure_limit_exceeded' in violations
    assert 'single_stock_exposure_limit_exceeded' in violations
    assert metrics['bucket_max_symbol_exposure'] == 7000.0
    assert metrics['max_single_stock_exposure'] == 7000.0


def test_news_momentum_rejects_above_three_percent_symbol_weight():
    payload = _payload(strategy_bucket='news_momentum', requested_quantity=40.0)

    violations, warnings, metrics = check_stock_limits(payload)

    assert 'bucket_symbol_exposure_limit_exceeded' in violations
    assert 'single_stock_exposure_limit_exceeded' in violations
    assert metrics['bucket_max_symbol_exposure'] == 3000.0
    assert metrics['max_single_stock_exposure'] == 3000.0


def test_bucket_exposure_limit_rejects_projected_bucket_over_target():
    payload = _payload(
        strategy_bucket='news_momentum',
        requested_quantity=10.0,
        current_bucket_exposure=19500.0,
    )

    violations, warnings, metrics = check_stock_limits(payload)

    assert 'bucket_exposure_limit_exceeded' in violations
    assert metrics['projected_bucket_exposure'] == 20500.0
    assert metrics['max_bucket_exposure'] == 20000.0


def test_unassigned_bucket_keeps_global_stock_limit_only():
    payload = _payload(strategy_bucket='unassigned', requested_quantity=100.0)

    violations, warnings, metrics = check_stock_limits(payload)

    assert 'bucket_symbol_exposure_limit_exceeded' not in violations
    assert 'bucket_exposure_limit_exceeded' not in violations
    assert metrics['bucket_max_symbol_exposure'] is None
    assert metrics['max_bucket_exposure'] is None


def test_rebalance_target_does_not_double_count_existing_symbol_exposure():
    payload = _payload(
        symbol='ADBE',
        strategy_bucket='core_dividend',
        requested_quantity=100.0,
        current_symbol_exposure=9500.0,
        current_bucket_exposure=30000.0,
        target_value=10000.0,
    )

    violations, warnings, metrics = check_stock_limits(payload)

    assert 'single_stock_exposure_limit_exceeded' not in violations
    assert 'bucket_symbol_exposure_limit_exceeded' not in violations
    assert metrics['rebalance_aware'] is True
    assert metrics['requested_position_value'] == 10000.0
    assert metrics['effective_position_value'] == 500.0
    assert metrics['projected_symbol_exposure'] == 10000.0
    assert metrics['projected_bucket_exposure'] == 30500.0


def test_rebalance_target_still_rejects_target_above_symbol_limit():
    payload = _payload(
        symbol='ACGL',
        strategy_bucket='value_rebound',
        requested_quantity=340.0,
        current_symbol_exposure=0.0,
        target_value=34000.0,
    )

    violations, warnings, metrics = check_stock_limits(payload)

    assert 'single_stock_exposure_limit_exceeded' in violations
    assert 'bucket_symbol_exposure_limit_exceeded' in violations
    assert metrics['rebalance_aware'] is True
    assert metrics['effective_position_value'] == 34000.0
    assert metrics['projected_symbol_exposure'] == 34000.0
