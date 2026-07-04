import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import StandardResponse


REQUIRED_STANDARD_RESPONSE_FIELDS = {
    'status',
    'agent_type',
    'version',
    'schema_version',
    'timestamp',
    'correlation_id',
    'data',
    'metadata',
    'error',
    'confidence_score',
}


def assert_standard_response(payload):
    assert REQUIRED_STANDARD_RESPONSE_FIELDS.issubset(payload.keys())
    assert payload['agent_type'] == 'risk'
    assert payload['version'] == '1.5.0'
    assert payload['schema_version'] == '1.0'


def test_standard_response_has_contract_defaults():
    response = StandardResponse(
        status='success',
        data={'ok': True},
    )

    payload = response.model_dump(mode='json')

    assert REQUIRED_STANDARD_RESPONSE_FIELDS.issubset(payload.keys())
    assert payload['agent_type'] == 'risk'
    assert payload['version'] == '1.5.0'
    assert payload['schema_version'] == '1.0'
    assert payload['correlation_id'] is None
    assert payload['metadata'] == {}
    assert payload['confidence_score'] is None
    assert payload['timestamp']


def test_standard_response_rejects_invalid_schema_version():
    with pytest.raises(ValidationError):
        StandardResponse(
            status='success',
            schema_version='v1',
            data={},
        )


def test_version_endpoint_uses_standard_contract():
    client = TestClient(app)
    response = client.get('/version')

    assert response.status_code == 200
    payload = response.json()
    assert_standard_response(payload)
    assert payload['data']['api_contract'] == 'multi-agent-trading-api-contract'
    assert payload['data']['schema_version'] == '1.0'


def test_ready_endpoint_uses_standard_contract():
    client = TestClient(app)
    response = client.get('/ready')

    assert response.status_code == 200
    payload = response.json()
    assert_standard_response(payload)
    assert 'ready' in payload['data']
    assert 'emergency_halt' in payload['data']
    assert payload['metadata']['contract_source'] == 'risk-agent-runtime-contract'
