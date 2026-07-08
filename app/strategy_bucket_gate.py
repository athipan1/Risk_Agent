from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


CONTROLLED_STRATEGY_BUCKETS = {
    "core_dividend",
    "value_rebound",
    "news_momentum",
}
UNASSIGNED = "unassigned"
MIN_BUCKET_CONFIDENCE = 0.70
BLOCKED_CLASSIFICATION_STATUSES = {
    "conflict",
    "invalid",
    "review",
    "unassigned",
}


@dataclass(frozen=True)
class StrategyBucketGateResult:
    allowed: bool
    bucket: str
    confidence: float | None
    classification_status: str | None
    classifier_version: str | None
    reasons: tuple[str, ...]
    violations: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "strategy_bucket": self.bucket,
            "bucket_confidence": self.confidence,
            "bucket_classification_status": self.classification_status,
            "bucket_classifier_version": self.classifier_version,
            "bucket_classification_reasons": list(self.reasons),
            "min_bucket_confidence": MIN_BUCKET_CONFIDENCE,
            "classification_metadata_required": self.metadata_required,
            "violations": list(self.violations),
            "warnings": list(self.warnings),
        }


def _normalize_side(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def normalize_strategy_bucket(value: Any) -> str:
    return str(value or UNASSIGNED).strip().lower() or UNASSIGNED


def _normalize_status(value: Any) -> str | None:
    if value is None:
        return None
    status = str(value).strip().lower()
    return status or None


def _normalize_confidence(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _normalize_reasons(values: Iterable[Any] | None) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(str(value) for value in values if str(value).strip())


def evaluate_strategy_bucket_gate(
    *,
    side: Any,
    strategy_bucket: Any,
    trading_mode: str = "PAPER",
    bucket_confidence: Any = None,
    classification_status: Any = None,
    classifier_version: Any = None,
    classification_reasons: Iterable[Any] | None = None,
    require_metadata: bool = False,
    allow_legacy_missing_bucket: bool = False,
) -> StrategyBucketGateResult:
    """Validate bucket attribution before Risk approves new exposure.

    SELL/HOLD paths are never blocked by bucket attribution because they reduce
    exposure or create no exposure. BUY paths fail closed for unassigned,
    unknown, conflicting, invalid, review, or explicitly low-confidence buckets.

    Missing classification metadata is required for portfolio/trade-plan flows
    and for LIVE direct checks. A legacy PAPER direct request that omitted the
    bucket field entirely may be allowed temporarily with an audit warning.
    """
    normalized_side = _normalize_side(side)
    bucket = normalize_strategy_bucket(strategy_bucket)
    confidence = _normalize_confidence(bucket_confidence)
    status = _normalize_status(classification_status)
    version = str(classifier_version).strip() if classifier_version else None
    reasons = _normalize_reasons(classification_reasons)
    live_mode = str(trading_mode or "PAPER").strip().upper() == "LIVE"
    metadata_required = bool(require_metadata or live_mode)

    violations: list[str] = []
    warnings: list[str] = []

    if normalized_side != "buy":
        if bucket == UNASSIGNED:
            warnings.append("strategy_bucket_unassigned_exit_allowed")
        elif bucket not in CONTROLLED_STRATEGY_BUCKETS:
            warnings.append("unsupported_strategy_bucket_exit_allowed")
        return StrategyBucketGateResult(
            allowed=True,
            bucket=bucket,
            confidence=confidence,
            classification_status=status,
            classifier_version=version,
            reasons=reasons,
            violations=(),
            warnings=tuple(warnings),
            metadata_required=metadata_required,
        )

    legacy_bucket_omission = allow_legacy_missing_bucket and bucket == UNASSIGNED
    if bucket == UNASSIGNED:
        if legacy_bucket_omission:
            warnings.append("legacy_strategy_bucket_missing")
        else:
            violations.append("strategy_bucket_unassigned")
    elif bucket not in CONTROLLED_STRATEGY_BUCKETS:
        violations.append("unsupported_strategy_bucket")

    if status in BLOCKED_CLASSIFICATION_STATUSES:
        violations.append(f"strategy_bucket_classification_{status}")
    elif status is not None and status != "classified":
        violations.append("strategy_bucket_classification_status_invalid")

    if confidence is not None and confidence < MIN_BUCKET_CONFIDENCE:
        violations.append("strategy_bucket_confidence_below_minimum")

    metadata_missing = confidence is None or status is None or not version
    if metadata_missing:
        if metadata_required and not legacy_bucket_omission:
            violations.append("strategy_bucket_classification_metadata_required")
        else:
            warnings.append("strategy_bucket_classification_metadata_missing")

    return StrategyBucketGateResult(
        allowed=not violations,
        bucket=bucket,
        confidence=confidence,
        classification_status=status,
        classifier_version=version,
        reasons=reasons,
        violations=tuple(dict.fromkeys(violations)),
        warnings=tuple(dict.fromkeys(warnings)),
        metadata_required=metadata_required,
    )


def classification_fields_from_mapping(mapping: dict[str, Any] | None) -> dict[str, Any]:
    """Read Manager classifier fields from flat or nested payload shapes."""
    source = mapping or {}
    nested = source.get("strategy_bucket_classification")
    nested = nested if isinstance(nested, dict) else {}
    return {
        "bucket_confidence": source.get("bucket_confidence", nested.get("confidence")),
        "classification_status": source.get(
            "bucket_classification_status",
            nested.get("status"),
        ),
        "classifier_version": source.get(
            "bucket_classifier_version",
            nested.get("classifier_version"),
        ),
        "classification_reasons": source.get(
            "bucket_classification_reasons",
            nested.get("reasons") or [],
        ),
    }
