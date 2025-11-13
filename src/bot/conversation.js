import { Markup } from 'telegraf';
import settings from '../config/settings.js';
import * as messages from './messages.js';
import {
  STATE,
  SKILL_LEVEL_KEY,
  AWAITING_TEXT_KEY,
  AWAITING_OTHER_KEY,
  REPORT_READY_KEY,
  DIAGNOSIS_COMPLETE_KEY,
  SHEETS_SAVED_KEY,
  ANSWERS_KEY
} from './constants.js';
import {
  resetUserSession,
  getUserSession,
  getCurrentQuestion,
  advanceQuestion,
  toggleMultiOption,
  recordSingleAnswer,
  appendCustomAnswer,
  getQuestionById,
  getSelectedOptionKeys,
  setCurrentQuestionMessage,
  getCurrentQuestionMessage,
  getSkillLevelText,
  buildQuestionAnswerPairs,
  collectAllAnswers,
  appendChatHistory,
  getChatHistory
} from './utils.js';
import { skillLevelKeyboard, startKeyboard, questionOptionsKeyboard, singleButtonKeyboard, consultationKeyboard } from './keyboards.js';
import { analyzeAnswers, generateChatReply } from '../services/openai.js';
import { generateReport } from '../services/pdf.js';
import { storeAnswers } from '../services/sheets.js';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const MarkdownExtra = { parse_mode: 'HTML', disable_web_page_preview: false };

export function setupConversation(bot) {
  bot.start(handleStartCommand);

  bot.action(messages.START_BUTTON[0], async (ctx) => {
    await ctx.answerCbQuery();
    const userData = getUserSession(ctx.chat.id);
    userData.state = STATE.SKILL_LEVEL;
    await ctx.reply(messages.SKILL_LEVEL_PROMPT, {
      ...MarkdownExtra,
      ...skillLevelKeyboard()
    });
  });

  bot.action(/^skill_level_/, handleSkillSelection);
  bot.action(/^(video_ready|start_diagnosis)$/, handleVideoConfirmation);
  bot.action(/^q\|/, handleQuestionCallback);
  bot.action(messages.REPORT_BUTTON[0], handleReportRequest);

  bot.on('text', handleTextMessage);
  bot.on('message', handleNonTextMessage);
}

async function handleStartCommand(ctx) {
  const chatId = ctx.chat.id;
  const userData = resetUserSession(chatId);
  userData.state = STATE.WELCOME;

  await ctx.reply(messages.WELCOME_TEXT, {
    ...MarkdownExtra,
    ...startKeyboard()
  });
}

async function handleSkillSelection(ctx) {
  const chatId = ctx.chat.id;
  const userData = getUserSession(chatId);
  userData.state = STATE.SKILL_LEVEL;

  const choice = ctx.callbackQuery.data;
  userData[SKILL_LEVEL_KEY] = choice;
  await ctx.answerCbQuery();

  if (choice === messages.SKILL_LEVEL_OPTIONS[0][0] || choice === messages.SKILL_LEVEL_OPTIONS[1][0]) {
    userData.state = STATE.VIDEO;
    await ctx.reply(messages.VIDEO_MESSAGE, {
      ...MarkdownExtra
    });
    // Send video file
    const { LESSON_VIDEO_FILE_ID } = await import('./constants.js');
    if (LESSON_VIDEO_FILE_ID) {
      await ctx.replyWithVideo(LESSON_VIDEO_FILE_ID);
    } else {
      console.log('[video] Video file_id not set in constants.js');
    }
    // Send message with button after video
    await ctx.reply(messages.VIDEO_READY_MESSAGE, {
      ...MarkdownExtra,
      ...singleButtonKeyboard(messages.VIDEO_READY_BUTTON)
    });
    return;
  }

  userData.state = STATE.VIDEO;
  await ctx.reply(messages.EXPERT_SKIP_MESSAGE, {
    ...MarkdownExtra,
    ...singleButtonKeyboard(messages.DIAGNOSIS_BUTTON)
  });
}

async function handleVideoConfirmation(ctx) {
  const chatId = ctx.chat.id;
  await ctx.answerCbQuery();
  await startDiagnosisFlow(ctx, chatId, true);
}

async function startDiagnosisFlow(ctx, chatId, isNew = false) {
  const userData = getUserSession(chatId);
  userData.state = STATE.DIAGNOSIS;

  if (isNew) {
    await ctx.reply(messages.DIAGNOSIS_INTRO, MarkdownExtra);
  }

  await sendNextQuestion(ctx, chatId, { isNew: true });
}

async function sendNextQuestion(ctx, chatId, { isNew = false } = {}) {
  const userData = getUserSession(chatId);

  const question = isNew ? getCurrentQuestion(userData) : advanceQuestion(userData);
  if (!question) {
    return handleQuestionnaireComplete(ctx, chatId);
  }

  return sendQuestion(ctx, chatId, question, userData);
}

async function sendQuestion(ctx, chatId, question, userData) {
  delete userData[AWAITING_TEXT_KEY];
  delete userData[AWAITING_OTHER_KEY];

  const selectedKeys = new Set(getSelectedOptionKeys(userData, question.id));
  const keyboard = question.options
    ? questionOptionsKeyboard(question, selectedKeys)
    : undefined;

  if (!question.options && question.expectsText) {
    userData[AWAITING_TEXT_KEY] = question.id;
  }

  const message = await ctx.telegram.sendMessage(chatId, formatQuestionText(question, userData), {
    ...MarkdownExtra,
    ...(keyboard || {})
  });

  setCurrentQuestionMessage(userData, chatId, message.message_id);
  userData.state = question.section === 'readiness' ? STATE.READINESS : STATE.DIAGNOSIS;
  return message;
}

function formatQuestionText(question, userData) {
  const answer = getQuestionAnswerSummary(question, userData);
  if (answer) {
    return `${question.text}\n\n<b>Выбрано:</b>\n${answer}`;
  }
  return question.text;
}

function getQuestionAnswerSummary(question, userData) {
  const lines = [];
  const selected = getSelectedOptionKeys(userData, question.id) || [];
  const answersMap = userData[ANSWERS_KEY] || {};
  const entry = answersMap[question.id];

  if (selected.length && Array.isArray(question.options)) {
    for (const key of selected) {
      const option = question.options.find((opt) => opt.key === key);
      if (option) lines.push(`- ${option.text}`);
    }
  }

  if (entry && Array.isArray(entry.custom)) {
    for (const custom of entry.custom) {
      if (custom?.value) {
        lines.push(`- ${custom.option || '✍️ Другое'}: ${custom.value}`);
      }
    }
  }

  return lines.join('\n');
}

async function handleQuestionCallback(ctx) {
  await ctx.answerCbQuery();

  const chatId = ctx.chat.id;
  const userData = getUserSession(chatId);
  const [_, questionId, payload] = ctx.callbackQuery.data.split('|');
  const question = getQuestionById(questionId);
  if (!question) {
    return ctx.answerCbQuery('Неизвестный вопрос');
  }

  if (payload === 'done') {
    return sendNextQuestion(ctx, chatId);
  }

  const option = question.options?.find((opt) => opt.key === payload);
  if (!option) {
    return ctx.answerCbQuery('Неизвестный вариант');
  }

  if (option.requiresFreeText) {
    userData[AWAITING_OTHER_KEY] = {
      questionId: question.id,
      optionText: option.text,
      section: question.section,
      multiSelect: Boolean(question.multiSelect)
    };
    await ctx.reply(messages.CUSTOM_OPTION_PROMPT);
    return;
  }

  if (question.multiSelect) {
    toggleMultiOption(userData, question, option);
    const selectedKeys = new Set(getSelectedOptionKeys(userData, question.id));
    const keyboard = questionOptionsKeyboard(question, selectedKeys);
    const summary = formatQuestionText(question, userData);
    const msgRef = getCurrentQuestionMessage(userData);
    if (msgRef) {
      await ctx.telegram.editMessageText(msgRef.chatId, msgRef.messageId, undefined, summary, {
        ...MarkdownExtra,
        ...(keyboard || {})
      });
    }
    return;
  }

  recordSingleAnswer(userData, question.id, option.text);
  return sendNextQuestion(ctx, chatId);
}

async function handleTextMessage(ctx) {
  const chatId = ctx.chat.id;
  const userData = getUserSession(chatId);
  const text = ctx.message.text?.trim() || '';

  // Handle awaited "other" input
  const awaitingOther = userData[AWAITING_OTHER_KEY];
  if (awaitingOther) {
    const question = getQuestionById(awaitingOther.questionId);
    if (!question) {
      delete userData[AWAITING_OTHER_KEY];
      await ctx.reply(messages.PRE_CHAT_REMINDER);
      return;
    }

    if (awaitingOther.multiSelect) {
      appendCustomAnswer(userData, question.id, awaitingOther.optionText || '✍️ Другое', text);
      delete userData[AWAITING_OTHER_KEY];
      const keyboard = questionOptionsKeyboard(question, new Set(getSelectedOptionKeys(userData, question.id)));
      const summary = formatQuestionText(question, userData);
      const msgRef = getCurrentQuestionMessage(userData);
      if (msgRef) {
        await ctx.telegram.editMessageText(msgRef.chatId, msgRef.messageId, undefined, summary, {
          ...MarkdownExtra,
          ...(keyboard || {})
        });
      }
      return;
    }

    recordSingleAnswer(userData, question.id, text);
    delete userData[AWAITING_OTHER_KEY];
    return sendNextQuestion(ctx, chatId);
  }

  const awaitingTextId = userData[AWAITING_TEXT_KEY];
  if (awaitingTextId) {
    const question = getQuestionById(awaitingTextId);
    if (question) {
      recordSingleAnswer(userData, question.id, text);
      delete userData[AWAITING_TEXT_KEY];
      return sendNextQuestion(ctx, chatId);
    }
  }

  if (!userData[REPORT_READY_KEY]) {
    await ctx.reply(messages.PRE_CHAT_REMINDER);
    return;
  }

  await handleChatMessage(ctx, text, userData);
}

async function handleNonTextMessage(ctx) {
  if (ctx.message?.text) return; // already handled in text handler
  const userData = getUserSession(ctx.chat.id);
  if (!userData[REPORT_READY_KEY]) {
    await ctx.reply(messages.PRE_CHAT_REMINDER);
    return;
  }
  await ctx.reply(messages.CHAT_FALLBACK_MESSAGE);
}

async function handleQuestionnaireComplete(ctx, chatId) {
  const userData = getUserSession(chatId);
  userData[DIAGNOSIS_COMPLETE_KEY] = true;
  userData.state = STATE.REPORT;

  const keyboard = messages.REPORT_BUTTON[1]
    ? singleButtonKeyboard(messages.REPORT_BUTTON)
    : undefined;

  await ctx.telegram.sendMessage(chatId, messages.PRE_REPORT_MESSAGE, {
    ...MarkdownExtra,
    ...(keyboard || {})
  });
}

async function handleReportRequest(ctx) {
  const chatId = ctx.chat.id;
  const userData = getUserSession(chatId);
  await ctx.answerCbQuery();

  if (!userData[DIAGNOSIS_COMPLETE_KEY]) {
    await ctx.reply(messages.PRE_CHAT_REMINDER);
    return;
  }

  const metadata = buildUserMetadata(ctx.from);
  metadata.skill_level = getSkillLevelText(userData);
  metadata.timestamp = new Date().toISOString();

  if (!userData[SHEETS_SAVED_KEY]) {
    try {
      await storeAnswers(metadata, userData);
      userData[SHEETS_SAVED_KEY] = true;
    } catch (error) {
      console.error('[sheets] store error', error);
    }
  }

  const snapshot = JSON.parse(JSON.stringify(userData));
  const analysisPayload = buildAnalysisPayload(snapshot);
  const analysis = await analyzeAnswers(analysisPayload);
  const pdfPath = await generateReport(metadata, snapshot, analysis);

  try {
    if (pdfPath) {
      await ctx.replyWithDocument({ source: pdfPath, filename: pdfPath.split('/').pop() }, {
        caption: messages.REPORT_DELIVERY_MESSAGE,
        parse_mode: 'HTML'
      });
      await fs.unlink(pdfPath).catch(() => {});
    } else {
      await ctx.reply('Не удалось сформировать PDF-отчёт. Попробуй позже.');
    }
  } catch (error) {
    console.error('[pdf] send error', error);
    await ctx.reply('Не удалось отправить отчёт. Попробуй позже.');
  }

  userData[REPORT_READY_KEY] = true;
  userData.analysis = analysis;
  userData.analysisPayload = analysisPayload;
  userData.answersSnapshot = snapshot;

  const followUpKeyboard = consultationKeyboard();
  if (followUpKeyboard) {
    await ctx.reply(messages.POST_REPORT_MESSAGE, {
      ...MarkdownExtra,
      ...followUpKeyboard
    });
  } else {
    await ctx.reply(messages.POST_REPORT_MESSAGE, MarkdownExtra);
  }
}

async function handleChatMessage(ctx, userMessage, userData) {
  const message = userMessage.trim();
  if (!message) {
    await ctx.reply(messages.CHAT_FALLBACK_MESSAGE);
    return;
  }

  appendChatHistory(userData, 'user', message);
  const payload = buildChatPayload(userData, message);
  const reply = await generateChatReply(payload);

  if (reply) {
    appendChatHistory(userData, 'assistant', reply);
    await ctx.reply(reply);
  } else {
    await ctx.reply(messages.CHAT_FALLBACK_MESSAGE);
  }
}

function buildUserMetadata(user) {
  if (!user) return {};
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
  return {
    user_id: user.id,
    username: user.username || '',
    full_name: fullName
  };
}

function buildAnalysisPayload(userData) {
  return {
    skill_level: getSkillLevelText(userData),
    skill_level_key: userData[SKILL_LEVEL_KEY],
    answers: buildQuestionAnswerPairs(userData),
    answers_by_id: collectAllAnswers(userData)
  };
}

function buildChatPayload(userData, userMessage) {
  const analysis = userData.analysis || {};
  const analysisPayload = userData.analysisPayload || {};
  const history = getChatHistory(userData);

  return {
    analysis,
    answers: analysisPayload.answers || buildQuestionAnswerPairs(userData),
    answers_by_id: analysisPayload.answers_by_id || collectAllAnswers(userData),
    skill_level: getSkillLevelText(userData),
    history,
    user_message: userMessage
  };
}
