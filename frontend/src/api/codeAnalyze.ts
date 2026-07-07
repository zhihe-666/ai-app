/**
 * 代码变更分析 API 封装
 */
import { API_BASE } from '../utils/apiBase'
import { streamRequest } from '../utils/sse'

// ---- Types ----

export interface AnalysisRequest {
  repo_url?: string
  branch?: string
  frontend_paths?: string[]
  start_time: string
  end_time: string
  git_token?: string
}

export interface AnalysisResult {
  task_id?: string
  summary?: {
    analyzed_files: number
    feature_groups: number
    functional_changes?: number
    ui_changes?: number
  }
  functional_changes?: Array<{
    name: string
    confidence: number
    evidence_files: string[]
    description: string
    user_visible?: boolean
  }>
  removed_features?: Array<{
    name: string
    evidence_files: string[]
    description: string
  }>
  ui_updates?: string[]
  llm_status?: string
}

export interface ProgressEvent {
  step: string
  step_index?: number
  total_steps?: number
  message: string
  percentage: number
}

export interface SectionCompleteEvent {
  section: string
  message: string
  [key: string]: unknown
}

export interface TaskStatus {
  task_id: string
  status: string
  current_step: string
  step_index: number
  total_steps: number
  percentage: number
}

export interface SnapshotInfo {
  projectName?: string
  generatedAt?: string
  applications?: Array<{ name: string; path: string; role: string }>
}

// ---- API Functions ----

const LLM_CONFIG_KEY = 'ai_center_llm_config'

function getGitToken(): string {
  try {
    const raw = localStorage.getItem(LLM_CONFIG_KEY)
    if (raw) {
      const config = JSON.parse(raw)
      return config.gitToken || ''
    }
  } catch {}
  return ''
}

export function startAnalysis(
  params: AnalysisRequest,
  callbacks: {
    onProgress?: (data: ProgressEvent) => void
    onSectionComplete?: (data: SectionCompleteEvent) => void
    onComplete?: (data: AnalysisResult) => void
    onError?: (error: string) => void
  }
): AbortController {
  const controller = new AbortController()
  const body = { ...params, git_token: getGitToken() }

  streamRequest(
    '/code-analyze/start',
    body,
    {
      onProgress: callbacks.onProgress,
      onSectionComplete: callbacks.onSectionComplete,
      onComplete: (data: any) => callbacks.onComplete?.(data as AnalysisResult),
      onError: (data: any) => callbacks.onError?.(data?.error || data?.message || '未知错误'),
    },
    controller.signal
  ).catch((err) => {
    if (err?.name !== 'AbortError') {
      callbacks.onError?.(err?.message || '请求失败')
    }
  })

  return controller
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const res = await fetch(`${API_BASE}/code-analyze/status/${taskId}`)
  return res.json()
}

export function refreshSnapshot(callbacks: {
  onProgress?: (data: ProgressEvent) => void
  onComplete?: (data: { section: string; message: string }) => void
  onError?: (error: string) => void
}): AbortController {
  const controller = new AbortController()

  streamRequest(
    '/code-analyze/refresh-snapshot',
    {},
    {
      onProgress: callbacks.onProgress,
      onComplete: (data: any) => callbacks.onComplete?.(data as { section: string; message: string }),
      onError: (data: any) => callbacks.onError?.(data?.error || data?.message || '刷新失败'),
    },
    controller.signal
  ).catch((err) => {
    if (err?.name !== 'AbortError') {
      callbacks.onError?.(err?.message || '请求失败')
    }
  })

  return controller
}

export async function getSnapshotInfo(): Promise<SnapshotInfo> {
  const res = await fetch(`${API_BASE}/code-analyze/snapshot`)
  return res.json()
}

export async function exportMarkdown(result: AnalysisResult): Promise<void> {
  const res = await fetch(`${API_BASE}/code-analyze/export/markdown`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ result }),
  })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `code-analyze-report-${Date.now()}.md`
  a.click()
  URL.revokeObjectURL(url)
}

export async function exportToFeishu(result: AnalysisResult): Promise<string> {
  const res = await fetch(`${API_BASE}/code-analyze/export/feishu`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ result }),
  })
  const data = await res.json()
  if (!data.success) throw new Error(data.error || '导出失败')
  return data.doc_url
}

// ---- Repo Cache ----

export interface RepoCache {
  cached: boolean
  repo_url?: string
  branch?: string
  frontend_paths?: string[]
}

export async function getRepoCache(repoUrl: string): Promise<RepoCache> {
  const res = await fetch(`${API_BASE}/auth/repo-cache?repo_url=${encodeURIComponent(repoUrl)}`)
  return res.json()
}

export async function saveRepoCache(repoUrl: string, branch: string, frontendPaths: string[]): Promise<void> {
  await fetch(`${API_BASE}/auth/repo-cache`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url: repoUrl, branch, frontend_paths: frontendPaths }),
  })
}