from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _payload():
    return {
        "trade_plan": {
            "plan_id": "shadow-plan-1",
            "correlation_id": "corr-shadow-risk",
            "source": "scanner",
            "status": "risk_pending",
            "account_id": "1",
            "symbol": "NVDA",
            "side": "buy",
            "order_type": "market",
            "entry_price": 180.0,
            "quantity": 1,
            "final_quantity": 1,
            "time_in_force": "GTC",
            "strategy": "trend_following",
            "strategy_bucket": "value_rebound",
            "bucket_confidence": 0.9,
            "bucket_classification_status": "classified",
            "bucket_classification_reasons": ["shadow_test"],
            "bucket_classifier_version": "manager-strategy-bucket-v2",
            "final_verdict": "buy",
            "confidence_score": 0.7,
            "expected_r": 2.0,
            "risk": {
                "account_equity": 10000,
                "max_loss_amount": 5,
                "max_loss_pct": 0.0005,
                "risk_per_share": 5,
                "position_value": 180,
                "position_pct": 0.018,
                "reward_risk_ratio": 2.0,
            },
            "exit": {"stop_loss": 175.0, "take_profit": 190.0},
            "risk_approval_id": None,
            "manual_approval_required": True,
            "dry_run": True,
            "reasons": [],
            "guard_plan": {},
            "metadata": {
                "execution_mode": "shadow",
                "lane": "shadow",
                "broker_order_authorized": False,
            },
        },
        "trading_mode": "PAPER",
    }


def test_risk_trade_plan_gate_hard_blocks_shadow_lane():
    response = client.post("/risk/trade-plan-check", json=_payload())
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "rejected"
    assert body["data"]["approved"] is False
    assert body["data"]["risk_approval_id"] is None
    assert body["data"]["trade_plan_validation"] == "shadow_hard_block"
    assert body["data"]["broker_order_authorized"] is False
    assert "shadow_lane_execution_forbidden" in body["data"]["violations"]
