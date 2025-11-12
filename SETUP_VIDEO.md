# Настройка видео для бота

Видео файл `lesson.MOV` (146 MB) не включен в git репозиторий из-за размера.

## Вариант 1: Использовать file_id Telegram (рекомендуется)

1. Узнайте свой Telegram user ID (можно через бот @userinfobot)

2. Добавьте в `.env`:
```
ADMIN_CHAT_ID=your_telegram_user_id
```

3. Запустите скрипт для загрузки видео:
```bash
npm run upload-video
```

4. Скопируйте полученный `file_id` в `src/bot/constants.js`:
```javascript
export const LESSON_VIDEO_FILE_ID = 'BAACAgIAAxkBAAI...';
```

5. Раскомментируйте код отправки видео в `src/bot/conversation.js`:
```javascript
// Удалите console.log и раскомментируйте:
const { LESSON_VIDEO_FILE_ID } = await import('./constants.js');
if (LESSON_VIDEO_FILE_ID) {
  await ctx.replyWithVideo(LESSON_VIDEO_FILE_ID);
}
```

6. Закоммитьте изменения и запушьте в git

## Вариант 2: Разместить видео в облаке

1. Загрузите видео на YouTube, Vimeo или другой CDN
2. Измените код для отправки ссылки вместо файла
3. Используйте `ctx.reply()` с текстом и ссылкой

## Вариант 3: Использовать Vercel Blob Storage

1. Настройте Vercel Blob Storage
2. Загрузите видео туда
3. Используйте публичный URL для отправки

