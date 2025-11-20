import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';
import PDFDocument from 'pdfkit';
import settings from '../config/settings.js';
import { getSkillLevelText, buildQuestionAnswerPairs } from '../bot/utils.js';
import reportStatic from '../templates/reportStatic.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function registerFont(doc) {
  const envFontPath = (settings.pdfFontPath || '').trim();
  const candidatePaths = [envFontPath]
    .filter(Boolean)
    .concat([
      path.resolve(process.cwd(), 'fonts', 'DejaVuSans.ttf'),
      path.resolve(__dirname, '../../fonts/DejaVuSans.ttf')
    ]);

  for (const candidate of candidatePaths) {
    if (!fs.existsSync(candidate)) continue;

    try {
      doc.registerFont('CustomFont', candidate);
      return 'CustomFont';
    } catch (error) {
      console.warn('[pdf] failed to register font', { candidate, error });
    }
  }

  return 'Helvetica';
}

export async function generateReport(metadata, userData, analysis) {
  const filename = buildFileName(metadata);
  const outputDir = process.env.PDF_OUTPUT_DIR || path.join(os.tmpdir(), 'tg-transformator-reports');
  fs.mkdirSync(outputDir, { recursive: true });
  const filePath = path.join(outputDir, filename);

  return new Promise((resolve, reject) => {
    try {
      const doc = new PDFDocument({ size: 'A4', margin: 48 });
      const stream = fs.createWriteStream(filePath);
      doc.pipe(stream);

      const fontName = registerFont(doc);
      doc.font(fontName);
      buildReport(doc, metadata, userData, analysis, fontName);

      doc.end();
      stream.on('finish', () => resolve(filePath));
      stream.on('error', reject);
    } catch (error) {
      console.error('[pdf] generation error', error);
      reject(error);
    }
  });
}

function buildFileName(metadata = {}) {
  const userId = metadata.user_id || metadata.userId || 'client';
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  return `report_${userId}_${timestamp}.pdf`;
}

function buildReport(doc, metadata, userData, analysis, fontName) {
  doc.font(fontName).fontSize(20).text(reportStatic.title, { align: 'left' }).moveDown();

  const today = new Date().toLocaleDateString('ru-RU');
  const skill = getSkillLevelText(userData) || 'не указан';
  const clientName = metadata.full_name || metadata.username || 'Клиент 1ma.ai';

  doc.font(fontName).fontSize(10).fillColor('#555555');
  doc.text(`Дата: ${today}`);
  doc.text(`Клиент: ${clientName}`);
  doc.text(`Уровень компетенций в ИИ: ${skill}`);
  doc.moveDown();

  doc.font(fontName).fontSize(11).fillColor('#202124');
  for (const paragraph of reportStatic.introParagraphs) {
    doc.text(paragraph);
    doc.moveDown(0.5);
  }

  const sections = [
    { title: 'Кратко о бизнесе', content: [analysis.business_summary || 'Нет данных'] },
    { title: 'Приоритетные процессы', content: analysis.priority_processes || [] },
    { title: 'Возможности для внедрения ИИ', content: analysis.ai_opportunities || [] },
    { title: 'Быстрые победы — Quick wins', content: analysis.quick_wins || [] },
    { title: 'Долгосрочные инициативы', content: analysis.long_term || [] },
    { title: 'Следующие шаги', content: analysis.next_steps || [] },
    { title: 'Рекомендуемые инструменты и интеграции', content: analysis.recommended_tools || [] },
    { title: 'Готовые промпты для GPT', content: analysis.gpt_prompts || [] }
  ];

  sections.forEach(({ title, content }) => {
    doc.moveDown();
    doc.font(fontName).fontSize(14).fillColor('#1A73E8').text(title);
    doc.moveDown(0.3);
    doc.font(fontName).fontSize(11).fillColor('#202124');
    if (!content || content.length === 0) {
      doc.text('—');
    } else if (Array.isArray(content)) {
      content.forEach((item) => doc.text(`• ${item}`));
    } else {
      doc.text(content);
    }
  });

  doc.moveDown();
  doc.font(fontName).fontSize(14).fillColor('#1A73E8').text('Ключевые ответы диагностики');
  doc.moveDown(0.3).font(fontName).fontSize(11).fillColor('#202124');
  const pairs = buildQuestionAnswerPairs(userData).slice(0, 6);
  pairs.forEach(({ question, answer }) => {
    if (!answer?.trim()) return;
    doc.font(fontName).fontSize(12).fillColor('#202124').text(question);
    doc.font(fontName).fontSize(11).fillColor('#202124').text(answer).moveDown(0.5);
  });

  doc.moveDown();
  doc.font(fontName).fontSize(14).fillColor('#1A73E8').text('Чек-лист внедрения ИИ');
  doc.moveDown(0.3).font(fontName).fontSize(11).fillColor('#202124');
  (reportStatic.checklistItems || []).forEach((item) => doc.text(`• ${item}`));

  (reportStatic.staticSections || []).forEach((section) => {
    doc.moveDown();
    doc.font(fontName).fontSize(14).fillColor('#1A73E8').text(section.title);
    doc.moveDown(0.3).font(fontName).fontSize(11).fillColor('#202124');
    section.bullets.forEach((item) => doc.text(`• ${item}`));
  });
}
