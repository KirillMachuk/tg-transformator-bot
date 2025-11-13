# Как проверить логи бота

## На Vercel (Production)

1. **Откройте Vercel Dashboard**
   - Перейдите на https://vercel.com
   - Выберите ваш проект

2. **Просмотр логов**
   - Откройте раздел **"Logs"** или **"Functions" → "Logs"**
   - Или перейдите в **"Deployments"** → выберите последний деплой → **"Function Logs"**

3. **Фильтрация логов**
   - Ищите сообщения с префиксами:
     - `services.pdf_service` - логи генерации PDF и регистрации шрифта
     - `bot.handlers` - логи обработчиков бота
     - `[webhook]` - общие логи вебхука

4. **Что искать в логах при генерации PDF:**
   ```
   ============================================================
   Starting PDF generation with Cyrillic support
   ============================================================
   Attempting to register font: DejaVuSans from ...
   ✓ Registered font: DejaVuSans with subfontIndex=0
   ✓ Font DejaVuSans successfully registered and verified
   Registered fonts: ['DejaVuSans', 'Helvetica', ...]
   ✓ Using font: DejaVuSans (registered: True)
   ✓ Font DejaVuSans is ready for Cyrillic text
   All styles created with font: DejaVuSans
   ```

## Локально (если запускаете локально)

Логи выводятся в консоль (терминал), где запущен бот.

## Включение детального логирования (DEBUG)

Для более детальных логов добавьте в Vercel Environment Variables:
- **Name:** `LOG_LEVEL`
- **Value:** `DEBUG`

Или в локальном `.env`:
```
LOG_LEVEL=DEBUG
```

## Что проверить в логах

При генерации PDF проверьте:

1. **Регистрация шрифта:**
   - `Attempting to register font: DejaVuSans`
   - `✓ Registered font: DejaVuSans`
   - `✓ Font DejaVuSans successfully registered`

2. **Использование шрифта:**
   - `✓ Using font: DejaVuSans`
   - `All styles created with font: DejaVuSans`

3. **Ошибки:**
   - `Font file not found` - шрифт не найден
   - `Failed to register font` - ошибка регистрации
   - `Falling back to Helvetica` - используется Helvetica (кириллица не будет работать)

4. **Текст с кириллицей:**
   - `Prepared text with Cyrillic: ...` (при LOG_LEVEL=DEBUG)

## Быстрая проверка

После генерации PDF в логах должно быть:
- ✅ `✓ Font DejaVuSans successfully registered` 
- ✅ `✓ Using font: DejaVuSans`
- ❌ НЕ должно быть: `Falling back to Helvetica`

