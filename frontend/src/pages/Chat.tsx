import { useState, useRef, useEffect, useCallback } from 'react'
import { Typography, Input, Button, Card, Tag, Space, Avatar, Collapse, Spin, Empty, Tooltip, Popconfirm } from 'antd'
import { SendOutlined, RobotOutlined, UserOutlined, FileTextOutlined, LinkOutlined, HistoryOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { listConversations, getConversation, deleteConversation, clearConversations, type ChatSessionListItem } from '../api/chat'

const { Title, Text } = Typography

interface Source {
  collection: string
  score: number
  name?: string
  content?: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const msgEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // 历史对话
  const [history, setHistory] = useState<ChatSessionListItem[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)

  // 加载历史列表
  const loadHistory = useCallback(async () => {
    setLoadingHistory(true)
    try {
      const data = await listConversations(50)
      setHistory(data.conversations || [])
    } catch {
      // 忽略
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  // 自动滚动到底部
  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // 点击历史 → 加载详情到对话区
  const handleHistoryClick = useCallback(async (sessionId: string) => {
    try {
      const detail = await getConversation(sessionId)
      setActiveSessionId(sessionId)
      setMessages([
        { role: 'user', content: detail.query },
        { role: 'assistant', content: detail.answer, sources: detail.sources || [] },
      ])
      setError(null)
    } catch {
      // 忽略
    }
  }, [])

  // 删除单条历史
  const handleDeleteHistory = useCallback(async (sessionId: string) => {
    try {
      await deleteConversation(sessionId)
      setHistory(prev => prev.filter(h => h.id !== sessionId))
      if (activeSessionId === sessionId) {
        setActiveSessionId(null)
        setMessages([])
      }
    } catch {
      // 忽略
    }
  }, [activeSessionId])

  // 清空历史
  const handleClearHistory = useCallback(async () => {
    try {
      await clearConversations()
      setHistory([])
      setActiveSessionId(null)
      setMessages([])
    } catch {
      // 忽略
    }
  }, [])

  // 新建对话
  const handleNewChat = useCallback(() => {
    setActiveSessionId(null)
    setMessages([])
    setInput('')
    setError(null)
  }, [])

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const query = input.trim()
    setInput('')
    setError(null)

    // 添加用户消息
    setMessages(prev => [...prev, { role: 'user', content: query }])

    // 添加占位助手消息
    const msgIdx = messages.length + 1
    setMessages(prev => [...prev, { role: 'assistant', content: '', sources: [] }])
    setLoading(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch('/api/chat/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.error || `请求失败 (${res.status})`)
      }

      const reader = res.body?.getReader()
      if (!reader) throw new Error('无法读取响应流')

      const decoder = new TextDecoder()
      let buffer = ''
      let currentSources: Source[] = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // 保留未完成行

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const dataStr = line.slice(6).trim()
          if (!dataStr) continue

          try {
            const parsed = JSON.parse(dataStr)
            const type = parsed.type

            if (type === 'sources') {
              currentSources = parsed.sources || []
              // 更新消息的 sources
              setMessages(prev => {
                const copy = [...prev]
                const last = copy[copy.length - 1]
                if (last?.role === 'assistant') {
                  copy[copy.length - 1] = { ...last, sources: currentSources }
                }
                return copy
              })
            } else if (type === 'token') {
              const token = parsed.content || ''
              setMessages(prev => {
                const copy = [...prev]
                const last = copy[copy.length - 1]
                if (last?.role === 'assistant') {
                  copy[copy.length - 1] = { ...last, content: last.content + token }
                }
                return copy
              })
            } else if (type === 'done') {
              break
            } else if (type === 'error') {
              setError(parsed.content || '查询出错')
              // 更新最后一条消息显示错误
              setMessages(prev => {
                const copy = [...prev]
                const last = copy[copy.length - 1]
                if (last?.role === 'assistant') {
                  copy[copy.length - 1] = { ...last, content: `❌ ${parsed.content || '查询出错'}` }
                }
                return copy
              })
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return
      const errMsg = err.message || '网络错误'
      setError(errMsg)
      setMessages(prev => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last?.role === 'assistant') {
          copy[copy.length - 1] = { ...last, content: `❌ ${errMsg}` }
        }
        return copy
      })
    } finally {
      setLoading(false)
      abortRef.current = null
      // 刷新历史列表（流式结束后后端已存历史）
      loadHistory()
    }
  }

  return (
    <div style={{ padding: 24, height: '100%', display: 'flex', gap: 16 }}>
      {/* 左侧历史侧边栏 */}
      <Card
        size="small"
        style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column' }}
        bodyStyle={{ flex: 1, display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}
      >
        <div style={{ padding: '12px 12px 8px', display: 'flex', gap: 8, borderBottom: '1px solid #f0f0f0' }}>
          <Button type="primary" block icon={<FileTextOutlined />} onClick={handleNewChat}
            style={{ background: '#6366f1', borderColor: '#6366f1' }}>
            新对话
          </Button>
        </div>
        <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Space size={4}>
            <HistoryOutlined style={{ color: '#6b7280' }} />
            <Text type="secondary" style={{ fontSize: 12 }}>历史记录</Text>
          </Space>
          <Space size={4}>
            <Tooltip title="刷新">
              <ReloadOutlined style={{ color: '#9ca3af', cursor: 'pointer', fontSize: 13 }} onClick={loadHistory} />
            </Tooltip>
            {history.length > 0 && (
              <Popconfirm title="清空所有历史？" okText="清空" cancelText="取消" onConfirm={handleClearHistory}>
                <Tooltip title="清空">
                  <DeleteOutlined style={{ color: '#9ca3af', cursor: 'pointer', fontSize: 13 }} />
                </Tooltip>
              </Popconfirm>
            )}
          </Space>
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {loadingHistory ? (
            <div style={{ textAlign: 'center', padding: 20 }}><Spin size="small" /></div>
          ) : history.length === 0 ? (
            <div style={{ padding: 20 }}>
              <Empty description={<Text type="secondary" style={{ fontSize: 12 }}>暂无历史</Text>} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </div>
          ) : (
            history.map(h => (
              <div
                key={h.id}
                onClick={() => handleHistoryClick(h.id)}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  borderBottom: '1px solid #f8f8f8',
                  background: activeSessionId === h.id ? '#eef2ff' : 'transparent',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 4,
                }}
                onMouseEnter={e => { if (activeSessionId !== h.id) e.currentTarget.style.background = '#f9fafb' }}
                onMouseLeave={e => { if (activeSessionId !== h.id) e.currentTarget.style.background = 'transparent' }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 13,
                    color: activeSessionId === h.id ? '#4f46e5' : '#1f2937',
                    fontWeight: activeSessionId === h.id ? 500 : 400,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {h.title}
                  </div>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {h.created_at}
                  </Text>
                </div>
                <DeleteOutlined
                  style={{ color: '#d1d5db', fontSize: 12, flexShrink: 0 }}
                  onClick={e => { e.stopPropagation(); handleDeleteHistory(h.id) }}
                />
              </div>
            ))
          )}
        </div>
      </Card>

      {/* 右侧对话区 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Header */}
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Tag icon={<RobotOutlined />} color="purple">无矩 2.0 知识库</Tag>
          <Title level={3} style={{ margin: 0 }}>知识库问答</Title>
        </div>

        {/* Messages */}
        <Card
          style={{
            flex: 1,
            overflow: 'auto',
            marginBottom: 16,
            display: 'flex',
            flexDirection: 'column',
          }}
          bodyStyle={{ flex: 1, display: 'flex', flexDirection: 'column' }}
        >
        {messages.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
            <Avatar size={64} icon={<RobotOutlined />} style={{ background: '#6366f1' }} />
            <Title level={4} style={{ margin: 0 }}>无矩 2.0 知识库问答</Title>
            <Text type="secondary" style={{ textAlign: 'center' }}>
              在下方输入框输入问题，开始提问
            </Text>
          </div>
        ) : (
          <div style={{ flex: 1 }}>
            {messages.map((msg, i) => (
              <div key={i} style={{ marginBottom: 20 }}>
                <div style={{
                  display: 'flex',
                  gap: 12,
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}>
                  {msg.role === 'assistant' && (
                    <Avatar icon={<RobotOutlined />} style={{ background: '#6366f1' }} />
                  )}
                  <div style={{
                    maxWidth: '70%',
                    padding: '12px 16px',
                    borderRadius: 12,
                    background: msg.role === 'user' ? '#6366f1' : '#fff',
                    color: msg.role === 'user' ? '#fff' : '#1a202c',
                    border: msg.role === 'assistant' ? '1px solid #e2e8f0' : 'none',
                    whiteSpace: msg.role === 'user' ? 'pre-wrap' : 'normal',
                    lineHeight: 1.6,
                  }}>
                    {msg.role === 'assistant' ? (
                      <div className="chat-markdown">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content || (loading && i === messages.length - 1 ? '...' : '')}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      msg.content || (loading && i === messages.length - 1 ? '...' : '')
                    )}
                  </div>
                  {msg.role === 'user' && (
                    <Avatar icon={<UserOutlined />} style={{ background: '#6366f1' }} />
                  )}
                </div>

                {/* 引用来源 */}
                {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                  <div style={{ marginLeft: 52, marginTop: 8 }}>
                    <Collapse
                      ghost
                      size="small"
                      items={[{
                        key: 'sources',
                        label: (
                          <Space size={4}>
                            <LinkOutlined />
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              共 {msg.sources.length} 个引用来源
                            </Text>
                          </Space>
                        ),
                        children: (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {msg.sources.map((src, si) => (
                              <div key={si} style={{
                                padding: '8px 12px',
                                background: '#f8fafc',
                                borderRadius: 8,
                                border: '1px solid #e2e8f0',
                                fontSize: 13,
                              }}>
                                <Space size={8}>
                                  <Tag color="purple" style={{ margin: 0 }}>
                                    {src.collection || '知识库'}
                                  </Tag>
                                  <Text type="secondary">
                                    相关性: {(src.score * 100).toFixed(1)}%
                                  </Text>
                                </Space>
                                {src.name && (
                                  <div style={{ marginTop: 4, color: '#475569', fontWeight: 500 }}>
                                    {src.name}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        ),
                      }]}
                    />
                  </div>
                )}
              </div>
            ))}

            {/* 加载指示器 */}
            {loading && (
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginLeft: 0 }}>
                <Avatar icon={<RobotOutlined />} style={{ background: '#6366f1' }} />
                <Spin size="small" />
                <Text type="secondary">AI 思考中...</Text>
              </div>
            )}

            <div ref={msgEndRef} />
          </div>
        )}
      </Card>

      {/* Error banner */}
      {error && (
        <div style={{
          padding: '8px 16px',
          background: '#fef2f2',
          border: '1px solid #fecaca',
          borderRadius: 8,
          marginBottom: 12,
          color: '#dc2626',
          fontSize: 13,
        }}>
          ❌ {error}
        </div>
      )}

      {/* Input */}
      <div style={{ display: 'flex', gap: 12 }}>
        <Input
          size="large"
          placeholder="输入你的问题..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={handleSend}
          disabled={loading}
        />
        <Button
          type="primary"
          size="large"
          icon={<SendOutlined />}
          onClick={handleSend}
          loading={loading}
          disabled={!input.trim()}
          style={{ background: '#6366f1', borderColor: '#6366f1' }}
        >
          发送
        </Button>
      </div>
      </div>
    </div>
  )
}
