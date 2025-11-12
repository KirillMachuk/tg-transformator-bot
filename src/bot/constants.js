export const ANSWERS_KEY = 'answers';
export const QUESTION_INDEX_KEY = 'question_index';
export const AWAITING_TEXT_KEY = 'awaiting_text_question';
export const AWAITING_OTHER_KEY = 'awaiting_other_question';
export const SKILL_LEVEL_KEY = 'skill_level';
export const REPORT_READY_KEY = 'report_ready';
export const DIAGNOSIS_COMPLETE_KEY = 'diagnosis_complete';
export const CURRENT_QUESTION_MESSAGE_KEY = 'current_question_message';
export const SHEETS_SAVED_KEY = 'sheets_saved';
export const CHAT_HISTORY_KEY = 'chat_history';

export const STATE = {
  WELCOME: 'WELCOME',
  SKILL_LEVEL: 'SKILL_LEVEL',
  VIDEO: 'VIDEO',
  DIAGNOSIS: 'DIAGNOSIS',
  READINESS: 'READINESS',
  REPORT: 'REPORT',
  CHAT: 'CHAT'
};

// Video file_id from Telegram (upload video once and use this ID)
// To get file_id: upload video to bot, then use getUpdates to see the file_id
export const LESSON_VIDEO_FILE_ID = 'BAACAgIAAxkBAAM1aRTMcusnjp-ob01V8J8IcBjsUvEAAheKAAKCraBIYMogzCL0b8o2BA';
