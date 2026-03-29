from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

from app.database import (
    create_auth_token,
    create_session,
    delete_session,
    get_or_create_user,
    get_session_user,
    verify_auth_token,
)

router = APIRouter(prefix="/auth")

SESSION_COOKIE = "session_id"


class LoginRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    token: str


@router.post("/login")
async def login(body: LoginRequest):
    """Send a magic link. For MVP, returns the token directly (no email sending)."""
    token = create_auth_token(body.email)
    # In production, send email with link. For MVP, return token + log it.
    magic_link = f"/auth/verify?token={token}"
    print(f"[AUTH] Magic link for {body.email}: {magic_link}")
    return {
        "message": "Magic link sent! Check your email.",
        "magic_link": magic_link,  # MVP only — remove in production
        "token": token,  # MVP only — remove in production
    }


@router.post("/verify")
async def verify(body: VerifyRequest, response: Response):
    """Verify a magic link token and create a session."""
    email = verify_auth_token(body.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = get_or_create_user(email)
    session_id = create_session(user["id"])

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,  # 30 days
        secure=False,  # Set True in production with HTTPS
    )

    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "balance_cents": user["balance_cents"],
        }
    }


@router.get("/me")
async def get_me(request: Request):
    """Get current user from session cookie."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = get_session_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired")

    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "balance_cents": user["balance_cents"],
        }
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Clear session."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        delete_session(session_id)
    response.delete_cookie(key=SESSION_COOKIE)
    return {"message": "Logged out"}
