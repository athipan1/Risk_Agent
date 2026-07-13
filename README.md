# Risk Agent

Risk Agent คือบริการตรวจสอบความเสี่ยงก่อนส่งคำสั่งเทรดจริงในระบบ Multi-Agent Trading ของ `athipan1`.

หน้าที่หลักคือเป็น **Pre-Trade Risk Gate** ระหว่าง `Manager_Agent` และ `Execution_Agent` เพื่อจำกัด position size และ exposure, บังคับ protection price และใช้ session circuit breakers ก่อนอนุมัติคำสั่งใหม่

---

## Role in Current Trading System

```text
Scanner_Agent
    ↓
Manager_Agent
    ↓
Technical_Agent + Fundamental_Agent + Database_Agent
    ↓
Risk_Agent  ← SAFETY GATE
    ↓
Execution_Agent
    ↓
Learning_Agent
```

---

## Core Risk Rules

Default policy:

- Max position value per symbol: **10% of equity**
- Recommended safe range: **5–10% of equity**
- Max risk per trade: **1% of equity**
- Stop-loss required for every non-HOLD order
- Reject orders with invalid stop-loss direction
- Reject orders exceeding leverage or margin limits
- Reject trades if projected portfolio exposure exceeds allowed threshold

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Service health check |
| `/ready` | GET | Risk-gate readiness; returns not ready while emergency halt is active |
| `/version` | GET | Agent and API contract versions |
| `/risk/status` | GET | Runtime readiness and active circuit-breaker policy |
| `/risk/check` | POST | Full pre-trade risk validation |
| `/risk/position-size` | POST | Calculate allowed quantity based on stop-loss risk |
| `/risk/policy` | GET | Return active risk policy |
| `/risk/trade-plan-check` | POST | Validate a Manager trade plan |
| `/risk/portfolio-check` | POST | Validate a portfolio batch |
| `/risk/manager-gate` | POST | Validate a Manager decision and market context |
| `/risk/profit-plan-gate` | POST | Validate advisory profit-plan actions |
| `/risk/protection-plan` | POST | Build a non-broker-mutating protection plan |
| `/risk/halt` | POST | Trip the persistent runtime emergency halt (admin only) |
| `/risk/halt/clear` | POST | Clear the persistent runtime emergency halt (admin only) |

## Runtime Emergency Halt

Set a strong `ADMIN_TOKEN` before using the admin endpoints. Requests authenticate with the `X-Admin-Token` header. If `ADMIN_TOKEN` is missing, both endpoints fail closed with HTTP 503; a missing header returns 401 and a wrong token returns 403.

```bash
export ADMIN_TOKEN='replace-with-a-long-random-secret'

curl -X POST http://localhost:8007/risk/halt \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"reason":"broker anomaly detected"}'

curl -X POST http://localhost:8007/risk/halt/clear \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"reason":"broker health verified","confirm":true}'
```

Runtime state is stored in `EMERGENCY_HALT_FILE` (default `/data/emergency_halt.flag`). The Docker Compose configuration mounts `/data` on the named volume `risk-agent-data`, so trip and clear state survive container restarts. A persisted runtime value overrides the deploy-time `EMERGENCY_HALT` default. Clearing requires both a non-blank `reason` and `confirm: true`.

While halted, `/risk/check`, `/risk/position-size`, and `/risk/trade-plan-check` reject new risk approvals immediately. `/ready`, `/health`, `/risk/status`, and `/risk/policy` report the active runtime state.

---

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8007
```

Docker:

```bash
docker compose up --build
```

Run tests:

```bash
pytest -q
```

---

## Example Risk Check

```json
{
  "account_id": 1,
  "symbol": "AAPL",
  "side": "buy",
  "entry_price": 100,
  "protection_price": 95,
  "requested_quantity": 5,
  "equity": 10000,
  "current_symbol_exposure": 0,
  "current_total_exposure": 0,
  "open_orders_exposure": 0,
  "margin_multiplier": 1,
  "trading_mode": "PAPER"
}
```

---

## Integration Rule

`Manager_Agent` must call `/risk/check` before calling `Execution_Agent /execute`.

If Risk Agent returns `rejected`, Manager Agent must not place the order.
