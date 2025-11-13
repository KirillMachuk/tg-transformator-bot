#!/usr/bin/env node
import 'dotenv/config';
import { Telegraf } from 'telegraf';

const token = process.env.TELEGRAM_BOT_TOKEN;
const adminId = 169506026; // Kiryl's Telegram ID

if (!token) {
  console.error('TELEGRAM_BOT_TOKEN is not set');
  process.exit(1);
}

const bot = new Telegraf(token);

console.log('🤖 Бот запущен!');
console.log('📹 Отправьте видео файл lesson.MOV боту в Telegram');
console.log('📋 Я получу file_id и автоматически обновлю код\n');

bot.on('video', async (ctx) => {
  if (ctx.from.id !== adminId) {
    return; // Ignore messages from other users
  }

  const video = ctx.message.video;
  const fileId = video.file_id;
  const fileSize = (video.file_size / 1024 / 1024).toFixed(2);
  
  console.log('✅ Видео получено!');
  console.log(`📊 Размер: ${fileSize} MB`);
  console.log(`🆔 File ID: ${fileId}\n`);
  
  await ctx.reply(
    `✅ Видео получено!\n\n` +
    `📋 File ID сохранен:\n<code>${fileId}</code>\n\n` +
    `Обновляю код...`,
    { parse_mode: 'HTML' }
  );

  // Update constants.js
  const fs = await import('fs/promises');
  const path = await import('path');
  const { fileURLToPath } = await import('url');
  
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const constantsPath = path.join(__dirname, '../src/bot/constants.js');
  
  let content = await fs.readFile(constantsPath, 'utf-8');
  content = content.replace(
    /export const LESSON_VIDEO_FILE_ID = null;.*$/m,
    `export const LESSON_VIDEO_FILE_ID = '${fileId}';`
  );
  await fs.writeFile(constantsPath, content);
  
  // Update conversation.js
  const conversationPath = path.join(__dirname, '../src/bot/conversation.js');
  let convContent = await fs.readFile(conversationPath, 'utf-8');
  
  convContent = convContent.replace(
    /\/\/ Send video file[\s\S]*?console\.log\('\[video\].*?'\);/,
    `// Send video file
    const { LESSON_VIDEO_FILE_ID } = await import('./constants.js');
    if (LESSON_VIDEO_FILE_ID) {
      await ctx.replyWithVideo(LESSON_VIDEO_FILE_ID);
    } else {
      console.log('[video] Video file_id not set in constants.js');
    }`
  );
  await fs.writeFile(conversationPath, convContent);
  
  await ctx.reply(
    `✅ Код обновлен!\n\n` +
    `Файлы изменены:\n` +
    `- src/bot/constants.js\n` +
    `- src/bot/conversation.js\n\n` +
    `Запускаю коммит...`,
    { parse_mode: 'HTML' }
  );
  
  // Git commit and push
  const { exec } = await import('child_process');
  const { promisify } = await import('util');
  const execAsync = promisify(exec);
  
  try {
    await execAsync('git add src/bot/constants.js src/bot/conversation.js', {
      cwd: path.join(__dirname, '..')
    });
    await execAsync(`git commit -m "Добавлен file_id видео урока"`, {
      cwd: path.join(__dirname, '..')
    });
    await execAsync('git push origin main', {
      cwd: path.join(__dirname, '..')
    });
    
    await ctx.reply(
      `🚀 Готово!\n\n` +
      `✅ Изменения запушены в GitHub\n` +
      `✅ Vercel автоматически задеплоит обновления\n\n` +
      `⏱ Подожди 1-2 минуты и протестируй бота командой /start`,
      { parse_mode: 'HTML' }
    );
    
    console.log('\n✅ Все готово! Изменения запушены в git.');
    console.log('⏱  Vercel задеплоит обновления через 1-2 минуты.\n');
    
    setTimeout(() => {
      process.exit(0);
    }, 3000);
  } catch (error) {
    console.error('Ошибка при git операциях:', error);
    await ctx.reply(
      `❌ Ошибка при пуше в git:\n${error.message}\n\n` +
      `Запушьте изменения вручную:\n` +
      `<code>git add src/bot/constants.js src/bot/conversation.js\n` +
      `git commit -m "Добавлен file_id видео"\n` +
      `git push origin main</code>`,
      { parse_mode: 'HTML' }
    );
    process.exit(1);
  }
});

bot.launch().then(() => {
  console.log('Ожидаю видео...');
});

// Enable graceful stop
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));

