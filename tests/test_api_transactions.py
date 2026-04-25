import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_transaction_success(client):
    response = await client.post(
        "/api/v1/transactions/",
        json={"date": "2024-03-01", "description": "Coffee shop", "amount": -120.0, "category": "food"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["category"] == "food"
    assert data["description"] == "Coffee shop"


@pytest.mark.asyncio
async def test_create_transaction_zero_amount_rejected(client):
    response = await client.post(
        "/api/v1/transactions/",
        json={"date": "2024-03-01", "description": "Zero", "amount": 0},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_import_csv_bad_extension(client):
    response = await client.post(
        "/api/v1/transactions/import-csv",
        files={"file": ("data.txt", b"date,description,amount", "text/plain")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_import_csv_bad_columns(client):
    response = await client.post(
        "/api/v1/transactions/import-csv",
        files={"file": ("data.csv", b"name,value\nSwiggy,450", "text/csv")},
    )
    assert response.status_code == 422
