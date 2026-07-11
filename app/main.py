from fastapi import FastAPI

from app.checks import check_order
from app.manager_gate import check_manager_gate
from app.models import (
    ManagerGateRequest,
    PortfolioRiskCheckRequest,
    PositionSizeRequest,
    ProfitPlanGateRequest,
    RiskCheckRequest,
    RISK_AGENT_TYPE,
    RISK_AGENT_VERSION,
    SCHEMA_VERSION,
    StandardResponse,
    TradePlanRiskCheckRequest,
)
from app.policy import POLICY
from app.portfolio_checks import check_portfolio
from app.profit_plan_gate import check_profit_plan_gate
from app.protection_plan import ProtectionPlanRequest, build_protection_plan
from app.sizing import calculate_position_size
from app.trade_plan_adapter import check_trade_plan

app = FastAPI(title='Risk Agent', version=RISK_AGENT_VERSION)


def standard_response(*, data: dict, status: str = 'success', error=None, metadata: dict | None = None):
    return StandardResponse(
        status=status,
        data=data,
        metadata=metadata or {},
        error=error,
    )


@app.get('/version', response_model=StandardResponse)
def version():
    return standard_response(
        data={
            'agent_type': RISK_AGENT_TYPE,
            'version': RISK_AGENT_VERSION,
            'schema_version': SCHEMA_VERSION,
            'api_contract': 'multi-agent-trading-api-contract',
        },
        metadata={
            'required_operational_endpoints': ['/health', '/ready', '/version'],
        },
    )


@app.get('/ready', response_model=StandardResponse)
def ready():
    emergency_halt = POLICY.get('emergency_halt', False)
    stock_only_mode = POLICY.get('stock_only_mode', True)
    ready_for_stock_live = not emergency_halt and stock_only_mode
    ready_for_risk_gate = not emergency_halt
    is_ready = ready_for_risk_gate

    return standard_response(
        status='success' if is_ready else 'error',
        data={
            'ready': is_ready,
            'ready_for_stock_paper': True,
            'ready_for_stock_live': ready_for_stock_live,
            'ready_for_risk_gate': ready_for_risk_gate,
            'ready_for_protection_planning': True,
            'stock_only_mode': stock_only_mode,
            'allow_short_selling': POLICY.get('allow_short_selling', False),
            'allow_fractional_shares': POLICY.get('allow_fractional_shares', False),
            'emergency_halt': emergency_halt,
            'max_daily_loss_pct': POLICY.get('max_daily_loss_pct'),
            'max_weekly_loss_pct': POLICY.get('max_weekly_loss_pct'),
            'max_consecutive_losses': POLICY.get('max_consecutive_losses'),
        },
        metadata={
            'contract_source': 'risk-agent-runtime-contract',
        },
        error=None if is_ready else {
            'code': 'RISK_AGENT_NOT_READY',
            'message': 'Risk Agent readiness check failed',
            'retryable': False,
        },
    )


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'agent_type': RISK_AGENT_TYPE,
        'version': RISK_AGENT_VERSION,
        'schema_version': SCHEMA_VERSION,
        'data': {
            'session_risk_controls': True,
            'stock_risk_controls': True,
            'portfolio_allocation_controls': True,
            'trade_plan_controls': True,
            'manager_decision_gate': True,
            'profit_plan_gate': True,
            'existing_position_protection_planning': True,
            'stock_only_mode': POLICY.get('stock_only_mode', True),
            'allow_short_selling': POLICY.get('allow_short_selling', False),
            'emergency_halt': POLICY.get('emergency_halt', False),
            'max_daily_loss_pct': POLICY.get('max_daily_loss_pct'),
            'max_weekly_loss_pct': POLICY.get('max_weekly_loss_pct'),
            'max_single_stock_pct': POLICY.get('max_single_stock_pct'),
            'max_sector_exposure_pct': POLICY.get('max_sector_exposure_pct'),
            'strategy_bucket_limits': POLICY.get('strategy_bucket_limits'),
        },
    }


@app.get('/risk/policy')
def get_policy():
    return StandardResponse(status='success', data=POLICY)


@app.get('/risk/status')
def risk_status():
    return StandardResponse(
        status='success',
        data={
            'ready_for_stock_paper': True,
            'ready_for_stock_live': not POLICY.get('emergency_halt', False) and POLICY.get('stock_only_mode', True),
            'ready_for_portfolio_allocation': True,
            'ready_for_trade_plan_check': True,
            'ready_for_manager_decision_gate': True,
            'ready_for_profit_plan_gate': True,
            'ready_for_protection_planning': True,
            'stock_only_mode': POLICY.get('stock_only_mode', True),
            'allow_short_selling': POLICY.get('allow_short_selling', False),
            'allow_fractional_shares': POLICY.get('allow_fractional_shares', False),
            'max_single_stock_pct': POLICY.get('max_single_stock_pct'),
            'max_sector_exposure_pct': POLICY.get('max_sector_exposure_pct'),
            'strategy_bucket_limits': POLICY.get('strategy_bucket_limits'),
            'session_circuit_breakers': {
                'max_daily_loss_pct': POLICY.get('max_daily_loss_pct'),
                'max_weekly_loss_pct': POLICY.get('max_weekly_loss_pct'),
                'max_consecutive_losses': POLICY.get('max_consecutive_losses'),
                'emergency_halt': POLICY.get('emergency_halt', False),
            },
        },
    )


@app.post('/risk/position-size', response_model=StandardResponse)
def position_size(payload: PositionSizeRequest):
    return calculate_position_size(payload)


@app.post('/risk/check', response_model=StandardResponse)
def risk_check(payload: RiskCheckRequest):
    return check_order(payload)


@app.post('/risk/trade-plan-check', response_model=StandardResponse)
def trade_plan_risk_check(payload: TradePlanRiskCheckRequest):
    return check_trade_plan(payload)


@app.post('/risk/portfolio-check', response_model=StandardResponse)
def portfolio_risk_check(payload: PortfolioRiskCheckRequest):
    return check_portfolio(payload)


@app.post('/risk/manager-gate', response_model=StandardResponse)
def manager_decision_gate(payload: ManagerGateRequest):
    return check_manager_gate(payload)


@app.post('/risk/profit-plan-gate', response_model=StandardResponse)
def profit_plan_gate(payload: ProfitPlanGateRequest):
    return check_profit_plan_gate(payload)


@app.post('/risk/protection-plan', response_model=StandardResponse)
def protection_plan(payload: ProtectionPlanRequest):
    return standard_response(
        data=build_protection_plan(payload),
        metadata={
            'contract': 'risk-existing-position-protection-v1',
            'broker_mutation': False,
        },
    )
