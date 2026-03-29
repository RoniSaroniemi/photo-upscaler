import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.anyio
async def test_login_returns_magic_link():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/auth/login",
            json={"email": "test@example.com"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "magic_link" in data
    assert data["message"] == "Magic link sent! Check your email."


@pytest.mark.anyio
async def test_login_rejects_invalid_email():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/auth/login",
            json={"email": "not-an-email"},
        )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_verify_creates_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Get a token
        login_resp = await client.post(
            "/auth/login",
            json={"email": "test@example.com"},
        )
        token = login_resp.json()["token"]

        # Verify it
        verify_resp = await client.post(
            "/auth/verify",
            json={"token": token},
        )
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert data["user"]["email"] == "test@example.com"
    assert "session_id" in verify_resp.cookies


@pytest.mark.anyio
async def test_verify_rejects_invalid_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/auth/verify",
            json={"token": "invalid-token"},
        )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_verify_rejects_used_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login_resp = await client.post(
            "/auth/login",
            json={"email": "test@example.com"},
        )
        token = login_resp.json()["token"]

        # Use it once
        await client.post("/auth/verify", json={"token": token})
        # Try again
        response = await client.post("/auth/verify", json={"token": token})
    assert response.status_code == 400


@pytest.mark.anyio
async def test_me_returns_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login_resp = await client.post(
            "/auth/login",
            json={"email": "me@example.com"},
        )
        token = login_resp.json()["token"]
        verify_resp = await client.post("/auth/verify", json={"token": token})
        session_cookie = verify_resp.cookies.get("session_id")

        me_resp = await client.get(
            "/auth/me",
            cookies={"session_id": session_cookie},
        )
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["email"] == "me@example.com"


@pytest.mark.anyio
async def test_me_rejects_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_logout_clears_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login_resp = await client.post(
            "/auth/login",
            json={"email": "test@example.com"},
        )
        token = login_resp.json()["token"]
        verify_resp = await client.post("/auth/verify", json={"token": token})
        session_cookie = verify_resp.cookies.get("session_id")

        await client.post("/auth/logout", cookies={"session_id": session_cookie})

        me_resp = await client.get("/auth/me", cookies={"session_id": session_cookie})
    assert me_resp.status_code == 401
