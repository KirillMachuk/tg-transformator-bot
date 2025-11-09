"""Vercel webhook entrypoint."""

import asyncio
import base64
import json
import logging
import traceback
from http import HTTPStatus
from typing import Any, Dict

from telegram import Update
from telegram.error import TelegramError

from bot.handlers import build_application
from config import settings

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

application = None
_application_ready = False
_application_lock = None


async def _ensure_application_ready() -> None:
    """Make sure the application is initialized and started once per cold start."""
    global application, _application_ready, _application_lock

    if _application_ready:
        return

    if _application_lock is None:
        _application_lock = asyncio.Lock()

    async with _application_lock:
        if _application_ready:
            return

        if application is None:
            application = build_application()

        await application.initialize()
        await application.start()
        logger.info("Telegram application started successfully.")
        _application_ready = True


async def _process_update(update_json: Dict[str, Any]) -> None:
    await _ensure_application_ready()
    if application is None:
        raise RuntimeError("Application failed to initialize.")
    update = Update.de_json(update_json, bot=application.bot)
    await application.process_update(update)


def handler(event, context):
    del context
    method = (event.get("httpMethod") or event.get("method") or "POST").upper()
    if method == "GET":
        return {"statusCode": HTTPStatus.OK, "body": "ok"}

    body = event.get("body")
    if not body:
        return {"statusCode": HTTPStatus.BAD_REQUEST, "body": "missing body"}

    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception:
            return {"statusCode": HTTPStatus.BAD_REQUEST, "body": "invalid base64 body"}

    headers = event.get("headers") or {}
    if not _validate_secret(headers):
        return {"statusCode": HTTPStatus.FORBIDDEN, "body": "invalid secret"}

    try:
        update_json = json.loads(body)
    except json.JSONDecodeError:
        return {"statusCode": HTTPStatus.BAD_REQUEST, "body": "invalid json"}

    try:
        asyncio.run(_process_update(update_json))
    except TelegramError as exc:  # pragma: no cover - defensive logging
        logger.exception("Telegram API error while processing update.")
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR,
            "body": f"telegram error: {exc}",
        }
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Unhandled error while processing update.")
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR,
            "body": f"error: {exc}\n{trace}",
        }

    return {"statusCode": HTTPStatus.OK, "body": "ok"}


def _validate_secret(headers: Dict[str, Any]) -> bool:
    expected = settings.telegram_secret_token
    if not expected:
        return True
    for key, value in headers.items():
        if key.lower() == "x-telegram-bot-api-secret-token":
            return value == expected
    return False
