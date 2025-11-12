import 'dotenv/config';
import { Telegraf } from 'telegraf';
import settings from '../src/config/settings.js';
import { setupConversation } from '../src/bot/conversation.js';

const token = settings.telegramToken;

if (!token) {
  throw new Error('TELEGRAM_BOT_TOKEN is not configured');
}

const bot = new Telegraf(token);
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
