import csv
import io
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionCategory
from app.schemas.transaction import CSVImportResult, MonthComparison, SpendingByCategory, TransactionCreate
from app.services.categorizer import categorize_transactions


async def create_transaction(db: AsyncSession, session_id: uuid.UUID, data: TransactionCreate) -> Transaction:
    """Persist a single transaction to the database.

    Args:
        db: Async database session.
        session_id: UUID of the owning session.
        data: Validated transaction data.

    Returns:
        The created Transaction ORM instance.
    """
    transaction = Transaction(session_id=session_id, **data.model_dump())
    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def import_rows(
    db: AsyncSession,
    session_id: uuid.UUID,
    rows: list[tuple[date, str, Decimal]],
) -> CSVImportResult:
    """Deduplicate, AI-categorize, and persist a list of parsed transaction rows.

    Args:
        db: Async database session.
        session_id: UUID of the owning session.
        rows: List of (date, description, amount) tuples already parsed from CSV or PDF.

    Returns:
        CSVImportResult with imported count, skipped count, and transaction list.
    """
    # Filter rows that already exist in this session
    new_rows: list[tuple[date, str, Decimal]] = []
    for txn_date, description, amount in rows:
        existing = await db.execute(
            select(Transaction.id).where(
                Transaction.session_id == session_id,
                Transaction.date == txn_date,
                Transaction.description == description,
                Transaction.amount == amount,
            )
        )
        if existing.scalar_one_or_none() is None:
            new_rows.append((txn_date, description, amount))

    skipped = len(rows) - len(new_rows)

    if not new_rows:
        return CSVImportResult(imported=0, skipped_duplicates=skipped, transactions=[])

    descriptions = [desc for _, desc, _ in new_rows]
    categories = await categorize_transactions(descriptions)

    transactions: list[Transaction] = []
    for (txn_date, description, amount), category in zip(new_rows, categories):
        transaction = Transaction(
            session_id=session_id,
            date=txn_date,
            description=description,
            amount=amount,
            category=category,
        )
        db.add(transaction)
        transactions.append(transaction)

    await db.commit()
    for t in transactions:
        await db.refresh(t)
    return CSVImportResult(imported=len(transactions), skipped_duplicates=skipped, transactions=transactions)


async def import_csv(db: AsyncSession, session_id: uuid.UUID, csv_content: bytes) -> CSVImportResult:
    """Parse a bank CSV export and import rows into the given session.

    Expected CSV columns (case-insensitive): date, description, amount.
    Date must be ISO format (YYYY-MM-DD). Duplicate rows are skipped.

    Args:
        db: Async database session.
        session_id: UUID of the owning session.
        csv_content: Raw CSV file bytes.

    Returns:
        CSVImportResult with imported count, skipped count, and transaction list.

    Raises:
        ValueError: If CSV is missing required columns or contains unparseable amounts.
    """
    reader = csv.DictReader(io.StringIO(csv_content.decode("utf-8")))
    rows = list(reader)

    if not rows:
        return CSVImportResult(imported=0, skipped_duplicates=0, transactions=[])

    normalized = [{k.lower().strip(): v.strip() for k, v in row.items()} for row in rows]
    required = {"date", "description", "amount"}
    missing = required - set(normalized[0].keys())
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}. Got: {set(normalized[0].keys())}")

    parsed: list[tuple[date, str, Decimal]] = []
    for row in normalized:
        try:
            amount = Decimal(row["amount"].replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid amount '{row['amount']}' in row: {row}") from exc
        parsed.append((date.fromisoformat(row["date"]), row["description"], amount))

    return await import_rows(db, session_id, parsed)


async def get_spending_by_category(
    db: AsyncSession,
    session_id: uuid.UUID | None,
    start_date: date,
    end_date: date,
) -> list[SpendingByCategory]:
    """Aggregate spending by category within a date range.

    Args:
        db: Async database session.
        session_id: UUID of the session to query, or None to aggregate across all sessions.
        start_date: Inclusive start date.
        end_date: Inclusive end date.

    Returns:
        List of SpendingByCategory sorted by total spend descending.
    """
    filters = [
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.category != TransactionCategory.SAVINGS,
    ]
    if session_id is not None:
        filters.append(Transaction.session_id == session_id)

    result = await db.execute(
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .where(*filters)
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
    )
    return [
        SpendingByCategory(category=row.category, total=abs(row.total), count=row.count)
        for row in result.all()
    ]


async def compare_months(
    db: AsyncSession,
    session_id: uuid.UUID,
    year_a: int,
    month_a: int,
    year_b: int,
    month_b: int,
) -> list[MonthComparison]:
    """Compare spending by category between two calendar months for a session.

    Args:
        db: Async database session.
        session_id: UUID of the session to query.
        year_a: Year of the first month.
        month_a: Month number (1-12) of the first month.
        year_b: Year of the second month.
        month_b: Month number (1-12) of the second month.

    Returns:
        List of MonthComparison sorted by absolute delta descending.
    """

    async def _get_month(year: int, month: int) -> dict[TransactionCategory, Decimal]:
        result = await db.execute(
            select(Transaction.category, func.sum(Transaction.amount).label("total"))
            .where(
                Transaction.session_id == session_id,
                extract("year", Transaction.date) == year,
                extract("month", Transaction.date) == month,
                Transaction.category != TransactionCategory.SAVINGS,
            )
            .group_by(Transaction.category)
        )
        return {row.category: abs(row.total) for row in result.all()}

    month_a_data = await _get_month(year_a, month_a)
    month_b_data = await _get_month(year_b, month_b)

    all_categories = set(month_a_data.keys()) | set(month_b_data.keys())
    comparisons: list[MonthComparison] = []

    for category in all_categories:
        a_total = month_a_data.get(category, Decimal("0"))
        b_total = month_b_data.get(category, Decimal("0"))
        delta = b_total - a_total
        delta_pct = float(delta / a_total * 100) if a_total != 0 else 0.0
        comparisons.append(
            MonthComparison(
                category=category,
                month_a_total=a_total,
                month_b_total=b_total,
                delta=delta,
                delta_pct=round(delta_pct, 2),
            )
        )

    return sorted(comparisons, key=lambda x: abs(x.delta), reverse=True)
