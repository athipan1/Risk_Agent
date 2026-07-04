# Risk_Agent API Contract

This document defines the baseline API contract for `Risk_Agent` in the multi-agent trading system.

`Risk_Agent` is the safety gate for position sizing, order checks, trade-plan checks, portfolio checks, manager decision gates, and profit-plan gates.

## Standard Headers

Every internal request should include:

```http
Content-Type: application/json
X-Correlation-ID: <uuid>
X-API-KEY: <risk-agent-api-key>
```

## Standard Response Envelope

Every response should use this envelope:

```json
{
  "status": "success",
  "agent_type": "risk",
  "version": "1.5.0",
  "schema_version": "1.0",
  "timestamp": "2026-07-04T00:00:00Z",
  "correlation_id": "00000000-0000-0000-0000-000000000000",
  "data": {},
  "metadata": {},
  "error": null,
  "confidence_score": null
}
```

## Required Operational Endpoints

```http
GET /health
GET /ready
GET /version
```

| Endpoint | Purpose |
| --- | --- |
| `/health` | Reports whether the service is alive and exposes risk-control metadata. |
| `/ready` | Reports whether the risk gate is ready to approve or reject trade flows. |
| `/version` | Reports agent version, schema version, and API contract metadata. |

## Required Risk Endpoints

```http
POST /risk/position-size
POST /risk/check
POST /risk/trade-plan-check
POST /risk/portfolio-check
POST /risk/manager-gate
POST /risk/profit-plan-gate
```

## Safety Rules

1. `Risk_Agent` must remain a gate before execution.
2. `Risk_Agent` must not submit broker orders directly.
3. Emergency halt must make readiness fail.
4. Live readiness should require conservative policy controls.
5. Manager remains the orchestrator; Risk only approves, rejects, or recommends constraints.
6. Every trade-plan check should be traceable with a correlation ID in the broader workflow.
