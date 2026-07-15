import client from './client'

export interface ChatContext {
  content: string
  collection: string
  score: number
  metadata: Record<string, any>
}

export interface QueryContextsResponse {
  query: string
  contexts: ChatContext[]
}

export interface ChatSessionListItem {
  id: string
  title: string
  query: string
  created_at: string
}

export interface ChatSessionDetail extends ChatSessionListItem {
  answer: string
  sources: ChatContext[]
}

/** 流式问答（页面直接用 fetch + ReadableStream，这里保留兼容）*/
export async function sendMessage(query: string, conversationId?: string) {
  return client.post('/chat/send', { query, conversation_id: conversationId })
}

/** 非流式查询 → 返回检索 contexts（中控台自管 LLM 场景用）
 *  对齐 T025 文档 2.2：POST /api/query
 */
export async function queryContexts(query: string): Promise<QueryContextsResponse> {
  const res = await client.post('/chat/query', { query })
  return res.data
}

/** 问答历史列表（时间倒序） */
export async function listConversations(limit = 50): Promise<{ conversations: ChatSessionListItem[] }> {
  const res = await client.get('/chat/conversations', { params: { limit } })
  return res.data
}

/** 单条问答历史详情 */
export async function getConversation(sessionId: string): Promise<ChatSessionDetail> {
  const res = await client.get(`/chat/conversations/${sessionId}`)
  return res.data
}

/** 删除单条问答历史 */
export async function deleteConversation(sessionId: string): Promise<{ deleted: string }> {
  const res = await client.delete(`/chat/conversations/${sessionId}`)
  return res.data
}

/** 清空所有问答历史 */
export async function clearConversations(): Promise<{ deleted_count: number }> {
  const res = await client.delete('/chat/conversations')
  return res.data
}
