"""OpenAI service integration."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from openai import OpenAI
from openai.error import OpenAIError

from config import settings

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = (
    "Ты — консалтинг-эксперт из агентства 1ma.ai. Те задачи, которые ты решаешь:"
    " анализируешь бизнес клиента, подбираешь точки применения искусственного интеллекта,"
    " формируешь понятный план внедрения. Отвечай кратко, по делу и строго на русском языке."
)

CHAT_SYSTEM_PROMPT = (
    "Ты — персональный AI-консультант агентства 1ma.ai. Ты уже провёл диагностику бизнеса клиента и подготовил ему отчёт."
    " Сейчас клиент задаёт уточняющие вопросы, поэтому опирайся на ранее сделанные выводы и конкретику из отчёта."
    " Отвечай дружелюбно, подробно, с практическими рекомендациями. Не придумывай данных, если их нет — говори об этом."
    " Всегда предлагай следующий шаг и упоминай, как ИИ можно применить в реальных процессах."
)

ANALYSIS_USER_PROMPT = (
    "Проанализируй ответы клиента и подготовь рекомендации по внедрению ИИ.\n"
    "Ты должен вернуть JSON-объект со следующей строгой структурой:\n"
    "{\n"
    '  "business_summary": "краткое описание бизнеса и текущей ситуации",\n'
    '  "priority_processes": ["ключевой процесс 1", "ключевой процесс 2", ...],\n'
    '  "ai_opportunities": ["основная возможность 1", "основная возможность 2", ...],\n'
    '  "quick_wins": ["быстрый результат 1", ...],\n'
    '  "long_term": ["долгосрочная инициатива 1", ...],\n'
    '  "next_steps": ["шаг 1", "шаг 2", ...],\n'
    '  "recommended_tools": ["инструмент или интеграция 1", ...],\n'
    '  "gpt_prompts": ["пример запроса для GPT 1", ...]\n'
    "}\n"
    "Формулируй пункты с учётом отрасли клиента, его целей и масштаба."
    " Учитывай уровень компетенций клиента в ИИ."
    " Не добавляй никакого текста вне JSON. Не используй переносы строк внутри элементов, "
    "чтобы каждый пункт помещался в одну строку."
)

DEFAULT_ANALYSIS: Dict[str, Any] = {
    "business_summary": "",
    "priority_processes": [],
    "ai_opportunities": [],
    "quick_wins": [],
    "long_term": [],
    "next_steps": [],
    "recommended_tools": [],
    "gpt_prompts": [],
}

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def analyze_answers(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call OpenAI to generate structured AI recommendations."""
    try:
        client = _get_client()
    except RuntimeError as exc:
        logger.error("OpenAI configuration error: %s", exc)
        return DEFAULT_ANALYSIS.copy()

    request_payload = _build_prompt_payload(payload)

    try:
        response = client.responses.create(
            model=settings.openai_model,
            input=[
                {"role": "system", "content": [{"type": "text", "text": ANALYSIS_SYSTEM_PROMPT}]},
                {"role": "user", "content": [{"type": "text", "text": request_payload}]},
            ],
            temperature=0.2,
        )
    except OpenAIError as exc:  # pragma: no cover - external service
        logger.error("OpenAI API error: %s", exc)
        return DEFAULT_ANALYSIS.copy()

    output_text = getattr(response, "output_text", None) or _extract_text(response)
    if not output_text:
        logger.error("OpenAI response did not contain text output.")
        return DEFAULT_ANALYSIS.copy()

    try:
        parsed: Dict[str, Any] = json.loads(output_text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse OpenAI analysis JSON: %s", exc)
        return DEFAULT_ANALYSIS.copy()

    return _merge_with_default(parsed)


def generate_chat_reply(payload: Dict[str, Any]) -> str:
    try:
        client = _get_client()
    except RuntimeError as exc:
        logger.error("OpenAI configuration error: %s", exc)
        return ""

    request_payload = _build_chat_prompt(payload)

    try:
        response = client.responses.create(
            model=settings.openai_model,
            input=[
                {"role": "system", "content": [{"type": "text", "text": CHAT_SYSTEM_PROMPT}]},
                {"role": "user", "content": [{"type": "text", "text": request_payload}]},
            ],
            temperature=0.35,
        )
    except OpenAIError as exc:  # pragma: no cover - external service
        logger.error("OpenAI chat error: %s", exc)
        return ""

    output_text = getattr(response, "output_text", None) or _extract_text(response)
    return output_text.strip()


def _build_prompt_payload(payload: Dict[str, Any]) -> str:
    """Serialize payload for the model."""
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"{ANALYSIS_USER_PROMPT}\n\nДанные клиента:\n{serialized}"


def _build_chat_prompt(payload: Dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "Используй эти данные, чтобы ответить клиенту на его вопрос. "
        "Сформулируй ответ полностью на русском языке, без JSON, в виде нескольких абзацев и маркеров при необходимости.\n\n"
        f"{serialized}"
    )


def _extract_text(response) -> str:
    """Fallback extraction for older SDK versions."""
    try:
        return "".join(part.text for part in getattr(response, "output", []) if getattr(part, "text", None))
    except Exception:  # pragma: no cover - defensive
        return ""


def _merge_with_default(parsed: Dict[str, Any]) -> Dict[str, Any]:
    result = DEFAULT_ANALYSIS.copy()
    for key in result.keys():
        value = parsed.get(key, result[key])
        if isinstance(result[key], list):
            result[key] = _ensure_list_of_strings(value)
        else:
            result[key] = str(value) if value is not None else ""
    return result


def _ensure_list_of_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str) and value:
        return [value]
    return []
