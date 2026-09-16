from copy import deepcopy

from fastapi.testclient import TestClient

from app.main import app
from app.models import PortfolioRiskCheckRequest
from app.portfolio_checks import check_portfolio


def request(*, same_sector=False, same_symbol=False, **updates):
    p=dict(account_id=1,equity=100000,positions=[dict(
        symbol='AAA' if same_symbol else symbol,entry_price=100,protection_price=95,
        requested_quantity=100,strategy_bucket='core_dividend',bucket_confidence=.9,
        bucket_classification_status='classified',bucket_classifier_version='fixture-only',
        scanner_candidate={'metadata':{'sector':'Technology' if same_sector else sector}},
    ) for symbol,sector in zip(['AAA','BBB','CCC','DDD','EEE'],
       ['Technology','Healthcare','Industrials','Utilities','Financials'])])
    p.update(updates)
    return PortfolioRiskCheckRequest(**p)


def test_five_diversified_candidates_pass_actual_api_with_individual_limits():
    p=request()
    response=TestClient(app).post('/risk/portfolio-check',json=p.model_dump())
    assert response.status_code==200
    result=response.json()['data']
    assert result['approved_positions']==5
    assert result['projected_total_exposure']==50000
    assert all(value==10000 for value in result['projected_sector_exposures'].values())


def test_same_sector_batch_never_exceeds_unchanged_sector_cap():
    p=request(same_sector=True)
    before=deepcopy(p)
    result=check_portfolio(p).data
    assert result['projected_sector_exposures']['Technology']==25000
    assert [r['final_quantity'] for r in result['risk_approvals']]==[100,100,50,0,0]
    assert all('sector_exposure_limit_exceeded' in r['violations'] for r in result['risk_approvals'][3:])
    assert p==before
    reverse=p.model_copy(update={'positions':list(reversed(p.positions))})
    assert check_portfolio(reverse).data==result


def test_repeated_symbol_cannot_reuse_original_exposure_snapshot():
    result=check_portfolio(request(same_symbol=True)).data
    assert result['projected_symbol_exposures']['AAA']==10000
    assert result['approved_positions']==1


def test_existing_sector_and_open_orders_reduce_remaining_capacity():
    result=check_portfolio(request(same_sector=True,current_total_exposure=20000,
        current_sector_exposures={'Technology':20000},open_orders_exposure=75000)).data
    assert result['projected_sector_exposures']['Technology']==25000
    assert sum(r['approved_value'] for r in result['risk_approvals'])==5000


def test_emergency_halt_rejects_all_five_candidates():
    result=check_portfolio(request(session_risk_context={'emergency_halt':True})).data
    assert result['approved_positions']==0
    assert all('emergency_halt_active' in r['violations'] for r in result['risk_approvals'])
