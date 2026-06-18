from typing import Literal

from pydantic import BaseModel, Field


TradeSide = Literal['buy', 'sell', 'hold']


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
    margin_multiplier: float = Field(gt=0, default=1)


class StandardResponse(BaseModel):
    status: str
    agent_type: str = 'risk'
    version: str = '1.0.0'
    data: dict | None = None
    error: str | None = None
