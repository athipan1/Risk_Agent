# Strategy Bucket Risk Gate

Risk_Agent independently verifies Manager's strategy-bucket classification before approving new BUY exposure.

## Controlled buckets

- `core_dividend`
- `value_rebound`
- `news_momentum`
- `unassigned` (quarantine / historical attribution only)

`quality_growth` is no longer part of the controlled contract.

## BUY gate

A portfolio or TradePlan BUY requires all of the following:

```text
strategy_bucket in controlled buckets
bucket_classification_status == classified
bucket_confidence >= 0.70
bucket_classifier_version is present
```

Risk rejects BUY requests with any of these violations:

- `strategy_bucket_unassigned`
- `unsupported_strategy_bucket`
- `strategy_bucket_classification_conflict`
- `strategy_bucket_classification_invalid`
- `strategy_bucket_classification_review`
- `strategy_bucket_confidence_below_minimum`
- `strategy_bucket_classification_metadata_required`

The response includes `strategy_bucket_gate` diagnostics containing the requested bucket, confidence, status, classifier version, reasons, warnings, and violations.

## SELL and HOLD behavior

Bucket attribution must not prevent risk reduction. SELL and HOLD paths are not blocked by the bucket gate, including historical positions whose bucket is still `unassigned`.

The response records warnings such as:

```text
strategy_bucket_unassigned_exit_allowed
```

## Legacy direct PAPER checks

During migration, a direct PAPER `/risk/check` request that omits the `strategy_bucket` field entirely can continue with explicit warnings:

- `legacy_strategy_bucket_missing`
- `strategy_bucket_classification_metadata_missing`

This exception does not apply when the request explicitly sends `strategy_bucket=unassigned`. Portfolio and TradePlan BUY paths always require classifier metadata.

## Invariant

```text
Manager classified bucket
    == Risk approved bucket
    == Execution requested bucket
    == Database persisted bucket
```
