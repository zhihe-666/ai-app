/**
 * 通用 SSE 流式请求
 *
 * 按 SSE 规范 (\n\n 事件分隔) 解析, 正确处理 TCP chunk
 * 截断导致 data: JSON 行被拆分的场景。
 */
import { API_BASE } from './apiBase'

interface SSEHandlers {
  onProgress?: (data: any) => void
  onSectionComplete?: (data: any) => void
  onSectionError?: (data: any) => void
  onComplete?: (data: any) => void
  onError?: (data: any) => void
  onAgentComplete?: (data: any) => void
  onGate?: (data: any) => void
  onValidation?: (data: any) => void
}

const LLM_CONFIG_KEY = 'ai_center_llm_config'

function getLlmHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  try {
    const raw = localStorage.getItem(LLM_CONFIG_KEY)
    if (raw) {
      const config = JSON.parse(raw)
      if (config.apiKey) headers['X-Api-Key'] = config.apiKey
      if (config.baseUrl) headers['X-Base-Url'] = config.baseUrl
      if (config.model) headers['X-Model'] = config.model
    }
  } catch {
    // localStorage not available
  }
  return headers
}

/**
 * 从 SSE 事件块中提取 event type 和 data 字段
 *
 * 输入: 一个完整的 SSE 事件块 (不含结尾的 \n\n)
 * 例如:
 *   event: section_complete
 *   data: {"section":"active_rate",...}
 */
function parseSseBlock(block: string): { eventType: string; dataStr: string } {
  let eventType = ''
  const dataParts: string[] = []

  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) {
      eventType = line.slice(7).trim()
    } else if (line.startsWith('data: ')) {
      dataParts.push(line.slice(6))
    }
    // ignore other fields (id, retry, etc.)
  }

  return { eventType, dataStr: dataParts.join('\n') }
}

export async function streamRequest(url: string, body: any, handlers: SSEHandlers, signal?: AbortSignal) {
  const response = await fetch(`${API_BASE}${url}`, {
    method: 'POST',
    headers: getLlmHeaders(),
    body: JSON.stringify(body),
    signal,
  })

  if (!response.ok) {
    const text = await response.text()
    handlers.onError?.({ message: `请求失败 (${response.status}): ${text}` })
    return
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''      // 跨 chunk 的不完整数据

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // 按 \n\n 切分 — SSE 事件分隔符
      // buffer 中保留最后一段 (可能不完整)
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''

      for (const part of parts) {
        const trimmed = part.trim()
        if (!trimmed) continue

        const { eventType, dataStr } = parseSseBlock(trimmed)
        if (!dataStr) continue

        try {
          const data = JSON.parse(dataStr)
          switch (eventType) {
            case 'progress':
              handlers.onProgress?.(data)
              break
            case 'section_complete':
            case 'transcript_ready':
              handlers.onSectionComplete?.(data)
              break
            case 'section_error':
              handlers.onSectionError?.(data)
              break
            case 'agent_complete':
              handlers.onAgentComplete?.(data)
              break
            case 'gate':
              handlers.onGate?.(data)
              break
            case 'validation':
              handlers.onValidation?.(data)
              break
            case 'complete':
              handlers.onComplete?.(data)
              break
            case 'error':
              handlers.onError?.(data)
              break
          }
        } catch {
          // 仍然解析失败 — 丢弃 (非致命)
        }
      }
    }
  } catch (err: any) {
    if (err?.name === 'AbortError') return
    throw err
  }
}