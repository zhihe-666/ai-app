import { useState, useCallback, useEffect, useRef } from 'react'
import {
  Card, DatePicker, Button, Steps, Tag, Typography,
  Alert, Space, Tooltip, Statistic, Row, Col, Empty, Input, Divider,
} from 'antd'
import {
  CodeOutlined, PlayCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined,
  FileTextOutlined, FileAddOutlined,
  GithubOutlined, BranchesOutlined, CalendarOutlined, FolderOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
dayjs.locale('zh-cn')
import {
  startAnalysis, exportMarkdown, exportToFeishu,
  getRepoCache, saveRepoCache,
  AnalysisResult, ProgressEvent,
} from '../api/codeAnalyze'

const { RangePicker } = DatePicker
const { Text, Paragraph } = Typography

const THEME = {
  primary: '#6366f1',
  primaryLight: '#eef2ff',
  primaryBg: '#f8f9ff',
  border: '#e5e7eb',
}

const STEPS_CONFIG = [
  { title: '拉取仓库', key: 'git_fetch' },
  { title: '定位 commits', key: 'resolve_commits' },
  { title: '收集 commit 信息', key: 'commit_messages' },
  { title: '检出代码', key: 'checkout' },
  { title: '知识快照', key: 'snapshot' },
  { title: '生成 diff', key: 'diff' },
  { title: 'AST 分析', key: 'ast' },
  { title: 'LLM 归纳', key: 'llm' },
]

type StepStatus = 'pending' | 'process' | 'finish' | 'error'

export default function CodeAnalyze() {
  const DEFAULT_REPO = 'https://gitlab.shizhuang-inc.com/du-monorepo/algorithm-monorepo.git'
  const [repoUrl, setRepoUrl] = useState(DEFAULT_REPO)
  const [branch, setBranch] = useState('master')
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [selectedPaths, setSelectedPaths] = useState<string[]>(['apps/algorithm/ml-data', 'apps/algorithm/ml-main'])
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({})

  const completedRef = useRef<Set<string>>(new Set())
  const abortRef = useRef<AbortController | null>(null)

  const handleUrlBlur = useCallback(() => {
    if (repoUrl) {
      getRepoCache(repoUrl).then(cached => {
        if (cached?.cached && cached.branch) {
          setBranch(cached.branch)
          if (cached.frontend_paths?.length) {
            setSelectedPaths(cached.frontend_paths)
          }
        }
      }).catch(() => {})
    }
  }, [repoUrl])

  const handleStart = useCallback(() => {
    if (!dateRange?.[0] || !dateRange?.[1]) return
    if (selectedPaths.length === 0) {
      setError('请至少选择一个分析路径')
      return
    }

    setAnalyzing(true)
    setResult(null)
    setError(null)
    completedRef.current = new Set()

    const initial: Record<string, StepStatus> = {}
    STEPS_CONFIG.forEach(s => { initial[s.key] = 'pending' })
    setStepStatuses(initial)

    saveRepoCache(repoUrl, branch, selectedPaths).catch(() => {})

    const ctrl = startAnalysis(
      {
        repo_url: repoUrl,
        branch: branch,
        start_time: dateRange[0].startOf('day').format('YYYY-MM-DDTHH:mm:ssZ'),
        end_time: dateRange[1].endOf('day').format('YYYY-MM-DDTHH:mm:ssZ'),
        frontend_paths: selectedPaths,
      },
      {
        onProgress: (data: ProgressEvent) => {
          completedRef.current.add(data.step)
          setStepStatuses(prev => {
            const next = { ...prev }
            next[data.step] = 'process'
            const keys = Object.keys(next)
            const idx = keys.indexOf(data.step)
            for (let i = 0; i < idx; i++) {
              if (next[keys[i]] !== 'error') next[keys[i]] = 'finish'
            }
            return next
          })
        },
        onSectionComplete: (data) => {
          completedRef.current.add(data.section)
          setStepStatuses(prev => ({ ...prev, [data.section]: 'finish' }))
        },
        onComplete: (data: AnalysisResult) => {
          completedRef.current.add('llm')
          setStepStatuses(prev => {
            const next = { ...prev }
            for (const k of Object.keys(next)) {
              if (!completedRef.current.has(k)) next[k] = 'error'
            }
            next['llm'] = 'finish'
            return next
          })
          setResult(data)
          setAnalyzing(false)
        },
        onError: (err: string) => {
          setError(err)
          setAnalyzing(false)
        },
      }
    )
    abortRef.current = ctrl
  }, [dateRange, selectedPaths, repoUrl, branch])

  const handleCancel = useCallback(() => {
    abortRef.current?.abort()
    setAnalyzing(false)
  }, [])

  const currentStep = STEPS_CONFIG.findIndex(s => stepStatuses[s.key] === 'process')

  const stepsItems = STEPS_CONFIG.map(s => {
    const status = stepStatuses[s.key] || 'pending'
    return {
      title: s.title,
      status: status as 'pending' | 'process' | 'finish' | 'error',
      icon: status === 'finish' ? <CheckCircleOutlined /> :
            status === 'error' ? <CloseCircleOutlined /> :
            status === 'process' ? <LoadingOutlined /> : undefined,
    } as any
  })

  const statusLabel = (() => {
    const count = Object.keys(stepStatuses).length
    if (count === 0) return ''
    const done = Object.values(stepStatuses).filter(s => s === 'finish' || s === 'error').length
    const hasError = Object.values(stepStatuses).some(s => s === 'error')
    return hasError ? `${done}/${count} 步 — 有错误` : `${done}/${count} 步完成`
  })()

  const inputStyle: React.CSSProperties = {
    borderRadius: 8,
    border: `1.5px solid ${THEME.border}`,
  }

  return (
    <div style={{ padding: 24, height: '100vh', overflow: 'auto', background: '#f5f5ff' }}>
      {/* Config Card */}
      <Card
        style={{
          marginBottom: 16,
          borderRadius: 12,
          border: `1px solid ${THEME.border}`,
          boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
        }}
        bodyStyle={{ padding: '20px 24px' }}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {/* Row 1: Repo + Branch + Date */}
          <Row gutter={[16, 12]} align="middle">
            <Col xs={24} md={10}>
              <Space size={4} direction="vertical" style={{ width: '100%' }}>
                <Text style={{ fontSize: 12, color: '#6b7280', fontWeight: 500 }}>
                  <GithubOutlined style={{ marginRight: 4 }} />目标仓库
                </Text>
                <Input
                  size="middle"
                  value={repoUrl}
                  onChange={e => setRepoUrl(e.target.value)}
                  onBlur={handleUrlBlur}
                  disabled={analyzing}
                  placeholder="https://gitlab.com/org/repo.git"
                  prefix={<GithubOutlined style={{ color: '#9ca3af' }} />}
                  style={inputStyle}
                />
              </Space>
            </Col>
            <Col xs={12} md={4}>
              <Space size={4} direction="vertical" style={{ width: '100%' }}>
                <Text style={{ fontSize: 12, color: '#6b7280', fontWeight: 500 }}>
                  <BranchesOutlined style={{ marginRight: 4 }} />分支
                </Text>
                <Input
                  size="middle"
                  value={branch}
                  onChange={e => setBranch(e.target.value)}
                  disabled={analyzing}
                  placeholder="master"
                  prefix={<BranchesOutlined style={{ color: '#9ca3af' }} />}
                  style={inputStyle}
                />
              </Space>
            </Col>
            <Col xs={12} md={10}>
              <Space size={4} direction="vertical" style={{ width: '100%' }}>
                <Text style={{ fontSize: 12, color: '#6b7280', fontWeight: 500 }}>
                  <CalendarOutlined style={{ marginRight: 4 }} />时间段
                </Text>
                <RangePicker
                  picker="date"
                  value={dateRange}
                  onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
                  disabled={analyzing}
                  disabledDate={(current) => current && current.isAfter(dayjs().endOf('day'))}
                  style={{ ...inputStyle, width: '100%' }}
                />
              </Space>
            </Col>
          </Row>

          {/* Row 2: Path + Actions */}
          <Row gutter={[16, 12]} align="middle">
            <Col xs={24} md={12}>
              <Space size={4} direction="vertical" style={{ width: '100%' }}>
                <Text style={{ fontSize: 12, color: '#6b7280', fontWeight: 500 }}>
                  <FolderOutlined style={{ marginRight: 4 }} />分析路径
                </Text>
                <Input
                  size="middle"
                  value={selectedPaths.join(', ')}
                  onChange={e => setSelectedPaths(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  disabled={analyzing}
                  placeholder="apps/algorithm/ml-data, apps/algorithm/ml-main"
                  prefix={<FolderOutlined style={{ color: '#9ca3af' }} />}
                  suffix={<Text type="secondary" style={{ fontSize: 11 }}>逗号分隔</Text>}
                  style={inputStyle}
                />
              </Space>
            </Col>
            <Col xs={24} md={12}>
              <Space size={12} style={{ paddingTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={handleStart}
                  loading={analyzing}
                  disabled={!dateRange || selectedPaths.length === 0}
                  size="middle"
                  style={{
                    borderRadius: 8,
                    background: THEME.primary,
                    borderColor: THEME.primary,
                    height: 40,
                    paddingInline: 24,
                    fontWeight: 500,
                    boxShadow: '0 2px 6px rgba(99,102,241,0.25)',
                  }}
                >
                  {analyzing ? '分析中...' : '开始分析'}
                </Button>
                {analyzing && (
                  <Button
                    danger
                    onClick={handleCancel}
                    size="middle"
                    style={{ borderRadius: 8, height: 40 }}
                  >
                    取消
                  </Button>
                )}
              </Space>
            </Col>
          </Row>
        </Space>
      </Card>

      {/* Progress Area */}
      {(analyzing || Object.keys(stepStatuses).length > 0) && (
        <Card
          size="small"
          style={{
            marginBottom: 16,
            borderRadius: 12,
            border: `1px solid ${THEME.border}`,
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            background: '#fff',
          }}
          bodyStyle={{ padding: '16px 20px' }}
        >
          <Row align="middle" gutter={16}>
            <Col flex="auto">
              <Steps
                current={currentStep}
                size="small"
                items={stepsItems}
                style={{
                  ['--ant-steps-nav-arrow-color' as string]: THEME.primary,
                  ['--ant-steps-icon-active-color' as string]: THEME.primary,
                  ['--ant-steps-heading-color' as string]: THEME.primary,
                }}
              />
            </Col>
            {statusLabel && (
              <Col>
                <Tag
                  color={statusLabel.includes('错误') ? 'error' : 'processing'}
                  style={{ borderRadius: 12, fontSize: 11, marginRight: 0 }}
                >
                  {statusLabel}
                </Tag>
              </Col>
            )}
          </Row>
        </Card>
      )}

      {/* Error */}
      {error && (
        <Alert
          type="error"
          message="分析失败"
          description={error}
          closable
          style={{ marginBottom: 16, borderRadius: 8 }}
          onClose={() => setError(null)}
        />
      )}

      {/* Result */}
      {result && (
        <Card
          title={
            <Space>
              <CodeOutlined style={{ color: THEME.primary }} />
              <span style={{ fontWeight: 600 }}>分析报告</span>
              <Tag color={result.llm_status === 'success' ? 'blue' : 'orange'} style={{ borderRadius: 8 }}>
                {result.llm_status === 'success' ? 'LLM 分析' : '规则层降级'}
              </Tag>
            </Space>
          }
          style={{
            borderRadius: 12,
            border: `1px solid ${THEME.border}`,
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
          bodyStyle={{ padding: '20px 24px' }}
        >
          {result.summary && (
            <Row gutter={16} style={{ marginBottom: 20 }}>
              {[
                { label: 'Feature Groups', value: result.summary.feature_groups, suffix: '组', color: THEME.primary },
                { label: '功能变更', value: result.summary.functional_changes ?? '-', suffix: '项', color: '#10b981' },
                { label: 'UI 变更', value: result.summary.ui_changes ?? '-', suffix: '项', color: '#8b5cf6' },
                { label: '分析文件', value: result.summary.analyzed_files, suffix: '个', color: '#f59e0b' },
              ].map((item, idx) => (
                <Col span={6} key={idx}>
                  <div style={{
                    background: THEME.primaryBg,
                    borderRadius: 10,
                    padding: '14px 16px',
                    borderLeft: `3px solid ${item.color}`,
                  }}>
                    <Text style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>
                      {item.label}
                    </Text>
                    <Text strong style={{ fontSize: 22, color: item.color }}>
                      {item.value}
                    </Text>
                    <Text style={{ fontSize: 12, color: '#9ca3af', marginLeft: 4 }}>{item.suffix}</Text>
                  </div>
                </Col>
              ))}
            </Row>
          )}

          {/* Export buttons */}
          {result.functional_changes && result.functional_changes.length > 0 && (
            <Space style={{ marginBottom: 16 }}>
              <Button
                icon={<FileTextOutlined />}
                onClick={() => exportMarkdown(result)}
                style={{ borderRadius: 8 }}
              >
                导出 Markdown
              </Button>
              <Button
                icon={<FileAddOutlined />}
                onClick={async () => {
                  try {
                    const url = await exportToFeishu(result)
                    window.open(url, '_blank')
                  } catch (e: any) {
                    setError(e.message || '导出到飞书失败')
                  }
                }}
                style={{ borderRadius: 8 }}
              >
                导出到飞书文档
              </Button>
            </Space>
          )}

          {/* Functional Changes */}
          {result.functional_changes && result.functional_changes.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <Text strong style={{ fontSize: 15 }}>
                <Tag color="blue" style={{ borderRadius: 8 }}>📦 功能变更 ({result.functional_changes.length})</Tag>
              </Text>
              {result.functional_changes.map((f, i) => (
                <Card
                  key={i}
                  size="small"
                  style={{
                    marginTop: 8,
                    borderRadius: 10,
                    border: `1px solid ${THEME.border}`,
                    background: '#f8faff',
                  }}
                  bodyStyle={{ padding: '12px 16px' }}
                >
                  <Space>
                    <Text strong style={{ color: '#1f2937' }}>{f.name}</Text>
                    {f.confidence && <Tag style={{ borderRadius: 8, fontSize: 11 }}>conf: {f.confidence.toFixed(2)}</Tag>}
                  </Space>
                  {f.description && (
                    <Paragraph style={{ marginTop: 8, marginBottom: 4, color: '#4b5563', fontSize: 13 }}>
                      {f.description}
                    </Paragraph>
                  )}
                  {f.evidence_files && f.evidence_files.length > 0 && (
                    <Space wrap style={{ marginTop: 6 }}>
                      {f.evidence_files.slice(0, 20).map((file, j) => (
                        <Tooltip key={j} title={file}>
                          <Tag style={{
                            maxWidth: 260,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            fontSize: 11,
                            borderRadius: 6,
                            border: `1px solid ${THEME.border}`,
                          }}>
                            {file.split('/').pop()}
                          </Tag>
                        </Tooltip>
                      ))}
                      {f.evidence_files.length > 20 && (
                        <Tag style={{ fontSize: 11, borderRadius: 6, border: `1px solid ${THEME.border}`, background: '#f5f5f5' }}>
                          +{f.evidence_files.length - 20} 个文件
                        </Tag>
                      )}
                    </Space>
                  )}
                </Card>
              ))}
            </div>
          )}

          {/* Removed Features */}
          {result.removed_features && result.removed_features.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <Text strong style={{ fontSize: 15 }}>
                <Tag color="red" style={{ borderRadius: 8 }}>🗑️ 功能下线 ({result.removed_features.length})</Tag>
              </Text>
              {result.removed_features.map((f, i) => (
                <Card
                  key={i}
                  size="small"
                  style={{
                    marginTop: 8,
                    borderRadius: 10,
                    border: `1px solid #fecaca`,
                    background: '#fff5f5',
                  }}
                  bodyStyle={{ padding: '12px 16px' }}
                >
                  <Space><Text strong style={{ color: '#991b1b' }}>{f.name}</Text></Space>
                  {f.description && (
                    <Paragraph style={{ marginTop: 6, marginBottom: 4, color: '#7f1d1d', fontSize: 13 }}>
                      {f.description}
                    </Paragraph>
                  )}
                </Card>
              ))}
            </div>
          )}

          {/* UI Updates */}
          {result.ui_updates && result.ui_updates.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 15 }}>
                <Tag color="purple" style={{ borderRadius: 8 }}>🎨 UI 更新 ({result.ui_updates.length})</Tag>
              </Text>
              <Card
                size="small"
                style={{
                  marginTop: 8,
                  borderRadius: 10,
                  border: `1px solid ${THEME.border}`,
                  background: '#faf5ff',
                }}
                bodyStyle={{ padding: '10px 16px' }}
              >
                {result.ui_updates.map((u, i) => (
                  <div key={i} style={{ padding: '3px 0', color: '#6b21a8', fontSize: 13 }}>• {u}</div>
                ))}
              </Card>
            </div>
          )}

          {/* Empty state */}
          {(!result.functional_changes || result.functional_changes.length === 0) &&
           (!result.removed_features || result.removed_features.length === 0) &&
           (!result.ui_updates || result.ui_updates.length === 0) && (
            <Empty description="未检测到有效变更" />
          )}
        </Card>
      )}
    </div>
  )
}