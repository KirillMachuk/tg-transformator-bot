import OpenAI from 'openai';
import settings from '../config/settings.js';

const ANALYSIS_SYSTEM_PROMPT = 'Ты — консалтинг-эксперт из агентства 1ma.ai. Те задачи, которые ты решаешь: анализируешь бизнес клиента, подбираешь точки применения искусственного интеллекта, формируешь понятный план внедрения. Отвечай кратко, по делу и строго на русском языке.';

const CHAT_SYSTEM_PROMPT = 'Ты — персональный AI-консультант агентства 1ma.ai. Ты уже провёл диагностику бизнеса клиента и подготовил ему отчёт. Сейчас клиент задаёт уточняющие вопросы, поэтому опирайся на ранее сделанные выводы и конкретику из отчёта. Отвечай дружелюбно, подробно, с практическими рекомендациями. Не придумывай данных, если их нет — говори об этом. Всегда предлагай следующий шаг и упоминай, как ИИ можно применить в реальных процессах.';

const SUMMARY_SYSTEM_PROMPT = 'Ты — помощник для создания краткого резюме контекста. Создай сжатую выжимку из вопросов, ответов и анализа, сохраняя ключевую информацию для контекста чата. Отвечай только текстом, без JSON.';
const MAX_OUTPUT_TOKENS = 700; // keep answers concise but practical

const ANALYSIS_USER_PROMPT = `Проанализируй ответы клиента и подготовь рекомендации по внедрению ИИ.
Ты ДОЛЖЕН вернуть ТОЛЬКО валидный JSON-объект, без дополнительного текста до или после.
Используй следующую СТРОГУЮ структуру:
{
  "business_summary": "краткое описание бизнеса и текущей ситуации",
  "priority_processes": ["ключевой процесс 1", "ключевой процесс 2"],
  "ai_opportunities": ["основная возможность 1", "основная возможность 2"],
  "quick_wins": ["быстрый результат 1"],
  "long_term": ["долгосрочная инициатива 1"],
  "next_steps": ["шаг 1", "шаг 2"],
  "recommended_tools": ["инструмент или интеграция 1"],
  "gpt_prompts": ["пример запроса для GPT 1"]
}

КРИТИЧЕСКИ ВАЖНО:
- Возвращай ТОЛЬКО валидный JSON
- Все строки должны быть правильно экранированы
- Не используй переносы строк внутри значений
- Закрывай все кавычки
- Не добавляй никакого текста до или после JSON
- Проверь что JSON валиден перед отправкой

Формулируй пункты с учётом отрасли клиента, его целей и масштаба.`;

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

/**
 * Safely parse JSON with error handling and repair attempts
 * @param {string} text - The text to parse as JSON
 * @returns {Object|null} Parsed JSON object or null if parsing fails
 */
function safeJsonParse(text) {
  if (!text || typeof text !== 'string') return null;
  
  // Try direct parsing first
  try {
    return JSON.parse(text);
  } catch (e) {
    // Direct parsing failed, try to repair
  }
  
  // Try to extract JSON from markdown code blocks
  const jsonBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  if (jsonBlockMatch) {
    try {
      return JSON.parse(jsonBlockMatch[1]);
    } catch (e) {
      // Continue to other repair attempts
    }
  }
  
  // Try to find JSON object boundaries
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    try {
      return JSON.parse(jsonMatch[0]);
    } catch (e) {
      // Try to repair common JSON errors
      let repaired = jsonMatch[0];
      
      // Fix unterminated strings by closing them
      repaired = repaired.replace(/("[^"]*$)/m, '$1"');
      
      // Remove trailing commas
      repaired = repaired.replace(/,(\s*[}\]])/g, '$1');
      
      // Try parsing the repaired JSON
      try {
        return JSON.parse(repaired);
      } catch (e) {
        console.error('[openai] JSON repair failed:', e.message);
      }
    }
  }
  
  return null;
}

function buildResponseRequest(systemPrompt, userPayload, overrides = {}) {
  return {
    model: settings.openaiModel,
    input: [
      { role: 'system', content: [{ type: 'input_text', text: systemPrompt }] },
      { role: 'user', content: [{ type: 'input_text', text: userPayload }] }
    ],
    max_output_tokens: MAX_OUTPUT_TOKENS,
    reasoning: { effort: 'medium' },
    text: { verbosity: 'medium' },
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
    if (!text) {
      console.error('[openai] No text extracted from response');
      return { ...DEFAULT_ANALYSIS };
    }
    
    // Try to parse the JSON with error handling and repair
    const parsed = safeJsonParse(text);
    if (!parsed) {
      console.error('[openai] Failed to parse JSON response. Raw text:', text.substring(0, 500));
      return { ...DEFAULT_ANALYSIS };
    }
    
    console.log('[openai] Successfully parsed analysis response');
    return mergeWithDefault(parsed);
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
  const payloadSize = requestPayload?.length || 0;
  const estimatedTokens = estimateTokens(requestPayload);
  
  console.log('[openai] generateChatReply: Starting request', {
    payloadSize,
    estimatedTokens,
    hasContextSummary: !!payload?.context_summary,
    hasAnalysis: !!payload?.analysis,
    hasHistory: Array.isArray(payload?.history) && payload.history.length > 0,
    userMessage: payload?.user_message?.substring(0, 100) || 'no message'
  });

  try {
    const requestConfig = buildResponseRequest(CHAT_SYSTEM_PROMPT, requestPayload);
    console.log('[openai] generateChatReply: Request config', {
      model: requestConfig.model,
      maxOutputTokens: requestConfig.max_output_tokens,
      inputLength: requestConfig.input?.length || 0
    });

    const response = await client.responses.create(requestConfig);

    console.log('[openai] generateChatReply: Received response', {
      hasResponse: !!response,
      responseType: typeof response,
      responseKeys: response ? Object.keys(response) : [],
      hasOutputText: typeof response?.output_text === 'string',
      hasOutputArray: Array.isArray(response?.output),
      outputArrayLength: Array.isArray(response?.output) ? response.output.length : 0
    });

    // Log full response structure for debugging (truncated if too large)
    if (response) {
      const responseStr = JSON.stringify(response);
      if (responseStr.length > 1000) {
        console.log('[openai] generateChatReply: Response structure (truncated)', responseStr.substring(0, 1000) + '...');
      } else {
        console.log('[openai] generateChatReply: Full response structure', response);
      }
    }

    const text = extractText(response)?.trim?.();
    
    console.log('[openai] generateChatReply: Extracted text', {
      hasText: !!text,
      textLength: text?.length || 0,
      textPreview: text ? text.substring(0, 200) : 'no text'
    });

    if (!text) {
      console.error('[openai] generateChatReply: No text extracted from response');
    }

    return text || '';
  } catch (error) {
    console.error('[openai] generateChatReply: Error occurred', {
      message: error?.message,
      status: error?.status,
      type: error?.type,
      param: error?.param,
      code: error?.code,
      error: error?.error,
      stack: error?.stack,
      response: error?.response ? JSON.stringify(error.response).substring(0, 500) : undefined
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
  console.log('[openai] buildChatPayload: Building payload', {
    hasData: !!data,
    hasContextSummary: !!data?.context_summary,
    hasAnalysis: !!data?.analysis,
    hasAnswers: !!data?.answers,
    hasAnswersById: !!data?.answers_by_id,
    hasHistory: Array.isArray(data?.history),
    historyLength: Array.isArray(data?.history) ? data.history.length : 0,
    hasUserMessage: !!data?.user_message,
    userMessageLength: data?.user_message?.length || 0,
    dataKeys: data ? Object.keys(data) : []
  });

  // If summary exists, use it; otherwise use full data
  if (data.context_summary) {
    const historyText = serializeHistory(data.history);
    const payload = `Используй эту выжимку контекста и историю диалога, чтобы ответить клиенту на его вопрос. Сформулируй ответ полностью на русском языке, без JSON, в виде нескольких абзацев и маркеров при необходимости.

Выжимка контекста:
${data.context_summary}

История диалога:
${historyText || 'Нет истории'}

Вопрос клиента: ${data.user_message || ''}`;

    const payloadSize = payload.length;
    const estimatedTokens = estimateTokens(payload);
    console.log('[openai] buildChatPayload: Created payload with summary', {
      payloadSize,
      estimatedTokens,
      contextSummaryLength: data.context_summary?.length || 0,
      historyTextLength: historyText?.length || 0
    });

    return payload;
  }

  // Use full data if no summary
  const serialized = JSON.stringify(data, null, 2);
  const historyText = serializeHistory(data.history);
  const analysisText = formatAnalysisForChat(data.analysis);

  const payload = `Контекст клиента (ответы анкеты, анализ и выдержки из PDF):
${analysisText}

Ответы по вопросам (id -> ответ):
${JSON.stringify(data.answers_by_id || {}, null, 2)}

История диалога:
${historyText || 'Нет истории'}

Текстовая копия данных:
${serialized}

Вопрос клиента: ${data.user_message || ''}`;

  const payloadSize = payload.length;
  const estimatedTokens = estimateTokens(payload);
  console.log('[openai] buildChatPayload: Created payload with full data', {
    payloadSize,
    estimatedTokens,
    analysisTextLength: analysisText?.length || 0,
    serializedLength: serialized?.length || 0,
    historyTextLength: historyText?.length || 0,
    answersByIdLength: JSON.stringify(data.answers_by_id || {}).length
  });

  // Validate required fields
  if (!data.user_message) {
    console.warn('[openai] buildChatPayload: Warning - no user_message provided');
  }
  if (!data.analysis && !data.context_summary) {
    console.warn('[openai] buildChatPayload: Warning - no analysis or context_summary provided');
  }

  return payload;
}

function extractText(response) {
  if (!response) {
    console.log('[openai] extractText: No response provided');
    return '';
  }

  console.log('[openai] extractText: Processing response', {
    responseType: typeof response,
    responseKeys: Object.keys(response),
    hasOutputText: 'output_text' in response,
    hasOutput: 'output' in response,
    outputTextType: typeof response.output_text,
    outputIsArray: Array.isArray(response.output)
  });

  // Responses API v2: top-level output_text shortcut
  if (typeof response.output_text === 'string' && response.output_text.trim()) {
    console.log('[openai] extractText: Found output_text at top level', {
      length: response.output_text.length,
      preview: response.output_text.substring(0, 100)
    });
    return response.output_text;
  }

  // Responses API: output array with typed blocks
  if (Array.isArray(response.output)) {
    console.log('[openai] extractText: Processing output array', {
      length: response.output.length
    });

    for (let i = 0; i < response.output.length; i++) {
      const item = response.output[i];
      console.log(`[openai] extractText: Processing output[${i}]`, {
        itemType: typeof item,
        itemKeys: item ? Object.keys(item) : [],
        hasOutputText: typeof item?.output_text === 'string',
        hasContent: Array.isArray(item?.content),
        contentLength: Array.isArray(item?.content) ? item.content.length : 0
      });

      if (typeof item?.output_text === 'string' && item.output_text.trim()) {
        console.log('[openai] extractText: Found output_text in item', {
          length: item.output_text.length,
          preview: item.output_text.substring(0, 100)
        });
        return item.output_text;
      }

      const content = Array.isArray(item?.content) ? item.content : [];
      for (let j = 0; j < content.length; j++) {
        const part = content[j];
        console.log(`[openai] extractText: Processing content[${j}]`, {
          partType: typeof part,
          partKeys: part ? Object.keys(part) : [],
          hasOutputText: typeof part?.output_text === 'string',
          hasText: typeof part?.text === 'string'
        });

        if (typeof part?.output_text === 'string' && part.output_text.trim()) {
          console.log('[openai] extractText: Found output_text in content part', {
            length: part.output_text.length,
            preview: part.output_text.substring(0, 100)
          });
          return part.output_text;
        }
        if (typeof part?.text === 'string' && part.text.trim()) {
          console.log('[openai] extractText: Found text in content part', {
            length: part.text.length,
            preview: part.text.substring(0, 100)
          });
          return part.text;
        }
      }
    }
  }
  
  // If we get here, text was not found - log full structure
  console.error('[openai] extractText: Could not extract text from response. Full structure:', JSON.stringify(response, null, 2).substring(0, 2000));
  
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
