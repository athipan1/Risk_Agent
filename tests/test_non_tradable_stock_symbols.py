import pytest

from app.models import RiskCheckRequest
from app.stock_limits import check_stock_limits


@pytest.mark.parametrize("symbol", ["CASH", "USD", "USDT", "USDC"])
def test_non_tradable_cash_symbols_are_rejected(symbol):
    payload = RiskCheckRequest(
        account_id=1,
        symbol=symbol,
        side="buy",
        entry_price=100,
        protection_price=95,
        equity=100000,
        requested_quantity=1,
        asset_class="stock",
        trading_mode="PAPER",
    )

    violations, warnings, metrics = check_stock_limits(payload)

    assert "stock_symbol_required" in violations
    assert metrics["symbol_is_stock_like"] is False


def test_normal_stock_symbol_is_still_allowed_by_symbol_guard():
    payload = RiskCheckRequest(
        account_id=1,
        symbol="ACGL",
        side="buy",
        entry_price=100,
        protection_price=95,
        equity=100000,
        requested_quantity=1,
        asset_class="stock",
        trading_mode="PAPER",
    )

    violations, warnings, metrics = check_stock_limits(payload)

    assert "stock_symbol_required" not in violations
    assert metrics["symbol_is_stock_like"] is True
