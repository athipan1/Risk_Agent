from app.checks import check_order
from app.models import RiskCheckRequest


def _request(**overrides):
    data = {
        'account_id': 1,
        'symbol': 'XYZ',
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
        'strategy_bucket': 'core_dividend',
        'bucket_confidence': 0.88,
        'bucket_classification_status': 'classified',
        'bucket_classification_reasons': ['quality_score:80'],
        'bucket_classifier_version': 'manager-strategy-bucket-v2',
    }
    data.update(overrides)
    return RiskCheckRequest(**data)


def test_valid_classified_buy_passes_bucket_gate():
    response = check_order(_request())

    assert response.data['strategy_bucket_gate']['allowed'] is True
    assert response.data['strategy_bucket_gate']['strategy_bucket'] == 'core_dividend'
    assert response.data['strategy_bucket_gate']['bucket_confidence'] == 0.88
    assert 'strategy_bucket_unassigned' not in response.data['violations']


def test_explicit_unassigned_buy_is_rejected():
    response = check_order(
        _request(
            strategy_bucket='unassigned',
            bucket_confidence=None,
            bucket_classification_status='unassigned',
            bucket_classifier_version=None,
        )
    )

    assert response.status == 'rejected'
    assert response.data['approved'] is False
    assert 'strategy_bucket_unassigned' in response.data['violations']
    assert response.data['strategy_bucket_gate']['allowed'] is False


def test_low_confidence_buy_is_rejected():
    response = check_order(_request(bucket_confidence=0.69))

    assert response.status == 'rejected'
    assert 'strategy_bucket_confidence_below_minimum' in response.data['violations']


def test_conflicting_classification_is_rejected():
    response = check_order(_request(bucket_classification_status='conflict'))

    assert response.status == 'rejected'
    assert 'strategy_bucket_classification_conflict' in response.data['violations']


def test_live_buy_requires_classifier_metadata():
    response = check_order(
        _request(
            trading_mode='LIVE',
            bucket_confidence=None,
            bucket_classification_status=None,
            bucket_classifier_version=None,
            daily_realized_pnl=0,
            weekly_realized_pnl=0,
            consecutive_losses=0,
            trades_today=0,
            symbol_trades_today=0,
            emergency_halt=False,
        )
    )

    assert response.status == 'rejected'
    assert 'strategy_bucket_classification_metadata_required' in response.data['violations']


def test_sell_with_unassigned_bucket_is_allowed_by_bucket_gate():
    response = check_order(
        _request(
            side='sell',
            protection_price=105.0,
            strategy_bucket='unassigned',
            bucket_confidence=None,
            bucket_classification_status=None,
            bucket_classifier_version=None,
        )
    )

    assert response.data['strategy_bucket_gate']['allowed'] is True
    assert 'strategy_bucket_unassigned_exit_allowed' in response.data['strategy_bucket_gate']['warnings']


def test_legacy_paper_request_that_omits_bucket_is_warned_not_silently_classified():
    payload = {
        'account_id': 1,
        'symbol': 'LEGACY',
        'side': 'buy',
        'entry_price': 100.0,
        'protection_price': 95.0,
        'equity': 100000.0,
        'requested_quantity': 10.0,
        'trading_mode': 'PAPER',
        'asset_class': 'stock',
    }

    response = check_order(RiskCheckRequest(**payload))

    assert response.data['strategy_bucket_gate']['allowed'] is True
    assert response.data['strategy_bucket'] == 'unassigned'
    assert 'legacy_strategy_bucket_missing' in response.data['warnings']
    assert 'strategy_bucket_classification_metadata_missing' in response.data['warnings']
