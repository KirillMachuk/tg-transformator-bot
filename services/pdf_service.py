"""PDF generation service."""

from __future__ import annotations

import html
import logging
import os
import tempfile
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

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(os.getenv("PDF_OUTPUT_DIR", tempfile.gettempdir())) / "tg_transformator_reports"
REPORTS_DIR.mkdir(exist_ok=True, parents=True)

DEFAULT_FONT_NAME = "Helvetica"


def _prepare_text(text: str) -> str:
    """Prepare text for PDF: ensure Unicode string and escape HTML."""
    if text is None:
        return ""
    
    if isinstance(text, bytes):
        try:
            text = text.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text = text.decode('latin-1')
            except UnicodeDecodeError:
                text = text.decode('utf-8', errors='replace')
    
    # Ensure it's a string
    text = str(text)
    
    # Verify it's actually Unicode (not already encoded)
    try:
        text.encode('utf-8').decode('utf-8')
    except Exception:
        logger.warning(f"Text encoding issue detected: {text[:50]}")
    
    # Escape HTML but preserve Unicode characters
    escaped = html.escape(text)
    
    # Log if we have Cyrillic characters
    if any('\u0400' <= char <= '\u04FF' for char in text):
        logger.debug(f"Prepared text with Cyrillic: {text[:30]}...")
    
    return escaped


def generate_report(
    metadata: Dict[str, Any],
    user_data: Dict[str, Any],
    analysis: Dict[str, Any],
) -> Path:
    """Generate a PDF report and return its path."""
    logger.info("=" * 60)
    logger.info("Starting PDF generation with Cyrillic support")
    logger.info("=" * 60)
    
    font_name = _ensure_font()
    
    # Verify font is registered and log details
    registered_fonts = pdfmetrics.getRegisteredFontNames()
    logger.info(f"Registered fonts: {registered_fonts}")
    
    if font_name not in registered_fonts and font_name != DEFAULT_FONT_NAME:
        logger.error(f"Font {font_name} is not registered! Available fonts: {registered_fonts}")
        font_name = DEFAULT_FONT_NAME
        logger.warning(f"Falling back to {DEFAULT_FONT_NAME} - Cyrillic will NOT display correctly!")
    else:
        logger.info(f"✓ Using font: {font_name} (registered: {font_name in registered_fonts})")
        if font_name == DEFAULT_FONT_NAME:
            logger.warning("⚠ Using default Helvetica - Cyrillic will NOT display correctly! Set PDF_FONT_PATH in .env")
        else:
            logger.info(f"✓ Font {font_name} is ready for Cyrillic text")
    
    styles = _build_styles(font_name)
    
    # Test Cyrillic rendering
    test_text = "Тест кириллицы: Привет, мир!"
    logger.debug(f"Test Cyrillic text: {test_text}")
    logger.debug(f"Test text encoding: {test_text.encode('utf-8')}")

    file_name = _build_file_name(metadata)
    file_path = REPORTS_DIR / file_name

    doc = SimpleDocTemplate(
        str(file_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        # Ensure fonts are embedded in PDF for proper display
        embedFonts=True,
    )

    story: List[Any] = []
    _build_header(story, metadata, user_data, styles)
    _build_intro(story, styles)
    _build_dynamic_sections(story, user_data, analysis, styles)
    _build_static_sections(story, styles)

    doc.build(story)
    return file_path


def _ensure_font() -> str:
    """Register and return font name for Cyrillic support."""
    font_path = getattr(settings, "pdf_font_path", "").strip()
    
    # Remove quotes if present (from .env)
    if font_path.startswith('"') and font_path.endswith('"'):
        font_path = font_path[1:-1]
    if font_path.startswith("'") and font_path.endswith("'"):
        font_path = font_path[1:-1]
    
    if font_path:
        # Try absolute path first, then relative
        path_obj = Path(font_path)
        if not path_obj.is_absolute():
            # Try relative to project root
            project_root = Path(__file__).parent.parent
            path_obj = project_root / font_path
        
        if path_obj.exists():
            font_name = path_obj.stem
            logger.info(f"Attempting to register font: {font_name} from {path_obj}")
            
            try:
                # Check if font is already registered
                if font_name not in pdfmetrics.getRegisteredFontNames():
                    # Register TTFont for Cyrillic support
                    # Method 1: Try with subfontIndex=0 (main Unicode table)
                    registered = False
                    try:
                        ttf_font = TTFont(font_name, str(path_obj), subfontIndex=0)
                        pdfmetrics.registerFont(ttf_font)
                        logger.info(f"✓ Registered font: {font_name} with subfontIndex=0")
                        registered = True
                    except Exception as subfont_error:
                        logger.warning(f"Method 1 failed (subfontIndex=0): {subfont_error}")
                        
                        # Method 2: Try without subfontIndex
                        try:
                            ttf_font = TTFont(font_name, str(path_obj))
                            pdfmetrics.registerFont(ttf_font)
                            logger.info(f"✓ Registered font: {font_name} without subfontIndex")
                            registered = True
                        except Exception as no_subfont_error:
                            logger.error(f"Method 2 also failed: {no_subfont_error}")
                    
                    # Verify registration
                    if registered and font_name in pdfmetrics.getRegisteredFontNames():
                        logger.info(f"✓ Font {font_name} successfully registered and verified")
                        # Test with a Cyrillic character
                        try:
                            test_font = pdfmetrics.getFont(font_name)
                            logger.info(f"✓ Font object retrieved: {type(test_font)}")
                        except Exception as test_error:
                            logger.warning(f"Could not retrieve font object: {test_error}")
                    else:
                        raise RuntimeError(f"Font {font_name} was not registered properly")
                else:
                    logger.info(f"Font {font_name} already registered")
                
                return font_name
            except Exception as e:
                logger.error(f"Failed to register font {path_obj}: {e}", exc_info=True)
        else:
            logger.error(f"Font file not found: {path_obj} (resolved from: {font_path})")
    else:
        logger.warning("PDF_FONT_PATH not set, using default Helvetica (Cyrillic will NOT display)")
    
    return DEFAULT_FONT_NAME


def _build_styles(font_name: str) -> StyleSheet1:
    """Build paragraph styles with the specified font."""
    styles = getSampleStyleSheet()
    
    # Verify font is available before using it
    registered_fonts = pdfmetrics.getRegisteredFontNames()
    if font_name not in registered_fonts:
        logger.error(f"Font {font_name} not in registered fonts: {registered_fonts}")
        logger.warning(f"Falling back to Helvetica - Cyrillic will NOT display!")
        font_name = DEFAULT_FONT_NAME
    
    # Create styles without parent to ensure font is used correctly
    # This prevents font inheritance issues with Cyrillic fonts
    style_configs = [
        {
            "name": "ReportTitle",
            "fontName": font_name,
            "fontSize": 20,
            "leading": 26,
            "alignment": TA_LEFT,
            "textColor": colors.HexColor("#1F1F1F"),
            "spaceAfter": 12,
        },
        {
            "name": "ReportHeading",
            "fontName": font_name,
            "fontSize": 14,
            "leading": 18,
            "textColor": colors.HexColor("#1A73E8"),
            "spaceBefore": 16,
            "spaceAfter": 8,
        },
        {
            "name": "ReportBody",
            "fontName": font_name,
            "fontSize": 11,
            "leading": 15,
            "textColor": colors.HexColor("#202124"),
            "spaceAfter": 6,
        },
        {
            "name": "ReportMeta",
            "fontName": font_name,
            "fontSize": 10,
            "leading": 13,
            "textColor": colors.HexColor("#5F6368"),
            "spaceAfter": 4,
        },
    ]
    
    for config in style_configs:
        try:
            styles.add(ParagraphStyle(**config))
            logger.debug(f"Created style {config['name']} with font {font_name}")
        except Exception as e:
            logger.error(f"Failed to create style {config['name']}: {e}")
            # Fallback to default font
            config["fontName"] = DEFAULT_FONT_NAME
            styles.add(ParagraphStyle(**config))
    
    logger.info(f"All styles created with font: {font_name}")
    return styles


def _build_header(story: List[Any], metadata: Dict[str, Any], user_data: Dict[str, Any], styles: StyleSheet1) -> None:
    story.append(Paragraph(_prepare_text(report_static.REPORT_TITLE), styles["ReportTitle"]))

    today = datetime.now().strftime("%d.%m.%Y")
    skill_level = utils.get_skill_level_text(user_data) or "не указан"
    client_name = metadata.get("full_name") or metadata.get("username") or "Клиент 1ma.ai"

    meta_lines = [
        f"Дата: {today}",
        f"Клиент: {_prepare_text(client_name)}",
        f"Уровень компетенций в ИИ: {_prepare_text(skill_level)}",
    ]

    for line in meta_lines:
        story.append(Paragraph(line, styles["ReportMeta"]))

    story.append(Spacer(1, 6))


def _build_intro(story: List[Any], styles: StyleSheet1) -> None:
    for paragraph in report_static.INTRO_PARAGRAPHS:
        story.append(Paragraph(_prepare_text(paragraph), styles["ReportBody"]))
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
        story.append(Paragraph(_prepare_text(business_summary), styles["ReportBody"]))
    else:
        story.append(Paragraph(_prepare_text("Нет данных — заполни анкету подробнее, чтобы получить персональный разбор."), styles["ReportBody"]))

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
                f"<b>{_prepare_text(pair['question'])}</b><br/>{_prepare_text(answer)}",
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
    story.append(Paragraph(_prepare_text(title), styles["ReportHeading"]))


def _add_bullet_list(story: List[Any], items: Iterable[Any], styles: StyleSheet1) -> None:
    clean_items = [item for item in items if isinstance(item, str) and item.strip()]
    if not clean_items:
        story.append(Paragraph("—", styles["ReportBody"]))
        return

    bullet_items: List[ListItem] = []
    for item in clean_items:
        paragraph = Paragraph(_prepare_text(item), styles["ReportBody"])
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
        paragraph = Paragraph(_prepare_text(item), styles["ReportBody"])
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
