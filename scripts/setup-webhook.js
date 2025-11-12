#!/usr/bin/env node
import 'dotenv/config';

const API_ROOT = 'https://api.telegram.org';

async function callTelegram(method, token, params = {}) {
  const url = new URL(`${API_ROOT}/bot${token}/${method}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.append(key, value);
    }
  });

  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Telegram API error ${res.status}: ${text}`);
  }
  return res.json();
}

async function main() {
  const action = process.argv[2];
  if (!['set', 'delete'].includes(action)) {
    console.error('Usage: node scripts/setup-webhook.js <set|delete> [--url=https://example.com/api/bot]');
    process.exit(1);
  }

  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token) {
    console.error('TELEGRAM_BOT_TOKEN is not set');
    process.exit(1);
  }

  if (action === 'set') {
    const urlArg = process.argv.find((arg) => arg.startsWith('--url='));
    const webhookUrl = urlArg ? urlArg.slice('--url='.length) : process.env.WEBHOOK_URL;
    if (!webhookUrl) {
      console.error('Provide webhook URL via --url or WEBHOOK_URL env');
      process.exit(1);
    }

    const secret = process.env.TELEGRAM_SECRET_TOKEN;
    const response = await callTelegram('setWebhook', token, {
      url: webhookUrl,
      secret_token: secret || undefined,
      allowed_updates: JSON.stringify(['message', 'callback_query'])
    });
    console.log(JSON.stringify(response, null, 2));
    process.exit(response.ok ? 0 : 1);
  }

  if (action === 'delete') {
    const response = await callTelegram('deleteWebhook', token);
    console.log(JSON.stringify(response, null, 2));
    process.exit(response.ok ? 0 : 1);
  }
}

main().catch((error) => {
  console.error('Failed to manage webhook:', error);
  process.exit(1);
});
