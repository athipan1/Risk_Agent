from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


TradeSide = Literal['buy', 'sell', 'hold']
TradingMode = Literal['PAPER', 'LIVE']
AssetClass = Literal['stock', 'xauusd', 'crypto', 'multi']
StrategyBucket = Literal['core_dividend', 'value_rebound', 'news_momentum', 'unassigned']
TradePlanStatus = Literal['draft', 'risk_pending', 'risk_approved', 'manual_approval_required', 'execution_ready', 'rejected']
TradePlanSource = Literal['single_analysis', 'multi_analysis', 'scanner', 'manual', 'replay']
OrderType = Literal['market', 'limit']
TimeInForce = Literal['GTC', 'IOC', 'FOK']


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


class TradePlanRiskEnvelope(BaseModel):
    account_equity: float | None = Field(default=None, gt=0)
    cash_available: float | None = Field(default=None, ge=0)
    max_loss_amount: float = Field(gt=0)
    max_loss_pct: float = Field(gt=0, le=1)
    risk_per_share: float | None = Field(default=None, gt=0)
    position_value: float | None = Field(default=None, ge=0)
    position_pct: float | None = Field(default=None, ge=0, le=1)
    reward_risk_ratio: float | None = Field(default=None, gt=0)
    session_risk_loaded: bool = False
    portfolio_context_loaded: bool = False


class TradePlanExitEnvelope(BaseModel):
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    trailing_stop_pct: float | None = Field(default=None, gt=0, lt=1)
    break_even_trigger_r: float | None = Field(default=None, gt=0)
    partial_exit_pct: float | None = Field(default=None, gt=0, lt=1)
    time_stop_minutes: int | None = Field(default=None, gt=0)
    exit_reason: str | None = None


class TradePlanPayload(BaseModel):
    plan_id: str
    correlation_id: str
    source: TradePlanSource = 'single_analysis'
    status: TradePlanStatus = 'draft'
    account_id: int | str
    symbol: str
    side: TradeSide
    order_type: OrderType = 'market'
    entry_price: float | None = Field(default=None, gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    quantity: float = Field(gt=0)
    final_quantity: float | None = Field(default=None, gt=0)
    time_in_force: TimeInForce = 'GTC'
    strategy: str = 'unassigned'
    strategy_bucket: StrategyBucket = 'unassigned'
    final_verdict: str
    confidence_score: float = Field(ge=0, le=1)
    expected_r: float | None = None
    risk: TradePlanRiskEnvelope
    exit: TradePlanExitEnvelope = Field(default_factory=TradePlanExitEnvelope)
    risk_approval_id: str | None = None
    manual_approval_required: bool = True
    dry_run: bool = False
    reasons: list[str] = Field(default_factory=list)
    guard_plan: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_trade_plan_direction(self):
        reference_price = self.entry_price or self.limit_price
        if self.order_type == 'limit' and self.limit_price is None:
            raise ValueError('limit_price is required when order_type is limit')
        if reference_price is not None and self.exit.stop_loss is not None:
            if self.side == 'buy' and self.exit.stop_loss >= reference_price:
                raise ValueError('buy trade stop_loss must be below entry/limit price')
            if self.side == 'sell' and self.exit.stop_loss <= reference_price:
                raise ValueError('sell trade stop_loss must be above entry/limit price')
        return self


class TradePlanRiskCheckRequest(BaseModel):
    trade_plan: TradePlanPayload
    equity: float | None = Field(default=None, gt=0)
    current_symbol_exposure: float = Field(ge=0, default=0)
    current_total_exposure: float = Field(ge=0, default=0)
    open_orders_exposure: float = Field(ge=0, default=0)
    margin_multiplier: float = Field(gt=0, default=1)
    trading_mode: TradingMode = 'PAPER'
    asset_class: AssetClass = 'stock'
    sector: str | None = None
    owned_quantity: float = Field(ge=0, default=0)
    current_sector_exposure: float = Field(ge=0, default=0)
    current_bucket_exposure: float = Field(ge=0, default=0)
    target_weight: float | None = Field(default=None, ge=0)
    allocation_pct: float | None = Field(default=None, ge=0)
    target_value: float | None = Field(default=None, ge=0)
    session_risk_context: dict[str, Any] = Field(default_factory=dict)


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
