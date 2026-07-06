import { useState, useRef, useEffect } from 'react'
import { Typography, Input, Button, Card, Tag, Space, Avatar, Collapse, Spin } from 'antd'
import { SendOutlined, RobotOutlined, UserOutlined, FileTextOutlined, LinkOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

const SUGGESTIONS = [
  { tag: '架构概览', title: '无矩 2.0 的整体架构是什么样的？' },
  { tag: '配置说明', title: 'DAG 调度配置包含哪些参数？' },
  { tag: '节点配置', title: 'Kafka 渠道节点如何配置？' },
  { tag: '算子使用', title: 'Join 算子多表关联怎么配置？' },
]

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

  // 自动滚动到底部
  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

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
    }
  }

  // 点击建议问题
  const handleSuggestionClick = (title: string) => {
    setInput(title)
  }

  return (
    <div style={{ padding: 32, height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Tag icon={<RobotOutlined />} color="purple">无矩 2.0 知识库</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>RAG 检索增强生成 · FastAPI 微服务</Text>
        </div>
        <Title level={3} style={{ margin: 0 }}>知识库问答</Title>
        <Text type="secondary">基于无矩 2.0 后端代码知识库，回答架构、API、节点配置等问题</Text>
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
            <Text type="secondary" style={{ textAlign: 'center', maxWidth: 400 }}>
              基于无矩 2.0 后端代码构建的 RAG 知识库，可以回答平台架构、API 接口、业务流程、节点配置等相关问题。
            </Text>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 8 }}>
              {SUGGESTIONS.map((s, i) => (
                <Card
                  key={i}
                  hoverable
                  size="small"
                  onClick={() => handleSuggestionClick(s.title)}
                  style={{ cursor: 'pointer', textAlign: 'center' }}
                >
                  <Tag color="purple" style={{ marginBottom: 4 }}>{s.tag}</Tag>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{s.title}</div>
                </Card>
              ))}
            </div>
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
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.6,
                  }}>
                    {msg.content || (loading && i === messages.length - 1 ? '...' : '')}
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
  )
}
