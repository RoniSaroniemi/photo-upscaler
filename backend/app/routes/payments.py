import os

import stripe
from fastapi import APIRouter, HTTPException, Request

from app.database import add_balance, get_balance, get_session_user, get_transactions

router = APIRouter(prefix="/payments")

SESSION_COOKIE = "session_id"

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

TOPUP_AMOUNTS = {
    500: "$5.00",
    1000: "$10.00",
    2000: "$20.00",
}

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def _get_user(request: Request) -> dict:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_session_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired")
    return user


@router.get("/balance")
async def get_user_balance(request: Request):
    user = _get_user(request)
    return {
        "balance_cents": user["balance_cents"],
        "balance_display": f"${user['balance_cents'] / 100:.2f}",
    }


@router.post("/checkout")
async def create_checkout(request: Request):
    """Create a Stripe Checkout session for adding balance."""
    user = _get_user(request)

    body = await request.json()
    amount_cents = body.get("amount_cents", 500)

    if amount_cents not in TOPUP_AMOUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid amount. Choose from: {list(TOPUP_AMOUNTS.keys())}",
        )

    if not stripe.api_key:
        # MVP fallback: simulate payment without Stripe
        new_balance = add_balance(
            user["id"],
            amount_cents,
            f"Simulated top-up of {TOPUP_AMOUNTS[amount_cents]}",
            stripe_session_id="simulated",
        )
        return {
            "simulated": True,
            "message": f"Balance updated (Stripe not configured)",
            "balance_cents": new_balance,
            "balance_display": f"${new_balance / 100:.2f}",
        }

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"Photo Upscaler Balance — {TOPUP_AMOUNTS[amount_cents]}",
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=f"{FRONTEND_URL}/account?payment=success",
        cancel_url=f"{FRONTEND_URL}/account?payment=cancelled",
        metadata={
            "user_id": user["id"],
            "amount_cents": str(amount_cents),
        },
    )

    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    if webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # MVP: accept without verification if no webhook secret configured
        import json
        event = json.loads(payload)

    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        user_id = metadata.get("user_id")
        amount_cents = int(metadata.get("amount_cents", 0))

        if user_id and amount_cents:
            add_balance(
                user_id,
                amount_cents,
                f"Stripe top-up of ${amount_cents / 100:.2f}",
                stripe_session_id=session.get("id"),
            )

    return {"received": True}


@router.get("/transactions")
async def get_user_transactions(request: Request):
    user = _get_user(request)
    transactions = get_transactions(user["id"])
    return {
        "transactions": [
            {
                "id": tx["id"],
                "amount_cents": tx["amount_cents"],
                "amount_display": f"${abs(tx['amount_cents']) / 100:.2f}",
                "type": tx["type"],
                "description": tx["description"],
                "created_at": tx["created_at"],
            }
            for tx in transactions
        ]
    }
