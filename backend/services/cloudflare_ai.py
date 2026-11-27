import os

import requests


ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
API_ROOT = (
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run"
    if ACCOUNT_ID
    else None
)


def run_model(model, payload, timeout=120):
    if not ACCOUNT_ID or not API_TOKEN:
        raise RuntimeError(
            "Cloudflare AI is not configured. Set CLOUDFLARE_ACCOUNT_ID "
            "and CLOUDFLARE_API_TOKEN in the backend environment."
        )

    response = requests.post(
        f"{API_ROOT}/{model}",
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        json=payload,
        timeout=timeout,
    )

    try:
        body = response.json()
    except ValueError:
        body = {}

    if not response.ok or not body.get("success", True):
        details = body.get("errors") or body.get("messages") or response.text
        raise RuntimeError(
            f"Cloudflare AI request failed ({response.status_code}): {details}"
        )

    return body.get("result", body)
