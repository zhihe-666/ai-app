/**
 * 知识库管理 API 封装
 *
 * 全部代理到后端 /api/kb-manage/*，后端再转发到无矩2.0 :8000/api/admin/*
 */
import client from './client'

// ── Types ──────────────────────────────────────────────────────

export interface Collection {
  name: string
  count: number
  type: 'auto_generated' | 'user_imported'
  description: string
}

export interface SyncStatus {
  last_sync: string
  status: string
  fingerprint_methods: number
}

export interface CollectionsResponse {
  collections: Collection[]
  total_docs: number
  sync_status: SyncStatus
}

export interface BrowseDoc {
  id: string
  title?: string
  file_name?: string
  file_format?: string
  preview: string
  preview_length: number
  metadata?: Record<string, any>
  doc_type: string
  imported_at?: string
}

export interface BrowseResponse {
  collection: string
  page: number
  page_size: number
  total: number
  total_pages: number
  docs: BrowseDoc[]
}

export interface DocDetail {
  id: string
  content: string
  metadata?: Record<string, any>
  collection: string
}

export interface SqliteDatabase {
  name: string
  path: string
  description: string
  tables: { name: string; count: number; description: string }[]
}

export interface SqliteTablesResponse {
  databases: SqliteDatabase[]
}

export interface SqliteTableResponse {
  database: string
  table: string
  columns: string[]
  rows: string[][]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ImportTextResponse {
  id: string
  title: string
  collection: string
  chunks: number
  file_name: string | null
  file_format: string | null
}

export interface ImportFileResponse {
  id: string
  title: string
  file_name: string
  file_format: string
  content_length: number
  chunks: number
  collection: string
}

export interface DeleteResponse {
  deleted: boolean
  collection: string
  doc_id: string
}

export interface SyncResponse {
  task_id: number
  status: string
  message: string
  dry_run: boolean
}

export interface SyncStatusResponse {
  task_id: number
  status: string
  started_at: string | null
  finished_at: string | null
  result_summary: string | null
  dry_run: boolean
}

// ── API Functions ──────────────────────────────────────────────

/** 1. 知识库概览 */
export async function getCollections(): Promise<CollectionsResponse> {
  const res = await client.get('/kb-manage/collections')
  return res.data.data
}

/** 2. 浏览集合内容 */
export async function browseCollection(collection: string, page = 1, pageSize = 20, keyword = ''): Promise<BrowseResponse> {
  const res = await client.get('/kb-manage/browse', { params: { collection, page, page_size: pageSize, keyword } })
  return res.data.data
}

/** 3. 查看单条文档全文 */
export async function getDocument(collection: string, docId: string): Promise<DocDetail> {
  const res = await client.get('/kb-manage/doc', { params: { collection, doc_id: docId } })
  return res.data.data
}

/** 4. SQLite 数据库/表列表 */
export async function getSqliteTables(): Promise<SqliteTablesResponse> {
  const res = await client.get('/kb-manage/sqlite/tables')
  return res.data.data
}

/** 5. SQLite 表内容 */
export async function getSqliteTable(dbName: string, tableName: string, page = 1, pageSize = 20): Promise<SqliteTableResponse> {
  const res = await client.get('/kb-manage/sqlite/table', { params: { db_name: dbName, table_name: tableName, page, page_size: pageSize } })
  return res.data.data
}

/** 6. 导入文本 */
export async function importText(title: string, content: string, metadata?: Record<string, any>): Promise<ImportTextResponse> {
  const res = await client.post('/kb-manage/import', { title, content, metadata })
  return res.data.data
}

/** 7. 导入文件 */
export async function importFile(file: File, title?: string, metadata?: string): Promise<ImportFileResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (title) formData.append('title', title)
  if (metadata) formData.append('metadata', metadata)
  const res = await client.post('/kb-manage/import/file', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data.data
}

/** 8. 删除文档 */
export async function deleteDocument(collection: string, docId: string): Promise<DeleteResponse> {
  const res = await client.delete('/kb-manage/delete', { data: { collection, doc_id: docId } })
  return res.data.data
}

/** 9. 触发代码同步 */
export async function triggerSync(dryRun = true, rebuildCore = false, rebuildWiki = false): Promise<SyncResponse> {
  const res = await client.post(`/kb-manage/sync?dry_run=${dryRun}&rebuild_core=${rebuildCore}&rebuild_wiki=${rebuildWiki}`)
  return res.data.data
}

/** 10. 轮询同步状态 */
export async function getSyncStatus(taskId: number): Promise<SyncStatusResponse> {
  const res = await client.get('/kb-manage/sync/status', { params: { task_id: taskId } })
  return res.data.data
}