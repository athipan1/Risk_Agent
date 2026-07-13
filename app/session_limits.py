from app.models import RiskCheckRequest
from app.policy import (
    COOLDOWN_MINUTES_AFTER_LOSS_STREAK,
    MAX_CONSECUTIVE_LOSSES,
    MAX_DAILY_LOSS_PCT,
    MAX_SYMBOL_TRADES_PER_DAY,
    MAX_TRADES_PER_DAY,
    MAX_WEEKLY_LOSS_PCT,
    SYMBOL_COOLDOWN_MINUTES,
)
from app.runtime_halt import is_emergency_halt_active


def _loss_pct(realized_pnl: float, equity: float) -> float:
    if equity <= 0:
        return 0.0
    return abs(min(0.0, realized_pnl)) / equity


def check_session_limits(payload: RiskCheckRequest) -> tuple[list[str], list[str], dict]:
    """Return session/circuit-breaker violations, warnings, and metrics.

    This function is deliberately stateless. Manager/Database supplies the current
    session counters, while Risk Agent owns policy evaluation and fail-closed
    decisions.
    """
    violations: list[str] = []
    warnings: list[str] = []

    daily_loss_pct = _loss_pct(payload.daily_realized_pnl, payload.equity)
    weekly_loss_pct = _loss_pct(payload.weekly_realized_pnl, payload.equity)

    emergency_halt = is_emergency_halt_active() or payload.emergency_halt
    if emergency_halt:
        violations.append('emergency_halt_active')

    if daily_loss_pct >= MAX_DAILY_LOSS_PCT:
        violations.append('daily_loss_limit_exceeded')

    if weekly_loss_pct >= MAX_WEEKLY_LOSS_PCT:
        violations.append('weekly_loss_limit_exceeded')

    if payload.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        violations.append('max_consecutive_losses_exceeded')
        minutes = payload.minutes_since_last_loss
        if minutes is None or minutes < COOLDOWN_MINUTES_AFTER_LOSS_STREAK:
            violations.append('loss_streak_cooldown_active')

    if payload.trades_today >= MAX_TRADES_PER_DAY:
        violations.append('max_trades_per_day_exceeded')

    if payload.symbol_trades_today >= MAX_SYMBOL_TRADES_PER_DAY:
        violations.append('max_symbol_trades_per_day_exceeded')

    symbol_minutes = payload.minutes_since_last_symbol_trade
    if symbol_minutes is not None and symbol_minutes < SYMBOL_COOLDOWN_MINUTES:
        violations.append('symbol_cooldown_active')

    if daily_loss_pct >= MAX_DAILY_LOSS_PCT * 0.80 and daily_loss_pct < MAX_DAILY_LOSS_PCT:
        warnings.append('daily_loss_near_limit')

    if weekly_loss_pct >= MAX_WEEKLY_LOSS_PCT * 0.80 and weekly_loss_pct < MAX_WEEKLY_LOSS_PCT:
        warnings.append('weekly_loss_near_limit')

    metrics = {
        'daily_realized_pnl': round(payload.daily_realized_pnl, 2),
        'weekly_realized_pnl': round(payload.weekly_realized_pnl, 2),
        'daily_loss_pct': round(daily_loss_pct, 6),
        'weekly_loss_pct': round(weekly_loss_pct, 6),
        'consecutive_losses': payload.consecutive_losses,
        'trades_today': payload.trades_today,
        'symbol_trades_today': payload.symbol_trades_today,
        'minutes_since_last_loss': payload.minutes_since_last_loss,
        'minutes_since_last_symbol_trade': payload.minutes_since_last_symbol_trade,
        'emergency_halt': emergency_halt,
        'limits': {
            'max_daily_loss_pct': MAX_DAILY_LOSS_PCT,
            'max_weekly_loss_pct': MAX_WEEKLY_LOSS_PCT,
            'max_consecutive_losses': MAX_CONSECUTIVE_LOSSES,
            'cooldown_minutes_after_loss_streak': COOLDOWN_MINUTES_AFTER_LOSS_STREAK,
            'max_trades_per_day': MAX_TRADES_PER_DAY,
            'max_symbol_trades_per_day': MAX_SYMBOL_TRADES_PER_DAY,
            'symbol_cooldown_minutes': SYMBOL_COOLDOWN_MINUTES,
        },
    }
    return violations, warnings, metrics
