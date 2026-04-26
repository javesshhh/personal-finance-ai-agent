import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.subscription import PriceChangeAlert, SubscriptionRead
from app.services import session_service, subscription_service
from core.database import get_db

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


async def _resolve_session(session_id: uuid.UUID, db: AsyncSession) -> uuid.UUID:
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session.id


@router.post("/detect", response_model=list[SubscriptionRead])
async def detect_subscriptions(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[SubscriptionRead]:
    await _resolve_session(session_id, db)
    subs = await subscription_service.detect_subscriptions(db, session_id)
    return [SubscriptionRead.model_validate(s) for s in subs]


@router.get("/", response_model=list[SubscriptionRead])
async def list_subscriptions(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[SubscriptionRead]:
    await _resolve_session(session_id, db)
    return await subscription_service.get_all_subscriptions(db, session_id)


@router.get("/price-changes", response_model=list[PriceChangeAlert])
async def price_changes(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[PriceChangeAlert]:
    await _resolve_session(session_id, db)
    return await subscription_service.get_price_changes(db, session_id)
