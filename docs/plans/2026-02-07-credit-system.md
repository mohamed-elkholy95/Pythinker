# Credit Point System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace raw token/cost display with a human-friendly "credit" abstraction that lets normal users understand usage without knowing what tokens are — inspired by Manus's credit system.

**Architecture:** A credit is a normalized unit derived from underlying USD costs. The conversion formula `credits = cost_usd × CREDITS_PER_DOLLAR` (default: 1000 credits per $1) runs server-side in a new `CreditService` that wraps the existing `UsageService`. Users see credits everywhere the UI currently shows tokens/dollars. The existing token-level tracking remains untouched for admin/developer use — credits are a **view layer** on top. User plans define monthly credit allocations and the system enforces limits per-user (not just per-session).

**Tech Stack:** Python/Pydantic (domain models), MongoDB/Beanie (documents), FastAPI (routes), Vue 3/TypeScript (frontend), existing UsageService + pricing infrastructure.

---

## Phase 1: Backend Domain — Credit Models & User Plans

### Task 1: Add CreditPlan and UserCredit domain models

**Files:**
- Create: `backend/app/domain/models/credit.py`
- Test: `backend/tests/domain/models/test_credit.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/models/test_credit.py
"""Tests for credit system domain models."""

import pytest
from datetime import UTC, datetime

from app.domain.models.credit import (
    CreditPlan,
    CreditTier,
    UserCredit,
    CreditTransaction,
    TransactionType,
    credit_from_cost,
    cost_from_credit,
    CREDITS_PER_DOLLAR,
)


class TestCreditConversion:
    """Test credit <-> cost conversion functions."""

    def test_credit_from_cost_basic(self):
        """$1 = 1000 credits by default."""
        assert credit_from_cost(1.0) == 1000.0

    def test_credit_from_cost_zero(self):
        assert credit_from_cost(0.0) == 0.0

    def test_credit_from_cost_small(self):
        """$0.001 = 1 credit."""
        assert credit_from_cost(0.001) == 1.0

    def test_cost_from_credit_basic(self):
        """1000 credits = $1."""
        assert cost_from_credit(1000.0) == 1.0

    def test_cost_from_credit_roundtrip(self):
        """Roundtrip conversion preserves value."""
        original = 42.5
        assert cost_from_credit(credit_from_cost(original)) == pytest.approx(original)


class TestCreditTier:
    """Test CreditTier enum."""

    def test_tier_values(self):
        assert CreditTier.FREE == "free"
        assert CreditTier.PRO == "pro"
        assert CreditTier.TEAM == "team"


class TestCreditPlan:
    """Test CreditPlan model."""

    def test_free_plan_defaults(self):
        plan = CreditPlan(
            id="free",
            name="Free",
            tier=CreditTier.FREE,
            monthly_credits=500,
            description="Free tier with limited credits",
        )
        assert plan.monthly_credits == 500
        assert plan.tier == CreditTier.FREE
        assert plan.is_active is True

    def test_pro_plan(self):
        plan = CreditPlan(
            id="pro",
            name="Pro",
            tier=CreditTier.PRO,
            monthly_credits=50000,
            max_credits_per_session=5000,
            description="Pro tier for power users",
        )
        assert plan.monthly_credits == 50000
        assert plan.max_credits_per_session == 5000


class TestUserCredit:
    """Test UserCredit model."""

    def test_default_balance(self):
        uc = UserCredit(user_id="u1", plan_id="free", monthly_allowance=500)
        assert uc.balance == 0.0
        assert uc.used_this_month == 0.0

    def test_has_sufficient_balance(self):
        uc = UserCredit(user_id="u1", plan_id="free", monthly_allowance=500, balance=100.0)
        assert uc.has_sufficient(50.0) is True
        assert uc.has_sufficient(100.0) is True
        assert uc.has_sufficient(101.0) is False

    def test_deduct(self):
        uc = UserCredit(user_id="u1", plan_id="free", monthly_allowance=500, balance=100.0)
        uc.deduct(30.0)
        assert uc.balance == 70.0
        assert uc.used_this_month == 30.0

    def test_deduct_insufficient_raises(self):
        uc = UserCredit(user_id="u1", plan_id="free", monthly_allowance=500, balance=10.0)
        with pytest.raises(ValueError, match="Insufficient"):
            uc.deduct(20.0)

    def test_reset_monthly(self):
        uc = UserCredit(
            user_id="u1", plan_id="free", monthly_allowance=500,
            balance=50.0, used_this_month=450.0,
        )
        uc.reset_monthly()
        assert uc.balance == 500.0
        assert uc.used_this_month == 0.0


class TestCreditTransaction:
    """Test CreditTransaction model."""

    def test_deduction_transaction(self):
        tx = CreditTransaction(
            user_id="u1",
            session_id="s1",
            amount=-5.0,
            type=TransactionType.USAGE,
            description="LLM call: claude-3-5-sonnet",
            balance_after=95.0,
        )
        assert tx.amount == -5.0
        assert tx.type == TransactionType.USAGE

    def test_refund_transaction(self):
        tx = CreditTransaction(
            user_id="u1",
            session_id="s1",
            amount=5.0,
            type=TransactionType.REFUND,
            description="Task failed — credits refunded",
            balance_after=100.0,
        )
        assert tx.amount == 5.0
        assert tx.type == TransactionType.REFUND

    def test_monthly_grant_transaction(self):
        tx = CreditTransaction(
            user_id="u1",
            amount=500.0,
            type=TransactionType.MONTHLY_GRANT,
            description="Monthly credit grant — Free plan",
            balance_after=500.0,
        )
        assert tx.type == TransactionType.MONTHLY_GRANT
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/panda/Desktop/Projects/pyth-main && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/domain/models/test_credit.py -v --no-header -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.models.credit'`

**Step 3: Write minimal implementation**

```python
# backend/app/domain/models/credit.py
"""Credit system domain models.

Credits are a user-friendly abstraction over raw USD costs.
Conversion: 1 credit = $0.001 (i.e., 1000 credits = $1.00).

This provides a simpler mental model for users:
- "This task used 12 credits" vs "$0.012"
- "You have 450 credits remaining" vs "$0.45 remaining"
"""

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

# ── Conversion constants ──────────────────────────────────────────────

CREDITS_PER_DOLLAR: float = 1000.0  # 1 credit = $0.001


def credit_from_cost(cost_usd: float) -> float:
    """Convert USD cost to credits."""
    return round(cost_usd * CREDITS_PER_DOLLAR, 2)


def cost_from_credit(credits: float) -> float:
    """Convert credits to USD cost."""
    return credits / CREDITS_PER_DOLLAR


# ── Enums ─────────────────────────────────────────────────────────────

class CreditTier(str, Enum):
    """Subscription tier levels."""

    FREE = "free"
    PRO = "pro"
    TEAM = "team"


class TransactionType(str, Enum):
    """Types of credit transactions."""

    USAGE = "usage"  # Normal consumption from LLM/tool usage
    MONTHLY_GRANT = "monthly_grant"  # Monthly credit allocation
    REFUND = "refund"  # Refund for failed tasks
    BONUS = "bonus"  # Promotional or one-time bonus
    ADJUSTMENT = "adjustment"  # Manual admin adjustment


# ── Models ────────────────────────────────────────────────────────────

class CreditPlan(BaseModel):
    """A credit plan defining monthly allocation and limits.

    Plans are system-defined (seeded), not user-created.
    """

    id: str
    name: str
    tier: CreditTier
    monthly_credits: float  # Credits granted per month
    max_credits_per_session: float | None = None  # Per-session cap
    description: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserCredit(BaseModel):
    """Per-user credit balance and usage tracking.

    One UserCredit per user. Updated atomically on every usage event.
    """

    user_id: str
    plan_id: str  # References CreditPlan.id
    monthly_allowance: float  # Snapshot of plan's monthly_credits at grant time
    balance: float = 0.0  # Current available credits
    used_this_month: float = 0.0  # Credits consumed in current billing period
    billing_cycle_start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def has_sufficient(self, amount: float) -> bool:
        """Check if user has enough credits for an operation."""
        return self.balance >= amount

    def deduct(self, amount: float) -> None:
        """Deduct credits from balance.

        Raises:
            ValueError: If insufficient balance.
        """
        if not self.has_sufficient(amount):
            raise ValueError(
                f"Insufficient credits: need {amount:.1f}, have {self.balance:.1f}"
            )
        self.balance -= amount
        self.used_this_month += amount
        self.updated_at = datetime.now(UTC)

    def add(self, amount: float) -> None:
        """Add credits to balance (refund, bonus, grant)."""
        self.balance += amount
        self.updated_at = datetime.now(UTC)

    def reset_monthly(self) -> None:
        """Reset balance to monthly allowance at start of billing cycle."""
        self.balance = self.monthly_allowance
        self.used_this_month = 0.0
        self.billing_cycle_start = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)


class CreditTransaction(BaseModel):
    """Immutable ledger entry for credit changes.

    Every credit change (usage, grant, refund) creates a transaction.
    This provides a full audit trail.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str
    session_id: str | None = None  # None for grants/adjustments
    amount: float  # Positive = credit added, negative = credit consumed
    type: TransactionType
    description: str = ""
    balance_after: float  # Balance after this transaction
    metadata: dict = Field(default_factory=dict)  # model, tokens, etc.
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/panda/Desktop/Projects/pyth-main && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/domain/models/test_credit.py -v --no-header -q`
Expected: All 14 tests PASS

**Step 5: Commit**

```bash
git add backend/app/domain/models/credit.py backend/tests/domain/models/test_credit.py
git commit -m "feat(credit): add credit system domain models — CreditPlan, UserCredit, CreditTransaction"
```

---

### Task 2: Add credit plan seeds

**Files:**
- Create: `backend/app/infrastructure/seeds/credit_plans_seed.py`
- Modify: `backend/app/main.py` (register seed)

**Step 1: Write the seed file**

```python
# backend/app/infrastructure/seeds/credit_plans_seed.py
"""Seed data for credit plans.

Defines the available credit tiers. Run on startup to ensure plans exist.
"""

import logging

from app.domain.models.credit import CreditPlan, CreditTier

logger = logging.getLogger(__name__)

# ── Plan definitions ──────────────────────────────────────────────────

CREDIT_PLANS: list[CreditPlan] = [
    CreditPlan(
        id="free",
        name="Free",
        tier=CreditTier.FREE,
        monthly_credits=500,
        max_credits_per_session=100,
        description="Get started with 500 credits per month",
    ),
    CreditPlan(
        id="pro",
        name="Pro",
        tier=CreditTier.PRO,
        monthly_credits=50_000,
        max_credits_per_session=5_000,
        description="50K credits per month for power users",
    ),
    CreditPlan(
        id="team",
        name="Team",
        tier=CreditTier.TEAM,
        monthly_credits=200_000,
        max_credits_per_session=20_000,
        description="200K credits per month for teams",
    ),
]


async def seed_credit_plans() -> None:
    """Seed credit plans into the database.

    Uses upsert to avoid duplicates on repeated startup.
    """
    from app.infrastructure.models.documents import CreditPlanDocument

    for plan in CREDIT_PLANS:
        existing = await CreditPlanDocument.find_one(
            CreditPlanDocument.plan_id == plan.id
        )
        if not existing:
            doc = CreditPlanDocument.from_domain(plan)
            await doc.save()
            logger.info(f"Seeded credit plan: {plan.name} ({plan.monthly_credits} credits/mo)")
        else:
            logger.debug(f"Credit plan already exists: {plan.name}")
```

**Step 2: Register seed in main.py** — add `await seed_credit_plans()` after existing seed calls in the startup event handler.

Look at `backend/app/main.py` for the startup function and add the import + call alongside existing seeds (e.g., `seed_connectors`).

**Step 3: Commit**

```bash
git add backend/app/infrastructure/seeds/credit_plans_seed.py backend/app/main.py
git commit -m "feat(credit): add credit plan seed data — free/pro/team tiers"
```

---

## Phase 2: Backend Infrastructure — MongoDB Documents

### Task 3: Add CreditPlanDocument, UserCreditDocument, CreditTransactionDocument

**Files:**
- Modify: `backend/app/infrastructure/models/documents.py` (add 3 new document classes)
- Modify: `backend/app/main.py` (register documents with Beanie)

**Step 1: Add document classes to documents.py**

Add these after the existing `DailyUsageDocument` class:

```python
class CreditPlanDocument(BaseDocument["CreditPlan"], id_field="plan_id", domain_model_class="CreditPlan"):
    """MongoDB document for credit plans."""

    plan_id: str
    name: str
    tier: str  # CreditTier value
    monthly_credits: float
    max_credits_per_session: float | None = None
    description: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "credit_plans"
        indexes: ClassVar[list[Any]] = [
            "plan_id",
            "tier",
        ]


class UserCreditDocument(BaseDocument["UserCredit"], id_field="user_id", domain_model_class="UserCredit"):
    """MongoDB document for per-user credit balance.

    One document per user. Updated atomically via $inc/$set.
    """

    user_id: str
    plan_id: str
    monthly_allowance: float
    balance: float = 0.0
    used_this_month: float = 0.0
    billing_cycle_start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "user_credits"
        indexes: ClassVar[list[Any]] = [
            "user_id",
            "plan_id",
        ]


class CreditTransactionDocument(BaseDocument["CreditTransaction"], id_field="transaction_id", domain_model_class="CreditTransaction"):
    """MongoDB document for credit transaction ledger.

    Immutable — transactions are never updated or deleted.
    """

    transaction_id: str
    user_id: str
    session_id: str | None = None
    amount: float
    type: str  # TransactionType value
    description: str = ""
    balance_after: float
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "credit_transactions"
        indexes: ClassVar[list[Any]] = [
            "transaction_id",
            "user_id",
            IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("session_id", ASCENDING)]),
        ]
```

**Step 2: Register documents in main.py Beanie init**

Add `CreditPlanDocument`, `UserCreditDocument`, `CreditTransactionDocument` to the `document_models` list in the Beanie initialization call.

**Step 3: Implement `from_domain` / `to_domain` methods**

Follow the existing `BaseDocument` pattern used by `UsageDocument` and `DailyUsageDocument`. Map domain model fields 1:1 to document fields.

**Step 4: Commit**

```bash
git add backend/app/infrastructure/models/documents.py backend/app/main.py
git commit -m "feat(credit): add MongoDB documents — CreditPlanDocument, UserCreditDocument, CreditTransactionDocument"
```

---

## Phase 3: Backend Application — CreditService

### Task 4: Create CreditService with core operations

**Files:**
- Create: `backend/app/application/services/credit_service.py`
- Test: `backend/tests/application/services/test_credit_service.py`

**Step 1: Write failing tests**

```python
# backend/tests/application/services/test_credit_service.py
"""Tests for CreditService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import UTC, datetime

from app.domain.models.credit import (
    CreditPlan,
    CreditTier,
    TransactionType,
    credit_from_cost,
)


class TestCreditFromCostIntegration:
    """Test cost-to-credit conversion at service level."""

    def test_small_llm_call(self):
        """A $0.005 LLM call = 5 credits."""
        assert credit_from_cost(0.005) == 5.0

    def test_expensive_llm_call(self):
        """A $0.15 LLM call = 150 credits."""
        assert credit_from_cost(0.15) == 150.0

    def test_free_model(self):
        """A $0 LLM call (local model) = 0 credits."""
        assert credit_from_cost(0.0) == 0.0


class TestCreditServiceDeductFromSession:
    """Test credit deduction flow triggered by LLM usage."""

    @pytest.mark.asyncio
    async def test_deduct_records_transaction(self):
        """Deducting credits should create a transaction."""
        from app.application.services.credit_service import CreditService

        service = CreditService()

        # Mock the DB calls
        with patch.object(service, "_get_user_credit") as mock_get, \
             patch.object(service, "_save_user_credit") as mock_save, \
             patch.object(service, "_save_transaction") as mock_tx:

            mock_get.return_value = MagicMock(
                user_id="u1",
                plan_id="free",
                balance=100.0,
                used_this_month=0.0,
                has_sufficient=lambda x: True,
            )

            result = await service.deduct_credits(
                user_id="u1",
                session_id="s1",
                amount=5.0,
                description="LLM call: claude-3-5-sonnet",
                metadata={"model": "claude-3-5-sonnet", "tokens": 1500},
            )

            assert result is True
            mock_save.assert_called_once()
            mock_tx.assert_called_once()

    @pytest.mark.asyncio
    async def test_deduct_insufficient_returns_false(self):
        """Deducting more credits than available should return False."""
        from app.application.services.credit_service import CreditService

        service = CreditService()

        with patch.object(service, "_get_user_credit") as mock_get:
            mock_get.return_value = MagicMock(
                user_id="u1",
                balance=2.0,
                has_sufficient=lambda x: x <= 2.0,
            )

            result = await service.deduct_credits(
                user_id="u1",
                session_id="s1",
                amount=10.0,
                description="LLM call",
            )

            assert result is False
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/panda/Desktop/Projects/pyth-main && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/application/services/test_credit_service.py -v --no-header -q`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/app/application/services/credit_service.py
"""Credit service — manages credit balances, deductions, and transactions.

Wraps the existing UsageService cost data and converts to credits.
This is the single entry point for all credit operations.
"""

import logging
from datetime import UTC, datetime

from app.domain.models.credit import (
    CreditTransaction,
    TransactionType,
    UserCredit,
    credit_from_cost,
)
from app.infrastructure.models.documents import (
    CreditTransactionDocument,
    UserCreditDocument,
)

logger = logging.getLogger(__name__)


class CreditService:
    """Manages user credit balances and transactions."""

    async def _get_user_credit(self, user_id: str) -> UserCreditDocument | None:
        """Get user credit document from DB."""
        return await UserCreditDocument.find_one(
            UserCreditDocument.user_id == user_id
        )

    async def _save_user_credit(self, doc: UserCreditDocument) -> None:
        """Save user credit document."""
        await doc.save()

    async def _save_transaction(self, tx: CreditTransaction) -> None:
        """Save a credit transaction to the ledger."""
        doc = CreditTransactionDocument.from_domain(tx)
        await doc.save()

    async def ensure_user_credit(self, user_id: str, plan_id: str = "free") -> UserCreditDocument:
        """Ensure a UserCredit document exists for the user.

        Creates one with the plan's monthly allowance if missing.
        Called on user registration or first usage.
        """
        doc = await self._get_user_credit(user_id)
        if doc:
            return doc

        from app.infrastructure.models.documents import CreditPlanDocument

        plan_doc = await CreditPlanDocument.find_one(
            CreditPlanDocument.plan_id == plan_id
        )
        monthly = plan_doc.monthly_credits if plan_doc else 500.0

        doc = UserCreditDocument(
            user_id=user_id,
            plan_id=plan_id,
            monthly_allowance=monthly,
            balance=monthly,
            used_this_month=0.0,
        )
        await doc.save()

        # Record the initial grant
        await self._save_transaction(CreditTransaction(
            user_id=user_id,
            amount=monthly,
            type=TransactionType.MONTHLY_GRANT,
            description=f"Initial credit grant — {plan_id} plan",
            balance_after=monthly,
        ))

        logger.info(f"Created user credit for {user_id}: {monthly} credits ({plan_id} plan)")
        return doc

    async def get_balance(self, user_id: str) -> dict:
        """Get user's current credit balance and plan info."""
        doc = await self.ensure_user_credit(user_id)
        return {
            "balance": round(doc.balance, 1),
            "used_this_month": round(doc.used_this_month, 1),
            "monthly_allowance": round(doc.monthly_allowance, 1),
            "plan_id": doc.plan_id,
            "billing_cycle_start": doc.billing_cycle_start,
        }

    async def deduct_credits(
        self,
        user_id: str,
        session_id: str,
        amount: float,
        description: str = "",
        metadata: dict | None = None,
    ) -> bool:
        """Deduct credits from user balance.

        Returns True if deduction succeeded, False if insufficient balance.
        """
        doc = await self.ensure_user_credit(user_id)

        if not doc.balance >= amount:
            logger.warning(
                f"Insufficient credits for user {user_id}: "
                f"need {amount:.1f}, have {doc.balance:.1f}"
            )
            return False

        # Atomic update
        collection = UserCreditDocument.get_motor_collection()
        await collection.find_one_and_update(
            {"user_id": user_id},
            {
                "$inc": {
                    "balance": -amount,
                    "used_this_month": amount,
                },
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )

        new_balance = doc.balance - amount

        # Record transaction
        await self._save_transaction(CreditTransaction(
            user_id=user_id,
            session_id=session_id,
            amount=-amount,
            type=TransactionType.USAGE,
            description=description,
            balance_after=new_balance,
            metadata=metadata or {},
        ))

        logger.debug(
            f"Deducted {amount:.1f} credits from user {user_id} "
            f"(balance: {new_balance:.1f})"
        )
        return True

    async def deduct_for_llm_usage(
        self,
        user_id: str,
        session_id: str,
        model: str,
        total_cost_usd: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> bool:
        """Deduct credits for an LLM call based on its USD cost.

        This is the main integration point — called after record_llm_usage().
        """
        credits = credit_from_cost(total_cost_usd)
        if credits <= 0:
            return True  # Free model, no deduction needed

        return await self.deduct_credits(
            user_id=user_id,
            session_id=session_id,
            amount=credits,
            description=f"LLM: {model}",
            metadata={
                "model": model,
                "cost_usd": total_cost_usd,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )

    async def refund_session(self, user_id: str, session_id: str) -> float:
        """Refund all credits consumed by a failed session.

        Returns the total credits refunded.
        """
        # Sum all usage transactions for this session
        docs = await CreditTransactionDocument.find(
            CreditTransactionDocument.user_id == user_id,
            CreditTransactionDocument.session_id == session_id,
            CreditTransactionDocument.type == TransactionType.USAGE.value,
        ).to_list()

        total_consumed = sum(abs(d.amount) for d in docs)
        if total_consumed <= 0:
            return 0.0

        # Add credits back
        collection = UserCreditDocument.get_motor_collection()
        result = await collection.find_one_and_update(
            {"user_id": user_id},
            {
                "$inc": {
                    "balance": total_consumed,
                    "used_this_month": -total_consumed,
                },
                "$set": {"updated_at": datetime.now(UTC)},
            },
            return_document=True,
        )

        new_balance = result["balance"] if result else 0.0

        # Record refund transaction
        await self._save_transaction(CreditTransaction(
            user_id=user_id,
            session_id=session_id,
            amount=total_consumed,
            type=TransactionType.REFUND,
            description=f"Refund for failed session {session_id}",
            balance_after=new_balance,
        ))

        logger.info(f"Refunded {total_consumed:.1f} credits to user {user_id} for session {session_id}")
        return total_consumed

    async def get_transactions(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """Get recent credit transactions for a user."""
        docs = (
            await CreditTransactionDocument.find(
                CreditTransactionDocument.user_id == user_id
            )
            .sort("-created_at")
            .limit(limit)
            .to_list()
        )

        return [
            {
                "id": d.transaction_id,
                "amount": d.amount,
                "type": d.type,
                "description": d.description,
                "balance_after": d.balance_after,
                "session_id": d.session_id,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]


# ── Singleton ─────────────────────────────────────────────────────────

_credit_service: CreditService | None = None


def get_credit_service() -> CreditService:
    """Get the global CreditService instance."""
    global _credit_service
    if _credit_service is None:
        _credit_service = CreditService()
    return _credit_service
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/panda/Desktop/Projects/pyth-main && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/application/services/test_credit_service.py -v --no-header -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/application/services/credit_service.py backend/tests/application/services/test_credit_service.py
git commit -m "feat(credit): add CreditService — deduction, refund, balance, transactions"
```

---

## Phase 4: Backend Integration — Hook into LLM Usage Recording

### Task 5: Wire CreditService into UsageService

**Files:**
- Modify: `backend/app/application/services/usage_service.py` (add credit deduction after recording)
- Test: `backend/tests/application/services/test_usage_credit_integration.py`

**Step 1: Write failing integration test**

```python
# backend/tests/application/services/test_usage_credit_integration.py
"""Test that UsageService triggers credit deduction after recording LLM usage."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestUsageCreditIntegration:
    @pytest.mark.asyncio
    async def test_record_llm_usage_deducts_credits(self):
        """Recording LLM usage should also deduct credits."""
        from app.application.services.usage_service import UsageService

        service = UsageService()

        # Mock MongoDB operations
        with patch("app.application.services.usage_service.UsageDocument") as mock_doc_cls, \
             patch("app.application.services.usage_service.DailyUsageDocument") as mock_daily_cls, \
             patch("app.application.services.usage_service.get_credit_service") as mock_get_credit:

            mock_doc = MagicMock()
            mock_doc.save = AsyncMock()
            mock_doc_cls.from_domain.return_value = mock_doc

            # Mock daily aggregate update
            mock_daily_collection = MagicMock()
            mock_daily_collection.find_one_and_update = AsyncMock()
            mock_daily_cls.get_pymongo_collection.return_value = mock_daily_collection

            # Mock credit service
            mock_credit = AsyncMock()
            mock_credit.deduct_for_llm_usage = AsyncMock(return_value=True)
            mock_get_credit.return_value = mock_credit

            await service.record_llm_usage(
                user_id="u1",
                session_id="s1",
                model="claude-3-5-sonnet-20241022",
                prompt_tokens=1000,
                completion_tokens=500,
            )

            # Credit deduction should have been called
            mock_credit.deduct_for_llm_usage.assert_called_once()
            call_args = mock_credit.deduct_for_llm_usage.call_args
            assert call_args.kwargs["user_id"] == "u1"
            assert call_args.kwargs["session_id"] == "s1"
            assert call_args.kwargs["model"] == "claude-3-5-sonnet-20241022"
```

**Step 2: Run test to verify it fails**

Expected: FAIL (credit deduction not yet integrated)

**Step 3: Modify `usage_service.py`**

Add to `record_llm_usage()` after the existing `await self._update_daily_aggregate(record)` call:

```python
# Deduct credits (non-blocking — don't fail usage recording if credit deduction fails)
try:
    from app.application.services.credit_service import get_credit_service
    credit_service = get_credit_service()
    await credit_service.deduct_for_llm_usage(
        user_id=user_id,
        session_id=session_id,
        model=model,
        total_cost_usd=total_cost,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
except Exception as e:
    logger.warning(f"Credit deduction failed (usage still recorded): {e}")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/panda/Desktop/Projects/pyth-main && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/application/services/test_usage_credit_integration.py -v --no-header -q`
Expected: PASS

**Step 5: Run full test suite to ensure no regressions**

Run: `cd /Users/panda/Desktop/Projects/pyth-main && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/ -q --timeout=30`

**Step 6: Commit**

```bash
git add backend/app/application/services/usage_service.py backend/tests/application/services/test_usage_credit_integration.py
git commit -m "feat(credit): wire credit deduction into UsageService.record_llm_usage()"
```

---

## Phase 5: Backend API — Credit Endpoints

### Task 6: Add credit API routes and schemas

**Files:**
- Create: `backend/app/interfaces/schemas/credit.py`
- Create: `backend/app/interfaces/api/credit_routes.py`
- Modify: `backend/app/interfaces/api/routes.py` (register credit routes)

**Step 1: Create response schemas**

```python
# backend/app/interfaces/schemas/credit.py
"""API schemas for credit system endpoints."""

from datetime import datetime

from pydantic import BaseModel


class CreditBalanceResponse(BaseModel):
    """User's current credit balance."""

    balance: float
    used_this_month: float
    monthly_allowance: float
    plan_id: str
    plan_name: str
    billing_cycle_start: datetime | None = None


class CreditTransactionResponse(BaseModel):
    """A single credit transaction."""

    id: str
    amount: float
    type: str
    description: str
    balance_after: float
    session_id: str | None = None
    created_at: str | None = None


class CreditTransactionListResponse(BaseModel):
    """List of credit transactions."""

    transactions: list[CreditTransactionResponse]
    total: int


class CreditPlanResponse(BaseModel):
    """A credit plan."""

    id: str
    name: str
    tier: str
    monthly_credits: float
    max_credits_per_session: float | None = None
    description: str


class CreditPlansListResponse(BaseModel):
    """List of available credit plans."""

    plans: list[CreditPlanResponse]


class CreditSummaryResponse(BaseModel):
    """Combined credit summary for dashboard display."""

    balance: float
    used_this_month: float
    monthly_allowance: float
    plan_id: str
    plan_name: str
    usage_percentage: float  # 0-100
    credits_per_dollar: float
```

**Step 2: Create routes**

```python
# backend/app/interfaces/api/credit_routes.py
"""API routes for credit system."""

import logging

from fastapi import APIRouter, Depends, Query

from app.application.services.credit_service import get_credit_service
from app.domain.models.user import User
from app.infrastructure.models.documents import CreditPlanDocument
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.credit import (
    CreditBalanceResponse,
    CreditPlanResponse,
    CreditPlansListResponse,
    CreditSummaryResponse,
    CreditTransactionListResponse,
    CreditTransactionResponse,
)
from app.domain.models.credit import CREDITS_PER_DOLLAR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/balance", response_model=APIResponse[CreditBalanceResponse])
async def get_credit_balance(
    current_user: User = Depends(get_current_user),
):
    """Get current user's credit balance and plan info."""
    credit_service = get_credit_service()
    data = await credit_service.get_balance(current_user.id)

    # Get plan name
    plan_doc = await CreditPlanDocument.find_one(
        CreditPlanDocument.plan_id == data["plan_id"]
    )
    plan_name = plan_doc.name if plan_doc else data["plan_id"].title()

    return APIResponse(
        success=True,
        data=CreditBalanceResponse(
            balance=data["balance"],
            used_this_month=data["used_this_month"],
            monthly_allowance=data["monthly_allowance"],
            plan_id=data["plan_id"],
            plan_name=plan_name,
            billing_cycle_start=data.get("billing_cycle_start"),
        ),
    )


@router.get("/summary", response_model=APIResponse[CreditSummaryResponse])
async def get_credit_summary(
    current_user: User = Depends(get_current_user),
):
    """Get credit summary for dashboard display."""
    credit_service = get_credit_service()
    data = await credit_service.get_balance(current_user.id)

    plan_doc = await CreditPlanDocument.find_one(
        CreditPlanDocument.plan_id == data["plan_id"]
    )
    plan_name = plan_doc.name if plan_doc else data["plan_id"].title()

    allowance = data["monthly_allowance"] or 1.0
    usage_pct = min(100.0, (data["used_this_month"] / allowance) * 100)

    return APIResponse(
        success=True,
        data=CreditSummaryResponse(
            balance=data["balance"],
            used_this_month=data["used_this_month"],
            monthly_allowance=data["monthly_allowance"],
            plan_id=data["plan_id"],
            plan_name=plan_name,
            usage_percentage=round(usage_pct, 1),
            credits_per_dollar=CREDITS_PER_DOLLAR,
        ),
    )


@router.get("/transactions", response_model=APIResponse[CreditTransactionListResponse])
async def get_credit_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """Get recent credit transactions."""
    credit_service = get_credit_service()
    transactions = await credit_service.get_transactions(current_user.id, limit)

    return APIResponse(
        success=True,
        data=CreditTransactionListResponse(
            transactions=[
                CreditTransactionResponse(**tx) for tx in transactions
            ],
            total=len(transactions),
        ),
    )


@router.get("/plans", response_model=APIResponse[CreditPlansListResponse])
async def get_credit_plans():
    """Get all available credit plans."""
    docs = await CreditPlanDocument.find(
        CreditPlanDocument.is_active == True  # noqa: E712
    ).to_list()

    return APIResponse(
        success=True,
        data=CreditPlansListResponse(
            plans=[
                CreditPlanResponse(
                    id=d.plan_id,
                    name=d.name,
                    tier=d.tier,
                    monthly_credits=d.monthly_credits,
                    max_credits_per_session=d.max_credits_per_session,
                    description=d.description,
                )
                for d in docs
            ]
        ),
    )
```

**Step 3: Register routes in `routes.py`**

Add `from app.interfaces.api.credit_routes import router as credit_router` and include it.

**Step 4: Commit**

```bash
git add backend/app/interfaces/schemas/credit.py backend/app/interfaces/api/credit_routes.py backend/app/interfaces/api/routes.py
git commit -m "feat(credit): add credit API endpoints — balance, summary, transactions, plans"
```

---

## Phase 6: Backend — Existing Usage Endpoints Return Credits

### Task 7: Add credit fields to existing usage API responses

**Files:**
- Modify: `backend/app/interfaces/schemas/usage.py` (add credit fields)
- Modify: `backend/app/interfaces/api/usage_routes.py` (populate credit fields)

**Step 1: Add credit fields to existing schemas**

Add to each response schema:

```python
# In TodayUsageResponse:
credits_used: float = 0.0  # Credits consumed today

# In MonthUsageResponse:
credits_used: float = 0.0  # Credits consumed this month

# In UsageSummaryResponse — add top-level credit info:
credit_balance: float = 0.0
credit_allowance: float = 0.0

# In SessionUsageResponse:
credits_consumed: float = 0.0  # Credits consumed by this session
```

**Step 2: Populate credit fields in route handlers**

In `get_usage_summary()`, call `get_credit_service().get_balance()` and include credit data:

```python
credit_service = get_credit_service()
credit_data = await credit_service.get_balance(current_user.id)
# Then populate the new fields in the response
```

Use `credit_from_cost()` to convert cost fields to credit equivalents in session and daily responses.

**Step 3: Commit**

```bash
git add backend/app/interfaces/schemas/usage.py backend/app/interfaces/api/usage_routes.py
git commit -m "feat(credit): add credit fields to existing usage API responses"
```

---

## Phase 7: Frontend — API Types & Functions

### Task 8: Add credit API client

**Files:**
- Create: `frontend/src/api/credits.ts`

**Step 1: Write the API client**

```typescript
// frontend/src/api/credits.ts
import { apiClient } from './client'

export interface CreditBalance {
  balance: number
  used_this_month: number
  monthly_allowance: number
  plan_id: string
  plan_name: string
  billing_cycle_start: string | null
}

export interface CreditSummary {
  balance: number
  used_this_month: number
  monthly_allowance: number
  plan_id: string
  plan_name: string
  usage_percentage: number
  credits_per_dollar: number
}

export interface CreditTransaction {
  id: string
  amount: number
  type: string
  description: string
  balance_after: number
  session_id: string | null
  created_at: string | null
}

export interface CreditTransactionList {
  transactions: CreditTransaction[]
  total: number
}

export interface CreditPlan {
  id: string
  name: string
  tier: string
  monthly_credits: number
  max_credits_per_session: number | null
  description: string
}

export interface CreditPlansList {
  plans: CreditPlan[]
}

export async function getCreditBalance(): Promise<CreditBalance> {
  const response = await apiClient.get<{ data: CreditBalance }>('/credits/balance')
  return response.data.data
}

export async function getCreditSummary(): Promise<CreditSummary> {
  const response = await apiClient.get<{ data: CreditSummary }>('/credits/summary')
  return response.data.data
}

export async function getCreditTransactions(limit: number = 50): Promise<CreditTransactionList> {
  const response = await apiClient.get<{ data: CreditTransactionList }>(`/credits/transactions?limit=${limit}`)
  return response.data.data
}

export async function getCreditPlans(): Promise<CreditPlansList> {
  const response = await apiClient.get<{ data: CreditPlansList }>('/credits/plans')
  return response.data.data
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/credits.ts
git commit -m "feat(credit): add frontend credit API client — balance, summary, transactions, plans"
```

---

## Phase 8: Frontend — Composable

### Task 9: Create useCredits composable

**Files:**
- Create: `frontend/src/composables/useCredits.ts`

**Step 1: Write the composable**

```typescript
// frontend/src/composables/useCredits.ts
import { ref, computed } from 'vue'
import {
  getCreditSummary,
  getCreditTransactions,
  type CreditSummary,
  type CreditTransaction,
} from '@/api/credits'

const summary = ref<CreditSummary | null>(null)
const transactions = ref<CreditTransaction[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

export function useCredits() {
  const balance = computed(() => summary.value?.balance ?? 0)
  const usedThisMonth = computed(() => summary.value?.used_this_month ?? 0)
  const monthlyAllowance = computed(() => summary.value?.monthly_allowance ?? 0)
  const usagePercentage = computed(() => summary.value?.usage_percentage ?? 0)
  const planName = computed(() => summary.value?.plan_name ?? 'Free')

  const balanceDisplay = computed(() => {
    const b = balance.value
    if (b >= 10000) return `${(b / 1000).toFixed(1)}K`
    return b.toFixed(0)
  })

  async function fetchSummary() {
    try {
      loading.value = true
      error.value = null
      summary.value = await getCreditSummary()
    } catch (e) {
      error.value = 'Failed to load credit data'
    } finally {
      loading.value = false
    }
  }

  async function fetchTransactions(limit: number = 50) {
    try {
      const result = await getCreditTransactions(limit)
      transactions.value = result.transactions
    } catch {
      // Silently fail
    }
  }

  function formatCredits(amount: number): string {
    const abs = Math.abs(amount)
    if (abs >= 10000) return `${(abs / 1000).toFixed(1)}K`
    if (abs >= 1000) return `${(abs / 1000).toFixed(1)}K`
    return abs.toFixed(0)
  }

  return {
    summary,
    transactions,
    loading,
    error,
    balance,
    usedThisMonth,
    monthlyAllowance,
    usagePercentage,
    planName,
    balanceDisplay,
    fetchSummary,
    fetchTransactions,
    formatCredits,
  }
}
```

**Step 2: Commit**

```bash
git add frontend/src/composables/useCredits.ts
git commit -m "feat(credit): add useCredits composable — global credit state management"
```

---

## Phase 9: Frontend — Redesign UsageSettings with Credit-First Display

### Task 10: Redesign UsageSettings.vue to show credits prominently

**Files:**
- Modify: `frontend/src/components/settings/UsageSettings.vue`
- Modify: `frontend/src/api/usage.ts` (add credit fields to existing types)

**Step 1: Update usage.ts types**

Add credit fields to `TodayUsage`, `MonthUsage`, `UsageSummary`:

```typescript
// Add to TodayUsage:
credits_used: number

// Add to MonthUsage:
credits_used: number

// Add to UsageSummary:
credit_balance: number
credit_allowance: number
```

**Step 2: Redesign UsageSettings.vue**

Replace the hero stats section to show **credits as the primary metric**:

- **Primary card**: "Credits Remaining" — large number with progress bar (balance / monthly_allowance)
- **Secondary card**: "Used This Month" — credits consumed with percentage
- **Activity row**: Keep LLM Calls, Tool Calls, Active Days (already good)
- **Chart**: Keep existing daily chart but add a toggle: "Credits" vs "Tokens"
- **Table**: Add credits column, keep tokens as secondary/collapsible
- **Plan badge**: Show current plan name (Free/Pro/Team) in the header

The key design principle: **credits are front and center, tokens/cost are available but secondary**. Users who want raw data can still see it.

**Step 3: Import and use the `useCredits` composable**

```typescript
import { useCredits } from '@/composables/useCredits'
const { summary: creditSummary, fetchSummary: fetchCredits, formatCredits, balance, usagePercentage, planName } = useCredits()
```

Call `fetchCredits()` alongside `fetchSummary()` in `onMounted`.

**Step 4: Commit**

```bash
git add frontend/src/components/settings/UsageSettings.vue frontend/src/api/usage.ts
git commit -m "feat(credit): redesign UsageSettings — credits-first display with progress bar"
```

---

## Phase 10: Frontend — Credit Balance in Chat UI

### Task 11: Add credit balance indicator to ChatPage

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue` (or ChatBox.vue — wherever the toolbar/status area is)

**Step 1: Add a small credit balance badge**

Display a compact credit indicator near the chat input (similar to how ConnectorButton is placed). Shows:
- Current balance (e.g., "342 credits")
- Color coding: green (>50%), yellow (20-50%), red (<20%)
- Clicking opens the Usage settings tab

This uses the existing `useCredits` composable's `balance` and `usagePercentage` computed properties.

**Step 2: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "feat(credit): add credit balance indicator to chat UI"
```

---

## Phase 11: Auto-Initialize Credits for New Users

### Task 12: Wire credit initialization into user registration

**Files:**
- Modify: `backend/app/application/services/auth_service.py` (or wherever user registration happens)

**Step 1: Find the registration flow**

Search for user creation logic (likely in auth_service.py or user_service.py).

**Step 2: Add credit initialization**

After creating a new user, call:

```python
from app.application.services.credit_service import get_credit_service
credit_service = get_credit_service()
await credit_service.ensure_user_credit(user_id=new_user.id, plan_id="free")
```

This creates the UserCredit document with the free plan's monthly allowance.

**Step 3: Commit**

```bash
git add backend/app/application/services/auth_service.py
git commit -m "feat(credit): auto-initialize credits on user registration"
```

---

## Phase 12: Monthly Credit Reset

### Task 13: Add monthly credit reset logic

**Files:**
- Add method to: `backend/app/application/services/credit_service.py`

**Step 1: Add reset method to CreditService**

```python
async def reset_monthly_credits(self) -> int:
    """Reset all users' monthly credits.

    Should be called by a cron job or scheduler at billing cycle start.
    Returns the number of users reset.
    """
    docs = await UserCreditDocument.find_all().to_list()
    count = 0

    for doc in docs:
        plan_doc = await CreditPlanDocument.find_one(
            CreditPlanDocument.plan_id == doc.plan_id
        )
        monthly = plan_doc.monthly_credits if plan_doc else doc.monthly_allowance

        old_balance = doc.balance
        collection = UserCreditDocument.get_motor_collection()
        await collection.find_one_and_update(
            {"user_id": doc.user_id},
            {
                "$set": {
                    "balance": monthly,
                    "used_this_month": 0.0,
                    "monthly_allowance": monthly,
                    "billing_cycle_start": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            },
        )

        await self._save_transaction(CreditTransaction(
            user_id=doc.user_id,
            amount=monthly,
            type=TransactionType.MONTHLY_GRANT,
            description=f"Monthly credit reset — {doc.plan_id} plan",
            balance_after=monthly,
        ))

        count += 1
        logger.info(f"Reset credits for user {doc.user_id}: {old_balance:.0f} → {monthly:.0f}")

    return count
```

**Step 2: Add admin endpoint (optional)**

```python
# In credit_routes.py
@router.post("/admin/reset-monthly")
async def admin_reset_monthly_credits(
    current_user: User = Depends(get_current_user),
):
    """Admin-only: trigger monthly credit reset."""
    if current_user.role != "admin":
        return APIResponse(success=False, error="Admin access required")

    credit_service = get_credit_service()
    count = await credit_service.reset_monthly_credits()
    return APIResponse(success=True, data={"users_reset": count})
```

**Step 3: Commit**

```bash
git add backend/app/application/services/credit_service.py backend/app/interfaces/api/credit_routes.py
git commit -m "feat(credit): add monthly credit reset logic + admin endpoint"
```

---

## Phase 13: Session-Level Credit Enforcement

### Task 14: Add per-session credit limit check in agent execution

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py` (check credit balance before/during execution)

**Step 1: Add credit check before LLM calls**

In the agent execution flow (where `_usage_context` is set up), add a credit balance check:

```python
# Before starting execution, verify user has credits
credit_service = get_credit_service()
balance_data = await credit_service.get_balance(self._user_id)
if balance_data["balance"] <= 0:
    # Emit a budget exhausted event and stop execution
    await self._emit_event(BudgetEvent(
        action="exhausted",
        budget_limit=balance_data["monthly_allowance"],
        consumed=balance_data["used_this_month"],
        remaining=0,
        percentage_used=100.0,
        session_paused=True,
    ))
    return  # Don't execute
```

This hooks into the existing `BudgetEvent` SSE mechanism so the frontend already knows how to handle it.

**Step 2: Commit**

```bash
git add backend/app/domain/services/agent_task_runner.py
git commit -m "feat(credit): enforce credit balance check before agent execution"
```

---

## Phase 14: Lint, Type-Check, Full Test Suite

### Task 15: Final validation

**Step 1: Backend lint**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/backend && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && ruff check . && ruff format --check .`

Fix any issues.

**Step 2: Frontend type-check and lint**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/frontend && bun run type-check && bun run lint`

Fix any issues.

**Step 3: Full test suite**

Run: `cd /Users/panda/Desktop/Projects/pyth-main && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/ -q --timeout=30`

All existing + new tests should pass.

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore(credit): lint fixes and type corrections"
```

---

## Summary

| Phase | What | Files | Tests |
|-------|------|-------|-------|
| 1 | Domain models (CreditPlan, UserCredit, CreditTransaction) | 1 new | 14 |
| 2 | Seed data (free/pro/team plans) | 1 new, 1 modified | 0 |
| 3 | MongoDB documents (3 collections) | 1 modified | 0 |
| 4 | CreditService (deduct, refund, balance, transactions) | 1 new | 5 |
| 5 | Wire into UsageService.record_llm_usage() | 1 modified | 1 |
| 6 | Credit API routes (balance, summary, transactions, plans) | 2 new, 1 modified | 0 |
| 7 | Add credit fields to existing usage responses | 2 modified | 0 |
| 8 | Frontend API client (credits.ts) | 1 new | 0 |
| 9 | useCredits composable | 1 new | 0 |
| 10 | Redesign UsageSettings.vue (credits-first) | 2 modified | 0 |
| 11 | Credit balance indicator in chat UI | 1 modified | 0 |
| 12 | User registration → credit init | 1 modified | 0 |
| 13 | Monthly credit reset + admin endpoint | 2 modified | 0 |
| 14 | Session-level credit enforcement | 1 modified | 0 |
| 15 | Lint, type-check, full test suite | — | — |

**New files:** 6 backend, 2 frontend = **8 total**
**Modified files:** ~10
**Total tests added:** ~20
