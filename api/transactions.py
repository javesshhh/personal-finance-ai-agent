from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.transaction import CSVImportResult, MonthComparison, SpendingByCategory, TransactionCreate, TransactionRead
from app.services import transaction_service
from core.database import get_db

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    db: AsyncSession = Depends(get_db),
) -> TransactionRead:
    transaction = await transaction_service.create_transaction(db, data)
    return TransactionRead.model_validate(transaction)


@router.post("/import-csv", response_model=CSVImportResult, status_code=status.HTTP_201_CREATED)
async def import_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> CSVImportResult:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Uploaded file must have a .csv extension")
    content = await file.read()
    try:
        return await transaction_service.import_csv(db, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/spending", response_model=list[SpendingByCategory])
async def get_spending(
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
) -> list[SpendingByCategory]:
    return await transaction_service.get_spending_by_category(db, start_date, end_date)


@router.get("/compare", response_model=list[MonthComparison])
async def compare_months(
    year_a: int,
    month_a: int,
    year_b: int,
    month_b: int,
    db: AsyncSession = Depends(get_db),
) -> list[MonthComparison]:
    return await transaction_service.compare_months(db, year_a, month_a, year_b, month_b)
