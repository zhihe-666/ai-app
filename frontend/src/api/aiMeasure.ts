/**
 * AI 编程数据报告 API 封装
 */
import { API_BASE } from '../utils/apiBase'
import { streamRequest } from '../utils/sse'

export interface TestTokenResult {
  ok: boolean
  message: string
}

export interface GenerateRequest {
  access_token: string
  pilot_names: string
  start_date: string
  end_date: string
  sections: string[]
}

export interface WriteToFeishuRequest {
  title: string
  content: string
}

export interface WriteToFeishuResult {
  doc_url: string
  title?: string
  error?: string
}

export interface ProgressEvent {
  section: string
  status: 'running' | 'complete' | 'error'
  message: string
}

export interface SectionCompleteEvent {
  section: string
  title: string
  row_count: number
  rows: any[]
  markdown: string
}

export interface SectionErrorEvent {
  section: string
  title: string
  message: string
}

export interface CompleteEvent {
  report_markdown: string
  sections_completed: number
  total_sections: number
}

/**
 * SSE 事件回调
 */
export interface GenerateCallbacks {
  onProgress?: (data: ProgressEvent) => void
  onSectionComplete?: (data: SectionCompleteEvent) => void
  onSectionError?: (data: SectionErrorEvent) => void
  onComplete: (data: CompleteEvent) => void
  onError?: (error: string) => void
}

/** 获取试点人员名单 */
export async function getPilotNames(): Promise<{ names: string }> {
  const resp = await fetch(`${API_BASE}/ai-measure/pilot-names`)
  return resp.json()
}

/** 保存试点人员名单 */
export async function savePilotNames(names: string): Promise<{ ok: boolean; message: string }> {
  const resp = await fetch(`${API_BASE}/ai-measure/pilot-names`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ names }),
  })
  return resp.json()
}

/** 获取 TL 名单 */
export async function getTlNames(): Promise<{ names: string }> {
  const resp = await fetch(`${API_BASE}/ai-measure/tl-names`)
  return resp.json()
}

/** 保存 TL 名单 */
export async function saveTlNames(names: string): Promise<{ ok: boolean; message: string }> {
  const resp = await fetch(`${API_BASE}/ai-measure/tl-names`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ names }),
  })
  return resp.json()
}

/** 测试 Token 连通性 */
export async function testToken(accessToken: string): Promise<TestTokenResult> {
  const resp = await fetch(`${API_BASE}/ai-measure/test-token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ access_token: accessToken }),
  })
  return resp.json()
}

/** 流式生成报告 — 使用 sse.ts 的 streamRequest */
export async function generateReport(
  req: GenerateRequest,
  callbacks: GenerateCallbacks,
  signal?: AbortSignal
): Promise<void> {
  await streamRequest('/ai-measure/generate', req, {
    onProgress: (data) => callbacks.onProgress?.(data as ProgressEvent),
    onSectionComplete: (data) => callbacks.onSectionComplete?.(data as SectionCompleteEvent),
    onSectionError: (data) => callbacks.onSectionError?.(data as SectionErrorEvent),
    onComplete: (data) => callbacks.onComplete(data as CompleteEvent),
    onError: (data) => callbacks.onError?.(data?.message || '生成失败'),
  }, signal)
}

/** 写入飞书文档 */
export async function writeToFeishu(req: WriteToFeishuRequest): Promise<WriteToFeishuResult> {
  const resp = await fetch(`${API_BASE}/ai-measure/write-to-feishu`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  return resp.json()
}