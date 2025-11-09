"""Keyboard builders for inline buttons."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Set

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import settings
from . import messages
from .questions import Option, Question


def _build_inline_keyboard(rows: Sequence[Sequence[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(list(rows))


def skill_level_keyboard() -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for callback_data, text in messages.SKILL_LEVEL_OPTIONS:
        if not text:
            continue
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
    return _build_inline_keyboard(buttons)


def start_keyboard() -> InlineKeyboardMarkup:
    return single_button_keyboard(messages.START_BUTTON)


def single_button_keyboard(button_data: tuple[str, str]) -> InlineKeyboardMarkup:
    callback_data, text = button_data
    return _build_inline_keyboard([[InlineKeyboardButton(text=text, callback_data=callback_data)]])


def question_options_keyboard(
    question: Question,
    selected_options: Set[str] | None = None,
) -> InlineKeyboardMarkup:
    selected_options = selected_options or set()
    rows: List[List[InlineKeyboardButton]] = []

    if question.options:
        for option in question.options:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=_display_option_text(option, selected_options),
                        callback_data=f"q|{question.id}|{option.key}",
                    )
                ]
            )

    if question.multi_select:
        rows.append(
            [
                InlineKeyboardButton(
                    text=messages.MULTI_SELECT_DONE_BUTTON[1],
                    callback_data=f"q|{question.id}|done",
                )
            ]
        )

    return _build_inline_keyboard(rows)


def _display_option_text(option: Option, selected_options: Set[str]) -> str:
    if option.key in selected_options:
        return option.text
    return option.text


def consultation_keyboard() -> Optional[InlineKeyboardMarkup]:
    url = settings.consultation_url.strip()
    if not url:
        return None
    button = InlineKeyboardButton(text=messages.CONSULTATION_BUTTON_TEXT, url=url)
    return _build_inline_keyboard([[button]])
