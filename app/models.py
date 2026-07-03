from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


TradeSide = Literal['buy', 'sell', 'hold']
TradingMode = Literal['PAPER', 'LIVE']
AssetClass = Literal['stock', 'xauusd', 'crypto', 'multi']
StrategyBucket = Literal['core_dividend', 'quality_growth', 'value_rebound', 'news_momentum', 'unassigned']
TradePlanStatus = Literal['draft', 'risk_pending', 'risk_approved', 'manual_approval_required', 'execution_ready', 'rejected']
TradePlanSource = Literal['single_analysis', 'multi_analysis', 'scanner', 'manual', 'replay']
OrderType = Literal['market', 'limit']
TimeInForce = Literal['GTC', 'IOC', 'FOK']
PositionSide = Literal['long', 'short']
ProfitActionName = Literal['hold', 'move_stop', 'partial_exit', 'exit_all']


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
    asset_class: AssetClass = 'stock'
    sector: str | None = None
    owned_quantity: float = Field(ge=0, default=0)
    current_sector_exposure: float = Field(ge=0, default=0)
    strategy_bucket: StrategyBucket = 'unassigned'
    current_bucket_exposure: float = Field(ge=0, default=0)
    target_weight: float | None = Field(default=None, ge=0)
    allocation_pct: float | None = Field(default=None, ge=0)
    target_value: float | None = Field(default=None, ge=0)
    take_profit_price: float | None = Field(default=None, gt=0)
    reward_risk_ratio: float | None = Field(default=None, gt=0)
    daily_realized_pnl: float = 0.0
    weekly_realized_pnl: float = 0.0
    consecutive_losses: int = Field(ge=0, default=0)
    trades_today: int = Field(ge=0, default=0)
    symbol_trades_today: int = Field(ge=0, default=0)
    minutes_since_last_loss: float | None = Field(default=None, ge=0)
    minutes_since_last_symbol_trade: float | None = Field(default=None, ge=0)
    emergency_halt: bool = False


class ManagerDecisionPayload(BaseModel):
    decision: str
    confidence: str | None = None
    recommended_strategy: str | None = None
    backtest_best_strategy: str | None = None
    reason: str | None = None


class ManagerMarketContext(BaseModel):
    position_size_multiplier: float = Field(default=1.0, ge=0, le=1)
    risk_budget_multiplier: float = Field(default=1.0, ge=0, le=1)
    exposure_cap: float = Field(default=1.0, ge=0, le=1)
    effective_size_multiplier: float | None = Field(default=None, ge=0, le=1)
    allowed_strategies: list[str] = Field(default_factory=list)
    blocked_strategies: list[str] = Field(default_factory=list)
    decision_notes: list[str] = Field(default_factory=list)


class ManagerAccountContext(BaseModel):
    equity: float = Field(gt=0)
    current_exposure_pct: float = Field(default=0, ge=0, le=1)
    current_symbol_exposure_pct: float = Field(default=0, ge=0, le=1)
    open_orders_exposure_pct: float = Field(default=0, ge=0, le=1)


class ManagerGateRequest(BaseModel):
    symbol: str = 'UNKNOWN'
    decision: ManagerDecisionPayload
    market_context: ManagerMarketContext = Field(default_factory=ManagerMarketContext)
    account: ManagerAccountContext
    requested_position_pct: float = Field(default=0.10, ge=0, le=1)
    trading_mode: TradingMode = 'PAPER'


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
        if reference_price is not None and self.exit.take_profit is not None:
            if self.side == 'buy' and self.exit.take_profit <= reference_price:
                raise ValueError('buy trade take_profit must be above entry/limit price')
            if self.side == 'sell' and self.exit.take_profit >= reference_price:
                raise ValueError('sell trade take_profit must be below entry/limit price')
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


class ProfitPositionPayload(BaseModel):
    symbol: str
    side: PositionSide = 'long'
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    current_price: float = Field(gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    strategy_bucket: StrategyBucket = 'unassigned'


class ProfitPlanAction(BaseModel):
    action: ProfitActionName
    symbol: str
    quantity: float = Field(ge=0)
    recommended_stop: float | None = Field(default=None, gt=0)
    reason: str | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfitPlanPayload(BaseModel):
    symbol: str
    current_r_multiple: float | None = None
    unrealized_pl_pct: float | None = None
    primary_action: ProfitActionName
    actions: list[ProfitPlanAction]
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfitPlanGateRequest(BaseModel):
    position: ProfitPositionPayload
    profit_plan: ProfitPlanPayload
    trading_mode: TradingMode = 'PAPER'
    max_partial_exit_pct: float = Field(default=0.50, gt=0, le=1)
    min_partial_exit_r: float = Field(default=1.0, ge=0)
    require_manual_exit_all: bool = True

    @model_validator(mode='after')
    def validate_symbol_consistency(self):
        if self.position.symbol.upper() != self.profit_plan.symbol.upper():
            raise ValueError('position symbol and profit plan symbol must match')
        return self


class StandardResponse(BaseModel):
    status: str
    agent_type: str = 'risk'
    version: str = '1.0.0'
    data: dict | None = None
    error: str | None = None
    confidence_score: float | None = None
