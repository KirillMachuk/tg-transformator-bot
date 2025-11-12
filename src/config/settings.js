import 'dotenv/config';

const settings = {
  telegramToken: process.env.TELEGRAM_BOT_TOKEN || '',
  telegramSecretToken: process.env.TELEGRAM_SECRET_TOKEN || '',
  openaiApiKey: process.env.OPENAI_API_KEY || '',
  openaiModel: process.env.OPENAI_MODEL || 'gpt-5-mini',
  googleCredentialsJson: process.env.GOOGLE_CREDENTIALS_JSON || '',
  googleSheetId: process.env.GOOGLE_SHEET_ID || '',
  googleSheetRange: process.env.GOOGLE_SHEET_RANGE || 'Ответы!A:Z',
  gasEndpoint: process.env.GAS_ENDPOINT || '',
  pdfFontPath: process.env.PDF_FONT_PATH || '',
  consultationUrl: process.env.CONSULTATION_URL || '',
  webhookUrl: process.env.WEBHOOK_URL || ''
};

export default settings;
