/**
 * MeetingTodo — 会议 TODO 提取主页面
 *
 * 分屏布局：左侧逐字稿 | 右侧待办
 * 工作流：输入链接 → SSE 流式提取 → 逐字稿展示 → 待办展示 → 生成飞书文档
 */
import { useState, useRef } from 'react'
import {
  Input,
  Button,
  Steps,
  Typography,
  Empty,
  Card,
  Flex,
  message,
  Alert,
  Space,
} from 'antd'
import {
  LinkOutlined,
  RobotOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons'
import TranscriptPanel from '../components/TranscriptPanel'
import TodoPanel from '../components/TodoPanel'
import { streamRequest } from '../utils/sse'

const { Title, Text } = Typography

interface TodoItem {
  id: number
  description: string
  module: string
  ddl: string
  assignee: string
  assignee_open_id: string
  is_uncertain: boolean
  uncertainty_reason: string
}

interface ModuleGroup {
  name: string
  todos: TodoItem[]
}

interface MeetingInfo {
  title: string
  time: string
  minutes_link: string
  minute_token: string
  create_time_ms?: number
}

const STEPS = [
  { title: '获取妙记信息' },
  { title: '提取逐字稿' },
  { title: 'AI 分析待办' },
  { title: '完成' },
]

export default function MeetingTodo() {
  const [link, setLink] = useState('')
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // 分屏数据
  const [meetingInfo, setMeetingInfo] = useState<MeetingInfo | null>(null)
  const [transcript, setTranscript] = useState<string>('')
  const [moduleGroups, setModuleGroups] = useState<ModuleGroup[]>([])
  const [showTranscript, setShowTranscript] = useState(false)

  // SSE 流程状态
  const [analysisStage, setAnalysisStage] = useState<'idle' | 'fetching' | 'transcript_ready' | 'analyzing' | 'done'>('idle')
  const [transcriptLoading, setTranscriptLoading] = useState(false)
  const [todoLoading, setTodoLoading] = useState(false)
  // 每次提取递增，用于强制刷新 TodoPanel（清空编辑缓存）
  const [extractKey, setExtractKey] = useState(0)
  // 文档生成状态
  const [docUrl, setDocUrl] = useState<string | null>(null)

  const linkInputRef = useRef<HTMLInputElement>(null)

  const handleExtract = async () => {
    if (!link.trim()) return

    // 每次重新提取时清空旧数据，递增 key 让子组件刷新
    setExtractKey(k => k + 1)
    setDocUrl(null)
    setLoading(true)
    setError(null)
    setMeetingInfo(null)
    setTranscript('')
    setModuleGroups([])
    setShowTranscript(false)
    setAnalysisStage('fetching')
    setCurrentStep(0)
    setTranscriptLoading(true)
    setTodoLoading(false)

    try {
      await streamRequest('/meeting-todo/extract', { link }, {
        onProgress: (data: any) => {
          if (data.step === 1) setCurrentStep(0)
          else if (data.step === 2) setCurrentStep(1)
          else if (data.step === 3) {
            setCurrentStep(2)
            setAnalysisStage('analyzing')
            setTodoLoading(true)
            setTranscriptLoading(false)
          }
        },
        onSectionComplete: (data: any) => {
          if (data.step === 'transcript_ready') {
            setMeetingInfo(data.data.meeting_info)
            setTranscript(data.data.content)
            setShowTranscript(true)
            setAnalysisStage('transcript_ready')
            setCurrentStep(2)
            setTranscriptLoading(false)
          }
        },
        onComplete: (data: any) => {
          setModuleGroups(data.data.module_groups)
          setAnalysisStage('done')
          setCurrentStep(3)
          setTodoLoading(false)
          setLoading(false)
        },
        onError: (data: any) => {
          setError(data.message)
          setLoading(false)
          setTranscriptLoading(false)
          setTodoLoading(false)
          message.error(data.message)
        },
      })
    } catch (e: any) {
      const errMsg = e?.message || '提取过程异常'
      setError(errMsg)
      setLoading(false)
      setTranscriptLoading(false)
      setTodoLoading(false)
      message.error(errMsg)
    }
  }

  const handleGenerateDoc = async (
    info: MeetingInfo,
    groups: ModuleGroup[],
  ) => {
    setGenerating(true)
    setDocUrl(null)
    try {
      const { default: client } = await import('../api/client')
      const resp = await client.post('/meeting-todo/generate', {
        meeting_info: info,
        module_groups: groups,
      })
      const data = resp.data
      if (data.url) {
        setDocUrl(data.url)
        message.success('文档创建成功！')
      } else {
        message.error(data.error || '创建失败')
      }
    } catch (e: any) {
      message.error(e?.response?.data?.error || '生成文档失败')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div style={{ padding: 32, height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>📋 会议 TODO 提取</Title>
        <Text type="secondary">输入飞书妙记链接，AI 自动提取待办事项并生成结构化会议纪要文档</Text>
      </div>

      {/* Input area */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Flex gap={12} align="flex-start">
          <Input
            ref={linkInputRef as any}
            size="large"
            placeholder="请粘贴飞书妙记链接（如 https://poizon.feishu.cn/minutes/obcnxxx）"
            prefix={<LinkOutlined />}
            value={link}
            onChange={e => setLink(e.target.value)}
            disabled={loading}
            style={{ flex: 1 }}
            onPressEnter={handleExtract}
          />
          <Button
            type="primary"
            size="large"
            loading={loading}
            disabled={!link.trim()}
            onClick={handleExtract}
            icon={<RobotOutlined />}
            style={{ background: '#6366f1', borderColor: '#6366f1' }}
          >
            {loading ? '提取中...' : '提取'}
          </Button>
        </Flex>

        {loading && (
          <Steps
            current={currentStep}
            size="small"
            style={{ marginTop: 12 }}
            items={STEPS.map(s => ({ title: s.title }))}
          />
        )}
      </Card>

      {/* Error alert */}
      {error && (
        <Alert
          type="error"
          message="提取失败"
          description={error}
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: 16 }}
          showIcon
        />
      )}

      {/* 文档生成成功提示 — 放在输入区和分屏之间，始终可见 */}
      {docUrl && (
        <Card style={{ marginBottom: 16, background: '#f6ffed', borderColor: '#b7eb8f' }}>
          <Flex align="center" gap={12}>
            <CheckCircleOutlined style={{ fontSize: 24, color: '#52c41a' }} />
            <div style={{ flex: 1 }}>
              <Text strong style={{ fontSize: 15 }}>会议纪要文档已生成</Text>
              <br />
              <a href={docUrl} target="_blank" rel="noopener noreferrer">
                {docUrl}
              </a>
            </div>
            <Button type="primary" ghost href={docUrl} target="_blank" icon={<FileTextOutlined />}>
              打开文档
            </Button>
          </Flex>
        </Card>
      )}

      {/* Split view: transcript | todos */}
      {(analysisStage !== 'idle' && !error) && (
        <div style={{ flex: 1, display: 'flex', gap: 16, minHeight: 0 }}>
          {/* Left: Transcript */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {showTranscript && meetingInfo ? (
              <TranscriptPanel
                meetingInfo={meetingInfo}
                content={transcript}
                loading={transcriptLoading}
              />
            ) : (
              <Card
                title={
                  <Flex align="center" gap={8}>
                    <FileTextOutlined />
                    <span>逐字稿</span>
                  </Flex>
                }
                size="small"
                style={{ height: '100%' }}
              >
                <div style={{ textAlign: 'center', paddingTop: 80 }}>
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="正在获取逐字稿..."
                  />
                </div>
              </Card>
            )}
          </div>

          {/* Right: Todos */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <TodoPanel
              key={extractKey}
              meetingInfo={meetingInfo}
              moduleGroups={moduleGroups}
              loading={todoLoading}
              onGenerateDoc={handleGenerateDoc}
              generating={generating}
            />
          </div>
        </div>
      )}

      {/* Initial empty state */}
      {analysisStage === 'idle' && !error && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <div>
                <p>输入妙记链接后点击「提取」开始分析</p>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  支持飞书妙记链接格式：minutes/xxx
                </Text>
              </div>
            }
          />
        </div>
      )}
    </div>
  )
}