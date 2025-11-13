import 'dotenv/config';
import { Telegraf, session } from 'telegraf';
import settings from '../src/config/settings.js';
import { setupConversation } from '../src/bot/conversation.js';

const token = settings.telegramToken;

if (!token) {
  throw new Error('TELEGRAM_BOT_TOKEN is not configured');
}

const bot = new Telegraf(token);

// Use session middleware to persist user data across requests
// This uses memory store which works within the same process
bot.use(session({
  defaultSession: () => ({
    answers: {},
    question_index: 0,
    report_ready: false,
    diagnosis_complete: false,
    sheets_saved: false,
    chat_history: []
  })
}));

setupConversation(bot);

export default async function handler(req, res) {
  if (req.method === 'GET') {
    return res.status(200).json({ ok: true, status: 'tg-transformator telegraf handler' });
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const secretHeader = req.headers['x-telegram-bot-api-secret-token'];
  if (settings.telegramSecretToken && secretHeader !== settings.telegramSecretToken) {
    return res.status(403).json({ error: 'Invalid secret token' });
  }

  try {
    await bot.handleUpdate(req.body);
    res.status(200).json({ ok: true });
  } catch (error) {
    console.error('[webhook] error', error);
    res.status(500).json({ ok: false });
  }
}
