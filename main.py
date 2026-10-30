import asyncio
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="webhook-relay-service")

# In-memory delivery log: delivery_id -> delivery record.
DELIVERIES: dict[str, dict] = {}


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    """Verify an HMAC-SHA256 signature in the form sha256=<hex digest>."""
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def target_url_for(source: str) -> str:
    return os.getenv(f"TARGET_URL_{source.upper()}", "")


async def forward_once(delivery: dict) -> bool:
    target = target_url_for(delivery["source"])
    if not target:
        return False
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(target, json=delivery["payload"])
        return resp.status_code < 400


async def forward_with_retry(delivery: dict, attempts: int = 3) -> None:
    delay = 1.0
    for attempt in range(1, attempts + 1):
        ok = await forward_once(delivery)
        delivery["attempts"] = attempt
        if ok:
            delivery["status"] = "delivered"
            return
        delivery["status"] = "retrying" if attempt < attempts else "failed"
        if attempt < attempts:
            await asyncio.sleep(delay)
            delay *= 2


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/{source}")
async def receive_webhook(source: str, request: Request, x_signature_256: str | None = Header(default=None)):
    body = await request.body()
    secret = os.getenv(f"WEBHOOK_SECRET_{source.upper()}", "")
    if secret and not verify_signature(secret, body, x_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    delivery_id = str(uuid.uuid4())
    delivery = {
        "id": delivery_id, "source": source, "payload": payload,
        "status": "received", "attempts": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    DELIVERIES[delivery_id] = delivery
    await forward_with_retry(delivery)
    return {"delivery_id": delivery_id, "status": delivery["status"]}


@app.get("/deliveries")
def list_deliveries():
    return {"deliveries": list(DELIVERIES.values())}


@app.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: str):
    delivery = DELIVERIES.get(delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return delivery


@app.post("/deliveries/{delivery_id}/retry")
async def retry_delivery(delivery_id: str):
    delivery = DELIVERIES.get(delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    await forward_with_retry(delivery)
    return delivery
