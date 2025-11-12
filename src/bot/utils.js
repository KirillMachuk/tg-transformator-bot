import {
  ANSWERS_KEY,
  QUESTION_INDEX_KEY,
  AWAITING_TEXT_KEY,
  AWAITING_OTHER_KEY,
  SKILL_LEVEL_KEY,
  REPORT_READY_KEY,
  DIAGNOSIS_COMPLETE_KEY,
  CURRENT_QUESTION_MESSAGE_KEY,
  SHEETS_SAVED_KEY,
  CHAT_HISTORY_KEY
} from './constants.js';
import { getAllQuestions } from './questions.js';
import { SKILL_LEVEL_OPTIONS } from './messages.js';

const sessionStore = new Map();

export function resetUserSession(chatId) {
  const userData = {
    [ANSWERS_KEY]: {},
    [QUESTION_INDEX_KEY]: 0,
    [REPORT_READY_KEY]: false,
    [DIAGNOSIS_COMPLETE_KEY]: false,
    [SHEETS_SAVED_KEY]: false,
    [CHAT_HISTORY_KEY]: []
  };
  sessionStore.set(chatId, userData);
  return userData;
}

export function getUserSession(chatId) {
  if (!sessionStore.has(chatId)) {
    resetUserSession(chatId);
  }
  return sessionStore.get(chatId);
}

export function getAllQuestionSequence() {
  return getAllQuestions();
}

export function getCurrentQuestion(userData) {
  const questions = getAllQuestionSequence();
  const index = userData[QUESTION_INDEX_KEY] ?? 0;
  if (index >= 0 && index < questions.length) {
    return questions[index];
  }
  return null;
}

export function advanceQuestion(userData) {
  const questions = getAllQuestionSequence();
  const index = (userData[QUESTION_INDEX_KEY] ?? 0) + 1;
  userData[QUESTION_INDEX_KEY] = index;
  if (index >= 0 && index < questions.length) {
    return questions[index];
  }
  return null;
}

export function recordAnswer(userData, questionId, value) {
  const answers = userData[ANSWERS_KEY] || (userData[ANSWERS_KEY] = {});
  answers[questionId] = value;
}

export function getAnswer(userData, questionId, defaultValue = null) {
  return userData[ANSWERS_KEY]?.[questionId] ?? defaultValue;
}

export function toggleMultiOption(userData, question, option) {
  const answers = userData[ANSWERS_KEY] || (userData[ANSWERS_KEY] = {});
  const entry = answers[question.id] || (answers[question.id] = { selected: [], custom: [] });
  const selected = entry.selected || (entry.selected = []);
  const idx = selected.indexOf(option.key);
  if (idx >= 0) {
    selected.splice(idx, 1);
  } else {
    selected.push(option.key);
  }
  return entry;
}

export function appendCustomAnswer(userData, questionId, optionText, value) {
  const answers = userData[ANSWERS_KEY] || (userData[ANSWERS_KEY] = {});
  const entry = answers[questionId] || (answers[questionId] = { selected: [], custom: [] });
  const custom = entry.custom || (entry.custom = []);
  custom.push({ option: optionText, value });
}

export function recordSingleAnswer(userData, questionId, value) {
  const answers = userData[ANSWERS_KEY] || (userData[ANSWERS_KEY] = {});
  answers[questionId] = value;
}

export function getSelectedOptionKeys(userData, questionId) {
  const entry = getAnswer(userData, questionId, {});
  return Array.isArray(entry?.selected) ? entry.selected : [];
}

export function setCurrentQuestionMessage(userData, chatId, messageId) {
  userData[CURRENT_QUESTION_MESSAGE_KEY] = { chatId, messageId };
}

export function getCurrentQuestionMessage(userData) {
  const ref = userData[CURRENT_QUESTION_MESSAGE_KEY];
  if (!ref) return null;
  const { chatId, messageId } = ref;
  if (typeof chatId === 'number' && typeof messageId === 'number') {
    return { chatId, messageId };
  }
  return null;
}

export function getQuestionById(questionId) {
  return getAllQuestionSequence().find((q) => q.id === questionId) || null;
}

export function getSkillLevelText(userData) {
  const skillKey = userData[SKILL_LEVEL_KEY];
  for (const [key, text] of SKILL_LEVEL_OPTIONS) {
    if (key === skillKey) return text;
  }
  return '';
}

function findOptionByKey(question, key) {
  if (!Array.isArray(question?.options)) return null;
  return question.options.find((option) => option.key === key) || null;
}

export { findOptionByKey };

export function formatQuestionAnswer(question, userData) {
  const answer = getAnswer(userData, question.id);
  if (answer == null) return '';

  if (typeof answer === 'object' && !Array.isArray(answer)) {
    const parts = [];
    for (const key of answer.selected || []) {
      const option = findOptionByKey(question, key);
      if (option) parts.push(option.text);
    }
    for (const custom of answer.custom || []) {
      const optionLabel = custom.option || '✍️ Другое';
      const value = custom.value || '';
      if (value) parts.push(`${optionLabel}: ${value}`);
    }
    return parts.join('\n');
  }

  if (Array.isArray(answer)) {
    return answer.map((item) => String(item)).join('\n');
  }

  return String(answer);
}

export function collectAllAnswers(userData) {
  const answers = {};
  for (const question of getAllQuestionSequence()) {
    answers[question.id] = formatQuestionAnswer(question, userData);
  }
  return answers;
}

export function buildQuestionAnswerPairs(userData) {
  const pairs = [];
  for (const question of getAllQuestionSequence()) {
    pairs.push({
      id: question.id,
      question: stripMarkdown(question.text),
      answer: formatQuestionAnswer(question, userData)
    });
  }
  return pairs;
}

export function stripMarkdown(text) {
  return text
    .replace(/^>\s*/gm, '')
    .replace(/\*\*/g, '')
    .replace(/\*/g, '')
    .replace(/`/g, '')
    .replace(/_/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function appendChatHistory(userData, role, message, limit = 12) {
  const history = userData[CHAT_HISTORY_KEY] || (userData[CHAT_HISTORY_KEY] = []);
  history.push({ role, message });
  if (history.length > limit) {
    history.splice(0, history.length - limit);
  }
}

export function getChatHistory(userData) {
  const history = userData[CHAT_HISTORY_KEY];
  if (Array.isArray(history)) {
    return [...history];
  }
  return [];
}

export function clearSessions() {
  sessionStore.clear();
}
