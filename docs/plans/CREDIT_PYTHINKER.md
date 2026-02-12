# Pythinker Credit System Plan

Status: In Progress  
Last Updated: 2026-02-12  
Owner: Platform / Billing / Agent Runtime

## 1. Objective

Introduce a first-class credit ledger for Pythinker that is deterministic, auditable, and explainable, while reusing the existing token/cost usage pipeline.

Target outcomes:

- Per-task credit charging with factorized explanation.
- Deterministic debit order across credit buckets.
- Auto and manual refunds with immutable audit trail.
- User and admin APIs for balance, history, and dispute handling.
- Nightly reconciliation proving ledger correctness.

## 2. Current State (Code-Backed)

Completed observations:

1. Usage tracking already exists for tokens and USD cost.
File references: `backend/app/domain/models/usage.py`, `backend/app/application/services/usage_service.py`, `backend/app/interfaces/api/usage_routes.py`, `frontend/src/api/usage.ts`
2. Daily aggregation and pricing surfaces are already implemented.
File references: `backend/app/infrastructure/models/documents.py`, `backend/app/domain/services/usage/pricing.py`, `backend/app/interfaces/schemas/usage.py`
3. Session-level budget controls exist in USD/token terms, not credit-wallet terms.
File references: `backend/app/infrastructure/models/documents.py`, `backend/app/domain/services/concurrency/token_budget.py`
4. No dedicated credit domain models, credit ledger, or credit APIs currently exist.

Gap summary:

- We can measure usage today, but we cannot enforce plan-tier credit policy or provide credit-level user transparency/refunds.

## 3. External Policy Inputs and Caveats

Known external references used for initial policy shape:

- Manus help center pages about bucket ordering, resets, and refunds.
- Manus API docs indicating `credit_usage` in task responses.

Design rule for Pythinker:

- External product behavior is reference input, not source of truth.
- Final behavior is controlled by `CreditPolicyVersion` records in Pythinker.
- Any unresolved external contradictions stay marked as `Open Decision` until product signs off.

## 4. Scope

In scope:

- Credit ledger domain and persistence.
- Debit/refund engines with idempotency.
- Policy versioning and policy-effective charging.
- Daily/monthly grant-expire jobs.
- User/admin credit APIs.
- Frontend credit visibility.
- Reconciliation + observability.

Out of scope for this phase:

- Payment provider integration.
- Tax/invoice/accounting workflows.
- Multi-tenant revenue reporting.

## 5. Architecture (Layered)

Dependency rule: Domain -> Application -> Infrastructure -> Interfaces.

### 5.1 Domain Layer

New models:

- `CreditBucketType`: `daily_refresh`, `monthly_plan`, `add_on`
- `CreditEventType`: `granted`, `debited`, `refunded`, `expired`, `admin_adjusted`
- `CreditLedgerEntry`: immutable event row
- `CreditPolicyVersion`: effective policy snapshot and coefficients
- `TaskCreditUsage`: task-level factors and final charged credits
- `RefundRequest`: manual refund workflow state

New domain services:

- `CreditCalculator`: converts measured task factors into integer credits.
- `CreditDebitEngine`: applies deterministic bucket split.
- `CreditRefundEngine`: computes safe refundable amounts and refund bucket mapping.
- `CreditReconciler`: replays ledger and compares computed vs stored balances.

### 5.2 Application Layer

New application services:

- `CreditService` for balance reads, charge/refund commands, history views.
- `CreditPolicyService` for policy version activation.
- `CreditSchedulerService` for daily/monthly grant+expire routines.

Integration with existing `UsageService`:

- `UsageService` remains the source for token/cost measurements.
- Credit engines consume usage outputs plus runtime/tool metadata.
- Do not duplicate token/cost aggregation logic.

### 5.3 Infrastructure Layer

New collections/documents:

- `credit_ledger` (append-only)
- `credit_policy_versions`
- `task_credit_usage`
- `credit_refund_requests`
- `credit_idempotency`

Indexes (minimum):

- `credit_ledger`: `(user_id, created_at desc)`, `(task_id)`, `(idempotency_key unique)`.
- `task_credit_usage`: `(task_id unique)`, `(user_id, created_at desc)`.
- `credit_refund_requests`: `(user_id, status, created_at desc)`.
- `credit_policy_versions`: `(effective_from desc)`, `(is_active)`.

### 5.4 Interface Layer

New API routes:

- `backend/app/interfaces/api/credit_routes.py`
- `backend/app/interfaces/api/admin_credit_routes.py`

New schemas:

- `backend/app/interfaces/schemas/credit.py`

Frontend integration targets:

- Extend settings usage UI with credit widgets.
File references: `frontend/src/components/settings/UsageSettings.vue`, `frontend/src/api/usage.ts`
- Add dedicated API client module for credit endpoints.
Proposed file: `frontend/src/api/credits.ts`

## 6. Ledger Rules and Invariants

Hard invariants:

1. Ledger is append-only; updates/deletes are forbidden.
2. Balance is derived from ledger events, not mutable counters alone.
3. Debit order is deterministic and policy-versioned.
4. Refund cannot exceed prior debit for the linked task.
5. Every write command is idempotent.

Required ledger fields:

- `entry_id`
- `user_id`
- `task_id` (nullable for non-task grants/adjustments)
- `event_type`
- `bucket_type`
- `delta_credits` (signed int)
- `policy_version`
- `reason_code`
- `idempotency_key`
- `created_by`
- `created_at`

## 7. Credit Calculation Policy (v1 Draft)

Formula:

`total_credits = ceil(base + runtime + complexity + tool_cost + mode_cost + external_api_cost + io_cost)`

Policy notes:

- Keep coefficients in `CreditPolicyVersion`, not hardcoded.
- Enforce `min_charge_per_task >= 1`.
- Optional `max_charge_per_task` and per-mode caps.
- Store raw factors + rounded result for explainability.

Explainability payload per task:

- `policy_version`
- `raw_measurements`
- `factor_breakdown`
- `rounded_total`
- `bucket_debit_split`

## 8. Debit and Refund Algorithms

### 8.1 Debit Order

Default order:

1. `daily_refresh`
2. `monthly_plan`
3. `add_on`

Behavior:

- Consume from each bucket until charge is satisfied or all buckets are exhausted.
- If insufficient credits, return domain error (`insufficient_credits`) and do not partially debit.

### 8.2 Refund Rules

Auto-refund triggers:

- Platform error before meaningful completion.
- Tool-provider outage causing non-delivery.
- Internal timeout with no useful task output.

Manual refund flow:

- States: `pending` -> `approved` or `rejected`.
- Store reviewer identity, decision reason, and decision timestamp.

Refund posting:

- Refund to original debit buckets proportionally by historical split.
- Never exceed net debited credits for the task.

## 9. Scheduler and Time Semantics

Daily routine:

- Execute at policy-defined reset timezone (default: `Asia/Shanghai` for UTC+8 semantics).
- Expire prior daily bucket residual.
- Grant new daily bucket.

Monthly routine:

- Execute at user billing-cycle boundary (policy-defined).
- Grant monthly plan bucket.
- Expire/carry depending on policy flags.

Reconciliation routine:

- Nightly ledger replay per user.
- Emit alert on any non-zero drift.

## 10. API Contract Draft

User APIs:

- `GET /credits/balance`
- `GET /credits/ledger?from=&to=&cursor=`
- `GET /credits/tasks/{task_id}`
- `POST /credits/refunds/requests`
- `GET /credits/refunds/requests/{request_id}`

Admin APIs:

- `POST /admin/credits/adjustments`
- `POST /admin/credits/refunds/{request_id}/decision`
- `GET /admin/credits/reconciliation`
- `POST /admin/credits/policies/activate`

Compatibility note:

- Keep existing `/usage/*` APIs unchanged during credit rollout.
- Credit APIs are additive.

## 11. Frontend Plan

User-facing:

- Add credit balance card with bucket breakdown + reset countdown.
- Add ledger timeline (debits/refunds/grants/expirations).
- Add "Why this task cost X credits" drilldown panel.
- Add refund request form + status view.

Admin-facing:

- Refund queue with triage filters.
- Manual adjustment form with required reason code.
- Reconciliation dashboard with drift metrics.

## 12. Observability and Controls

Metrics:

- `pythinker_credits_debited_total`
- `pythinker_credits_refunded_total`
- `pythinker_credits_expired_total`
- `pythinker_credit_refund_requests_total`
- `pythinker_credit_reconciliation_mismatches_total`
- `pythinker_credit_policy_version_active`

Alerts:

- Reconciliation mismatch > 0.
- Refund backlog beyond SLA.
- Charge spike anomaly above rolling baseline.

Abuse controls:

- Rate limit refund requests per user.
- Require structured reason code for admin adjustments.
- Flag bursty high-cost task patterns.

## 13. Implementation Phases

### Phase 0: Design Lock and Policy Decisions
Status: In Progress

Tasks:

1. Finalize bucket semantics and expiry rules in policy schema.
2. Resolve add-on expiration decision.
3. Lock v1 coefficient set and caps.

Deliverables:

- Updated `docs/plans/CREDIT_PYTHINKER.md`
- Initial `CreditPolicyVersion` JSON shape

### Phase 1: Domain and Persistence Foundation
Status: Not Started

Tasks:

1. Add credit domain models and enums.
2. Add repository abstractions.
3. Add Beanie documents + indexes for credit collections.
4. Add migration/init script updates for new collections.

Primary targets:

- `backend/app/domain/models/` (new credit models)
- `backend/app/domain/repositories/` (credit repository interface)
- `backend/app/infrastructure/models/documents.py`
- `backend/scripts/init_mongodb.py`

### Phase 2: Debit/Refund Engines and Runtime Integration
Status: Not Started

Tasks:

1. Implement calculator/debit/refund domain services.
2. Hook debit path into task completion pipeline.
3. Hook auto-refund path into known failure paths.
4. Persist `TaskCreditUsage` explainability payload.

Primary targets:

- `backend/app/domain/services/credits/` (new package)
- `backend/app/domain/services/agent_task_runner.py`
- `backend/app/domain/services/flows/plan_act.py`
- `backend/app/application/services/usage_service.py` (integration points only)

### Phase 3: API Layer
Status: Not Started

Tasks:

1. Add user credit endpoints.
2. Add admin adjustment/refund/policy endpoints.
3. Add schema models and route registration.

Primary targets:

- `backend/app/interfaces/api/credit_routes.py` (new)
- `backend/app/interfaces/api/admin_credit_routes.py` (new)
- `backend/app/interfaces/schemas/credit.py` (new)
- `backend/app/interfaces/api/routes.py`

### Phase 4: Frontend
Status: Not Started

Tasks:

1. Add credit API client module.
2. Extend settings UI with credit balance + ledger + task explanation.
3. Add refund request UX.

Primary targets:

- `frontend/src/api/credits.ts` (new)
- `frontend/src/components/settings/UsageSettings.vue`
- `frontend/src/components/settings/UsageChart.vue` (if needed for credit mode)

### Phase 5: Schedulers, Reconciliation, and Hardening
Status: Not Started

Tasks:

1. Implement daily/monthly jobs.
2. Implement nightly reconciliation worker.
3. Add metrics/alerts/dashboards.
4. Load-test idempotency and concurrency paths.

Primary targets:

- `backend/app/application/services/credits_scheduler_service.py` (new)
- `backend/app/infrastructure/observability/prometheus_metrics.py`
- `prometheus/` and `grafana/` configs

## 14. Verification Plan

Unit tests:

- Calculator correctness by factor matrix.
- Deterministic bucket split and rounding behavior.
- Refund bounds and proportional restore.
- Policy version selection by effective time.

Integration tests:

- End-to-end task charge writes ledger + task usage record.
- Idempotent retry does not duplicate ledger events.
- Auto-refund path posts correct inverse events.
- Daily/monthly jobs behave correctly at timezone boundaries.

Property tests:

- Ledger replay equals reported balances for randomized event streams.

Repo verification commands after implementation:

- `cd frontend && bun run lint && bun run type-check`
- `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

## 15. Open Decisions

1. Add-on credit expiration policy under long inactivity.
2. Monthly rollover behavior by tier.
3. Default timezone for daily reset in self-hosted deployments.
4. Whether insufficient credits pauses task creation or allows overdraft with post-billing.

## 16. Definition of Done

1. Every charged task has an explainable, persisted credit breakdown.
2. Ledger replay reconciliation returns zero drift in steady state.
3. Refund decisions are traceable and idempotent.
4. User can view balance, ledger history, and per-task explanation in UI.
5. Admin can adjust, review refunds, and inspect reconciliation anomalies.
6. Existing `/usage/*` functionality remains backward compatible.
