"""Utility helpers for bot logic."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from . import messages
from .questions import Option, Question, get_all_questions

ANSWERS_KEY = "answers"
QUESTION_INDEX_KEY = "question_index"
AWAITING_TEXT_KEY = "awaiting_text_question"
AWAITING_OTHER_KEY = "awaiting_other_question"
SKILL_LEVEL_KEY = "skill_level"
REPORT_READY_KEY = "report_ready"
DIAGNOSIS_COMPLETE_KEY = "diagnosis_complete"
CURRENT_QUESTION_MESSAGE_KEY = "current_question_message"
SHEETS_SAVED_KEY = "sheets_saved"
CHAT_HISTORY_KEY = "chat_history"


def reset_user_session(user_data: Dict[str, Any]) -> None:
    user_data.clear()
    user_data[ANSWERS_KEY] = {}
    user_data[QUESTION_INDEX_KEY] = 0
    user_data[REPORT_READY_KEY] = False
    user_data[DIAGNOSIS_COMPLETE_KEY] = False
    user_data.pop(CURRENT_QUESTION_MESSAGE_KEY, None)
    user_data[SHEETS_SAVED_KEY] = False
    user_data[CHAT_HISTORY_KEY] = []


def ensure_user_data(user_data: Dict[str, Any]) -> Dict[str, Any]:
    if ANSWERS_KEY not in user_data:
        reset_user_session(user_data)
    return user_data


def get_all_question_sequence() -> List[Question]:
    return get_all_questions()


def get_current_question(user_data: Dict[str, Any]) -> Optional[Question]:
    questions = get_all_question_sequence()
    index = user_data.get(QUESTION_INDEX_KEY, 0)
    if 0 <= index < len(questions):
        return questions[index]
    return None


def advance_question(user_data: Dict[str, Any]) -> Optional[Question]:
    questions = get_all_question_sequence()
    index = user_data.get(QUESTION_INDEX_KEY, 0) + 1
    user_data[QUESTION_INDEX_KEY] = index
    if 0 <= index < len(questions):
        return questions[index]
    return None


def record_answer(user_data: Dict[str, Any], question_id: str, value: Any) -> None:
    answers = user_data.setdefault(ANSWERS_KEY, {})
    answers[question_id] = value


def get_answer(user_data: Dict[str, Any], question_id: str, default: Any = None) -> Any:
    return user_data.get(ANSWERS_KEY, {}).get(question_id, default)


def toggle_multi_option(
    user_data: Dict[str, Any],
    question: Question,
    option: Option,
) -> Dict[str, Any]:
    answers = user_data.setdefault(ANSWERS_KEY, {})
    entry: Dict[str, Any] = answers.setdefault(question.id, {"selected": [], "custom": []})
    selected: List[str] = entry.setdefault("selected", [])
    if option.key in selected:
        selected.remove(option.key)
    else:
        selected.append(option.key)
    return entry


def get_selected_option_keys(user_data: Dict[str, Any], question_id: str) -> List[str]:
    entry = get_answer(user_data, question_id, {})
    return entry.get("selected", []) if isinstance(entry, dict) else []


def append_custom_answer(user_data: Dict[str, Any], question_id: str, option_text: str, value: str) -> None:
    answers = user_data.setdefault(ANSWERS_KEY, {})
    entry: Dict[str, Any] = answers.setdefault(question_id, {"selected": [], "custom": []})
    custom: List[Dict[str, str]] = entry.setdefault("custom", [])
    custom.append({"option": option_text, "value": value})


def record_single_answer(user_data: Dict[str, Any], question_id: str, value: Any) -> None:
    answers = user_data.setdefault(ANSWERS_KEY, {})
    answers[question_id] = value


def set_current_question_message(user_data: Dict[str, Any], chat_id: int, message_id: int) -> None:
    user_data[CURRENT_QUESTION_MESSAGE_KEY] = {"chat_id": chat_id, "message_id": message_id}


def get_current_question_message(user_data: Dict[str, Any]) -> Optional[Dict[str, int]]:
    message_ref = user_data.get(CURRENT_QUESTION_MESSAGE_KEY)
    if message_ref and isinstance(message_ref, dict):
        chat_id = message_ref.get("chat_id")
        message_id = message_ref.get("message_id")
        if isinstance(chat_id, int) and isinstance(message_id, int):
            return {"chat_id": chat_id, "message_id": message_id}
    return None


def get_question_by_id(question_id: str) -> Optional[Question]:
    for question in get_all_question_sequence():
        if question.id == question_id:
            return question
    return None


def get_skill_level_text(user_data: Dict[str, Any]) -> str:
    skill_key = user_data.get(SKILL_LEVEL_KEY, "")
    for key, text in messages.SKILL_LEVEL_OPTIONS:
        if key == skill_key:
            return text
    return ""


def format_question_answer(question: Question, user_data: Dict[str, Any]) -> str:
    answer = get_answer(user_data, question.id)

    if answer is None:
        return ""

    if isinstance(answer, dict):
        parts: List[str] = []
        for key in answer.get("selected", []):
            option = find_option_by_key(question, key)
            if option:
                parts.append(option.text)
        for custom_entry in answer.get("custom", []):
            if isinstance(custom_entry, dict):
                option_label = custom_entry.get("option", "✍️ Другое")
                value = custom_entry.get("value", "")
                if value:
                    parts.append(f"{option_label}: {value}")
        return "\n".join(parts)

    if isinstance(answer, list):
        return "\n".join(str(item) for item in answer)

    return str(answer)


def collect_all_answers(user_data: Dict[str, Any]) -> Dict[str, str]:
    answers: Dict[str, str] = {}
    for question in get_all_question_sequence():
        answers[question.id] = format_question_answer(question, user_data)
    return answers


def find_option_by_key(question: Question, key: str) -> Optional[Option]:
    if not question.options:
        return None
    for option in question.options:
        if option.key == key:
            return option
    return None


def build_question_answer_pairs(user_data: Dict[str, Any]) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    for question in get_all_question_sequence():
        pairs.append(
            {
                "id": question.id,
                "question": strip_markdown(question.text),
                "answer": format_question_answer(question, user_data),
            }
        )
    return pairs


def strip_markdown(text: str) -> str:
    stripped = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    stripped = stripped.replace("**", "")
    stripped = stripped.replace("*", "")
    stripped = stripped.replace("`", "")
    stripped = stripped.replace("_", "")
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip()


def append_chat_history(user_data: Dict[str, Any], role: str, message: str, limit: int = 12) -> None:
    history: List[Dict[str, str]] = user_data.setdefault(CHAT_HISTORY_KEY, [])
    history.append({"role": role, "message": message})
    if len(history) > limit:
        del history[0 : len(history) - limit]


def get_chat_history(user_data: Dict[str, Any]) -> List[Dict[str, str]]:
    history = user_data.get(CHAT_HISTORY_KEY, [])
    if isinstance(history, list):
        return list(history)
    return []
