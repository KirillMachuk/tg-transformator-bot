"""Google Sheets / Google Apps Script integration service."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings
from bot import questions, utils

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_sheets_service = None


def store_answers(metadata: Dict[str, Any], user_data: Dict[str, Any]) -> None:
    """Persist answers using preferred integration (GAS endpoint or Sheets API)."""
    payload = _build_payload(metadata, user_data)

    if settings.gas_endpoint:
        if _post_to_gas(payload):
            logger.info("Saved answers for user %s via GAS endpoint.", payload["meta"].get("user_id"))
            return
        logger.warning("Falling back to Google Sheets API due to GAS endpoint failure.")

    if settings.google_credentials_json and settings.google_sheet_id:
        _append_to_google_sheet(payload)
    else:
        logger.info("No Google Sheets integration configured; answers not stored.")


def _build_payload(metadata: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = metadata.get("timestamp")
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()

    answers_by_id = utils.collect_all_answers(user_data)
    questions_list = questions.get_all_questions()

    answers_detailed: List[Dict[str, Any]] = []
    for question in questions_list:
        answers_detailed.append(
            {
                "id": question.id,
                "question_markdown": question.text,
                "question_plain": utils.strip_markdown(question.text),
                "answer": answers_by_id.get(question.id, ""),
            }
        )

    meta = {
        "timestamp": timestamp,
        "user_id": metadata.get("user_id", ""),
        "username": metadata.get("username", ""),
        "full_name": metadata.get("full_name", ""),
        "skill_level": utils.get_skill_level_text(user_data),
    }

    return {
        "meta": meta,
        "answers_by_id": answers_by_id,
        "answers": answers_detailed,
    }


def _post_to_gas(payload: Dict[str, Any]) -> bool:
    try:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            settings.gas_endpoint,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
            if response.status != 200:
                logger.error("GAS endpoint returned status %s", response.status)
                return False
            body = response.read()
            if not body:
                return True
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                return True
            return bool(payload.get("ok", True))
    except urllib.error.URLError as exc:
        logger.error("Failed to POST data to GAS endpoint: %s", exc)
    return False


def _append_to_google_sheet(payload: Dict[str, Any]) -> None:
    service = _get_sheets_service()
    if service is None:
        logger.error("Failed to initialize Google Sheets service; data not stored.")
        return

    values = _build_row(payload)
    body = {"values": [values]}

    try:
        service.spreadsheets().values().append(
            spreadsheetId=settings.google_sheet_id,
            range=settings.google_sheet_range,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
        logger.info("Saved answers for user %s to Google Sheets.", payload["meta"].get("user_id"))
    except HttpError as exc:  # pragma: no cover - external service
        logger.error("Failed to append row to Google Sheets: %s", exc)


def _build_row(payload: Dict[str, Any]) -> List[str]:
    meta = payload["meta"]
    answers_map = payload["answers_by_id"]

    values: List[str] = [
        meta.get("timestamp", ""),
        str(meta.get("user_id", "")),
        meta.get("username", ""),
        meta.get("full_name", ""),
        meta.get("skill_level", ""),
    ]

    for question in questions.get_all_questions():
        values.append(answers_map.get(question.id, ""))

    return values


def _get_sheets_service():
    global _sheets_service
    if _sheets_service is not None:
        return _sheets_service

    try:
        credentials = _build_credentials()
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Invalid Google credentials: %s", exc)
        return None

    try:
        _sheets_service = build(
            "sheets",
            "v4",
            credentials=credentials,
            cache_discovery=False,
        )
    except Exception as exc:  # pragma: no cover - external service
        logger.error("Failed to create Google Sheets client: %s", exc)
        _sheets_service = None

    return _sheets_service


def _build_credentials() -> Credentials:
    if not settings.google_credentials_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON is not set.")

    credentials_info = json.loads(settings.google_credentials_json)
    return Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
