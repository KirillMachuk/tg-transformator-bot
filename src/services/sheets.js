import fetch from 'node-fetch';
import { google } from 'googleapis';
import settings from '../config/settings.js';
import { collectAllAnswers, buildQuestionAnswerPairs } from '../bot/utils.js';

let sheetsClient;

export async function storeAnswers(metadata, userData) {
  const payload = buildPayload(metadata, userData);

  if (settings.gasEndpoint) {
    const ok = await postToGas(payload);
    if (ok) return;
    console.warn('[sheets] GAS endpoint failed, falling back to Sheets API');
  }

  if (settings.googleCredentialsJson && settings.googleSheetId) {
    await appendToGoogleSheet(payload);
  }
}

function buildPayload(metadata, userData) {
  const timestamp = metadata.timestamp || new Date().toISOString();
  const answersById = collectAllAnswers(userData);
  const answers = buildQuestionAnswerPairs(userData).map((item) => ({
    id: item.id,
    question_markdown: item.question,
    question_plain: item.question,
    answer: item.answer
  }));

  // Include analysis if available
  const analysis = userData.analysis || null;
  const analysisJson = analysis ? JSON.stringify(analysis) : '';

  return {
    meta: {
      timestamp,
      user_id: metadata.user_id || '',
      username: metadata.username || '',
      full_name: metadata.full_name || '',
      skill_level: metadata.skill_level || ''
    },
    answers_by_id: answersById,
    answers,
    analysis: analysisJson
  };
}

async function postToGas(payload) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const res = await fetch(settings.gasEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    if (!res.ok) return false;
    const body = await res.text();
    if (!body) return true;
    try {
      const json = JSON.parse(body);
      return Boolean(json.ok);
    } catch {
      return true;
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      console.error('[sheets] GAS request timeout');
    } else {
      console.error('[sheets] GAS request error', error);
    }
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

async function appendToGoogleSheet(payload) {
  const client = await getSheetsClient();
  if (!client) return;

  const values = buildRow(payload);
  await client.spreadsheets.values.append({
    spreadsheetId: settings.googleSheetId,
    range: settings.googleSheetRange,
    valueInputOption: 'RAW',
    insertDataOption: 'INSERT_ROWS',
    requestBody: { values: [values] }
  });
}

function buildRow(payload) {
  const meta = payload.meta || {};
  const answers = payload.answers_by_id || {};
  const row = [
    meta.timestamp || '',
    String(meta.user_id || ''),
    meta.username || '',
    meta.full_name || '',
    meta.skill_level || ''
  ];

  const pairs = payload.answers || [];
  for (const pair of pairs) {
    row.push(pair.answer || '');
  }

  // Add analysis as last column (JSON string)
  row.push(payload.analysis || '');
  return row;
}

async function getSheetsClient() {
  if (sheetsClient) return sheetsClient;
  if (!settings.googleCredentialsJson) {
    console.warn('[sheets] GOOGLE_CREDENTIALS_JSON is not set');
    return null;
  }

  try {
    const credentials = JSON.parse(settings.googleCredentialsJson);
    const auth = new google.auth.GoogleAuth({
      credentials,
      scopes: ['https://www.googleapis.com/auth/spreadsheets']
    });
    const client = await auth.getClient();
    sheetsClient = google.sheets({ version: 'v4', auth: client });
    return sheetsClient;
  } catch (error) {
    console.error('[sheets] failed to create client', error);
    sheetsClient = null;
    return null;
  }
}
