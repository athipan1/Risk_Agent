from __future__ import annotations

import re
from typing import Tuple

from app.models import RiskCheckRequest
from app.policy import (
    ALLOW_FRACTIONAL_SHARES,
    ALLOW_SHORT_SELLING,
    ASSET_CLASS,
    MAX_SECTOR_EXPOSURE_PCT,
    MAX_SINGLE_STOCK_PCT,
    MIN_EQUITY_FOR_LIVE_STOCK,
    STOCK_ONLY_MODE,
)

_STOCK_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(?:[.-][A-Z])?$")
_CRYPTO_HINTS = {"BTC", "ETH", "SOL", "DOGE", "USDT", "USDC", "BNB", "XRP", "ADA"}


def _is_stock_symbol(symbol: str) -> bool:
    symbol = str(symbol or "").strip().upper()
    if not symbol or "/" in symbol or ":" in symbol:
        return False
    if symbol in _CRYPTO_HINTS or symbol.startswith(tuple(_CRYPTO_HINTS)):
        return False
    if symbol in {"XAU", "XAUUSD", "GOLD", "GC"}:
        return False
    return bool(_STOCK_SYMBOL_RE.match(symbol))


def check_stock_limits(payload: RiskCheckRequest) -> Tuple[list[str], list[str], dict]:
    violations: list[str] = []
    warnings: list[str] = []
    position_value = payload.entry_price * payload.requested_quantity
    projected_symbol_exposure = payload.current_symbol_exposure + position_value
    projected_sector_exposure = payload.current_sector_exposure + position_value
    max_single_stock_value = payload.equity * MAX_SINGLE_STOCK_PCT
    max_sector_value = payload.equity * MAX_SECTOR_EXPOSURE_PCT

    if STOCK_ONLY_MODE:
        if payload.asset_class != 'stock' or ASSET_CLASS != 'stock':
            violations.append('stock_only_asset_class_required')
        if not _is_stock_symbol(payload.symbol):
            violations.append('stock_symbol_required')

    if payload.trading_mode == 'LIVE' and payload.equity < MIN_EQUITY_FOR_LIVE_STOCK:
        violations.append('minimum_live_stock_equity_required')

    if payload.side == 'sell' and not ALLOW_SHORT_SELLING and payload.requested_quantity > payload.owned_quantity:
        violations.append('short_selling_disabled')

    if not ALLOW_FRACTIONAL_SHARES and payload.requested_quantity != int(payload.requested_quantity):
        violations.append('fractional_shares_disabled')

    if projected_symbol_exposure > max_single_stock_value:
        violations.append('single_stock_exposure_limit_exceeded')

    if payload.sector and projected_sector_exposure > max_sector_value:
        violations.append('sector_exposure_limit_exceeded')

    if projected_symbol_exposure > max_single_stock_value * 0.80:
        warnings.append('near_single_stock_exposure_limit')

    if payload.sector and projected_sector_exposure > max_sector_value * 0.80:
        warnings.append('near_sector_exposure_limit')

    metrics = {
        'asset_class': payload.asset_class,
        'stock_only_mode': STOCK_ONLY_MODE,
        'symbol_is_stock_like': _is_stock_symbol(payload.symbol),
        'allow_short_selling': ALLOW_SHORT_SELLING,
        'allow_fractional_shares': ALLOW_FRACTIONAL_SHARES,
        'owned_quantity': payload.owned_quantity,
        'sector': payload.sector,
        'current_sector_exposure': round(payload.current_sector_exposure, 2),
        'projected_sector_exposure': round(projected_sector_exposure, 2),
        'max_sector_exposure': round(max_sector_value, 2),
        'projected_symbol_exposure': round(projected_symbol_exposure, 2),
        'max_single_stock_exposure': round(max_single_stock_value, 2),
        'min_equity_for_live_stock': MIN_EQUITY_FOR_LIVE_STOCK,
    }
    return violations, warnings, metrics
