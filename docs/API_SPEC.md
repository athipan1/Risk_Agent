# Risk Agent API Spec

Base URL: http://localhost:8007

## GET /health

Returns service status.

## GET /risk/policy

Returns active policy.

## POST /risk/position-size

Calculates safe quantity using trade loss limit and max position value.

Request fields:

- symbol
- side
- entry_price
- protection_price
- equity

## POST /risk/check

Main pre-trade gate used by Manager_Agent before Execution_Agent.

Request fields:

- account_id
- symbol
- side
- entry_price
- protection_price
- requested_quantity
- equity
- current_symbol_exposure
- current_total_exposure
- margin_multiplier

## Manager_Agent Integration

Flow:

1. Manager receives buy or sell decision.
2. Manager asks Database_Agent for equity and exposure.
3. Manager builds RiskCheckRequest.
4. Manager calls Risk_Agent /risk/check.
5. If approved, Manager sends order to Execution_Agent.
6. If rejected, Manager returns hold or reduced-size recommendation.
7. Manager logs the result to Learning_Agent.
