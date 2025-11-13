"""Vercel webhook entrypoint."""

import asyncio
import base64
import json
import logging
import os
import sys
import traceback
from http import HTTPStatus
from typing import Any, Dict

try:
    from werkzeug.wrappers import Response
except Exception:  # pragma: no cover - fallback if werkzeug missing
    Response = None

from telegram import Update
from telegram.error import TelegramError

from bot.handlers import build_application
from config import settings

logger = logging.getLogger(__name__)
if not logger.handlers:
    # Set DEBUG level for detailed PDF font logging
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def _log(message: str, payload: Any | None = None, *, stream=sys.stderr) -> None:
    text = f"[webhook] {message}" if payload is None else f"[webhook] {message}: {payload}"
    try:
        stream.write(text + "\n")
        stream.flush()
    except Exception:
        logger.debug("Failed to emit log line: %s", text)


def _debug_log(message: str, payload: Any | None = None) -> None:
    _log(message, payload, stream=sys.stderr)


_log("module imported", stream=sys.stderr)
_log("TELEGRAM_BOT_TOKEN present", bool(settings.telegram_token), stream=sys.stderr)
_log("TELEGRAM_SECRET_TOKEN present", bool(settings.telegram_secret_token), stream=sys.stderr)


def _normalize_event(raw_event: Any) -> Dict[str, Any]:
    if isinstance(raw_event, dict):
        return raw_event
    if isinstance(raw_event, str):
        try:
            return json.loads(raw_event)
        except Exception:
            return {}
    if raw_event is None:
        return {}
    try:
        return dict(raw_event)
    except Exception:
        return {}


def _make_response(body: str, status: int = 200, *, content_type: str = "text/plain; charset=utf-8"):
    if Response is not None:
        return Response(body, status=status, content_type=content_type)
    return body, status, {"Content-Type": content_type}


async def _process_update(update_json: Dict[str, Any]) -> None:
    _debug_log("building application")
    application = build_application()
    initialized = False
    started = False

    try:
        _debug_log("initializing application")
        await application.initialize()
        initialized = True
        _debug_log("starting application")
        await application.start()
        started = True

        update = Update.de_json(update_json, bot=application.bot)
        _debug_log("processing update", update_json.get("update_id"))
        await application.process_update(update)
    finally:
        await _shutdown_application(application, started=started, initialized=initialized)


async def _shutdown_application(application, *, started: bool, initialized: bool) -> None:
    if started:
        try:
            _debug_log("stopping application")
            await application.stop()
        except Exception as exc:
            logger.warning("Failed to stop application cleanly: %s", exc)
    if initialized:
        try:
            _debug_log("shutting down application")
            await application.shutdown()
        except Exception as exc:
            logger.warning("Failed to shutdown application cleanly: %s", exc)


def handler(event, context=None):
    try:
        if hasattr(event, "method"):
            return _handle_http_request(event)

        event_dict = _normalize_event(event)
        return _handle_lambda_event(event_dict)
    except Exception as exc:
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.exception("Unhandled error in webhook handler.")
        print("[webhook] fatal handler error:", exc, flush=True)
        print(trace, flush=True)
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR,
            "body": f"error: {exc}\n{trace}",
        }


def _handle_lambda_event(event: Dict[str, Any]) -> Dict[str, Any]:
    print("[webhook] handler invoked", flush=True)
    print("[webhook] event keys:", list(event.keys()), flush=True)

    method = (event.get("httpMethod") or event.get("method") or "POST").upper()
    if method == "GET":
        return {"statusCode": 200, "body": "ok"}

    body = event.get("body")
    if not body:
        return {"statusCode": HTTPStatus.BAD_REQUEST, "body": "missing body"}

    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception:
            return {"statusCode": HTTPStatus.BAD_REQUEST, "body": "invalid base64 body"}

    headers = event.get("headers") or {}
    _debug_log("headers", headers)
    status, message = _process_payload(body, headers)
    return {"statusCode": int(status), "body": message}


def _handle_http_request(request) -> Any:
    method = (getattr(request, "method", None) or "POST").upper()
    print("[webhook] handler invoked (http request)", flush=True)
    print("[webhook] request method:", method, flush=True)

    if method == "GET":
        return _make_response("ok", status=200)

    body = request.get_data(as_text=True) if hasattr(request, "get_data") else ""
    if not body:
        return _make_response("missing body", status=HTTPStatus.BAD_REQUEST)

    headers = dict(getattr(request, "headers", {}) or {})
    _debug_log("headers", headers)
    status, message = _process_payload(body, headers)
    return _make_response(message, status=int(status))


def _process_payload(body: str, headers: Dict[str, Any]) -> tuple[int, str]:
    if not _validate_secret(headers):
        return HTTPStatus.FORBIDDEN, "invalid secret"

    try:
        update_json = json.loads(body)
    except json.JSONDecodeError:
        return HTTPStatus.BAD_REQUEST, "invalid json"

    try:
        _debug_log("received update", update_json)
        asyncio.run(_process_update(update_json))
    except TelegramError as exc:  # pragma: no cover - defensive logging
        logger.exception("Telegram API error while processing update.")
        traceback.print_exc()
        return HTTPStatus.INTERNAL_SERVER_ERROR, f"telegram error: {exc}"
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Unhandled error while processing update.")
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print("[webhook] exception while processing update:", exc, flush=True)
        print(trace, flush=True)
        return (
            HTTPStatus.INTERNAL_SERVER_ERROR,
            f"error: {exc}\n{trace}\nToken present: {bool(settings.telegram_token)}",
        )

    return HTTPStatus.OK, "ok"


def _validate_secret(headers: Dict[str, Any]) -> bool:
    expected = settings.telegram_secret_token
    if not expected:
        return True
    for key, value in headers.items():
        if key.lower() == "x-telegram-bot-api-secret-token":
            return value == expected
    return False
