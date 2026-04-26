import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.schemas.session import SessionCreate


async def create_session(db: AsyncSession, data: SessionCreate) -> Session:
    """Create a new named session.

    Args:
        db: Async database session.
        data: Session name.

    Returns:
        The created Session ORM instance.

    Raises:
        ValueError: If a session with the same name already exists.
    """
    existing = await db.execute(select(Session).where(Session.name == data.name))
    if existing.scalar_one_or_none():
        raise ValueError(f"Session '{data.name}' already exists.")
    session = Session(name=data.name)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(db: AsyncSession) -> list[Session]:
    """Return all sessions ordered by creation time.

    Args:
        db: Async database session.

    Returns:
        List of Session ORM instances.
    """
    result = await db.execute(select(Session).order_by(Session.created_at))
    return list(result.scalars().all())


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    """Fetch a session by ID.

    Args:
        db: Async database session.
        session_id: UUID of the session.

    Returns:
        Session if found, else None.
    """
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def get_or_create_by_name(db: AsyncSession, name: str) -> Session:
    """Fetch a session by name, creating it if it does not exist.

    Matching is case-insensitive. If no exact match is found, falls back to
    a partial match (the stored name contains the given name or vice versa).
    Only creates a new session when no existing session matches at all.

    Args:
        db: Async database session.
        name: Session name (exact, case-insensitive, or partial).

    Returns:
        Existing or newly created Session.
    """
    from sqlalchemy import func as sqlfunc

    # 1. Case-insensitive exact match
    result = await db.execute(select(Session).where(sqlfunc.lower(Session.name) == name.lower()))
    session = result.scalar_one_or_none()
    if session:
        return session

    # 2. Partial match — stored name contains the query or query contains stored name
    all_sessions = (await db.execute(select(Session))).scalars().all()
    name_lower = name.lower()
    for s in all_sessions:
        if name_lower in s.name.lower() or s.name.lower() in name_lower:
            return s

    # 3. No match — create new session with the given name
    session = Session(name=name)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def delete_session(db: AsyncSession, session_id: uuid.UUID) -> bool:
    """Delete a session and cascade-delete all its transactions.

    Args:
        db: Async database session.
        session_id: UUID of the session.

    Returns:
        True if deleted, False if not found.
    """
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return False
    await db.delete(session)
    await db.commit()
    return True
