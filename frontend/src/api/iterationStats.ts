import client from './client'

/** 后端返回的原始行字段名 */
export interface RawStatsRow {
  project_name: string
  tl?: string
  total: number
  engineering: number
  aicoding: number
  aicoding_ratio: string
  sdd: number
  sdd_ratio: string
  e2e: number
  source_file?: string
  detail_count?: number
}

/** 前端展示时用的别名（兼容后端 project_name 字段） */
export type StatsRow = RawStatsRow & {
  /** 展示用快捷别名：project = project_name */
  project: string
  project_link: string
  fully_scheduled: number
}

export interface UploadResult {
  rows: RawStatsRow[]
  version: string
}

export interface BitableWriteResult {
  success: boolean
  updated_count: number
  errors: string[]
}

/** 从 RawStatsRow 数组计算合计行（用于导出/write-bitable，tl 为空） */
export function computeRawSummary(rows: RawStatsRow[]): RawStatsRow {
  const total = rows.reduce((s, r) => s + (r.total || 0), 0)
  const engineering = rows.reduce((s, r) => s + (r.engineering || 0), 0)
  const aicoding = rows.reduce((s, r) => s + (r.aicoding || 0), 0)
  const sdd = rows.reduce((s, r) => s + (r.sdd || 0), 0)
  const e2e = rows.reduce((s, r) => s + (r.e2e || 0), 0)

  const aicoding_ratio = engineering > 0 ? `${((aicoding / engineering) * 100).toFixed(2)}%` : '0%'
  const sdd_ratio = aicoding > 0 ? `${((sdd / aicoding) * 100).toFixed(2)}%` : '0%'

  return {
    project_name: '合计',
    tl: '',
    total,
    engineering,
    aicoding,
    aicoding_ratio,
    sdd,
    sdd_ratio,
    e2e,
  }
}

/** 将后端原始行转为前端展示行 */
export function normalizeRows(raw: RawStatsRow[]): StatsRow[] {
  return raw.map(r => ({
    ...r,
    project: r.project_name,
    project_link: '',
    fully_scheduled: 0,
  }))
}

/** 计算前端汇总行（含 StatsRow 额外字段） */
export function computeSummary(rows: StatsRow[]): StatsRow {
  const total = rows.reduce((s, r) => s + (r.total || 0), 0)
  const engineering = rows.reduce((s, r) => s + (r.engineering || 0), 0)
  const aicoding = rows.reduce((s, r) => s + (r.aicoding || 0), 0)
  const sdd = rows.reduce((s, r) => s + (r.sdd || 0), 0)
  const e2e = rows.reduce((s, r) => s + (r.e2e || 0), 0)

  const aicoding_ratio = engineering > 0 ? `${((aicoding / engineering) * 100).toFixed(1)}%` : '0%'
  const sdd_ratio = aicoding > 0 ? `${((sdd / aicoding) * 100).toFixed(1)}%` : '0%'

  return {
    project_name: '合计',
    project: '合计',
    project_link: '',
    tl: '',
    total,
    fully_scheduled: 0,
    engineering,
    aicoding,
    aicoding_ratio,
    sdd,
    sdd_ratio,
    e2e,
  }
}

/**
 * 上传 xlsx 文件 → 解析统计 → 返回结果
 */
export async function uploadStats(files: File[], version: string): Promise<UploadResult> {
  const formData = new FormData()
  files.forEach(f => formData.append('files', f))
  formData.append('version', version)
  const res = await client.post('/stats/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

/**
 * 将统计结果写入飞书多维表格
 */
export async function writeBitable(version: string, rows: RawStatsRow[]): Promise<BitableWriteResult> {
  const res = await client.post('/stats/write-bitable', { version, rows })
  return res.data
}

/**
 * 导出统计结果为 xlsx 文件（触发下载）
 */
export async function exportStatsXlsx(rows: RawStatsRow[], version: string): Promise<Blob> {
  const res = await client.post('/stats/export', { rows, version }, {
    responseType: 'blob',
  })
  return res.data
}