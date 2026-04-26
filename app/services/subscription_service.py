import json
import logging
import re
import uuid
from collections import defaultdict

from anthropic import AsyncAnthropic, BadRequestError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription
from app.models.transaction import Transaction, TransactionCategory
from app.schemas.subscription import PriceChangeAlert, SubscriptionRead
from core.config import settings

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=settings.anthropic_api_key)

SUBSCRIPTION_KEYWORDS = [
    "netflix", "spotify", "amazon prime", "hotstar", "disney", "youtube premium",
    "apple music", "apple one", "icloud", "google one", "microsoft 365",
    "adobe", "notion", "github", "slack", "zoom", "figma", "dropbox",
    "swiggy one", "zomato pro", "jio", "airtel", "vodafone", "vi ",
    "prime video", "zee5", "sonyliv", "mxplayer", "bookmyshow",
    "gym", "cult.fit", "healthify",
]


def _normalize(description: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", description.lower())).strip()


def _find_pattern(normalized: str) -> str | None:
    """Return the matched keyword if the description contains a known subscription."""
    for keyword in SUBSCRIPTION_KEYWORDS:
        if keyword in normalized:
            return keyword
    return None


async def detect_subscriptions(db: AsyncSession, session_id: uuid.UUID) -> list[Subscription]:
    """Scan transactions for the given session and upsert detected subscriptions.

    Groups transactions by subscription keyword. Only records with 2+ occurrences
    are treated as recurring. Waste scoring is attempted via Claude API, falls back
    to neutral scores on failure.

    Args:
        db: Async database session.
        session_id: UUID of the session to scan.

    Returns:
        List of upserted Subscription ORM instances.
    """
    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.session_id == session_id,
            Transaction.category == TransactionCategory.SUBSCRIPTIONS,
        )
        .order_by(Transaction.date)
    )
    transactions = result.scalars().all()

    grouped: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        pattern = _find_pattern(_normalize(t.description))
        if pattern:
            grouped[pattern].append(t)

    upserted: list[Subscription] = []

    for pattern, txns in grouped.items():
        if len(txns) < 2:
            continue

        sorted_txns = sorted(txns, key=lambda t: t.date)
        latest = sorted_txns[-1]
        previous = sorted_txns[-2]

        gaps = [(sorted_txns[i].date - sorted_txns[i - 1].date).days for i in range(1, len(sorted_txns))]
        avg_gap = int(sum(gaps) / len(gaps))

        existing = await db.execute(
            select(Subscription).where(
                Subscription.session_id == session_id,
                Subscription.normalized_pattern == pattern,
            )
        )
        sub = existing.scalar_one_or_none()

        if sub:
            sub.previous_amount = sub.latest_amount
            sub.latest_amount = latest.amount
            sub.last_charged = latest.date
            sub.frequency_days = avg_gap
            sub.is_active = True
        else:
            sub = Subscription(
                session_id=session_id,
                name=pattern.title(),
                normalized_pattern=pattern,
                latest_amount=latest.amount,
                previous_amount=previous.amount,
                last_charged=latest.date,
                frequency_days=avg_gap,
            )
            db.add(sub)

        upserted.append(sub)

    await db.commit()
    for s in upserted:
        await db.refresh(s)

    await _score_waste(db, upserted)
    return upserted


async def _score_waste(db: AsyncSession, subscriptions: list[Subscription]) -> None:
    """Use Claude to assign waste scores (0-100) to subscriptions.

    0 = essential, 100 = likely forgotten or wasteful.
    Falls back gracefully when Claude API is unavailable.

    Args:
        db: Async database session.
        subscriptions: Subscription instances to score.
    """
    if not subscriptions:
        return

    sub_list = "\n".join(
        [f"- {s.name}: ₹{s.latest_amount} every ~{s.frequency_days} days" for s in subscriptions]
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=(
                "You are a personal finance advisor scoring subscription waste for an Indian user. "
                "For each subscription return a JSON array with objects: name, score (0-100), reason (one sentence). "
                "0 = essential/high-value, 100 = likely forgotten or wasteful."
            ),
            messages=[{"role": "user", "content": sub_list}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        scores: list[dict] = json.loads(raw)
        score_map = {s["name"].lower(): s for s in scores}

        for sub in subscriptions:
            entry = score_map.get(sub.name.lower())
            if entry:
                sub.waste_score = entry["score"]
                sub.waste_reason = entry["reason"]
    except (BadRequestError, Exception) as exc:
        logger.warning("Waste scoring via Claude failed (%s), skipping scores.", exc)

    await db.commit()


async def get_all_subscriptions(db: AsyncSession, session_id: uuid.UUID) -> list[SubscriptionRead]:
    """Fetch all active subscriptions for a session, ordered by waste score descending.

    Args:
        db: Async database session.
        session_id: UUID of the session to query.

    Returns:
        List of SubscriptionRead schemas.
    """
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.session_id == session_id,
            Subscription.is_active == True,  # noqa: E712
        )
        .order_by(Subscription.waste_score.desc().nulls_last())
    )
    return [SubscriptionRead.model_validate(s) for s in result.scalars().all()]


async def get_price_changes(db: AsyncSession, session_id: uuid.UUID) -> list[PriceChangeAlert]:
    """Return subscriptions where the price increased since last detection.

    Args:
        db: Async database session.
        session_id: UUID of the session to query.

    Returns:
        List of PriceChangeAlert for subscriptions with price increases.
    """
    result = await db.execute(
        select(Subscription).where(
            Subscription.session_id == session_id,
            Subscription.previous_amount.is_not(None),
            Subscription.latest_amount > Subscription.previous_amount,
        )
    )
    return [
        PriceChangeAlert(
            name=s.name,
            previous_amount=s.previous_amount,
            latest_amount=s.latest_amount,
            change_pct=round(float((s.latest_amount - s.previous_amount) / s.previous_amount * 100), 2),
        )
        for s in result.scalars().all()
    ]
