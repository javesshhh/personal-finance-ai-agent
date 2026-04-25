# Phase 03 — Transaction Management

## Overview

The first full vertical slice. By the end of this phase you'll have:
- A `transactions` table in Postgres
- A CSV upload endpoint that parses bank exports and auto-categorizes with Claude
- A manual transaction entry endpoint
- MCP tools `get_spending` and `compare_months` queryable from Claude Desktop
- Tests covering the service layer

**Why first:** Transactions are the foundation of every other feature — subscriptions, health scores, and scenarios all depend on transaction data. Nothing else makes sense without them.

---

## Pros / Cons of Key Decisions

### Decision: AI categorization on upload vs. background job

| | On upload (sync) | Background job (async) |
|---|---|---|
| **Pro** | Immediate feedback; simpler flow | Faster upload response; better for large files |
| **Con** | Upload blocks until all transactions are categorized | Extra complexity; need polling or webhooks |
| **Verdict** | ✅ On upload for MVP — most CSVs are <500 rows; Claude API handles batches fast. Add async in v2 if needed. |

### Decision: Batch Claude API calls vs. one call per transaction

| | Batch (all transactions in one prompt) | Per-transaction |
|---|---|---|
| **Pro** | Much cheaper; Claude can see patterns across transactions for better categorization | Simpler prompt |
| **Con** | Long context for large files; hits token limits for 1000+ row CSVs | Very expensive; slow |
| **Verdict** | ✅ Batch in chunks of 50 — balance cost vs. context length |

### Decision: Store raw category string vs. enum

| | Enum | Raw string |
|---|---|---|
| **Pro** | Type-safe; easy to filter/aggregate | Flexible for unknown categories |
| **Con** | Must enumerate all possible values upfront | Inconsistent data over time |
| **Verdict** | ✅ Enum with a fallback `other` value — gives structure without brittleness |

---

## Checklist

### 1. Create the Transaction ORM model

- [ ] Create `app/models/transaction.py`:
  ```python
  import enum
  from datetime import date
  from decimal import Decimal

  from sqlalchemy import Date, Enum, Numeric, String, Text
  from sqlalchemy.orm import Mapped, mapped_column

  from core.database import Base


  class TransactionCategory(str, enum.Enum):
      FOOD = "food"
      TRANSPORT = "transport"
      SUBSCRIPTIONS = "subscriptions"
      UTILITIES = "utilities"
      ENTERTAINMENT = "entertainment"
      SAVINGS = "savings"
      HEALTHCARE = "healthcare"
      SHOPPING = "shopping"
      INCOME = "income"
      OTHER = "other"

      @classmethod
      def coerce(cls, value: str) -> "TransactionCategory":
          try:
              return cls(value.lower())
          except ValueError:
              return cls.OTHER


  class Transaction(Base):
      __tablename__ = "transactions"

      id: Mapped[int] = mapped_column(primary_key=True)
      date: Mapped[date] = mapped_column(Date, nullable=False)
      description: Mapped[str] = mapped_column(String(512), nullable=False)
      amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
      category: Mapped[TransactionCategory] = mapped_column(
          Enum(TransactionCategory), nullable=False, default=TransactionCategory.OTHER
      )
      notes: Mapped[str | None] = mapped_column(Text, nullable=True)
  ```
- [ ] Register the model in `app/models/__init__.py`:
  ```python
  from app.models.transaction import Transaction  # noqa: F401
  ```

---

### 2. Generate and apply the migration

- [ ] Generate migration:
  ```bash
  alembic revision --autogenerate -m "add transactions table"
  ```
- [ ] Open the generated file in `migrations/versions/` and verify it contains a `CREATE TABLE transactions` — do not apply until you've confirmed it looks correct
- [ ] Apply migration:
  ```bash
  alembic upgrade head
  ```
- [ ] Verify table exists:
  ```bash
  psql postgresql://finsight:finsight@localhost:5432/finsight \
    -c "\d transactions"
  ```

---

### 3. Create Pydantic schemas

- [ ] Create `app/schemas/transaction.py`:
  ```python
  from datetime import date
  from decimal import Decimal

  from pydantic import BaseModel, field_validator

  from app.models.transaction import TransactionCategory


  class TransactionCreate(BaseModel):
      date: date
      description: str
      amount: Decimal
      category: TransactionCategory = TransactionCategory.OTHER
      notes: str | None = None

      @field_validator("amount")
      @classmethod
      def amount_must_be_nonzero(cls, v: Decimal) -> Decimal:
          if v == 0:
              raise ValueError("Transaction amount cannot be zero")
          return v


  class TransactionRead(BaseModel):
      model_config = {"from_attributes": True}

      id: int
      date: date
      description: str
      amount: Decimal
      category: TransactionCategory
      notes: str | None


  class SpendingByCategory(BaseModel):
      category: TransactionCategory
      total: Decimal
      count: int


  class MonthComparison(BaseModel):
      category: TransactionCategory
      month_a_total: Decimal
      month_b_total: Decimal
      delta: Decimal
      delta_pct: float
  ```

---

### 4. Create the categorization service (Claude API)

- [ ] Create `app/services/categorizer.py`:
  ```python
  import json

  from anthropic import AsyncAnthropic

  from app.models.transaction import TransactionCategory
  from core.config import settings

  client = AsyncAnthropic(api_key=settings.anthropic_api_key)

  CATEGORY_LIST = ", ".join([c.value for c in TransactionCategory])

  SYSTEM_PROMPT = f"""You are a financial transaction categorizer.
  Given a list of bank transactions, assign each one a category from this list:
  {CATEGORY_LIST}

  Rules:
  - Respond ONLY with a valid JSON array of category strings, one per transaction, in the same order.
  - Use "other" if no category fits.
  - Example: ["food", "transport", "subscriptions"]
  """


  async def categorize_transactions(descriptions: list[str]) -> list[TransactionCategory]:
      """Categorize a batch of transaction descriptions using Claude.

      Args:
          descriptions: List of transaction description strings.

      Returns:
          List of TransactionCategory values in the same order as input.
      """
      CHUNK_SIZE = 50
      results: list[TransactionCategory] = []

      for i in range(0, len(descriptions), CHUNK_SIZE):
          chunk = descriptions[i : i + CHUNK_SIZE]
          user_message = json.dumps(chunk)

          response = await client.messages.create(
              model="claude-sonnet-4-6",
              max_tokens=512,
              system=SYSTEM_PROMPT,
              messages=[{"role": "user", "content": user_message}],
          )

          raw = response.content[0].text.strip()
          categories_raw: list[str] = json.loads(raw)
          results.extend([TransactionCategory.coerce(c) for c in categories_raw])

      return results
  ```

---

### 5. Create the transaction service

- [ ] Create `app/services/transaction_service.py`:
  ```python
  import csv
  import io
  from datetime import date
  from decimal import Decimal, InvalidOperation

  from sqlalchemy import extract, func, select
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.transaction import Transaction, TransactionCategory
  from app.schemas.transaction import MonthComparison, SpendingByCategory, TransactionCreate
  from app.services.categorizer import categorize_transactions


  async def create_transaction(db: AsyncSession, data: TransactionCreate) -> Transaction:
      """Persist a single transaction to the database.

      Args:
          db: Async database session.
          data: Validated transaction data.

      Returns:
          The created Transaction ORM instance.
      """
      transaction = Transaction(**data.model_dump())
      db.add(transaction)
      await db.commit()
      await db.refresh(transaction)
      return transaction


  async def import_csv(db: AsyncSession, csv_content: bytes) -> list[Transaction]:
      """Parse a bank CSV export, categorize transactions with AI, and persist them.

      Expected CSV columns (case-insensitive): date, description, amount
      Date format: YYYY-MM-DD or DD/MM/YYYY

      Args:
          db: Async database session.
          csv_content: Raw CSV file bytes.

      Returns:
          List of created Transaction ORM instances.

      Raises:
          ValueError: If CSV is missing required columns.
      """
      reader = csv.DictReader(io.StringIO(csv_content.decode("utf-8")))
      rows = list(reader)

      if not rows:
          return []

      # Normalize column names to lowercase
      normalized = [{k.lower().strip(): v.strip() for k, v in row.items()} for row in rows]
      required = {"date", "description", "amount"}
      if not required.issubset(set(normalized[0].keys())):
          raise ValueError(f"CSV must contain columns: {required}. Got: {set(normalized[0].keys())}")

      descriptions = [row["description"] for row in normalized]
      categories = await categorize_transactions(descriptions)

      transactions: list[Transaction] = []
      for row, category in zip(normalized, categories):
          try:
              amount = Decimal(row["amount"].replace(",", ""))
          except InvalidOperation as e:
              raise ValueError(f"Invalid amount '{row['amount']}' in row: {row}") from e

          transaction = Transaction(
              date=date.fromisoformat(row["date"]),
              description=row["description"],
              amount=amount,
              category=category,
          )
          db.add(transaction)
          transactions.append(transaction)

      await db.commit()
      for t in transactions:
          await db.refresh(t)
      return transactions


  async def get_spending_by_category(
      db: AsyncSession,
      start_date: date,
      end_date: date,
  ) -> list[SpendingByCategory]:
      """Aggregate spending by category within a date range.

      Args:
          db: Async database session.
          start_date: Inclusive start date.
          end_date: Inclusive end date.

      Returns:
          List of SpendingByCategory with total and count per category.
      """
      result = await db.execute(
          select(
              Transaction.category,
              func.sum(Transaction.amount).label("total"),
              func.count(Transaction.id).label("count"),
          )
          .where(Transaction.date >= start_date, Transaction.date <= end_date, Transaction.amount < 0)
          .group_by(Transaction.category)
          .order_by(func.sum(Transaction.amount))
      )
      return [
          SpendingByCategory(category=row.category, total=abs(row.total), count=row.count)
          for row in result.all()
      ]


  async def compare_months(
      db: AsyncSession,
      year_a: int,
      month_a: int,
      year_b: int,
      month_b: int,
  ) -> list[MonthComparison]:
      """Compare spending by category between two calendar months.

      Args:
          db: Async database session.
          year_a: Year of the first month.
          month_a: Month number (1-12) of the first month.
          year_b: Year of the second month.
          month_b: Month number (1-12) of the second month.

      Returns:
          List of MonthComparison with delta and delta_pct per category.
      """
      async def _get_month(year: int, month: int) -> dict[TransactionCategory, Decimal]:
          result = await db.execute(
              select(Transaction.category, func.sum(Transaction.amount).label("total"))
              .where(
                  extract("year", Transaction.date) == year,
                  extract("month", Transaction.date) == month,
                  Transaction.amount < 0,
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
  ```

---

### 6. Create API routes

- [ ] Create `api/transactions.py`:
  ```python
  from datetime import date

  from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.schemas.transaction import MonthComparison, SpendingByCategory, TransactionCreate, TransactionRead
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


  @router.post("/import-csv", response_model=list[TransactionRead], status_code=status.HTTP_201_CREATED)
  async def import_csv(
      file: UploadFile = File(...),
      db: AsyncSession = Depends(get_db),
  ) -> list[TransactionRead]:
      if not file.filename or not file.filename.endswith(".csv"):
          raise HTTPException(status_code=400, detail="File must be a .csv")
      content = await file.read()
      try:
          transactions = await transaction_service.import_csv(db, content)
      except ValueError as e:
          raise HTTPException(status_code=422, detail=str(e)) from e
      return [TransactionRead.model_validate(t) for t in transactions]


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
  ```
- [ ] Register the router in `core/app.py`:
  ```python
  from api.transactions import router as transactions_router
  app.include_router(transactions_router, prefix="/api/v1")
  ```

---

### 7. Add MCP tools `get_spending` and `compare_months`

- [ ] Create `mcp_server/tools/transactions.py`:
  ```python
  from datetime import date

  from mcp.server import Server
  from mcp.types import TextContent, Tool

  from app.services import transaction_service
  from core.database import AsyncSessionLocal

  def register_transaction_tools(server: Server) -> None:
      @server.tool()
      async def get_spending(start_date: str, end_date: str) -> list[TextContent]:
          """Get spending totals by category between two dates (YYYY-MM-DD format)."""
          async with AsyncSessionLocal() as db:
              results = await transaction_service.get_spending_by_category(
                  db,
                  date.fromisoformat(start_date),
                  date.fromisoformat(end_date),
              )
          lines = [f"{r.category.value}: ₹{r.total:,.2f} ({r.count} transactions)" for r in results]
          return [TextContent(type="text", text="\n".join(lines))]

      @server.tool()
      async def compare_months(year_a: int, month_a: int, year_b: int, month_b: int) -> list[TextContent]:
          """Compare spending by category between two months."""
          async with AsyncSessionLocal() as db:
              results = await transaction_service.compare_months(db, year_a, month_a, year_b, month_b)
          lines = [
              f"{r.category.value}: ₹{r.month_a_total:,.2f} → ₹{r.month_b_total:,.2f} "
              f"({'↑' if r.delta > 0 else '↓'} {abs(r.delta_pct):.1f}%)"
              for r in results
          ]
          return [TextContent(type="text", text="\n".join(lines))]
  ```
- [ ] Create `mcp_server/server.py` (main MCP server entry point):
  ```python
  import asyncio

  from mcp.server import Server
  from mcp.server.stdio import stdio_server

  from mcp_server.tools.transactions import register_transaction_tools

  server = Server("finsight")
  register_transaction_tools(server)


  async def main() -> None:
      async with stdio_server() as (read_stream, write_stream):
          await server.run(read_stream, write_stream, server.create_initialization_options())


  if __name__ == "__main__":
      asyncio.run(main())
  ```
- [ ] Create `mcp_server/tools/__init__.py` (empty)

---

### 8. Write tests

- [ ] Create `tests/test_transaction_service.py`:
  ```python
  from datetime import date
  from decimal import Decimal
  from unittest.mock import AsyncMock, patch

  import pytest

  from app.models.transaction import TransactionCategory
  from app.schemas.transaction import TransactionCreate


  @pytest.fixture
  def sample_csv() -> bytes:
      return b"date,description,amount\n2024-01-15,Swiggy Food Delivery,-450.00\n2024-01-16,Uber Ride,-230.00"


  @pytest.mark.asyncio
  async def test_import_csv_categorizes_and_persists(db_session, sample_csv):
      with patch(
          "app.services.transaction_service.categorize_transactions",
          new_callable=AsyncMock,
          return_value=[TransactionCategory.FOOD, TransactionCategory.TRANSPORT],
      ):
          from app.services import transaction_service
          transactions = await transaction_service.import_csv(db_session, sample_csv)

      assert len(transactions) == 2
      assert transactions[0].category == TransactionCategory.FOOD
      assert transactions[1].category == TransactionCategory.TRANSPORT
      assert transactions[0].amount == Decimal("-450.00")


  @pytest.mark.asyncio
  async def test_import_csv_missing_columns_raises(db_session):
      bad_csv = b"name,value\nSwiggy,450"
      from app.services import transaction_service
      with pytest.raises(ValueError, match="CSV must contain columns"):
          await transaction_service.import_csv(db_session, bad_csv)


  @pytest.mark.asyncio
  async def test_create_transaction(db_session):
      from app.services import transaction_service
      data = TransactionCreate(
          date=date(2024, 1, 15),
          description="Test",
          amount=Decimal("-100.00"),
          category=TransactionCategory.FOOD,
      )
      t = await transaction_service.create_transaction(db_session, data)
      assert t.id is not None
      assert t.category == TransactionCategory.FOOD
  ```
- [ ] Create `tests/conftest.py` with async DB fixtures:
  ```python
  import pytest
  import pytest_asyncio
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

  from app.models import *  # noqa: F401, F403 — registers all models with Base
  from core.database import Base

  TEST_DATABASE_URL = "postgresql+asyncpg://finsight:finsight@localhost:5432/finsight_test"


  @pytest_asyncio.fixture(scope="session")
  async def engine():
      engine = create_async_engine(TEST_DATABASE_URL)
      async with engine.begin() as conn:
          await conn.run_sync(Base.metadata.create_all)
      yield engine
      async with engine.begin() as conn:
          await conn.run_sync(Base.metadata.drop_all)
      await engine.dispose()


  @pytest_asyncio.fixture
  async def db_session(engine):
      factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
      async with factory() as session:
          yield session
          await session.rollback()
  ```
- [ ] Create a test database:
  ```bash
  psql postgresql://finsight:finsight@localhost:5432/postgres \
    -c "CREATE DATABASE finsight_test;"
  ```
- [ ] Run tests:
  ```bash
  pytest tests/test_transaction_service.py -v
  ```

---

## Verification — Phase 03 Complete

- [ ] `alembic current` shows the transactions migration applied
- [ ] `psql ... -c "\d transactions"` shows all columns including the `category` enum
- [ ] `curl -X POST http://localhost:8000/api/v1/transactions/ -H "Content-Type: application/json" -d '{"date":"2024-01-15","description":"Coffee","amount":-150.00,"category":"food"}'` → returns created transaction with `id`
- [ ] Upload a real bank CSV via Swagger UI at `http://localhost:8000/docs` → transactions appear with AI-assigned categories
- [ ] `pytest tests/test_transaction_service.py -v` → all tests pass
- [ ] `ruff check .` → no errors
- [ ] Commit:
  ```bash
  git add -A
  git commit -m "feat(transactions): add transaction model, CSV import, categorization, and MCP tools"
  ```
