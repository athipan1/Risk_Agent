from fastapi import FastAPI

from app.checks import check_order
from app.manager_gate import check_manager_gate
from app.models import ManagerGateRequest, PortfolioRiskCheckRequest, PositionSizeRequest, RiskCheckRequest, StandardResponse, TradePlanRiskCheckRequest
from app.policy import POLICY
from app.portfolio_checks import check_portfolio
from app.sizing import calculate_position_size
from app.trade_plan_adapter import check_trade_plan

app = FastAPI(title='Risk Agent', version='1.4.0')


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'agent_type': 'risk',
        'version': '1.4.0',
        'data': {
            'session_risk_controls': True,
            'stock_risk_controls': True,
            'portfolio_allocation_controls': True,
            'trade_plan_controls': True,
            'manager_decision_gate': True,
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
    return {'status': 'success', 'agent_type': 'risk', 'version': '1.4.0', 'data': POLICY, 'error': None}


@app.get('/risk/status')
def risk_status():
    return {
        'status': 'success',
        'agent_type': 'risk',
        'version': '1.4.0',
        'data': {
            'ready_for_stock_paper': True,
            'ready_for_stock_live': not POLICY.get('emergency_halt', False) and POLICY.get('stock_only_mode', True),
            'ready_for_portfolio_allocation': True,
            'ready_for_trade_plan_check': True,
            'ready_for_manager_decision_gate': True,
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
        'error': None,
    }


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
