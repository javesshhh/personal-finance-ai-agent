import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.transaction import CSVImportResult, MonthComparison, SpendingByCategory, TransactionCreate, TransactionRead
from app.services import session_service, transaction_service
from app.services.pdf_parser import parse_pdf
from core.database import get_db

router = APIRouter(prefix="/transactions", tags=["transactions"])


async def _resolve_session(session_id: uuid.UUID, db: AsyncSession) -> uuid.UUID:
    """Validate that the session exists and return its ID."""
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session.id


@router.post("/", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TransactionRead:
    await _resolve_session(session_id, db)
    transaction = await transaction_service.create_transaction(db, session_id, data)
    return TransactionRead.model_validate(transaction)


@router.post("/import-csv", response_model=CSVImportResult, status_code=status.HTTP_201_CREATED)
async def import_csv(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> CSVImportResult:
    await _resolve_session(session_id, db)
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Uploaded file must have a .csv extension")
    content = await file.read()
    try:
        return await transaction_service.import_csv(db, session_id, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/import-pdf", response_model=CSVImportResult, status_code=status.HTTP_201_CREATED)
async def import_pdf(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> CSVImportResult:
    await _resolve_session(session_id, db)
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must have a .pdf extension")
    content = await file.read()
    try:
        parsed_rows = await parse_pdf(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rows = [(r.date, r.description, r.amount) for r in parsed_rows]
    return await transaction_service.import_rows(db, session_id, rows)


@router.get("/spending", response_model=list[SpendingByCategory])
async def get_spending(
    session_id: uuid.UUID,
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
) -> list[SpendingByCategory]:
    await _resolve_session(session_id, db)
    return await transaction_service.get_spending_by_category(db, session_id, start_date, end_date)


@router.get("/compare", response_model=list[MonthComparison])
async def compare_months(
    session_id: uuid.UUID,
    year_a: int,
    month_a: int,
    year_b: int,
    month_b: int,
    db: AsyncSession = Depends(get_db),
) -> list[MonthComparison]:
    await _resolve_session(session_id, db)
    return await transaction_service.compare_months(db, session_id, year_a, month_a, year_b, month_b)
