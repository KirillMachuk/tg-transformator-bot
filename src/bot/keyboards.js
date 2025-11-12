import { Markup } from 'telegraf';
import settings from '../config/settings.js';
import * as messages from './messages.js';

export function skillLevelKeyboard() {
  const rows = messages.SKILL_LEVEL_OPTIONS
    .filter(([, text]) => Boolean(text))
    .map(([callbackData, text]) => [Markup.button.callback(text, callbackData)]);
  return Markup.inlineKeyboard(rows);
}

export function startKeyboard() {
  return singleButtonKeyboard(messages.START_BUTTON);
}

export function singleButtonKeyboard([callbackData, text]) {
  return Markup.inlineKeyboard([[Markup.button.callback(text, callbackData)]]);
}

export function questionOptionsKeyboard(question, selectedOptions = new Set()) {
  const rows = [];

  if (Array.isArray(question?.options)) {
    for (const option of question.options) {
      const buttonText = option.text;
      rows.push([
        Markup.button.callback(buttonText, `q|${question.id}|${option.key}`)
      ]);
    }
  }

  if (question?.multiSelect) {
    rows.push([
      Markup.button.callback(messages.MULTI_SELECT_DONE_BUTTON[1], `q|${question.id}|done`)
    ]);
  }

  return Markup.inlineKeyboard(rows);
}

export function consultationKeyboard() {
  const url = (settings.consultationUrl || '').trim();
  if (!url) return null;
  return Markup.inlineKeyboard([[Markup.button.url(messages.CONSULTATION_BUTTON_TEXT, url)]]);
}
