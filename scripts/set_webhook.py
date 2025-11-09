#!/usr/bin/env python3
"""Utility to set or delete the Telegram webhook."""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

from dotenv import load_dotenv

load_dotenv()

API_ROOT = "https://api.telegram.org"


def _call_telegram(method: str, token: str, **params):
    url = f"{API_ROOT}/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(request) as response:  # nosec B310
        payload = response.read()
    return json.loads(payload)


def set_webhook(token: str, url: str, secret: str | None = None) -> dict:
    params = {"url": url}
    if secret:
        params["secret_token"] = secret
    return _call_telegram("setWebhook", token, **params)


def delete_webhook(token: str) -> dict:
    return _call_telegram("deleteWebhook", token)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Telegram webhook")
    parser.add_argument("action", choices=["set", "delete"], help="Action to perform")
    parser.add_argument("--url", dest="url", help="Public webhook URL (for set action)")
    args = parser.parse_args()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1

    if args.action == "set":
        webhook_url = args.url or os.getenv("WEBHOOK_URL")
        if not webhook_url:
            print("Provide webhook URL via --url or WEBHOOK_URL env", file=sys.stderr)
            return 1
        secret = os.getenv("TELEGRAM_SECRET_TOKEN")
        result = set_webhook(token, webhook_url, secret)
    else:
        result = delete_webhook(token)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
