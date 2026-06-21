from typing import Literal

from pydantic import BaseModel, Field


TradeSide = Literal['buy', 'sell', 'hold']
TradingMode = Literal['PAPER', 'LIVE']


class PositionSizeRequest(BaseModel):
    symbol: str
    side: TradeSide
    entry_price: float = Field(gt=0)
    protection_price: float = Field(gt=0)
    equity: float = Field(gt=0)


class RiskCheckRequest(PositionSizeRequest):
    account_id: int
    requested_quantity: float = Field(ge=0)
    current_symbol_exposure: float = Field(ge=0, default=0)
    current_total_exposure: float = Field(ge=0, default=0)
    open_orders_exposure: float = Field(ge=0, default=0)
    margin_multiplier: float = Field(gt=0, default=1)
    trading_mode: TradingMode = 'PAPER'

    # Session/circuit-breaker context supplied by Manager/Database.
    daily_realized_pnl: float = 0.0
    weekly_realized_pnl: float = 0.0
    consecutive_losses: int = Field(ge=0, default=0)
    trades_today: int = Field(ge=0, default=0)
    symbol_trades_today: int = Field(ge=0, default=0)
    minutes_since_last_loss: float | None = Field(default=None, ge=0)
    minutes_since_last_symbol_trade: float | None = Field(default=None, ge=0)
    emergency_halt: bool = False


class StandardResponse(BaseModel):
    status: str
    agent_type: str = 'risk'
    version: str = '1.0.0'
    data: dict | None = None
    error: str | None = None
