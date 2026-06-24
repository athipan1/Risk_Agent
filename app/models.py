from typing import Any, Literal

from pydantic import BaseModel, Field


TradeSide = Literal['buy', 'sell', 'hold']
TradingMode = Literal['PAPER', 'LIVE']
AssetClass = Literal['stock', 'xauusd', 'crypto', 'multi']
StrategyBucket = Literal['core_dividend', 'value_rebound', 'news_momentum', 'unassigned']


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

    # Stock-first context supplied by Manager/Database.
    asset_class: AssetClass = 'stock'
    sector: str | None = None
    owned_quantity: float = Field(ge=0, default=0)
    current_sector_exposure: float = Field(ge=0, default=0)

    # Core-satellite strategy bucket context supplied by Manager/Database.
    strategy_bucket: StrategyBucket = 'unassigned'
    current_bucket_exposure: float = Field(ge=0, default=0)

    # Manager portfolio-allocation context.
    target_weight: float | None = Field(default=None, ge=0)
    allocation_pct: float | None = Field(default=None, ge=0)
    target_value: float | None = Field(default=None, ge=0)

    # Session/circuit-breaker context supplied by Manager/Database.
    daily_realized_pnl: float = 0.0
    weekly_realized_pnl: float = 0.0
    consecutive_losses: int = Field(ge=0, default=0)
    trades_today: int = Field(ge=0, default=0)
    symbol_trades_today: int = Field(ge=0, default=0)
    minutes_since_last_loss: float | None = Field(default=None, ge=0)
    minutes_since_last_symbol_trade: float | None = Field(default=None, ge=0)
    emergency_halt: bool = False


class PortfolioRiskPosition(BaseModel):
    symbol: str
    side: TradeSide = 'buy'
    entry_price: float = Field(gt=0)
    protection_price: float = Field(gt=0)
    requested_quantity: float = Field(ge=0)
    strategy_bucket: StrategyBucket = 'unassigned'
    portfolio_context: dict[str, Any] = Field(default_factory=dict)
    scanner_candidate: dict[str, Any] | None = None
    score_breakdown: dict[str, Any] | None = None
    final_verdict: str | None = None


class PortfolioRiskCheckRequest(BaseModel):
    account_id: int
    equity: float = Field(gt=0)
    positions: list[PortfolioRiskPosition]
    allocation_plan: dict[str, Any] = Field(default_factory=dict)
    trading_mode: TradingMode = 'PAPER'
    asset_class: AssetClass = 'stock'
    current_total_exposure: float = Field(ge=0, default=0)
    open_orders_exposure: float = Field(ge=0, default=0)
    margin_multiplier: float = Field(gt=0, default=1)
    session_risk_context: dict[str, Any] = Field(default_factory=dict)
    current_symbol_exposures: dict[str, float] = Field(default_factory=dict)
    current_bucket_exposures: dict[str, float] = Field(default_factory=dict)
    current_sector_exposures: dict[str, float] = Field(default_factory=dict)


class StandardResponse(BaseModel):
    status: str
    agent_type: str = 'risk'
    version: str = '1.0.0'
    data: dict | None = None
    error: str | None = None
