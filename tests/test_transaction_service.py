from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.models.transaction import TransactionCategory
from app.schemas.transaction import TransactionCreate


@pytest.fixture
def sample_csv() -> bytes:
    return (
        b"date,description,amount\n"
        b"2024-01-15,Swiggy Food Delivery,-450.00\n"
        b"2024-01-16,Uber Ride,-230.00\n"
        b"2024-01-17,Netflix,-649.00\n"
    )


@pytest.mark.asyncio
async def test_create_transaction_persists(db_session):
    from app.services import transaction_service

    data = TransactionCreate(
        date=date(2024, 1, 15),
        description="Test coffee",
        amount=Decimal("-150.00"),
        category=TransactionCategory.FOOD,
    )
    t = await transaction_service.create_transaction(db_session, data)

    assert t.id is not None
    assert t.category == TransactionCategory.FOOD
    assert t.amount == Decimal("-150.00")


@pytest.mark.asyncio
async def test_create_transaction_zero_amount_rejected():
    with pytest.raises(Exception):
        TransactionCreate(
            date=date(2024, 1, 15),
            description="Zero",
            amount=Decimal("0"),
        )


@pytest.mark.asyncio
async def test_import_csv_categorizes_and_persists(db_session, sample_csv):
    from app.services import transaction_service

    with patch(
        "app.services.transaction_service.categorize_transactions",
        new_callable=AsyncMock,
        return_value=[
            TransactionCategory.FOOD,
            TransactionCategory.TRANSPORT,
            TransactionCategory.SUBSCRIPTIONS,
        ],
    ):
        transactions = await transaction_service.import_csv(db_session, sample_csv)

    assert len(transactions) == 3
    assert transactions[0].category == TransactionCategory.FOOD
    assert transactions[1].category == TransactionCategory.TRANSPORT
    assert transactions[2].category == TransactionCategory.SUBSCRIPTIONS
    assert transactions[0].amount == Decimal("-450.00")


@pytest.mark.asyncio
async def test_import_csv_missing_columns_raises(db_session):
    from app.services import transaction_service

    bad_csv = b"name,value\nSwiggy,450"
    with pytest.raises(ValueError, match="missing required columns"):
        await transaction_service.import_csv(db_session, bad_csv)


@pytest.mark.asyncio
async def test_import_csv_empty_returns_empty(db_session):
    from app.services import transaction_service

    empty_csv = b"date,description,amount\n"
    result = await transaction_service.import_csv(db_session, empty_csv)
    assert result == []


@pytest.mark.asyncio
async def test_get_spending_by_category(db_session):
    from app.services import transaction_service

    # Seed two food transactions
    data1 = TransactionCreate(date=date(2024, 2, 1), description="Swiggy", amount=Decimal("-500"), category=TransactionCategory.FOOD)
    data2 = TransactionCreate(date=date(2024, 2, 5), description="Zomato", amount=Decimal("-300"), category=TransactionCategory.FOOD)
    await transaction_service.create_transaction(db_session, data1)
    await transaction_service.create_transaction(db_session, data2)

    results = await transaction_service.get_spending_by_category(db_session, date(2024, 2, 1), date(2024, 2, 28))
    food = next((r for r in results if r.category == TransactionCategory.FOOD), None)

    assert food is not None
    assert food.total == Decimal("800")
    assert food.count == 2
