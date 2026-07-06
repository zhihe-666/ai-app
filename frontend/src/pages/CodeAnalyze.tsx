import { useState, useCallback, useEffect, useRef } from 'react'
import {
  Card, DatePicker, Button, Steps, Tag, Typography,
  Alert, Space, Tooltip, Statistic, Row, Col, Empty, Input,
} from 'antd'
import {
  CodeOutlined, ReloadOutlined, PlayCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined,
  FileTextOutlined, FileAddOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
dayjs.locale('zh-cn')
import {
  startAnalysis, refreshSnapshot, getSnapshotInfo,
  exportMarkdown, exportToFeishu,
  getRepoCache, saveRepoCache,
  AnalysisResult, ProgressEvent,
} from '../api/codeAnalyze'

const LABEL_STYLE: React.CSSProperties = { width: 80, textAlign: 'right' }
const { RangePicker } = DatePicker
const { Text, Paragraph } = Typography

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
  const [selectedPaths, setSelectedPaths] = useState<string[]>(['apps/algorithm/ml-data'])
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({})
  const [snapshotLabel, setSnapshotLabel] = useState('')

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

  useEffect(() => {
    getSnapshotInfo().then(info => {
      if (info?.generatedAt) {
        setSnapshotLabel(`知识快照生成于 ${dayjs(info.generatedAt).format('MM-DD HH:mm')}`)
      }
    }).catch(() => {})
  }, [])

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

    // Save repo config to cache
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

  const handleRefreshSnapshot = useCallback(() => {
    refreshSnapshot({
      onComplete: () => {
        getSnapshotInfo().then(info => {
          if (info?.generatedAt) {
            setSnapshotLabel(`知识快照已刷新: ${dayjs(info.generatedAt).format('MM-DD HH:mm')}`)
          }
        })
      },
      onError: (err) => setError(err),
    })
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

  return (
    <div style={{ padding: 24, height: '100vh', overflow: 'auto' }}>
      {/* Config Area */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="small">
          <Row gutter={16} align="middle">
            <Col style={LABEL_STYLE}><Text strong>目标仓库:</Text></Col>
            <Col flex="auto">
              <Input
                size="small"
                value={repoUrl}
                onChange={e => setRepoUrl(e.target.value)}
                onBlur={handleUrlBlur}
                disabled={analyzing}
                placeholder="https://gitlab.com/org/repo.git"
              />
            </Col>
          </Row>

          <Row gutter={16} align="middle">
            <Col style={LABEL_STYLE}><Text strong>分支:</Text></Col>
            <Col>
              <Input
                size="small"
                style={{ width: 200 }}
                value={branch}
                onChange={e => setBranch(e.target.value)}
                disabled={analyzing}
                placeholder="master"
              />
            </Col>
          </Row>

          <Row gutter={16} align="middle">
            <Col style={LABEL_STYLE}><Text strong>时间段:</Text></Col>
            <Col>
              <RangePicker
                picker="date"
                value={dateRange}
                onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
                disabled={analyzing}
                disabledDate={(current) => current && current.isAfter(dayjs().endOf('day'))}
              />
            </Col>
          </Row>

          <Row gutter={16} align="middle">
            <Col style={LABEL_STYLE}><Text strong>分析路径:</Text></Col>
            <Col>
              <Input
                size="small"
                style={{ width: 400 }}
                value={selectedPaths.join(', ')}
                onChange={e => setSelectedPaths(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                disabled={analyzing}
                placeholder="apps/algorithm/ml-data, apps/algorithm/ml-main"
              />
            </Col>
            <Col>
              <Text type="secondary" style={{ fontSize: 11 }}>逗号分隔</Text>
            </Col>
          </Row>

          <Row gutter={8} align="middle">
            <Col>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleStart}
                loading={analyzing}
                disabled={!dateRange || selectedPaths.length === 0}
              >
                开始分析
              </Button>
            </Col>
            {analyzing && (
              <Col>
                <Button danger onClick={handleCancel}>取消</Button>
              </Col>
            )}
            <Col>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleRefreshSnapshot}
                disabled={analyzing}
              >
                刷新知识快照
              </Button>
            </Col>
            {snapshotLabel && (
              <Col>
                <Text type="secondary" style={{ fontSize: 12 }}>{snapshotLabel}</Text>
              </Col>
            )}
          </Row>
        </Space>
      </Card>

      {/* Progress Area */}
      {(analyzing || Object.keys(stepStatuses).length > 0) && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Steps current={currentStep} direction="vertical" size="small" items={stepsItems} />
        </Card>
      )}

      {/* Error */}
      {error && (
        <Alert type="error" message="分析失败" description={error} closable
          style={{ marginBottom: 16 }} onClose={() => setError(null)} />
      )}

      {/* Result */}
      {result && (
        <Card size="small" title={
          <Space>
            <CodeOutlined />
            <span>分析报告</span>
            <Tag color={result.llm_status === 'success' ? 'blue' : 'orange'}>
              {result.llm_status === 'success' ? 'LLM 分析' : '规则层降级'}
            </Tag>
          </Space>
        }>
          {result.summary && (
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={6}><Statistic title="Feature Groups" value={result.summary.feature_groups} suffix="组" /></Col>
              <Col span={6}><Statistic title="功能变更" value={result.summary.functional_changes ?? '-'} suffix="项" /></Col>
              <Col span={6}><Statistic title="UI 变更" value={result.summary.ui_changes ?? '-'} suffix="项" /></Col>
              <Col span={6}><Statistic title="分析文件" value={result.summary.analyzed_files} suffix="个" /></Col>
            </Row>
          )}

          {/* Export buttons */}
          {result.new_features && result.new_features.length > 0 && (
            <Space style={{ marginBottom: 16 }}>
              <Button icon={<FileTextOutlined />} onClick={() => exportMarkdown(result)}>
                导出 Markdown
              </Button>
              <Button icon={<FileAddOutlined />} onClick={async () => {
                try {
                  const url = await exportToFeishu(result)
                  window.open(url, '_blank')
                } catch (e: any) {
                  setError(e.message || '导出到飞书失败')
                }
              }}>
                导出到飞书文档
              </Button>
            </Space>
          )}

          {/* New Features */}
          {result.new_features && result.new_features.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 15 }}>
                <Tag color="green">🆕 新增功能 ({result.new_features.length})</Tag>
              </Text>
              {result.new_features.map((f, i) => (
                <Card key={i} size="small" style={{ marginTop: 8, background: '#f6ffed' }}>
                  <Space>
                    <Text strong>{f.name}</Text>
                    {f.confidence && <Tag>conf: {f.confidence.toFixed(2)}</Tag>}
                    {f.user_visible && <Tag color="blue">用户可见</Tag>}
                  </Space>
                  {f.description && <Paragraph style={{ marginTop: 6, marginBottom: 4 }}>{f.description}</Paragraph>}
                  {f.evidence_files && f.evidence_files.length > 0 && (
                    <Space wrap>
                      {f.evidence_files.map((file, j) => (
                        <Tooltip key={j} title={file}>
                          <Tag style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 11 }}>
                            {file.split('/').pop()}
                          </Tag>
                        </Tooltip>
                      ))}
                    </Space>
                  )}
                </Card>
              ))}
            </div>
          )}

          {/* Modified Features */}
          {result.modified_features && result.modified_features.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 15 }}>
                <Tag color="orange">🔄 功能修改 ({result.modified_features.length})</Tag>
              </Text>
              {result.modified_features.map((f, i) => (
                <Card key={i} size="small" style={{ marginTop: 8, background: '#fffbe6' }}>
                  <Space>
                    <Text strong>{f.name}</Text>
                    {f.confidence && <Tag>conf: {f.confidence.toFixed(2)}</Tag>}
                    {f.user_visible === false && <Tag color="default">用户不可见</Tag>}
                  </Space>
                  {f.description && <Paragraph style={{ marginTop: 6, marginBottom: 4 }}>{f.description}</Paragraph>}
                  {f.evidence_files && f.evidence_files.length > 0 && (
                    <Space wrap>
                      {f.evidence_files.map((file, j) => (
                        <Tooltip key={j} title={file}>
                          <Tag style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 11 }}>
                            {file.split('/').pop()}
                          </Tag>
                        </Tooltip>
                      ))}
                    </Space>
                  )}
                </Card>
              ))}
            </div>
          )}

          {/* Removed Features */}
          {result.removed_features && result.removed_features.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 15 }}>
                <Tag color="red">🗑️ 功能下线 ({result.removed_features.length})</Tag>
              </Text>
              {result.removed_features.map((f, i) => (
                <Card key={i} size="small" style={{ marginTop: 8, background: '#fff2f0' }}>
                  <Space><Text strong>{f.name}</Text></Space>
                  {f.description && <Paragraph style={{ marginTop: 6, marginBottom: 4 }}>{f.description}</Paragraph>}
                </Card>
              ))}
            </div>
          )}

          {/* UI Updates */}
          {result.ui_updates && result.ui_updates.length > 0 && (
            <div>
              <Text strong style={{ fontSize: 15 }}>
                <Tag color="purple">🎨 UI 更新 ({result.ui_updates.length})</Tag>
              </Text>
              <Card size="small" style={{ marginTop: 8 }}>
                {result.ui_updates.map((u, i) => (
                  <div key={i} style={{ padding: '2px 0' }}>• {u}</div>
                ))}
              </Card>
            </div>
          )}

          {/* Empty state */}
          {(!result.new_features || result.new_features.length === 0) &&
           (!result.modified_features || result.modified_features.length === 0) &&
           (!result.removed_features || result.removed_features.length === 0) &&
           (!result.ui_updates || result.ui_updates.length === 0) && (
            <Empty description="未检测到有效变更" />
          )}
        </Card>
      )}
    </div>
  )
}