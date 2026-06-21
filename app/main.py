from fastapi import FastAPI

from app.checks import check_order
from app.models import PositionSizeRequest, RiskCheckRequest, StandardResponse
from app.policy import POLICY
from app.sizing import calculate_position_size

app = FastAPI(title='Risk Agent', version='1.1.0')


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'agent_type': 'risk',
        'version': '1.1.0',
        'data': {
            'session_risk_controls': True,
            'emergency_halt': POLICY.get('emergency_halt', False),
            'max_daily_loss_pct': POLICY.get('max_daily_loss_pct'),
            'max_weekly_loss_pct': POLICY.get('max_weekly_loss_pct'),
        },
    }


@app.get('/risk/policy')
def get_policy():
    return {'status': 'success', 'agent_type': 'risk', 'version': '1.1.0', 'data': POLICY, 'error': None}


@app.post('/risk/position-size', response_model=StandardResponse)
def position_size(payload: PositionSizeRequest):
    return calculate_position_size(payload)


@app.post('/risk/check', response_model=StandardResponse)
def risk_check(payload: RiskCheckRequest):
    return check_order(payload)
