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

export type SyncMode = 'backend' | 'frontend' | 'full'

export interface SyncResponse {
  task_id: number
  status: string
  mode: string
  dry_run: boolean
  message: string
}

export interface SyncStatusResponse {
  task_id: number
  status: string
  started_at: string | null
  finished_at: string | null
  result_summary: string | null
  dry_run: boolean
}

export interface SnapshotInfo {
  snapshot_id: string
  created_at: string
  reason: string
  triggered_by: string
  total_chroma_records: number
  sqlite_tables: number
}

export interface SnapshotDetail {
  snapshot_id: string
  created_at: string
  reason: string
  triggered_by: string
  collections: Record<string, number>
  sqlite_tables: { table: string; count: number }[]
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

/** 6. 导入文本（collection 默认 manual_kb，可指定其他可写集合）*/
export async function importText(
  title: string,
  content: string,
  metadata?: Record<string, any>,
  collection?: string,
): Promise<ImportTextResponse> {
  const res = await client.post('/kb-manage/import', { title, content, metadata, collection })
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

/** 9. 触发代码同步（T025 3 模式） */
export async function triggerSync(mode: SyncMode = 'backend', dryRun = true): Promise<SyncResponse> {
  // 仅 backend 模式支持 dry_run，frontend/full 直接真实同步
  const query = mode === 'backend' ? `mode=${mode}&dry_run=${dryRun}` : `mode=${mode}`
  const res = await client.post(`/kb-manage/sync?${query}`)
  return res.data.data
}

/** 10. 轮询同步状态 */
export async function getSyncStatus(taskId: number): Promise<SyncStatusResponse> {
  const res = await client.get('/kb-manage/sync/status', { params: { task_id: taskId } })
  return res.data.data
}

// ── 快照与回退（T025 新增）──────────────────────────────────────

/** 11. 创建快照 */
export async function createSnapshot(reason = 'manual'): Promise<{ snapshot_id: string; message: string }> {
  const res = await client.post('/kb-manage/snapshots', null, { params: { reason } })
  return res.data.data
}

/** 12. 快照列表（时间倒序） */
export async function listSnapshots(): Promise<{ snapshots: SnapshotInfo[]; total: number }> {
  const res = await client.get('/kb-manage/snapshots')
  return res.data.data
}

/** 13. 快照详情 */
export async function getSnapshotDetail(snapshotId: string): Promise<SnapshotDetail> {
  const res = await client.get(`/kb-manage/snapshots/${snapshotId}`)
  return res.data.data
}

/** 14. 一键回退（危险操作） */
export async function rollbackSnapshot(snapshotId: string): Promise<{ snapshot_id: string; restored: object }> {
  const res = await client.post('/kb-manage/rollback', null, { params: { snapshot_id: snapshotId } })
  return res.data.data
}

/** 15. 删除快照 */
export async function deleteSnapshot(snapshotId: string): Promise<{ deleted: string }> {
  const res = await client.delete(`/kb-manage/snapshots/${snapshotId}`)
  return res.data.data
}

// ── 图谱查询（深度模式 Agent 2 数据源）────────────────────────

export interface PlatformModule {
  module_name: string
  node_count: number
  description?: string
}

export interface ModulesResponse {
  modules: PlatformModule[]
  total: number
}

export interface ModuleOverview {
  module_name: string
  controllers: GraphNode[]
  apis: GraphNode[]
  frontend_pages: GraphNode[]
  external_deps: GraphNode[]
  services?: GraphNode[]
  description?: string
}

export interface GraphNode {
  node_id?: string
  name?: string
  node_type?: string
  module?: string
  source_file?: string
  [key: string]: any
}

export interface ImpactNode {
  node: GraphNode
  depth: number
  path: string[]
  edge_types_traversed: string[]
}

export interface ImpactResult {
  origin: GraphNode
  direction: 'outgoing' | 'incoming'
  impacted: ImpactNode[]
  summary_by_type: Record<string, number>
  candidates?: GraphNode[]
}

export interface FlowChain {
  [key: string]: any
}

/** 16. 12 业务模块清单（架构快照索引） */
export async function listModules(): Promise<ModulesResponse> {
  const res = await client.get('/kb-manage/modules')
  return res.data.data
}

/** 17. 单模块架构快照（支持中文模块名） */
export async function getModuleOverview(name: string): Promise<ModuleOverview> {
  const res = await client.get(`/kb-manage/modules/${encodeURIComponent(name)}`)
  return res.data.data
}

/** 18. 定向影响范围分析（in=谁依赖我，out=我改波及谁） */
export async function graphImpact(
  node: string,
  direction: 'in' | 'out' = 'in',
  depth = 5,
): Promise<ImpactResult> {
  const res = await client.get('/kb-manage/graph/impact', {
    params: { node, direction, depth },
  })
  return res.data.data
}

/** 19. API 完整调用链（frontend → controller → service → executor） */
export async function graphFlow(api: string): Promise<FlowChain> {
  const res = await client.get('/kb-manage/graph/flow', { params: { api } })
  return res.data.data
}

/** 20. 单个图谱节点详情 */
export async function getGraphNode(nodeId: string): Promise<GraphNode> {
  const res = await client.get(`/kb-manage/graph/node/${encodeURIComponent(nodeId)}`)
  return res.data.data
}

// ── 组件注册表（RenderEngine 消费）─────────────────────

export interface RegistryProp {
  name: string
  type: string
  required: boolean
}

export interface RegistryComponent {
  name: string
  category: 'antd' | 'project' | 'business'
  source_file: string
  props: RegistryProp[]
  subcomponents: string[]
  used_in_pages: string[]
  reuse_count: number
  description?: string
}

// ── 历史 PRD 管理 ─────────────────────────────

export interface PRDInfo {
  prd_id: string
  title: string
  author?: string
  version?: string
  status: 'draft' | 'review' | 'approved' | 'archived'
  related_modules?: string[]
  feature_scope?: string[]
  summary?: string
  created_at: string
  updated_at: string
}

export interface PRDDetail extends PRDInfo {
  content: string
  metadata_json?: Record<string, any>
}

export interface PRDListResponse {
  total: number
  page: number
  page_size: number
  total_pages: number
  items: PRDInfo[]
}

export interface PRDSearchResult {
  prd_id: string
  title: string
  author?: string
  version?: string
  status: string
  summary?: string
  related_modules?: string
  score: number
}

export interface DesignLayoutsResponse {
  total_pages: number
  page_type_counts: Record<string, number>
  most_used_components: string[]
  modules: Record<string, any[]>
}

/** 22. 历史 PRD 列表 */
export async function listPRDs(page = 1, pageSize = 20, keyword = '', status = ''): Promise<PRDListResponse> {
  const res = await client.get('/kb-manage/prds', { params: { page, page_size: pageSize, keyword, status } })
  return res.data.data
}

/** 23. 创建历史 PRD */
export async function createPRD(data: { title: string; content?: string; author?: string; version?: string; status?: string; related_modules?: string[]; feature_scope?: string[]; summary?: string }): Promise<{ prd_id: string; title: string }> {
  const res = await client.post('/kb-manage/prds', data)
  return res.data.data
}

/** 24. PRD 详情（含全文 content） */
export async function getPRDDetail(prdId: string): Promise<PRDDetail> {
  const res = await client.get(`/kb-manage/prds/${prdId}`)
  return res.data.data
}

/** 25. 更新 PRD */
export async function updatePRD(prdId: string, data: Partial<PRDDetail>): Promise<{ prd_id: string; title: string }> {
  const res = await client.put(`/kb-manage/prds/${prdId}`, data)
  return res.data.data
}

/** 26. 删除 PRD */
export async function deletePRD(prdId: string): Promise<{ deleted: string }> {
  const res = await client.delete(`/kb-manage/prds/${prdId}`)
  return res.data.data
}

/** 27. 语义搜索 PRD */
export async function searchPRDs(query: string, topK = 5): Promise<{ query: string; results: PRDSearchResult[] }> {
  const res = await client.post(`/kb-manage/prds/search?query=${encodeURIComponent(query)}&top_k=${topK}`)
  return res.data.data
}

/** 28. 页面布局注册表 */
export async function getDesignLayouts(): Promise<DesignLayoutsResponse> {
  const res = await client.get('/kb-manage/design-layouts')
  return res.data.data
}

/** 21. 获取组件注册表（project/business 组件信息，供 RenderEngine 占位渲染） */
export async function getComponentRegistry(): Promise<RegistryComponent[]> {
  try {
    const res = await client.get('/kb-manage/components/registry')
    return res.data.data || []
  } catch {
    return []
  }
}