/**
 * prdGen.ts — PRD 智能生成 API 封装
 *
 * 所有 SSE 流式接口复用 utils/sse.ts 的 streamRequest。
 * 所有同步接口使用 fetch，自动注入 LLM 请求头。
 * 导出接口使用 window.open 触发浏览器下载。
 */
import { API_BASE } from '../utils/apiBase'
import { streamRequest } from '../utils/sse'

// ── 类型定义 ──

export interface PRDSession {
  sessionId: string
  mode: 'simple' | 'medium' | 'deep'
  status: 'init' | 'chatting' | 'writing' | 'done'
}

export interface ChatRoundResponse {
  round: number
  question?: string
  status?: 'chatting' | 'ready_for_outline'
  reason?: string
  topic?: string
}

export interface CompletenessResult {
  completeness: number
  missingItems: string[]
}

export interface OutlineResult {
  outline: string[]
}

export interface SectionEvent {
  step?: string
  chunk?: string
  section: string
}

export interface SectionCompleteEvent {
  section: string
  content?: string
  outline?: string[]
  versionId?: string
}

export interface VersionInfo {
  id: string
  session_id: string
  section: string
  version_num: number
  created_at: string
}

export interface VersionContent extends VersionInfo {
  content: string
}

export interface MinutesParseResult {
  status: string
  minuteTitle: string
  extractedPoints: {
    featurePoints: string[]
    stakeholders: string[]
    constraints: string[]
    background: string
  }
}

export interface FileUploadResult {
  id: string
  filename: string
  file_type: 'temporary' | 'permanent'
  text_preview: string
}

/** SSE 事件回调（简单模式 / 章节生成） */
export interface SectionCallbacks {
  onProgress?: (data: SectionEvent) => void
  onSectionComplete?: (data: SectionCompleteEvent) => void
  onError?: (data: { message: string }) => void
  onComplete?: (data: { sessionId: string }) => void
}

// ── 深度模式类型 ──

export interface AgentCompleteEvent {
  agent: string
  data: any
  message?: string
}

export interface GateEvent {
  gate: 'conflict' | 'impact' | 'spec' | 'prototype' | 'agent1_review'
  conflicts?: any[]
  impact_warnings?: any[]
  features?: any[]
  requirements?: any
  gaps?: string[]
  message?: string
}

export interface ValidationIssue {
  level: 'error' | 'warn'
  field: string
  message: string
  action: string
}

export interface ValidationEvent {
  stage?: string
  validator?: string
  issues: ValidationIssue[]
  retry?: boolean
}

export interface DeepCallbacks {
  onProgress?: (data: any) => void
  onAgentComplete?: (data: AgentCompleteEvent) => void
  onGate?: (data: GateEvent) => void
  onValidation?: (data: ValidationEvent) => void
  onComplete?: (data: { sessionId: string; message: string; has_prd?: boolean }) => void
  onError?: (data: { message: string }) => void
}

// ── HTTP 工具 ──

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  try {
    const raw = localStorage.getItem('ai_center_llm_config')
    if (raw) {
      const cfg = JSON.parse(raw)
      if (cfg.apiKey) headers['X-Api-Key'] = cfg.apiKey
      if (cfg.baseUrl) headers['X-Base-Url'] = cfg.baseUrl
      if (cfg.model) headers['X-Model'] = cfg.model
    }
  } catch { /* ignore */ }
  return headers
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${API_BASE}/prd${path}`, {
    method: 'POST',
    headers: getHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`请求失败 (${resp.status}): ${text}`)
  }
  return resp.json()
}

async function get_<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}/prd${path}`, {
    method: 'GET',
    headers: getHeaders(),
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`请求失败 (${resp.status}): ${text}`)
  }
  return resp.json()
}

// ── API 函数 ──

/** 1. 创建会话 */
export async function createSession(mode: 'simple' | 'medium' | 'deep', userInput: string): Promise<PRDSession> {
  return post('/sessions', { mode, userInput })
}

/** 2. 简单模式 SSE 生成 */
export async function simpleGenerate(
  sessionId: string,
  callbacks: SectionCallbacks,
  signal?: AbortSignal,
  ragEnabled: boolean = true,
): Promise<void> {
  await streamRequest(
    `/prd/sessions/${sessionId}/simple-generate`,
    { rag_enabled: ragEnabled },
    {
      onProgress: (data) => callbacks.onProgress?.(data as SectionEvent),
      onSectionComplete: (data) => callbacks.onSectionComplete?.(data as SectionCompleteEvent),
      onComplete: (data) => callbacks.onComplete?.(data as { sessionId: string }),
      onError: (data) => callbacks.onError?.(data as { message: string }),
    },
    signal,
  )
}

/** 2b. 深度模式 SSE 生成（4 Agent + 3 闸口） */
export async function deepGenerate(
  sessionId: string,
  callbacks: DeepCallbacks,
  signal?: AbortSignal,
  ragEnabled: boolean = true,
): Promise<void> {
  await streamRequest(
    `/prd/sessions/${sessionId}/deep-generate`,
    { rag_enabled: ragEnabled },
    {
      onProgress: (data) => callbacks.onProgress?.(data),
      onAgentComplete: (data) => callbacks.onAgentComplete?.(data as AgentCompleteEvent),
      onGate: (data) => callbacks.onGate?.(data as GateEvent),
      onValidation: (data) => callbacks.onValidation?.(data as ValidationEvent),
      onComplete: (data) => callbacks.onComplete?.(data as any),
      onError: (data) => callbacks.onError?.(data as { message: string }),
    },
    signal,
  )
}

/** 2c. 深度模式人工闸口审批 */
export async function approveGate(
  sessionId: string,
  gate: 'conflict' | 'impact' | 'spec' | 'prototype' | 'agent1_review',
  approved: boolean,
  modifications?: string,
): Promise<{ ok: boolean; gate: string; approved: boolean }> {
  return post(`/sessions/${sessionId}/deep/approve`, { gate, approved, modifications: modifications || '' })
}

/** 2d. 深度模式 AI 原型增强（独立端点，闸口外触发） */
export async function deepPrototype(sessionId: string): Promise<{ html: string; sections: any[]; feature: string; spec: any }> {
  return post(`/sessions/${sessionId}/deep/prototype`, {})
}

/** 3. 启动中等模式对话 */
export async function startChat(sessionId: string): Promise<ChatRoundResponse> {
  return post(`/sessions/${sessionId}/start-chat`)
}

/** 4. 中等模式对话轮次 */
export async function chatRound(sessionId: string, answer: string): Promise<ChatRoundResponse> {
  return post(`/sessions/${sessionId}/chat`, { answer })
}

/** 4a. 重新讨论已完成话题 */
export async function rechatTopic(sessionId: string, topic: string): Promise<ChatRoundResponse> {
  return post(`/sessions/${sessionId}/rechat-topic`, { topic })
}

/** 4. 查询完备度 */
export async function getCompleteness(sessionId: string): Promise<CompletenessResult> {
  return get_(`/sessions/${sessionId}/completeness`)
}

/** 5. 生成大纲 */
export async function generateOutline(sessionId: string): Promise<OutlineResult> {
  return post(`/sessions/${sessionId}/outline`)
}

/** 6. 章节 SSE 生成 */
export async function generateSection(
  sessionId: string,
  section: string,
  callbacks: SectionCallbacks,
  signal?: AbortSignal,
  ragEnabled: boolean = true,
): Promise<void> {
  await streamRequest(
    `/prd/sessions/${sessionId}/sections/${section}/generate`,
    { rag_enabled: ragEnabled },
    {
      onProgress: (data) => callbacks.onProgress?.(data as SectionEvent),
      onSectionComplete: (data) => callbacks.onSectionComplete?.(data as SectionCompleteEvent),
      onError: (data) => callbacks.onError?.(data as { message: string }),
    },
    signal,
  )
}

/** 7. 编辑章节 */
export async function updateSection(sessionId: string, section: string, content: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/prd/sessions/${sessionId}/sections/${section}`, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify({ content }),
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`编辑失败 (${resp.status}): ${text}`)
  }
}

/** 8. 重新生成章节 */
export async function regenerateSection(
  sessionId: string,
  section: string,
  callbacks: SectionCallbacks,
  signal?: AbortSignal,
  ragEnabled: boolean = true,
): Promise<void> {
  await streamRequest(
    `/prd/sessions/${sessionId}/sections/${section}/regenerate`,
    { rag_enabled: ragEnabled },
    {
      onProgress: (data) => callbacks.onProgress?.(data as SectionEvent),
      onSectionComplete: (data) => callbacks.onSectionComplete?.(data as SectionCompleteEvent),
      onError: (data) => callbacks.onError?.(data as { message: string }),
    },
    signal,
  )
}

/** 9. 版本列表 */
export async function getVersions(sessionId: string, section?: string): Promise<{ versions: VersionInfo[] }> {
  const qs = section ? `?section=${encodeURIComponent(section)}` : ''
  return get_(`/sessions/${sessionId}/versions${qs}`)
}

/** 10. 版本内容 */
export async function getVersionContent(sessionId: string, versionId: string): Promise<VersionContent> {
  return get_(`/sessions/${sessionId}/versions/${versionId}`)
}

/** 11. 导出 PRD */
export function exportPRD(sessionId: string): void {
  // 使用 window.open 触发 GET 下载（自动携带 Cookie/Header）
  // 对于需要 Authorization header 的场景，用 fetch + blob 代替
  const params = new URLSearchParams()
  try {
    const raw = localStorage.getItem('ai_center_llm_config')
    if (raw) {
      const cfg = JSON.parse(raw)
      if (cfg.apiKey) params.set('api_key', cfg.apiKey)
    }
  } catch { /* ignore */ }
  const qs = params.toString()
  window.open(`${API_BASE}/prd/sessions/${sessionId}/export${qs ? '?' + qs : ''}`, '_blank')
}

/** 11b. 导出 PRD 到飞书文档（返回飞书文档 URL） */
export async function exportPRDToFeishu(sessionId: string): Promise<{ url: string; title: string }> {
  return post(`/sessions/${sessionId}/export/feishu`, {})
}

/** 12. 文件上传 */
export async function uploadFile(
  sessionId: string,
  file: File,
  fileType: 'temporary' | 'permanent',
): Promise<FileUploadResult> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('session_id', sessionId)
  formData.append('file_type', fileType)

  const headers: Record<string, string> = {}
  try {
    const raw = localStorage.getItem('ai_center_llm_config')
    if (raw) {
      const cfg = JSON.parse(raw)
      if (cfg.apiKey) headers['X-Api-Key'] = cfg.apiKey
      if (cfg.baseUrl) headers['X-Base-Url'] = cfg.baseUrl
      if (cfg.model) headers['X-Model'] = cfg.model
    }
  } catch { /* ignore */ }

  const resp = await fetch(`${API_BASE}/prd/files/upload`, {
    method: 'POST',
    headers,
    body: formData,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`上传失败 (${resp.status}): ${text}`)
  }
  return resp.json()
}

/** 13. 妙记解析 */
export async function parseMinutes(
  sessionId: string,
  url: string,
): Promise<MinutesParseResult> {
  return post(`/sessions/${sessionId}/minutes`, { url })
}
