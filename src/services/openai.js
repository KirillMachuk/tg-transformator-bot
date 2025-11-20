import OpenAI from 'openai';
import settings from '../config/settings.js';

const ANALYSIS_SYSTEM_PROMPT = 'Ты — консалтинг-эксперт из агентства 1ma.ai. Те задачи, которые ты решаешь: анализируешь бизнес клиента, подбираешь точки применения искусственного интеллекта, формируешь понятный план внедрения. Отвечай кратко, по делу и строго на русском языке.';

const CHAT_SYSTEM_PROMPT = 'Ты — персональный AI-консультант агентства 1ma.ai. Ты уже провёл диагностику бизнеса клиента и подготовил ему отчёт. Сейчас клиент задаёт уточняющие вопросы, поэтому опирайся на ранее сделанные выводы и конкретику из отчёта. Отвечай дружелюбно, подробно, с практическими рекомендациями. Не придумывай данных, если их нет — говори об этом. Всегда предлагай следующий шаг и упоминай, как ИИ можно применить в реальных процессах.';

const SUMMARY_SYSTEM_PROMPT = 'Ты — помощник для создания краткого резюме контекста. Создай сжатую выжимку из вопросов, ответов и анализа, сохраняя ключевую информацию для контекста чата. Отвечай только текстом, без JSON.';
const MAX_OUTPUT_TOKENS = 700; // keep answers concise but practical

const ANALYSIS_USER_PROMPT = `Проанализируй ответы клиента и подготовь рекомендации по внедрению ИИ.
Ты должен вернуть JSON-объект со следующей строгой структурой:
{
  "business_summary": "краткое описание бизнеса и текущей ситуации",
  "priority_processes": ["ключевой процесс 1", "ключевой процесс 2", ...],
  "ai_opportunities": ["основная возможность 1", "основная возможность 2", ...],
  "quick_wins": ["быстрый результат 1", ...],
  "long_term": ["долгосрочная инициатива 1", ...],
  "next_steps": ["шаг 1", "шаг 2", ...],
  "recommended_tools": ["инструмент или интеграция 1", ...],
  "gpt_prompts": ["пример запроса для GPT 1", ...]
}
Формулируй пункты с учётом отрасли клиента, его целей и масштаба. Учитывай уровень компетенций клиента в ИИ. Не добавляй никакого текста вне JSON. Не используй переносы строк внутри элементов, чтобы каждый пункт помещался в одну строку.`;

const DEFAULT_ANALYSIS = {
  business_summary: '',
  priority_processes: [],
  ai_opportunities: [],
  quick_wins: [],
  long_term: [],
  next_steps: [],
  recommended_tools: [],
  gpt_prompts: []
};

const client = settings.openaiApiKey ? new OpenAI({ apiKey: settings.openaiApiKey }) : null;

function buildResponseRequest(systemPrompt, userPayload, overrides = {}) {
  return {
    model: settings.openaiModel,
    input: [
      { role: 'system', content: [{ type: 'input_text', text: systemPrompt }] },
      { role: 'user', content: [{ type: 'input_text', text: userPayload }] }
    ],
    max_output_tokens: MAX_OUTPUT_TOKENS,
    reasoning: { effort: 'medium' },
    verbosity: 'medium',
    ...overrides
  };
}

export async function analyzeAnswers(payload) {
  if (!client) {
    console.error('[openai] OPENAI_API_KEY is not configured');
    return { ...DEFAULT_ANALYSIS };
  }

  const requestPayload = buildAnalysisPayload(payload);

  try {
    const response = await client.responses.create(
      buildResponseRequest(ANALYSIS_SYSTEM_PROMPT, requestPayload, { max_output_tokens: 800 })
    );

    const text = extractText(response);
    if (!text) return { ...DEFAULT_ANALYSIS };
    return mergeWithDefault(JSON.parse(text));
  } catch (error) {
    console.error('[openai] analyzeAnswers error', {
      message: error?.message,
      status: error?.status,
      type: error?.type,
      param: error?.param,
      code: error?.code,
      error: error?.error,
      stack: error?.stack
    });
    return { ...DEFAULT_ANALYSIS };
  }
}

export async function generateChatReply(payload) {
  if (!client) {
    console.error('[openai] OPENAI_API_KEY is not configured');
    return '';
  }

  const requestPayload = buildChatPayload(payload);

  try {
    const response = await client.responses.create(
      buildResponseRequest(CHAT_SYSTEM_PROMPT, requestPayload)
    );

    const text = extractText(response)?.trim?.();
    return text || '';
  } catch (error) {
    console.error('[openai] chat error', {
      message: error?.message,
      status: error?.status,
      type: error?.type,
      param: error?.param,
      code: error?.code,
      error: error?.error,
      stack: error?.stack
    });
    return '';
  }
}

function buildAnalysisPayload(data) {
  const serialized = JSON.stringify(data, null, 2);
  return `${ANALYSIS_USER_PROMPT}\n\nДанные клиента:\n${serialized}`;
}

/**
 * Estimate token count (rough approximation: 1 token ≈ 4 characters)
 */
function estimateTokens(text) {
  if (!text) return 0;
  return Math.ceil(text.length / 4);
}

/**
 * Create a summary of context if it's too large for OpenAI
 * @param {Object} data - Full context data (analysis, answers, etc.)
 * @returns {Promise<string>} Summary text or empty string if failed
 */
export async function createContextSummary(data) {
  if (!client) {
    console.error('[openai] OPENAI_API_KEY is not configured');
    return '';
  }

  const serialized = JSON.stringify(data, null, 2);
  const tokenCount = estimateTokens(serialized);

  // Only create summary if context is large (more than ~6000 tokens, leaving room for system prompt and response)
  if (tokenCount < 6000) {
    return '';
  }

  const summaryPrompt = `${SUMMARY_SYSTEM_PROMPT}\n\nСоздай краткую выжимку из следующего контекста, сохраняя ключевую информацию:\n\n${serialized}`;

  try {
    const response = await client.responses.create(
      buildResponseRequest(SUMMARY_SYSTEM_PROMPT, summaryPrompt, { max_output_tokens: 400 })
    );

    const summary = extractText(response).trim();
    console.log(`[openai] Created context summary: ${summary.length} chars (original: ${serialized.length} chars)`);
    return summary;
  } catch (error) {
    console.error('[openai] createContextSummary error', {
      message: error?.message,
      status: error?.status,
      type: error?.type,
      param: error?.param,
      code: error?.code,
      error: error?.error,
      stack: error?.stack
    });
    return '';
  }
}

function serializeHistory(history = [], limit = 10) {
  const recent = history.slice(-limit);
  return recent
    .map((msg) => `${msg.role}: ${msg.content || msg.message || ''}`.trim())
    .filter(Boolean)
    .join('\n');
}

function formatAnalysisForChat(analysis = {}) {
  const sections = [
    ['Кратко о бизнесе', analysis.business_summary],
    ['Приоритетные процессы', (analysis.priority_processes || []).join('; ')],
    ['Возможности для внедрения ИИ', (analysis.ai_opportunities || []).join('; ')],
    ['Быстрые победы', (analysis.quick_wins || []).join('; ')],
    ['Долгосрочные инициативы', (analysis.long_term || []).join('; ')],
    ['Следующие шаги', (analysis.next_steps || []).join('; ')],
    ['Рекомендуемые инструменты', (analysis.recommended_tools || []).join('; ')],
    ['Готовые промпты для GPT', (analysis.gpt_prompts || []).join('; ')]
  ];

  return sections
    .map(([title, value]) => `${title}: ${value || '—'}`)
    .join('\n');
}

function buildChatPayload(data) {
  // If summary exists, use it; otherwise use full data
  if (data.context_summary) {
    const historyText = serializeHistory(data.history);
    
    return `Используй эту выжимку контекста и историю диалога, чтобы ответить клиенту на его вопрос. Сформулируй ответ полностью на русском языке, без JSON, в виде нескольких абзацев и маркеров при необходимости.

Выжимка контекста:
${data.context_summary}

История диалога:
${historyText || 'Нет истории'}

Вопрос клиента: ${data.user_message || ''}`;
  }

  // Use full data if no summary
  const serialized = JSON.stringify(data, null, 2);
  const historyText = serializeHistory(data.history);
  const analysisText = formatAnalysisForChat(data.analysis);

  return `Контекст клиента (ответы анкеты, анализ и выдержки из PDF):
${analysisText}

Ответы по вопросам (id -> ответ):
${JSON.stringify(data.answers_by_id || {}, null, 2)}

История диалога:
${historyText || 'Нет истории'}

Текстовая копия данных:
${serialized}

Вопрос клиента: ${data.user_message || ''}`;
}

function extractText(response) {
  if (!response) return '';

  // Responses API v2: top-level output_text shortcut
  if (typeof response.output_text === 'string' && response.output_text.trim()) {
    return response.output_text;
  }

  // Responses API: output array with typed blocks
  if (Array.isArray(response.output)) {
    for (const item of response.output) {
      if (typeof item?.output_text === 'string' && item.output_text.trim()) {
        return item.output_text;
      }
      const content = Array.isArray(item?.content) ? item.content : [];
      for (const part of content) {
        if (typeof part?.output_text === 'string' && part.output_text.trim()) {
          return part.output_text;
        }
        if (typeof part?.text === 'string' && part.text.trim()) {
          return part.text;
        }
      }
    }
  }
  
  return '';
}

function mergeWithDefault(parsed) {
  const result = { ...DEFAULT_ANALYSIS };
  for (const key of Object.keys(result)) {
    const value = parsed?.[key];
    if (Array.isArray(result[key])) {
      result[key] = Array.isArray(value) ? value.map(String) : [];
    } else {
      result[key] = value != null ? String(value) : '';
    }
  }
  return result;
}
