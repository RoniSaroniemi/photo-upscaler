import pytest
from httpx import ASGITransport, AsyncClient

from app.database import add_balance, get_balance
from app.main import app


async def create_authenticated_client(client: AsyncClient) -> str:
    """Create a user, verify them, and return the session cookie."""
    login_resp = await client.post(
        "/auth/login",
        json={"email": "payer@example.com"},
    )
    token = login_resp.json()["token"]
    verify_resp = await client.post("/auth/verify", json={"token": token})
    return verify_resp.cookies.get("session_id")


@pytest.mark.anyio
async def test_balance_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/payments/balance")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_balance_returns_zero_for_new_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session = await create_authenticated_client(client)
        response = await client.get(
            "/payments/balance",
            cookies={"session_id": session},
        )
    assert response.status_code == 200
    assert response.json()["balance_cents"] == 0


@pytest.mark.anyio
async def test_checkout_simulated_adds_balance():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session = await create_authenticated_client(client)
        response = await client.post(
            "/payments/checkout",
            json={"amount_cents": 500},
            cookies={"session_id": session},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["simulated"] is True
    assert data["balance_cents"] == 500


@pytest.mark.anyio
async def test_checkout_rejects_invalid_amount():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session = await create_authenticated_client(client)
        response = await client.post(
            "/payments/checkout",
            json={"amount_cents": 999},
            cookies={"session_id": session},
        )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_transactions_empty_for_new_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session = await create_authenticated_client(client)
        response = await client.get(
            "/payments/transactions",
            cookies={"session_id": session},
        )
    assert response.status_code == 200
    assert response.json()["transactions"] == []


@pytest.mark.anyio
async def test_transactions_after_topup():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session = await create_authenticated_client(client)
        await client.post(
            "/payments/checkout",
            json={"amount_cents": 1000},
            cookies={"session_id": session},
        )
        response = await client.get(
            "/payments/transactions",
            cookies={"session_id": session},
        )
    assert response.status_code == 200
    txns = response.json()["transactions"]
    assert len(txns) == 1
    assert txns[0]["type"] == "topup"
    assert txns[0]["amount_cents"] == 1000


@pytest.mark.anyio
async def test_webhook_processes_checkout_completed():
    """Test that a simulated webhook event adds balance."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First create a user
        session = await create_authenticated_client(client)

        # Get user ID from /auth/me
        me_resp = await client.get("/auth/me", cookies={"session_id": session})
        user_id = me_resp.json()["user"]["id"]

        # Simulate a webhook
        webhook_payload = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "metadata": {
                        "user_id": user_id,
                        "amount_cents": "2000",
                    },
                }
            },
        }

        response = await client.post(
            "/payments/webhook",
            json=webhook_payload,
        )
    assert response.status_code == 200
    assert response.json()["received"] is True
    assert get_balance(user_id) == 2000
