from fastapi import FastAPI

from app.checks import check_order
from app.models import PositionSizeRequest, RiskCheckRequest, StandardResponse
from app.policy import POLICY
from app.sizing import calculate_position_size

app = FastAPI(title='Risk Agent', version='1.2.0')


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'agent_type': 'risk',
        'version': '1.2.0',
        'data': {
            'session_risk_controls': True,
            'stock_risk_controls': True,
            'stock_only_mode': POLICY.get('stock_only_mode', True),
            'allow_short_selling': POLICY.get('allow_short_selling', False),
            'emergency_halt': POLICY.get('emergency_halt', False),
            'max_daily_loss_pct': POLICY.get('max_daily_loss_pct'),
            'max_weekly_loss_pct': POLICY.get('max_weekly_loss_pct'),
            'max_single_stock_pct': POLICY.get('max_single_stock_pct'),
            'max_sector_exposure_pct': POLICY.get('max_sector_exposure_pct'),
        },
    }


@app.get('/risk/policy')
def get_policy():
    return {'status': 'success', 'agent_type': 'risk', 'version': '1.2.0', 'data': POLICY, 'error': None}


@app.get('/risk/status')
def risk_status():
    return {
        'status': 'success',
        'agent_type': 'risk',
        'version': '1.2.0',
        'data': {
            'ready_for_stock_paper': True,
            'ready_for_stock_live': not POLICY.get('emergency_halt', False) and POLICY.get('stock_only_mode', True),
            'stock_only_mode': POLICY.get('stock_only_mode', True),
            'allow_short_selling': POLICY.get('allow_short_selling', False),
            'allow_fractional_shares': POLICY.get('allow_fractional_shares', False),
            'max_single_stock_pct': POLICY.get('max_single_stock_pct'),
            'max_sector_exposure_pct': POLICY.get('max_sector_exposure_pct'),
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
