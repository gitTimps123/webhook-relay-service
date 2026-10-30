# webhook-relay-service

Webhook receiver and relay service — verifies HMAC signatures, stores deliveries, retries failed forwards with backoff and keeps a delivery log.

## Flow

```
receive -> verify -> store -> forward -> retry
```

1. Receive: a provider posts to `/webhooks/{source}`.
2. Verify: the request body is checked against its HMAC-SHA256 signature using the source secret.
3. Store: the delivery is recorded in the in-memory delivery log with its status.
4. Forward: the payload is forwarded to the configured target URL for that source.
5. Retry: a failed forward is retried with exponential backoff, and its attempts are recorded in the log.

## Endpoints

- `GET /health` — service health check.
- `POST /webhooks/{source}` — webhook intake for a source. Send the signature in the `X-Signature-256` header as `sha256=<hex digest>`.
- `GET /deliveries` — list recorded deliveries.
- `GET /deliveries/{delivery_id}` — get one delivery.
- `POST /deliveries/{delivery_id}/retry` — retry forwarding a delivery.

## Configuration

Set these environment variables:

- `WEBHOOK_SECRET_<SOURCE>` — HMAC secret for a source, for example `WEBHOOK_SECRET_GITHUB`.
- `TARGET_URL_<SOURCE>` — URL to forward that source's webhooks to.

Secrets are read from the environment and are not committed to the repository. For production use, replace the in-memory log with a persistent store.

## How to run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

The API is then available at http://127.0.0.1:8000, with interactive docs at http://127.0.0.1:8000/docs.

## Stack

Python, FastAPI, httpx, Pydantic, Uvicorn.
