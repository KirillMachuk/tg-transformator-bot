import 'dotenv/config';
import { Telegraf, session } from 'telegraf';
import settings from '../src/config/settings.js';
import { setupConversation } from '../src/bot/conversation.js';
import { createSessionStore } from '../src/bot/redis-store.js';

const token = settings.telegramToken;

if (!token) {
  throw new Error('TELEGRAM_BOT_TOKEN is not configured');
}

const bot = new Telegraf(token);

// Use Redis session store for persistence across serverless requests
// Falls back to memory store if KV is not configured (local development)
const sessionStore = createSessionStore();

bot.use(session({
  store: sessionStore,
  defaultSession: () => ({
    answers: {},
    question_index: 0,
    report_ready: false,
    diagnosis_complete: false,
    sheets_saved: false,
    chat_history: []
  }),
  getSessionKey: (ctx) => {
    // Use chatId as session key
    if (!ctx.chat) return null;
    return `session:${ctx.chat.id}`;
  }
}));

setupConversation(bot);

export default async function handler(req, res) {
  // Log Redis configuration status
  const hasKVUrl = !!process.env.KV_REST_API_URL;
  const hasKVToken = !!process.env.KV_REST_API_TOKEN;
  console.log('[bot] Redis config check:', {
    hasKVUrl,
    hasKVToken,
    kvUrlLength: process.env.KV_REST_API_URL?.length || 0,
    kvTokenLength: process.env.KV_REST_API_TOKEN?.length || 0
  });

  if (req.method === 'GET') {
    return res.status(200).json({ 
      ok: true, 
      status: 'tg-transformator telegraf handler',
      redis: {
        configured: hasKVUrl && hasKVToken,
        hasUrl: hasKVUrl,
        hasToken: hasKVToken
      }
    });
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const secretHeader = req.headers['x-telegram-bot-api-secret-token'];
  if (settings.telegramSecretToken && secretHeader !== settings.telegramSecretToken) {
    return res.status(403).json({ error: 'Invalid secret token' });
  }

  try {
    const update = req.body;
    console.log('[bot] Handling update:', {
      updateId: update?.update_id,
      messageType: update?.message ? 'message' : update?.callback_query ? 'callback' : 'unknown'
    });
    await bot.handleUpdate(update);
    res.status(200).json({ ok: true });
  } catch (error) {
    console.error('[webhook] error', error);
    res.status(500).json({ ok: false });
  }
}
