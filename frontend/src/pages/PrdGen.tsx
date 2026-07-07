/**
 * PrdGen — PRD 智能生成工作台页面
 *
 * 流程：
 *   简单模式：输入 → 大纲 → 逐章节流式生成 → 编辑/导出
 *   中等模式：输入 → 3-5 轮问答 → 大纲 → 逐章节流式生成 → 编辑/导出
 *
 * 状态覆盖：loading、empty、error、streaming
 */
import React, { useState, useRef, useCallback } from 'react'
import {
  Typography, Input, Button, Card, Steps, Tag, Space, Alert, message,
  Upload, Table, Modal, Spin, Empty, Radio, Checkbox, Divider,
} from 'antd'
import {
  ThunderboltOutlined, FileTextOutlined, LinkOutlined,
  UploadOutlined, SendOutlined, ReloadOutlined,
  DownloadOutlined, EditOutlined, EyeOutlined,
  CheckCircleOutlined, LoadingOutlined, RightCircleOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ReactDiffViewer from 'react-diff-viewer-continued'
import {
  createSession, simpleGenerate, startChat, chatRound,
  generateOutline, generateSection, regenerateSection,
  updateSection, getVersions, getVersionContent,
  exportPRD, uploadFile, parseMinutes, rechatTopic,
} from '../api/prdGen'
import type {
  SectionEvent, SectionCompleteEvent, ChatRoundResponse,
  VersionInfo, VersionContent,
} from '../api/prdGen'

const { Title, Text } = Typography
const { TextArea } = Input

const SECTION_LABELS: Record<string, string> = {
  overview: '功能概述',
  roles: '用户角色',
  features: '功能清单',
  stories: '用户故事',
  boundaries: '边界条件与异常处理',
  nonfunctional: '非功能需求',
}

// 7 个话题（与后端 _QUESTION_TOPICS 完全对齐）
const TOPIC_STEPS = [
  { title: '问题与方案', icon: '💡' },
  { title: '用户与场景', icon: '👥' },
  { title: '核心功能', icon: '🎯' },
  { title: '操作流程', icon: '➡️' },
  { title: '边界与约束', icon: '🚧' },
  { title: '非功能需求', icon: '⚡' },
  { title: '依赖与范围', icon: '🔗' },
]

type StepStatus = 'wait' | 'process' | 'finish' | 'error'

interface ChatMsg {
  role: 'user' | 'system'
  content: string
  round: number
  topic?: string  // 可选，标识该消息所属话题
}

interface VersionDisplay {
  id: string
  versionNum: number
  section: string
  createdAt: string
}

export default function PrdGen() {
  // ── 会话状态 ──
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [mode, setMode] = useState<'simple' | 'medium'>('simple')
  const [sessionStatus, setSessionStatus] = useState<'init' | 'chatting' | 'writing' | 'done'>('init')

  // ── 输入状态 ──
  const [userInput, setUserInput] = useState('')
  const [minutesUrl, setMinutesUrl] = useState('')
  const [minutesResult, setMinutesResult] = useState<any>(null)
  const [parsingMinutes, setParsingMinutes] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState<any[]>([])
  const [uploading, setUploading] = useState(false)

  // 输入源勾选（可多选）
  const [inputSources, setInputSources] = useState<string[]>(['text'])

  // ── 中等模式状态 ──
  const [chatHistory, setChatHistory] = useState<ChatMsg[]>([])
  const [currentQuestion, setCurrentQuestion] = useState('')
  const [chatAnswer, setChatAnswer] = useState('')
  const [chatting, setChatting] = useState(false)
  const [readyForOutline, setReadyForOutline] = useState(false)
  const [readyReason, setReadyReason] = useState('')
  const [currentTopic, setCurrentTopic] = useState('')
  const [completedTopics, setCompletedTopics] = useState<string[]>([])
  const [topicHistoryStart, setTopicHistoryStart] = useState<number>(0) // 当前话题在 chatHistory 中的起始索引

  // ── 生成状态 ──
  const [generating, setGenerating] = useState(false)
  const [outline, setOutline] = useState<string[]>([])
  const [sectionContents, setSectionContents] = useState<Record<string, string>>({})
  const [sectionStatuses, setSectionStatuses] = useState<Record<string, StepStatus>>({})
  const [currentSection, setCurrentSection] = useState<string | null>(null)
  const [streamingContent, setStreamingContent] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const genIdRef = useRef(0)

  // ── 编辑器状态 ──
  const [editingSection, setEditingSection] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')
  const [showDiff, setShowDiff] = useState(false)
  const [oldContent, setOldContent] = useState('')
  const [newContent, setNewContent] = useState('')

  // ── 版本管理状态 ──
  const [versions, setVersions] = useState<VersionDisplay[]>([])
  const [versionsModalOpen, setVersionsModalOpen] = useState(false)
  const [versionSection, setVersionSection] = useState<string | null>(null)

  // ── 步骤条 ──
  const stepsCurrent = sessionStatus === 'init' ? 0
    : sessionStatus === 'chatting' ? 1
    : outline.length === 0 ? 2
    : Object.keys(sectionContents).length === 0 ? 2
    : 3

  // 步骤条标题随模式变化
  const stepItems = [
    { title: '输入需求', status: (sessionId ? 'finish' : 'process') as 'finish' | 'process' },
    { title: mode === 'medium' ? '补充信息' : '生成大纲',
      status: sessionStatus === 'init' ? 'wait' as const
        : sessionStatus === 'chatting' ? 'process' as const
        : sessionStatus === 'writing' || sessionStatus === 'done' ? 'finish' as const
        : 'wait' as const,
    },
    { title: '撰写章节',
      status: outline.length > 0 ? (Object.keys(sectionContents).length > 0 ? 'finish' as const : 'process' as const) : 'wait' as const,
    },
    { title: '完成', status: sessionStatus === 'done' ? 'finish' as const : 'wait' as const },
  ]

  // ── 创建会话 ──
  const handleStart = async () => {
    if (!userInput.trim() && !minutesResult) {
      message.warning('请输入需求描述或解析妙记链接')
      return
    }

    try {
      const session = await createSession(mode, userInput)
      setSessionId(session.sessionId)
      setSessionStatus(session.status)
      message.success('会话已创建')

      if (mode === 'simple') {
        // 直接开始生成
        await handleSimpleGenerate(session.sessionId)
      } else {
        // 进入问答阶段
        setSessionStatus('chatting')
        // 调用 startChat 获取第一个引导问题
        await handleStartChat(session.sessionId)
      }
    } catch (e: any) {
      message.error(e?.message || '创建会话失败')
    }
  }

  // ── 简单模式生成 ──
  const handleSimpleGenerate = async (sid: string) => {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const genId = ++genIdRef.current

    setGenerating(true)
    setOutline([])
    setSectionContents({})
    setSectionStatuses({})
    setStreamingContent('')

    try {
      await simpleGenerate(sid, {
        onProgress: (data: SectionEvent) => {
          if (genIdRef.current !== genId) return
          if (data.chunk) {
            setStreamingContent(prev => prev + (data.chunk || ''))
          }
          if (data.section && data.section !== 'outline') {
            setSectionStatuses(prev => ({ ...prev, [data.section!]: 'process' }))
          }
        },
        onSectionComplete: (data: SectionCompleteEvent) => {
          if (genIdRef.current !== genId) return
          if (data.outline) {
            setOutline(data.outline)
            setStreamingContent('')
          } else if (data.section && data.content) {
            setSectionStatuses(prev => ({ ...prev, [data.section!]: 'finish' }))
            setSectionContents(prev => ({ ...prev, [data.section!]: data.content! }))
            setStreamingContent('')
            setCurrentSection(data.section)
          }
        },
        onComplete: () => {
          if (genIdRef.current !== genId) return
          setGenerating(false)
          setSessionStatus('done')
          message.success('PRD 生成完成')
        },
        onError: (data) => {
          if (genIdRef.current !== genId) return
          setGenerating(false)
          message.error(data?.message || '生成失败')
        },
      }, controller.signal)
    } catch (e: any) {
      if (e?.name === 'AbortError') return
      setGenerating(false)
      message.error(e?.message || '生成异常')
    }
  }

  // ── 中等模式对话 ──
  const handleStartChat = async (sid: string) => {
    setChatting(true)
    setCompletedTopics([])
    setTopicHistoryStart(0)
    try {
      const result: ChatRoundResponse = await startChat(sid)
      if (result.question) {
        setCurrentQuestion(result.question)
        setCurrentTopic(result.topic || '')
        // 标记当前话题开始
        setTopicHistoryStart(chatHistory.length)
        setChatHistory(prev => [...prev, { role: 'system', content: result.question!, round: result.round, topic: result.topic }])
      }
    } catch (e: any) {
      message.error(e?.message || '启动对话失败')
    } finally {
      setChatting(false)
    }
  }

  const handleChatRound = async (sid: string, answer: string) => {
    setChatting(true)
    try {
      const result: ChatRoundResponse = await chatRound(sid, answer)
      const prevTopic = currentTopic
      const newChatMsg: ChatMsg = { role: 'user', content: answer, round: result.round, topic: prevTopic }
      setChatHistory(prev => [...prev, newChatMsg])
      setChatAnswer('')

      // 检测话题切换
      if (result.topic && result.topic !== prevTopic) {
        // 话题变了！标记已完成话题
        if (prevTopic) {
          setCompletedTopics(prev => [...prev, prevTopic])
        }
        setCurrentTopic(result.topic)
        setTopicHistoryStart(chatHistory.length + 1) // +1 因为刚加了 user 消息
      }

      if (result.status === 'ready_for_outline') {
        // 标记最后一个话题也完成
        if (currentTopic) {
          setCompletedTopics(prev => [...prev, currentTopic])
        }
        // 进入用户确认环节
        setReadyForOutline(true)
        setReadyReason(result.reason || '信息已收集完成')
      } else if (result.question) {
        setCurrentQuestion(result.question)
        const systemMsg: ChatMsg = { role: 'system', content: result.question, round: result.round, topic: result.topic || currentTopic }
        setChatHistory(prev => [...prev, systemMsg])
      }
    } catch (e: any) {
      message.error(e?.message || '对话失败')
    } finally {
      setChatting(false)
    }
  }

  /** 用户确认开始生成大纲 */
  const handleConfirmOutline = async () => {
    if (!sessionId) return
    setReadyForOutline(false)
    setSessionStatus('writing')
    message.success('开始生成大纲')
    await handleGenerateOutline(sessionId)
  }

  /** 重新讨论某个已完成话题 */
  const handleRechatTopic = async (topic: string) => {
    if (!sessionId) return
    setReadyForOutline(false)
    setChatting(true)
    try {
      const result = await rechatTopic(sessionId, topic)
      if (result.question) {
        // 将该话题从 completedTopics 移除，设置为当前话题
        setCompletedTopics(prev => prev.filter(t => t !== topic))
        setCurrentTopic(topic)
        setCurrentQuestion(result.question)
        // 恢复 chatting 状态
        const systemMsg: ChatMsg = { role: 'system', content: result.question, round: result.round, topic: topic }
        setChatHistory(prev => [...prev, systemMsg])
      }
    } catch (e: any) {
      message.error(e?.message || '重新讨论失败')
    } finally {
      setChatting(false)
    }
  }

  const handleSendChat = () => {
    if (!chatAnswer.trim() || !sessionId) return
    handleChatRound(sessionId, chatAnswer)
  }

  // ── 生成大纲 ──
  const handleGenerateOutline = async (sid: string) => {
    if (!sid) return
    try {
      const result = await generateOutline(sid)
      setOutline(result.outline)
      setSectionStatuses({})
      message.success('大纲生成完成')
    } catch (e: any) {
      message.error(e?.message || '大纲生成失败')
    }
  }

  // ── 生成章节 ──
  const handleGenerateSection = async (section: string) => {
    if (!sessionId) return
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const genId = ++genIdRef.current

    setCurrentSection(section)
    setShowDiff(false)

    // 如果已有内容，保存为 oldContent 用于 Diff
    const existing = sectionContents[section]
    if (existing) {
      setOldContent(existing)
      setShowDiff(true)
    }

    setGenerating(true)
    setStreamingContent('')

    try {
      await generateSection(sessionId, section, {
        onProgress: (data: SectionEvent) => {
          if (genIdRef.current !== genId) return
          if (data.chunk) {
            setStreamingContent(prev => prev + (data.chunk || ''))
          }
          setSectionStatuses(prev => ({ ...prev, [section]: 'process' }))
        },
        onSectionComplete: (data: SectionCompleteEvent) => {
          if (genIdRef.current !== genId) return
          if (data.content) {
            setSectionContents(prev => ({ ...prev, [section]: data.content! }))
            setNewContent(data.content)
            setStreamingContent('')
            setSectionStatuses(prev => ({ ...prev, [section]: 'finish' }))
          }
        },
        onError: (data) => {
          if (genIdRef.current !== genId) return
          setSectionStatuses(prev => ({ ...prev, [section]: 'error' }))
          setGenerating(false)
          message.error(data?.message || `章节「${SECTION_LABELS[section] || section}」生成失败`)
        },
      }, controller.signal)
    } catch (e: any) {
      if (e?.name === 'AbortError') return
      setSectionStatuses(prev => ({ ...prev, [section]: 'error' }))
      message.error(e?.message || '生成异常')
    } finally {
      setGenerating(false)
    }
  }

  // ── 重新生成章节 ──
  const handleRegenerateSection = async (section: string) => {
    if (!sessionId) return
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const genId = ++genIdRef.current

    const existing = sectionContents[section]
    if (existing) {
      setOldContent(existing)
      setShowDiff(true)
    }

    setGenerating(true)
    setStreamingContent('')

    try {
      await regenerateSection(sessionId, section, {
        onProgress: (data: SectionEvent) => {
          if (genIdRef.current !== genId) return
          if (data.chunk) {
            setStreamingContent(prev => prev + (data.chunk || ''))
          }
          setSectionStatuses(prev => ({ ...prev, [section]: 'process' }))
        },
        onSectionComplete: (data: SectionCompleteEvent) => {
          if (genIdRef.current !== genId) return
          if (data.content) {
            setSectionContents(prev => ({ ...prev, [section]: data.content! }))
            setNewContent(data.content)
            setStreamingContent('')
            setSectionStatuses(prev => ({ ...prev, [section]: 'finish' }))
          }
        },
        onError: (data) => {
          if (genIdRef.current !== genId) return
          setSectionStatuses(prev => ({ ...prev, [section]: 'error' }))
          setGenerating(false)
          message.error(data?.message || '重新生成失败')
        },
      }, controller.signal)
    } catch (e: any) {
      if (e?.name === 'AbortError') return
      message.error(e?.message || '重新生成异常')
    } finally {
      setGenerating(false)
    }
  }

  // ── 编辑章节 ──
  const handleEditSection = (section: string) => {
    setCurrentSection(section)
    setEditingSection(section)
    setEditContent(sectionContents[section] || '')
  }

  const handleSaveEdit = async () => {
    if (!sessionId || !editingSection) return
    try {
      await updateSection(sessionId, editingSection, editContent)
      setSectionContents(prev => ({ ...prev, [editingSection!]: editContent }))
      setEditingSection(null)
      message.success('章节内容已保存')
    } catch (e: any) {
      message.error(e?.message || '保存失败')
    }
  }

  // ── 版本管理 ──
  const handleShowVersions = async (section: string) => {
    if (!sessionId) return
    setVersionSection(section)
    try {
      const result = await getVersions(sessionId, section)
      setVersions(result.versions.map(v => ({
        id: v.id,
        versionNum: v.version_num,
        section: v.section,
        createdAt: v.created_at,
      })))
      setVersionsModalOpen(true)
    } catch (e: any) {
      message.error('获取版本列表失败')
    }
  }

  const handleRestoreVersion = async (vid: string) => {
    if (!sessionId) return
    try {
      const result: VersionContent = await getVersionContent(sessionId, vid)
      const sec = result.section
      setSectionContents(prev => ({ ...prev, [sec]: result.content }))
      setVersionsModalOpen(false)
      message.success(`已恢复到 v${result.version_num}`)
    } catch (e: any) {
      message.error('恢复版本失败')
    }
  }

  // ── 导出 ──
  const handleExport = () => {
    if (!sessionId) return
    exportPRD(sessionId)
  }

  // ── 妙记解析 ──
  const handleParseMinutes = async () => {
    if (!minutesUrl.trim()) {
      message.warning('请粘贴飞书妙记链接')
      return
    }
    // 自动创建会话（如果还没有）
    let sid = sessionId
    if (!sid) {
      try {
        const session = await createSession(mode, userInput)
        setSessionId(session.sessionId)
        sid = session.sessionId
      } catch (e: any) {
        message.error('创建会话失败')
        return
      }
    }
    setParsingMinutes(true)
    try {
      const result = await parseMinutes(sid, minutesUrl)
      if (result.status === 'success') {
        setMinutesResult(result)
        message.success(`妙记「${result.minuteTitle}」解析完成`)
      } else {
        message.error((result as any).message || '解析失败')
      }
    } catch (e: any) {
      message.error(e?.message || '解析失败')
    } finally {
      setParsingMinutes(false)
    }
  }

  // ── 文件上传 ──
  const handleFileUpload = useCallback(async (file: File) => {
    // 自动创建会话
    let sid = sessionId
    if (!sid) {
      try {
        const session = await createSession(mode, userInput)
        setSessionId(session.sessionId)
        sid = session.sessionId
      } catch (e: any) {
        message.warning('创建会话失败，请先点击"开始生成"')
        return false
      }
    }
    setUploading(true)
    try {
      const result = await uploadFile(sid, file, 'temporary')
      setUploadedFiles(prev => [...prev, result])
      message.success(`文件「${result.filename}」上传成功`)
    } catch (e: any) {
      message.error(e?.message || '上传失败')
    } finally {
      setUploading(false)
    }
    return false
  }, [sessionId, mode, userInput])

  // ── 重置 ──
  const handleReset = () => {
    if (abortRef.current) abortRef.current.abort()
    setSessionId(null)
    setSessionStatus('init')
    setOutline([])
    setSectionContents({})
    setSectionStatuses({})
    setStreamingContent('')
    setChatHistory([])
    setCurrentQuestion('')
    setReadyForOutline(false)
    setReadyReason('')
    setReadyForOutline(false)
    setReadyReason('')
    setCurrentTopic('')
    setCompletedTopics([])
    setTopicHistoryStart(0)
    setMinutesResult(null)
    setUploadedFiles([])
    setShowDiff(false)
    setEditingSection(null)
    setCurrentSection(null)
    setVersions([])
  }

  // ── 当前选中的章节内容 ──
  const selectedContent = currentSection ? sectionContents[currentSection] || streamingContent : ''

  const renderInputSection = () => (
    <Card title="输入需求" size="small" style={{ marginBottom: 16 }}>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {/* 模式选择 */}
        <div>
          <Text strong style={{ marginRight: 12 }}>生成模式：</Text>
          <Radio.Group value={mode} onChange={e => {
            if (sessionId) handleReset()
            setMode(e.target.value)
          }}>
            <Radio value="simple">简单模式</Radio>
            <Radio value="medium">中等模式（问答引导）</Radio>
          </Radio.Group>
        </div>

        {/* 输入源多选 */}
        <div>
          <Text strong style={{ marginRight: 12 }}>输入来源：</Text>
          <Checkbox.Group
            value={inputSources}
            onChange={vals => setInputSources(vals as string[])}
          >
            <Checkbox value="text">文字描述</Checkbox>
            <Checkbox value="minutes">飞书妙记</Checkbox>
            <Checkbox value="file">上传文件</Checkbox>
          </Checkbox.Group>
        </div>

        {/* 文字描述 */}
        {inputSources.includes('text') && (
          <div>
            <Text strong style={{ marginBottom: 6, display: 'block' }}>需求描述</Text>
            <TextArea
              rows={4}
              placeholder="描述你需要的功能，如：开发一个模型版本管理功能，支持模型注册、版本对比和灰度发布"
              value={userInput}
              onChange={e => setUserInput(e.target.value)}
            />
          </div>
        )}

        {/* 飞书妙记 */}
        {inputSources.includes('minutes') && (
          <div>
            <Text strong style={{ marginBottom: 6, display: 'block' }}>飞书妙记链接</Text>
            <Space.Compact style={{ width: '100%', marginBottom: 8 }}>
              <Input
                placeholder="粘贴飞书妙记链接..."
                value={minutesUrl}
                onChange={e => setMinutesUrl(e.target.value)}
                prefix={<LinkOutlined />}
                style={{ width: '65%' }}
              />
              <Button
                onClick={handleParseMinutes}
                loading={parsingMinutes}
                disabled={!sessionId}
              >
                解析妙记
              </Button>
            </Space.Compact>
            {minutesResult && (
              <Alert
                type="success"
                showIcon
                message={`妙记「${minutesResult.minuteTitle}」已解析`}
                description={`提取到 ${minutesResult.extractedPoints?.featurePoints?.length || 0} 个需求点`}
              />
            )}
          </div>
        )}

        {/* 上传文件 */}
        {inputSources.includes('file') && (
          <div>
            <Text strong style={{ marginBottom: 6, display: 'block' }}>上传文件</Text>
            <Upload.Dragger
              beforeUpload={handleFileUpload}
              showUploadList={false}
              accept=".md,.txt,.docx"
              disabled={!sessionId}
            >
              <p className="ant-upload-drag-icon"><UploadOutlined /></p>
              <p>点击或拖拽文件到此处上传</p>
              <p style={{ fontSize: 12, color: '#999' }}>支持 .md / .txt / .docx，≤10MB</p>
            </Upload.Dragger>
            {uploading && <Spin tip="上传中..." />}
            {uploadedFiles.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <Text strong>已上传文件：</Text>
                {uploadedFiles.map((f, i) => (
                  <Tag key={i} style={{ marginTop: 4 }}>{f.filename}</Tag>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 开始按钮 */}
        <Space>
          <Button
            type="primary"
            size="large"
            icon={<ThunderboltOutlined />}
            onClick={handleStart}
            loading={generating}
            disabled={generating || !!sessionId}
          >
            {mode === 'simple' ? '开始生成' : '开始对话'}
          </Button>
          {sessionId && (
            <Button icon={<ReloadOutlined />} onClick={handleReset}>重新开始</Button>
          )}
        </Space>
      </Space>
    </Card>
  )

  const renderChatSection = () => {
    if (mode !== 'medium' || sessionStatus !== 'chatting') return null

    // 计算当前话题在 TOPIC_STEPS 中的索引
    const currentTopicIdx = currentTopic
      ? TOPIC_STEPS.findIndex(t => currentTopic.includes(t.title.slice(0, 4)) || t.title === currentTopic)
      : -1

    // 构建 Steps items
    const topicStepItems = TOPIC_STEPS.map((t, idx) => {
      const isCompleted = completedTopics.includes(t.title)
      const isCurrent = idx === currentTopicIdx
      return {
        title: t.title,
        status: (isCompleted ? 'finish' : isCurrent ? 'process' : 'wait') as 'finish' | 'process' | 'wait',
        icon: isCompleted ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
              : isCurrent ? <RightCircleOutlined style={{ color: '#6366f1' }} />
              : undefined,
      }
    })

    // 检测话题切换，给对话历史插入分隔线
    const renderMessages = () => {
      let lastTopic = ''
      return chatHistory.map((msg, i) => {
        const showDivider = msg.topic && msg.topic !== lastTopic && lastTopic !== ''
        const isTopicStart = msg.topic && msg.topic !== lastTopic
        if (msg.topic) lastTopic = msg.topic

        // 话题切换分隔线
        const divider = showDivider ? (
          <div key={`divider-${i}`} style={{ margin: '12px 0', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Divider style={{ flex: 1, margin: 0 }} />
            <Tag color="purple" style={{ borderRadius: 8, fontSize: 11, flexShrink: 0, margin: 0 }}>
              🎯 进入话题：{msg.topic}
            </Tag>
            <Divider style={{ flex: 1, margin: 0 }} />
          </div>
        ) : null

        const isCurrentTopicMsg = msg.topic === currentTopic

        return (
          <React.Fragment key={i}>
            {divider}
            <div style={{
              marginBottom: 8,
              padding: '8px 12px',
              borderRadius: 8,
              background: msg.role === 'user' ? '#e8f4fd' : (isCurrentTopicMsg ? '#f0f5ff' : '#f5f5f5'),
              textAlign: msg.role === 'user' ? 'right' : 'left',
              borderLeft: msg.role === 'system' && isTopicStart ? '3px solid #6366f1' : undefined,
            }}>
              <Text>{msg.content}</Text>
            </div>
          </React.Fragment>
        )
      })
    }

    return (
      <Card title="需求引导对话" size="small" style={{ marginBottom: 16 }}>
        {/* 话题流水线 Steps */}
        {currentTopic && (
          <div style={{ marginBottom: 16, padding: '12px 16px', background: '#f8f9ff', borderRadius: 8, border: '1px solid #e8eaff' }}>
            <Steps
              current={currentTopicIdx >= 0 ? currentTopicIdx : 0}
              size="small"
              items={topicStepItems}
              style={{
                ['--ant-steps-nav-arrow-color' as string]: '#6366f1',
                ['--ant-steps-icon-active-color' as string]: '#6366f1',
                ['--ant-steps-heading-color' as string]: '#6366f1',
                ['--ant-steps-finish-icon-color' as string]: '#52c41a',
                ['--ant-steps-finish-heading-color' as string]: '#52c41a',
              }}
            />
          </div>
        )}

        {readyForOutline ? (
          <div>
            <Alert
              type="success"
              showIcon
              message="🎉 所有话题已收集完成"
              description={readyReason || '对话已覆盖全部 7 个话题，请确认信息是否完整'}
              style={{ marginBottom: 16 }}
            />

            {/* 话题回顾列表 */}
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 14, marginBottom: 8, display: 'block' }}>
                📋 话题回顾 — 点击可重新讨论
              </Text>
              {TOPIC_STEPS.map((t, idx) => {
                const topicName = t.title
                // 找到该话题在 chatHistory 中的消息
                const topicMsgs = chatHistory.filter(m => m.topic === topicName || (idx === 0 && !m.topic))
                const userMsgs = topicMsgs.filter(m => m.role === 'user')
                return (
                  <div key={topicName} style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    marginBottom: 6,
                    background: '#f9fafb',
                    borderRadius: 8,
                    border: '1px solid #e5e7eb',
                  }}>
                    <Space>
                      <span style={{ fontSize: 12, color: '#52c41a' }}>✅</span>
                      <Text strong style={{ fontSize: 13 }}>{topicName}</Text>
                      <Text style={{ fontSize: 12, color: '#6b7280' }}>
                        {userMsgs.length > 0 ? `${userMsgs.length} 条回答` : '已跳过'}
                      </Text>
                    </Space>
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => handleRechatTopic(topicName)}
                    >
                      修改
                    </Button>
                  </div>
                )
              })}
            </div>

            <Space>
              <Button type="primary" size="large" onClick={handleConfirmOutline}>
                确认，开始生成大纲
              </Button>
              <Button onClick={() => {
                setReadyForOutline(false)
                setCurrentQuestion('还有哪些信息需要补充？请告诉我。')
                setChatHistory(prev => [...prev, { role: 'system', content: '还有哪些信息需要补充？请告诉我。', round: chatHistory.length + 1, topic: currentTopic }])
              }}>
                还需要补充
              </Button>
            </Space>
          </div>
        ) : (
          <>
            {currentTopic && (
              <div style={{ marginBottom: 12, padding: '6px 14px', background: '#eef2ff', borderRadius: 6, borderLeft: '3px solid #6366f1' }}>
                <Text strong style={{ color: '#6366f1', fontSize: 13 }}>
                  💬 当前话题：{currentTopic}
                </Text>
                <Text style={{ marginLeft: 8, fontSize: 12, color: '#6b7280' }}>
                  （{completedTopics.length + 1}/{TOPIC_STEPS.length}）
                </Text>
              </div>
            )}
            <div style={{ maxHeight: 300, overflow: 'auto', marginBottom: 12 }}>
              {renderMessages()}
            </div>
            <Space.Compact style={{ width: '100%' }}>
              <Input
                placeholder="回答系统的问题..."
                value={chatAnswer}
                onChange={e => setChatAnswer(e.target.value)}
                onPressEnter={handleSendChat}
                disabled={chatting}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSendChat}
                loading={chatting}
              >
                发送
              </Button>
            </Space.Compact>
          </>
        )}
      </Card>
    )
  }

  const renderOutlineSection = () => {
    if (outline.length === 0 && sessionStatus === 'writing' && mode === 'simple') {
      return (
        <Card title="生成大纲" size="small" style={{ marginBottom: 16 }}>
          <Spin tip="正在生成大纲..." />
        </Card>
      )
    }
    if (outline.length === 0) return null

    return (
      <Card
        title="章节列表"
        size="small"
        style={{ marginBottom: 16 }}
        extra={sessionStatus === 'done' && (
          <Space>
            <Button icon={<DownloadOutlined />} onClick={handleExport}>导出 Markdown</Button>
          </Space>
        )}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          {outline.map((section, idx) => {
            const label = SECTION_LABELS[section] || section
            const status = sectionStatuses[section]
            const hasContent = !!sectionContents[section]
            const isCurrent = currentSection === section && generating

            return (
              <div key={section} style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                background: status === 'finish' ? '#f6ffed' : isCurrent ? '#fffbe6' : '#fafafa',
                borderRadius: 6,
                border: isCurrent ? '1px solid #faad14' : '1px solid #f0f0f0',
              }}>
                <Space>
                  {status === 'finish' ? (
                    <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  ) : isCurrent ? (
                    <LoadingOutlined style={{ color: '#faad14' }} />
                  ) : (
                    <span style={{ width: 14, display: 'inline-block' }}>{idx + 1}</span>
                  )}
                  <Text strong={isCurrent}>{label}</Text>
                  {hasContent && <Tag style={{ fontSize: 11 }}>已完成</Tag>}
                </Space>

                <Space size="small">
                  <Button
                    size="small"
                    type={hasContent ? 'default' : 'primary'}
                    icon={<ThunderboltOutlined />}
                    onClick={() => handleGenerateSection(section)}
                    loading={isCurrent}
                    disabled={generating && !isCurrent}
                  >
                    {hasContent ? '重新生成' : '生成'}
                  </Button>
                  {hasContent && (
                    <>
                      <Button size="small" icon={<EditOutlined />} onClick={() => handleEditSection(section)}>
                        编辑
                      </Button>
                      <Button size="small" icon={<EyeOutlined />} onClick={() => setCurrentSection(section)}>
                        查看
                      </Button>
                      <Button size="small" onClick={() => handleShowVersions(section)}>
                        版本
                      </Button>
                    </>
                  )}
                </Space>
              </div>
            )
          })}
        </Space>
      </Card>
    )
  }

  const renderEditorSection = () => {
    if (!currentSection && !editingSection && !selectedContent) return null
    const section = currentSection || editingSection
    if (!section) return null

    const content = editingSection === section ? editContent : selectedContent
    const label = SECTION_LABELS[section] || section

    return (
      <Card
        title={`${label}${showDiff ? ' — 对比视图' : ''}`}
        size="small"
        style={{ marginBottom: 16 }}
        extra={
          editingSection === section ? (
            <Space>
              <Button onClick={() => setEditingSection(null)}>取消</Button>
              <Button type="primary" onClick={handleSaveEdit}>保存</Button>
            </Space>
          ) : (
            <Space>
              <Button size="small" icon={<EditOutlined />} onClick={() => handleEditSection(section)}>
                编辑
              </Button>
              {sectionContents[section] && (
                <Button size="small" onClick={() => handleRegenerateSection(section)} loading={generating}>
                  重新生成
                </Button>
              )}
            </Space>
          )
        }
      >
        {showDiff && oldContent && newContent && (
          <div style={{ marginBottom: 16 }}>
            <ReactDiffViewer
              oldValue={oldContent}
              newValue={newContent}
              splitView={false}
              leftTitle="修改前"
              rightTitle="修改后"
            />
          </div>
        )}

        {editingSection === section ? (
          <TextArea
            rows={20}
            value={editContent}
            onChange={e => setEditContent(e.target.value)}
            style={{ fontFamily: 'monospace', fontSize: 13 }}
          />
        ) : content ? (
          <div style={{ maxHeight: 600, overflow: 'auto', padding: '12px 16px', background: '#fff', border: '1px solid #f0f0f0', borderRadius: 8, lineHeight: 1.8 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          </div>
        ) : generating ? (
          <Spin tip="正在生成..." />
        ) : (
          <Empty description="请点击章节按钮生成内容" />
        )}
      </Card>
    )
  }

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: 24 }}>
      <Title level={3}>
        <FileTextOutlined /> PRD 智能生成工作台
      </Title>

      {/* 步骤条 */}
      <Steps current={stepsCurrent} items={stepItems} style={{ marginBottom: 24 }} />

      {/* 输入区 */}
      {renderInputSection()}

      {/* 中等模式对话区 */}
      {renderChatSection()}

      {/* 大纲 + 章节列表 */}
      {renderOutlineSection()}

      {/* 编辑器 + 预览区 */}
      {renderEditorSection()}

      {/* 空状态 */}
      {!sessionId && !generating && (
        <Card>
          <Empty description="输入需求描述并点击按钮开始生成 PRD" />
        </Card>
      )}

      {/* 版本管理 Modal */}
      <Modal
        title={`版本历史 — ${versionSection ? (SECTION_LABELS[versionSection] || versionSection) : ''}`}
        open={versionsModalOpen}
        onCancel={() => setVersionsModalOpen(false)}
        footer={null}
        width={600}
      >
        {versions.length === 0 ? (
          <Empty description="暂无版本历史" />
        ) : (
          <Table
            dataSource={versions}
            columns={[
              { title: '版本号', dataIndex: 'versionNum', key: 'versionNum', render: (v: number) => `v${v}` },
              { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt', render: (t: string) => t ? t.replace('T', ' ').slice(0, 19) : '-' },
              {
                title: '操作',
                key: 'action',
                render: (_: any, record: VersionDisplay) => {
                  const isCurrent = record.versionNum === Math.max(...versions.map(v => v.versionNum))
                  return (
                    <Button
                      size="small"
                      type={isCurrent ? 'default' : 'primary'}
                      disabled={isCurrent}
                      onClick={() => handleRestoreVersion(record.id)}
                    >
                      {isCurrent ? '当前版本' : '恢复到此版本'}
                    </Button>
                  )
                },
              },
            ]}
            rowKey="id"
            size="middle"
            pagination={false}
          />
        )}
      </Modal>
    </div>
  )
}
