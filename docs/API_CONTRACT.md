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
  "version": "1.6.0",
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
POST /risk/protection-plan
```

## Runtime Emergency Halt

The emergency halt is a process-runtime control backed by a persistent state file. It can be changed without restarting the service. The persisted state overrides the deploy-time `EMERGENCY_HALT` default.

Configuration:

| Variable | Required | Purpose |
| --- | --- | --- |
| `ADMIN_TOKEN` | Required to operate admin endpoints | Shared secret compared with `X-Admin-Token`. If unset, admin endpoints return HTTP 503. |
| `EMERGENCY_HALT` | No | Deploy-time default used when no persisted runtime record exists. |
| `EMERGENCY_HALT_FILE` | No | Persistent state path; defaults to `/data/emergency_halt.flag`. |

### Trip halt

```http
POST /risk/halt
Content-Type: application/json
X-Admin-Token: <admin-token>

{"reason":"broker anomaly detected"}
```

Successful response data contains `active: true`, `reason`, `updated_at`, and `source`. The service logs the trip with its UTC timestamp and reason.

### Clear halt

```http
POST /risk/halt/clear
Content-Type: application/json
X-Admin-Token: <admin-token>

{"reason":"broker health verified","confirm":true}
```

Both a non-blank `reason` and literal `confirm: true` are required. Successful response data contains `active: false`, `reason`, `updated_at`, and `source`. The service logs the clear with its UTC timestamp and reason.

Authentication failures:

| Condition | HTTP status |
| --- | --- |
| `ADMIN_TOKEN` is not configured | 503 |
| `X-Admin-Token` is missing | 401 |
| `X-Admin-Token` is incorrect | 403 |

When active, the runtime halt must reject new approvals from `/risk/check`, `/risk/position-size`, and `/risk/trade-plan-check`. It must also be reflected by `/ready`, `/health`, `/risk/status`, and `/risk/policy`. Request-level `emergency_halt: true` remains an additional fail-safe and cannot be negated by clearing the runtime halt.

## Safety Rules

1. `Risk_Agent` must remain a gate before execution.
2. `Risk_Agent` must not submit broker orders directly.
3. Emergency halt must make readiness fail and reject new risk approvals.
4. Live readiness should require conservative policy controls.
5. Manager remains the orchestrator; Risk only approves, rejects, or recommends constraints.
6. Every trade-plan check should be traceable with a correlation ID in the broader workflow.
