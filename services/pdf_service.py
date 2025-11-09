"""PDF generation service."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from config import settings
from bot import utils
from templates import report_static

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

DEFAULT_FONT_NAME = "Helvetica"


def generate_report(
    metadata: Dict[str, Any],
    user_data: Dict[str, Any],
    analysis: Dict[str, Any],
) -> Path:
    """Generate a PDF report and return its path."""
    font_name = _ensure_font()
    styles = _build_styles(font_name)

    file_name = _build_file_name(metadata)
    file_path = REPORTS_DIR / file_name

    doc = SimpleDocTemplate(
        str(file_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    story: List[Any] = []
    _build_header(story, metadata, user_data, styles)
    _build_intro(story, styles)
    _build_dynamic_sections(story, user_data, analysis, styles)
    _build_static_sections(story, styles)

    doc.build(story)
    return file_path


def _ensure_font() -> str:
    font_path = getattr(settings, "pdf_font_path", "").strip()
    if font_path:
        path_obj = Path(font_path)
        if path_obj.exists():
            font_name = path_obj.stem
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(path_obj)))
                return font_name
            except Exception:  # pragma: no cover - fallback on font load error
                pass
    return DEFAULT_FONT_NAME


def _build_styles(font_name: str) -> StyleSheet1:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=20,
            leading=26,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#1F1F1F"),
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportHeading",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1A73E8"),
            spaceBefore=16,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportBody",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#202124"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportMeta",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#5F6368"),
            spaceAfter=4,
        )
    )
    return styles


def _build_header(story: List[Any], metadata: Dict[str, Any], user_data: Dict[str, Any], styles: StyleSheet1) -> None:
    story.append(Paragraph(report_static.REPORT_TITLE, styles["ReportTitle"]))

    today = datetime.now().strftime("%d.%m.%Y")
    skill_level = utils.get_skill_level_text(user_data) or "не указан"
    client_name = metadata.get("full_name") or metadata.get("username") or "Клиент 1ma.ai"

    meta_lines = [
        f"Дата: {today}",
        f"Клиент: {html.escape(client_name)}",
        f"Уровень компетенций в ИИ: {html.escape(skill_level)}",
    ]

    for line in meta_lines:
        story.append(Paragraph(line, styles["ReportMeta"]))

    story.append(Spacer(1, 6))


def _build_intro(story: List[Any], styles: StyleSheet1) -> None:
    for paragraph in report_static.INTRO_PARAGRAPHS:
        story.append(Paragraph(html.escape(paragraph), styles["ReportBody"]))
    story.append(Spacer(1, 10))


def _build_dynamic_sections(
    story: List[Any],
    user_data: Dict[str, Any],
    analysis: Dict[str, Any],
    styles: StyleSheet1,
) -> None:
    answers_map = utils.collect_all_answers(user_data)
    pairs = utils.build_question_answer_pairs(user_data)

    business_summary = analysis.get("business_summary", "")
    priority_processes = analysis.get("priority_processes", [])
    ai_opportunities = analysis.get("ai_opportunities", [])
    quick_wins = analysis.get("quick_wins", [])
    long_term = analysis.get("long_term", [])
    next_steps = analysis.get("next_steps", [])
    recommended_tools = analysis.get("recommended_tools", [])
    gpt_prompts = analysis.get("gpt_prompts", [])

    _add_section(story, "Кратко о бизнесе", styles)
    if business_summary:
        story.append(Paragraph(html.escape(business_summary), styles["ReportBody"]))
    else:
        story.append(Paragraph("Нет данных — заполни анкету подробнее, чтобы получить персональный разбор.", styles["ReportBody"]))

    _add_section(story, "Приоритетные процессы", styles)
    _add_bullet_list(story, priority_processes, styles)

    _add_section(story, "Возможности для внедрения ИИ", styles)
    _add_bullet_list(story, ai_opportunities, styles)

    _add_section(story, "Быстрые победы — Quick wins", styles)
    _add_bullet_list(story, quick_wins, styles)

    _add_section(story, "Долгосрочные инициативы", styles)
    _add_bullet_list(story, long_term, styles)

    _add_section(story, "Следующие шаги", styles)
    _add_bullet_list(story, next_steps, styles)

    _add_section(story, "Рекомендуемые инструменты и интеграции", styles)
    _add_bullet_list(story, recommended_tools, styles)

    _add_section(story, "Готовые промпты для GPT", styles)
    _add_numbered_list(story, gpt_prompts, styles)

    _add_section(story, "Ключевые ответы диагностики", styles)
    for pair in pairs[:6]:
        answer = pair["answer"].strip()
        if not answer:
            continue
        story.append(
            Paragraph(
                f"<b>{html.escape(pair['question'])}</b><br/>{html.escape(answer)}",
                styles["ReportBody"],
            )
        )


def _build_static_sections(story: List[Any], styles: StyleSheet1) -> None:
    _add_section(story, "Чек-лист внедрения ИИ", styles)
    _add_bullet_list(story, report_static.CHECKLIST_ITEMS, styles)

    for section in report_static.STATIC_SECTIONS:
        _add_section(story, section["title"], styles)
        _add_bullet_list(story, section["bullets"], styles)


def _add_section(story: List[Any], title: str, styles: StyleSheet1) -> None:
    story.append(Paragraph(html.escape(title), styles["ReportHeading"]))


def _add_bullet_list(story: List[Any], items: Iterable[Any], styles: StyleSheet1) -> None:
    clean_items = [item for item in items if isinstance(item, str) and item.strip()]
    if not clean_items:
        story.append(Paragraph("—", styles["ReportBody"]))
        return

    bullet_items: List[ListItem] = []
    for item in clean_items:
        paragraph = Paragraph(html.escape(item), styles["ReportBody"])
        bullet_items.append(ListItem(paragraph, leftIndent=0, bulletColor=colors.HexColor("#1A73E8")))

    story.append(
        ListFlowable(
            bullet_items,
            bulletType="bullet",
            start="circle",
            bulletFontSize=6,
            bulletColor=colors.HexColor("#1A73E8"),
            leftIndent=12,
        )
    )


def _add_numbered_list(story: List[Any], items: Iterable[Any], styles: StyleSheet1) -> None:
    clean_items = [item for item in items if isinstance(item, str) and item.strip()]
    if not clean_items:
        story.append(Paragraph("—", styles["ReportBody"]))
        return

    bullet_items: List[ListItem] = []
    for item in clean_items:
        paragraph = Paragraph(html.escape(item), styles["ReportBody"])
        bullet_items.append(ListItem(paragraph, leftIndent=0))

    story.append(
        ListFlowable(
            bullet_items,
            bulletType="1",
            start=1,
            leftIndent=12,
        )
    )


def _build_file_name(metadata: Dict[str, Any]) -> str:
    user_id = metadata.get("user_id") or "client"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"report_{user_id}_{timestamp}.pdf"
