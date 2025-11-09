"""Telegram bot handlers and conversation management."""

from __future__ import annotations

import asyncio
import copy
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from telegram import Update, User
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import settings

from . import keyboards, messages
from .questions import Question
from .states import ConversationState
from .utils import (
    ANSWERS_KEY,
    AWAITING_OTHER_KEY,
    AWAITING_TEXT_KEY,
    DIAGNOSIS_COMPLETE_KEY,
    REPORT_READY_KEY,
    SKILL_LEVEL_KEY,
    SHEETS_SAVED_KEY,
    advance_question,
    append_custom_answer,
    append_chat_history,
    ensure_user_data,
    get_answer,
    get_current_question,
    get_current_question_message,
    get_selected_option_keys,
    get_chat_history,
    get_skill_level_text,
    find_option_by_key,
    get_question_by_id,
    record_single_answer,
    reset_user_session,
    set_current_question_message,
    toggle_multi_option,
    build_question_answer_pairs,
    collect_all_answers,
)
from services import openai_service, pdf_service, sheets_service

logger = logging.getLogger(__name__)

Context = ContextTypes.DEFAULT_TYPE


def build_application() -> Application:
    application = (
        ApplicationBuilder()
        .token(settings.telegram_token)
        .concurrent_updates(True)
        .build()
    )

    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            ConversationState.WELCOME: [
                CallbackQueryHandler(handle_start_button, pattern="^start_intro$")
            ],
            ConversationState.SKILL_LEVEL: [
                CallbackQueryHandler(handle_skill_selection, pattern="^skill_level_")
            ],
            ConversationState.VIDEO: [
                CallbackQueryHandler(
                    handle_video_confirmation, pattern="^(video_ready|start_diagnosis)$"
                )
            ],
            ConversationState.DIAGNOSIS: _question_state_handlers(),
            ConversationState.READINESS: _question_state_handlers(),
            ConversationState.REPORT: [
                CallbackQueryHandler(handle_report_request, pattern="^generate_report$")
            ],
            ConversationState.CHAT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat_message)
            ],
        },
        fallbacks=[CommandHandler("start", start_command)],
        allow_reentry=True,
        name="main_conversation",
        persistent=False,
    )

    application.add_handler(conversation_handler)
    return application


def _question_state_handlers():
    return [
        CallbackQueryHandler(handle_question_callback, pattern=r"^q\|"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_response),
    ]


async def start_command(update: Update, context: Context) -> int:
    user_data = ensure_user_data(context.user_data)
    reset_user_session(user_data)

    if update.message:
        await update.message.reply_text(
            messages.WELCOME_TEXT,
            reply_markup=keyboards.start_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False,
        )

    return ConversationState.WELCOME


async def handle_start_button(update: Update, context: Context) -> int:
    query = update.callback_query
    await query.answer()

    ensure_user_data(context.user_data)

    await query.message.reply_text(
        messages.SKILL_LEVEL_PROMPT,
        reply_markup=keyboards.skill_level_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ConversationState.SKILL_LEVEL


async def handle_skill_selection(update: Update, context: Context) -> int:
    query = update.callback_query
    await query.answer()

    choice = query.data
    context.user_data[SKILL_LEVEL_KEY] = choice

    if choice in {messages.SKILL_LEVEL_OPTIONS[0][0], messages.SKILL_LEVEL_OPTIONS[1][0]}:
        await query.message.reply_text(
            messages.VIDEO_MESSAGE,
            reply_markup=keyboards.single_button_keyboard(messages.VIDEO_READY_BUTTON),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False,
        )
        return ConversationState.VIDEO

    await query.message.reply_text(
        messages.EXPERT_SKIP_MESSAGE,
        reply_markup=keyboards.single_button_keyboard(messages.DIAGNOSIS_BUTTON),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ConversationState.VIDEO


async def handle_video_confirmation(update: Update, context: Context) -> int:
    query = update.callback_query
    await query.answer()

    return await start_diagnosis_flow(query.message.chat_id, context)


async def start_diagnosis_flow(chat_id: int, context: Context) -> int:
    await context.bot.send_message(
        chat_id=chat_id,
        text=messages.DIAGNOSIS_INTRO,
        parse_mode=ParseMode.MARKDOWN,
    )
    return await send_next_question(chat_id, context, is_new=True)


async def send_next_question(chat_id: int, context: Context, is_new: bool = False) -> int:
    user_data = ensure_user_data(context.user_data)

    question: Optional[Question]
    if is_new:
        question = get_current_question(user_data)
    else:
        question = advance_question(user_data)

    if not question:
        return await handle_questionnaire_complete(chat_id, context)

    return await _send_question(chat_id, context, question)


async def _send_question(chat_id: int, context: Context, question: Question) -> int:
    user_data = ensure_user_data(context.user_data)
    user_data.pop(AWAITING_TEXT_KEY, None)
    user_data.pop(AWAITING_OTHER_KEY, None)

    if question.options:
        selected_keys = set(get_selected_option_keys(user_data, question.id))
        reply_markup = keyboards.question_options_keyboard(question, selected_keys)
    else:
        reply_markup = None
        if question.expects_text:
            user_data[AWAITING_TEXT_KEY] = question.id

    text = _format_question_text(question, user_data)
    message = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN,
    )
    set_current_question_message(user_data, chat_id, message.message_id)

    return _state_for_question(question)


def _format_question_text(question: Question, user_data: Dict[str, Any]) -> str:
    text = question.text
    entry = get_answer(user_data, question.id, {})

    if isinstance(entry, dict):
        selected_lines: List[str] = []
        for key in entry.get("selected", []):
            option = find_option_by_key(question, key)
            if option:
                selected_lines.append(f"- {option.text}")

        for custom_entry in entry.get("custom", []):
            if isinstance(custom_entry, dict):
                option_label = custom_entry.get("option", "✍️ Другое")
                value = custom_entry.get("value", "")
                if value:
                    selected_lines.append(f"- {option_label}: {value}")

        if selected_lines:
            text += "\n\n*Выбрано:*\n" + "\n".join(selected_lines)

    return text


async def _refresh_question_message(
    context: Context, question: Question, user_data: Dict[str, Any]
) -> None:
    message_ref = get_current_question_message(user_data)
    if not message_ref:
        return

    chat_id = message_ref.get("chat_id")
    message_id = message_ref.get("message_id")
    if chat_id is None or message_id is None:
        return

    selected_keys = set(get_selected_option_keys(user_data, question.id))
    reply_markup = keyboards.question_options_keyboard(question, selected_keys)
    new_text = _format_question_text(question, user_data)

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=new_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
        )
        set_current_question_message(user_data, chat_id, message_id)
    except Exception as exc:  # pragma: no cover - safeguard logging
        logger.warning("Failed to refresh question message: %s", exc)


def _state_for_question(question: Question) -> int:
    return (
        ConversationState.DIAGNOSIS
        if question.section == "business"
        else ConversationState.READINESS
    )


async def handle_question_callback(update: Update, context: Context) -> int:
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    if len(parts) != 3:
        logger.warning("Unexpected callback data: %s", query.data)
        return ConversationState.DIAGNOSIS

    _, question_id, payload = parts
    question = get_question_by_id(question_id)
    if not question:
        logger.warning("Unknown question id: %s", question_id)
        return ConversationState.DIAGNOSIS

    if payload == "done":
        return await _handle_multi_done(query, context, question)

    option = find_option_by_key(question, payload)
    if not option:
        logger.warning("Unknown option key: %s for question %s", payload, question_id)
        return _state_for_question(question)

    if option.requires_free_text:
        context.user_data[AWAITING_OTHER_KEY] = {
            "question_id": question.id,
            "option_text": option.text,
            "section": question.section,
            "multi_select": question.multi_select,
        }
        await query.message.reply_text(
            messages.CUSTOM_OPTION_PROMPT or "Пожалуйста, напиши свой вариант."
        )
        return _state_for_question(question)

    if question.multi_select:
        user_data = ensure_user_data(context.user_data)
        toggle_multi_option(user_data, question, option)
        selected_keys = set(get_selected_option_keys(user_data, question.id))
        reply_markup = keyboards.question_options_keyboard(question, selected_keys)
        new_text = _format_question_text(question, user_data)
        await query.message.edit_text(
            text=new_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
        )
        set_current_question_message(
            user_data, query.message.chat_id, query.message.message_id
        )
        return _state_for_question(question)

    record_single_answer(context.user_data, question.id, option.text)
    chat_id = query.message.chat_id
    return await send_next_question(chat_id, context)


async def _handle_multi_done(
    query, context: Context, question: Question
) -> int:
    chat_id = query.message.chat_id
    return await send_next_question(chat_id, context)
async def handle_text_response(update: Update, context: Context) -> int:
    user_data = ensure_user_data(context.user_data)
    text = (update.message.text or "").strip()

    other_ctx = user_data.get(AWAITING_OTHER_KEY)
    if other_ctx:
        question_id = other_ctx["question_id"]
        question = get_question_by_id(question_id)
        if not question:
            user_data.pop(AWAITING_OTHER_KEY, None)
            await update.message.reply_text(messages.PRE_CHAT_REMINDER)
            return ConversationState.DIAGNOSIS

        if question.multi_select:
            option_text = other_ctx.get("option_text", "✍️ Другое")
            append_custom_answer(user_data, question_id, option_text, text)
            user_data.pop(AWAITING_OTHER_KEY, None)
            await _refresh_question_message(context, question, user_data)
            return _state_for_question(question)

        record_single_answer(user_data, question_id, text)
        user_data.pop(AWAITING_OTHER_KEY, None)
        return await _advance_after_text(update, context, question)

    awaiting_text_question = user_data.get(AWAITING_TEXT_KEY)
    if awaiting_text_question:
        question = get_question_by_id(awaiting_text_question)
        if question:
            record_single_answer(user_data, question.id, text)
            user_data.pop(AWAITING_TEXT_KEY, None)
            return await _advance_after_text(update, context, question)

    if user_data.get(REPORT_READY_KEY):
        return await handle_chat_message(update, context)

    await update.message.reply_text(messages.PRE_CHAT_REMINDER)
    return ConversationState.DIAGNOSIS


async def _advance_after_text(
    update: Update, context: Context, question: Question
) -> int:
    chat_id = update.message.chat_id
    return await send_next_question(chat_id, context)


def _build_user_metadata(user: Optional[User]) -> Dict[str, Any]:
    if not user:
        return {}

    full_name_parts = [user.first_name or "", user.last_name or ""]
    full_name = " ".join(part for part in full_name_parts if part).strip()

    return {
        "user_id": user.id,
        "username": user.username or "",
        "full_name": full_name,
    }


async def _store_answers_async(metadata: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    loop = asyncio.get_running_loop()

    def _task():
        sheets_service.store_answers(metadata, snapshot)

    await loop.run_in_executor(None, _task)


def _build_analysis_payload(user_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "skill_level": get_skill_level_text(user_data),
        "skill_level_key": user_data.get(SKILL_LEVEL_KEY),
        "answers": build_question_answer_pairs(user_data),
        "answers_by_id": collect_all_answers(user_data),
    }


async def _analyze_answers_async(payload: Dict[str, Any]) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, openai_service.analyze_answers, payload)


async def _generate_pdf_async(
    metadata: Dict[str, Any],
    user_data: Dict[str, Any],
    analysis: Dict[str, Any],
) -> Path:
    loop = asyncio.get_running_loop()

    def _task() -> Path:
        return pdf_service.generate_report(metadata, user_data, analysis)

    return await loop.run_in_executor(None, _task)


async def _schedule_follow_up(application, chat_id: int) -> None:
    await asyncio.sleep(30)
    keyboard = keyboards.consultation_keyboard()
    await application.bot.send_message(
        chat_id=chat_id,
        text=messages.POST_REPORT_MESSAGE,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )


def _build_chat_payload(user_data: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    analysis = user_data.get("analysis") or {}
    analysis_payload = user_data.get("analysis_payload") or {}
    history = get_chat_history(user_data)

    return {
        "analysis": analysis,
        "answers": analysis_payload.get("answers") or build_question_answer_pairs(user_data),
        "answers_by_id": analysis_payload.get("answers_by_id") or collect_all_answers(user_data),
        "skill_level": get_skill_level_text(user_data),
        "history": history,
        "user_message": user_message,
    }


async def _generate_chat_reply_async(payload: Dict[str, Any]) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, openai_service.generate_chat_reply, payload)


async def handle_questionnaire_complete(chat_id: int, context: Context) -> int:
    context.user_data[DIAGNOSIS_COMPLETE_KEY] = True
    await context.bot.send_message(
        chat_id=chat_id,
        text=messages.PRE_REPORT_MESSAGE,
        reply_markup=(
            keyboards.single_button_keyboard(messages.REPORT_BUTTON)
            if messages.REPORT_BUTTON[1]
            else None
        ),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ConversationState.REPORT


async def handle_report_request(update: Update, context: Context) -> int:
    query = update.callback_query
    await query.answer()
    user_data = ensure_user_data(context.user_data)

    if not user_data.get(DIAGNOSIS_COMPLETE_KEY):
        await query.message.reply_text(messages.PRE_CHAT_REMINDER)
        return ConversationState.REPORT

    metadata = _build_user_metadata(query.from_user)

    if not user_data.get(SHEETS_SAVED_KEY):
        snapshot = copy.deepcopy(user_data)
        await _store_answers_async(metadata, snapshot)
        user_data[SHEETS_SAVED_KEY] = True

    snapshot = copy.deepcopy(user_data)
    analysis_payload = _build_analysis_payload(snapshot)
    analysis = await _analyze_answers_async(analysis_payload)
    pdf_path = await _generate_pdf_async(metadata, snapshot, analysis)

    chat_id = query.message.chat_id

    try:
        with pdf_path.open("rb") as pdf_file:
            await context.bot.send_document(
                chat_id=chat_id,
                document=pdf_file,
                filename=pdf_path.name,
                caption=messages.REPORT_DELIVERY_MESSAGE,
                parse_mode=ParseMode.MARKDOWN,
            )
    finally:
        pdf_path.unlink(missing_ok=True)

    context.user_data[REPORT_READY_KEY] = True
    context.user_data["analysis"] = analysis
    context.user_data["analysis_payload"] = analysis_payload
    context.user_data["answers_snapshot"] = snapshot

    follow_up_task = _schedule_follow_up(context.application, chat_id)
    context.application.create_task(follow_up_task)

    return ConversationState.REPORT


async def handle_chat_message(update: Update, context: Context) -> int:
    user_data = ensure_user_data(context.user_data)

    if not user_data.get(REPORT_READY_KEY):
        await update.message.reply_text(messages.PRE_CHAT_REMINDER)
        return ConversationState.REPORT

    user_message = (update.message.text or "").strip()
    if not user_message:
        await update.message.reply_text(messages.CHAT_FALLBACK_MESSAGE)
        return ConversationState.CHAT

    append_chat_history(user_data, "user", user_message)
    payload = _build_chat_payload(user_data, user_message)
    reply = await _generate_chat_reply_async(payload)

    if reply:
        append_chat_history(user_data, "assistant", reply)
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text(messages.CHAT_FALLBACK_MESSAGE)

    return ConversationState.CHAT
