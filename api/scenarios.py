import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.scenario import ScenarioRequest, ScenarioResult
from app.services import scenario_service, session_service
from core.database import get_db

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.post("/run", response_model=ScenarioResult)
async def run_scenario(
    request: ScenarioRequest,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ScenarioResult:
    """Run a what-if financial scenario for a session.

    Args:
        request: Scenario parameters — spending changes, target amount and description.
        session_id: UUID of the session to use for the spending baseline.
        db: Injected database session.

    Returns:
        ScenarioResult with months to goal, projected savings, narrative, and breakdown.

    Raises:
        HTTPException 404: If the session is not found.
        HTTPException 500: If scenario simulation fails unexpectedly.
    """
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    try:
        return await scenario_service.run_scenario(db, session_id, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scenario simulation failed: {exc}") from exc
