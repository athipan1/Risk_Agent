from __future__ import annotations

from typing import Any

from app.models import RiskCheckRequest
from app.session_limits import check_session_limits

KILL_SWITCH_VIOLATIONS = {
    'emergency_halt_active',
    'daily_loss_limit_exceeded',
    'weekly_loss_limit_exceeded',
    'max_consecutive_losses_exceeded',
    'loss_streak_cooldown_active',
    'max_trades_per_day_exceeded',
    'max_symbol_trades_per_day_exceeded',
}


def kill_switch_from_risk_payload(payload: RiskCheckRequest) -> tuple[bool, list[str], list[str], dict[str, Any]]:
    """Evaluate session-level circuit breakers for one risk payload."""
    violations, warnings, metrics = check_session_limits(payload)
    kill_switch_active = any(violation in KILL_SWITCH_VIOLATIONS for violation in violations)
    metrics = {
        **metrics,
        'kill_switch_active': kill_switch_active,
        'kill_switch_violations': [
            violation for violation in violations if violation in KILL_SWITCH_VIOLATIONS
        ],
    }
    return kill_switch_active, violations, warnings, metrics


def rejected_kill_switch_payload(
    *,
    trading_mode: str,
    asset_class: str,
    violations: list[str],
    warnings: list[str],
    metrics: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = {
        'approved': False,
        'approved_quantity': 0.0,
        'final_quantity': 0.0,
        'trading_mode': trading_mode,
        'asset_class': asset_class,
        'kill_switch_active': True,
        'violations': list(dict.fromkeys(violations)),
        'warnings': list(dict.fromkeys(warnings)),
        'session_risk': metrics,
    }
    if extra:
        data.update(extra)
    return data
