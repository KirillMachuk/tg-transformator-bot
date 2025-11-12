#!/usr/bin/env node
import 'dotenv/config';
import { Telegraf } from 'telegraf';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const token = process.env.TELEGRAM_BOT_TOKEN;
const adminChatId = process.env.ADMIN_CHAT_ID; // Your Telegram user ID

if (!token) {
  console.error('TELEGRAM_BOT_TOKEN is not set');
  process.exit(1);
}

if (!adminChatId) {
  console.error('ADMIN_CHAT_ID is not set. Set your Telegram user ID in .env');
  process.exit(1);
}

const bot = new Telegraf(token);

async function uploadVideo() {
  const videoPath = path.join(__dirname, '../lesson.MOV');
  
  if (!fs.existsSync(videoPath)) {
    console.error('Video file not found:', videoPath);
    process.exit(1);
  }

  console.log('Uploading video to Telegram...');
  console.log('File:', videoPath);
  console.log('Size:', (fs.statSync(videoPath).size / 1024 / 1024).toFixed(2), 'MB');

  try {
    const message = await bot.telegram.sendVideo(adminChatId, {
      source: videoPath
    }, {
      caption: 'Урок по ИИ для бота 1ma.ai\n\nСохраните file_id этого видео для использования в боте.'
    });

    const fileId = message.video.file_id;
    
    console.log('\n✅ Video uploaded successfully!');
    console.log('\n📋 Copy this file_id and paste it into src/bot/constants.js:');
    console.log('\nFile ID:', fileId);
    console.log('\nUpdate src/bot/constants.js:');
    console.log(`export const LESSON_VIDEO_FILE_ID = '${fileId}';`);
    
  } catch (error) {
    console.error('Error uploading video:', error.message);
    process.exit(1);
  }
  
  process.exit(0);
}

uploadVideo();

