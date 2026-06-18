# Risk Agent

Risk Agent คือบริการตรวจสอบความเสี่ยงก่อนส่งคำสั่งเทรดจริงในระบบ Multi-Agent Trading ของ `athipan1`.

หน้าที่หลักคือเป็น **Pre-Trade Risk Gate** ระหว่าง `Manager_Agent` และ `Execution_Agent` เพื่อป้องกันการใช้ margin/leverage หนักเกินไป, จำกัด position size และบังคับ stop-loss ทุกคำสั่ง

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
| `/risk/check` | POST | Full pre-trade risk validation |
| `/risk/position-size` | POST | Calculate allowed quantity based on stop-loss risk |
| `/risk/policy` | GET | Return active risk policy |

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
  "stop_loss_price": 95,
  "requested_quantity": 50,
  "equity": 10000,
  "current_symbol_exposure": 0,
  "current_total_exposure": 20000,
  "leverage": 1
}
```

---

## Integration Rule

`Manager_Agent` must call `/risk/check` before calling `Execution_Agent /execute`.

If Risk Agent returns `rejected`, Manager Agent must not place the order.
