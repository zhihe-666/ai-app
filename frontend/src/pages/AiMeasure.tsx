/**
 * AiMeasure — AI 编程数据报告页面
 *
 * 配置区：Token + 试点名单 + TL 名单 + 时间范围 + 报告模块
 * 进度区：竖向 Steps
 * 报告区：分模块 Ant Design Table 展示
 */
import React, { useState, useEffect, useRef } from 'react'
import {
  Typography,
  Input,
  Button,
  DatePicker,
  Checkbox,
  Card,
  Steps,
  Tag,
  Space,
  Alert,
  message,
  Table,
  Collapse,
} from 'antd'
import {
  KeyOutlined,
  UserOutlined,
  CalendarOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  CopyOutlined,
  FileAddOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import type { CompleteEvent, SectionCompleteEvent, SectionErrorEvent, ProgressEvent as ReportProgressEvent } from '../api/aiMeasure'
import {
  testToken,
  generateReport,
  writeToFeishu,
  getPilotNames,
  savePilotNames,
  getTlNames,
  saveTlNames,
} from '../api/aiMeasure'

const { Title, Text } = Typography
const { RangePicker } = DatePicker
const { TextArea } = Input

const REPORT_SECTIONS = [
  { key: 'active_rate', label: '试点人员活跃率', color: '#6366f1' },
  { key: 'inactive', label: '不活跃人员名单', color: '#d97706' },
  { key: 'skills', label: 'Skills 技能列表', color: '#059669' },
  { key: 'tl_usage', label: 'TL 使用情况', color: '#0891b2' },
] as const

type SectionStatus = 'wait' | 'process' | 'finish' | 'error'

/** 表格数据行 */
interface ReportRow {
  _section: string
  [key: string]: any
}

/** 模块表格列配置 */
interface SectionColumns {
  key: string
  title: string
  columns: {
    key: string
    title: string
    dataIndex: string
    render?: (val: any, record: any) => React.ReactNode
  }[]
}

/** 格式化百分比：36.02 → "36.02%" */
const fmtPct = (v: any): string => {
  if (v === undefined || v === null || v === '-') return '-'
  const n = typeof v === 'number' ? v : parseFloat(v)
  return isNaN(n) ? `${v}` : `${n.toFixed(2)}%`
}

const SECTION_COLUMNS: Record<string, SectionColumns> = {
  active_rate: {
    key: 'active_rate',
    title: '试点人员活跃率',
    columns: [
      { key: 'name', title: '姓名', dataIndex: 'name' },
      { key: 'activity_rate', title: '活跃率', dataIndex: 'activity_rate', render: (v: any) => fmtPct(v) },
      { key: 'tokens_m', title: 'Token 消耗(M)', dataIndex: 'tokens_m' },
      { key: 'code_ratio', title: 'AI 代码占比', dataIndex: 'code_ratio', render: (v: any) => fmtPct(v) },
      { key: 'commit_ratio', title: 'AI Commit 占比', dataIndex: 'commit_ratio', render: (v: any) => fmtPct(v) },
    ],
  },
  inactive: {
    key: 'inactive',
    title: '不活跃人员名单',
    columns: [
      { key: 'name', title: '姓名', dataIndex: 'name' },
      { key: 'username', title: '域账号', dataIndex: 'username' },
      { key: 'department', title: '组织', dataIndex: 'department' },
      { key: 'activity_rate', title: '活跃率', dataIndex: 'activity_rate', render: (v: any) => fmtPct(v) },
      { key: 'code_ratio', title: 'AI 代码占比', dataIndex: 'code_ratio', render: (v: any) => fmtPct(v) },
      { key: 'commit_ratio', title: 'AI Commit 占比', dataIndex: 'commit_ratio', render: (v: any) => fmtPct(v) },
    ],
  },
  skills: {
    key: 'skills',
    title: 'Skills 技能列表',
    columns: [
      { key: 'name', title: '技能名称', dataIndex: 'name', render: (v: any, r: any) => r.url ? <a href={r.url} target="_blank" rel="noreferrer">{v}</a> : v },
      { key: 'author', title: '贡献人', dataIndex: 'author' },
      { key: 'description', title: '描述', dataIndex: 'description' },
      { key: 'call_count', title: '调用次数', dataIndex: 'call_count' },
      { key: 'efficiency_minutes', title: '提效(分钟)', dataIndex: 'efficiency_minutes' },
      { key: 'updated_at', title: '更新时间', dataIndex: 'updated_at' },
    ],
  },
  tl_usage: {
    key: 'tl_usage',
    title: 'TL 使用情况',
    columns: [
      { key: 'name', title: '姓名', dataIndex: 'name' },
      { key: 'activity_rate', title: '活跃率', dataIndex: 'activity_rate', render: (v: any) => fmtPct(v) },
      { key: 'tokens_m', title: 'Token 消耗(M)', dataIndex: 'tokens_m' },
      { key: 'code_ratio', title: 'AI 代码占比', dataIndex: 'code_ratio', render: (v: any) => fmtPct(v) },
      { key: 'commit_ratio', title: 'AI Commit 占比', dataIndex: 'commit_ratio', render: (v: any) => fmtPct(v) },
    ],
  },
}

export default function AiMeasure() {
  // Config state
  const [token, setToken] = useState('')
  const [tokenStatus, setTokenStatus] = useState<'untested' | 'testing' | 'valid' | 'invalid'>('untested')
  const [tokenMessage, setTokenMessage] = useState('')
  const [pilotNames, setPilotNames] = useState('')
  const [tlNames, setTlNames] = useState('')
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null]>([dayjs().subtract(14, 'day'), dayjs()])
  const [selectedSections, setSelectedSections] = useState<string[]>(
    REPORT_SECTIONS.map(s => s.key)
  )

  // Generation state
  const [generating, setGenerating] = useState(false)
  const [steps, setSteps] = useState<Record<string, SectionStatus>>({})
  const [sectionRows, setSectionRows] = useState<Record<string, ReportRow[]>>({})
  const [sectionTitles, setSectionTitles] = useState<Record<string, string>>({})
  const [rowCounts, setRowCounts] = useState<Record<string, number>>({})

  // Write state
  const [writing, setWriting] = useState(false)
  const [copied, setCopied] = useState(false)
  const [docUrl, setDocUrl] = useState<string | null>(null)

  // 防止旧请求的回调污染当前 UI
  const generationIdRef = useRef(0)
  const abortRef = useRef<AbortController | null>(null)
  /** 跟踪已完成 sections（用于 batch 场景下区分 process 和 error） */
  const completedRef = useRef<Set<string>>(new Set())

  // 页面加载时读取保存的名单
  useEffect(() => {
    getPilotNames().then(res => setPilotNames(res.names)).catch(() => {})
    getTlNames().then(res => setTlNames(res.names)).catch(() => {})
  }, [])

  /** 测试 Token */
  const handleTestToken = async () => {
    // token 为空时使用后端默认 token
    setTokenStatus('testing')
    setTokenMessage('')
    try {
      const result = await testToken(token.trim())
      if (result.ok) {
        setTokenStatus('valid')
        setTokenMessage(result.message)
      } else {
        setTokenStatus('invalid')
        setTokenMessage(result.message)
      }
    } catch (e: any) {
      setTokenStatus('invalid')
      setTokenMessage(e?.message || '连接失败')
    }
  }

  /** 生成报告 */
  const handleGenerate = async () => {
    // token 为空时使用后端默认 token
    if (!dateRange[0] || !dateRange[1]) {
      message.warning('请选择时间范围')
      return
    }
    if (selectedSections.length === 0) {
      message.warning('请至少勾选一个报告模块')
      return
    }

    // 取消上一次请求（如果存在）
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller

    const genId = ++generationIdRef.current

    setGenerating(true)
    setSectionRows({})
    setSectionTitles({})
    setRowCounts({})
    setSteps({})
    setDocUrl(null)
    setCopied(false)
    completedRef.current = new Set()

    const initSteps: Record<string, SectionStatus> = {}
    selectedSections.forEach(s => { initSteps[s] = 'wait' })
    setSteps(initSteps)

    try {
      // 包装 callback，检查 genId 是否匹配
      const cb = (cbs: any) => {
        const wrapped: any = {}
        for (const key of Object.keys(cbs)) {
          wrapped[key] = (...args: any[]) => {
            if (generationIdRef.current !== genId) return // 旧请求，丢弃
            cbs[key]?.(...args)
          }
        }
        return wrapped
      }

      await generateReport(
        {
          access_token: token.trim(),
          pilot_names: pilotNames.trim(),
          start_date: dateRange[0]!.format('YYYY-MM-DD'),
          end_date: dateRange[1]!.format('YYYY-MM-DD'),
          sections: selectedSections,
        },
        cb({
          onProgress: (data: ReportProgressEvent) => {
            setSteps(prev => ({ ...prev, [data.section]: 'process' }))
          },
          onSectionComplete: (data: SectionCompleteEvent) => {
            completedRef.current.add(data.section)
            setSteps(prev => ({ ...prev, [data.section]: 'finish' }))
            setSectionTitles(prev => ({ ...prev, [data.section]: data.title }))
            setRowCounts(prev => ({ ...prev, [data.section]: data.row_count }))
            setSectionRows(prev => ({ ...prev, [data.section]: (data as any).rows || [] }))
          },
          onSectionError: (data: SectionErrorEvent) => {
            setSteps(prev => ({ ...prev, [data.section]: 'error' }))
            message.error(`「${data.title}」查询失败: ${data.message}`)
          },
          onComplete: (data: CompleteEvent) => {
            // debug: 确认前端版本
            console.log('[AiMeasure] onComplete:', data, 'completedRef:', [...completedRef.current])
            // 用 completedRef 真实状态判断，避免 batch 中 prev 过期
            setSteps(prev => {
              const next = { ...prev }
              for (const k of Object.keys(next)) {
                if (!completedRef.current.has(k)) {
                  next[k] = 'error'
                }
              }
              return next
            })
            setGenerating(false)
            setTimeout(() => {
              message.success(`报告生成完成（${data.sections_completed}/${data.total_sections} 模块）`)
            }, 0)
          },
          onError: (err: any) => {
            setGenerating(false)
            message.error(typeof err === 'string' ? err : err?.message || '生成失败')
          },
        }),
        controller.signal
      )
    } catch (e: any) {
      // AbortError 不显示
      if (e?.name === 'AbortError') return
      setGenerating(false)
      message.error(e?.message || '生成异常')
    }
  }

  /** 写入飞书 */
  const handleWrite = async () => {
    const allMarkdownParts = [`# 算法平台 AI 编程周报（${dateRange[0]?.format('YYYY-MM-DD')} ~ ${dateRange[1]?.format('YYYY-MM-DD')}）\n`]
    for (const section of selectedSections) {
      const rows = sectionRows[section]
      if (!rows || rows.length === 0) {
        allMarkdownParts.push(`## ${SECTION_COLUMNS[section]?.title || section}\n\n（无数据）\n`)
        continue
      }
      allMarkdownParts.push(`## ${SECTION_COLUMNS[section]?.title || section}\n`)
      const cols = SECTION_COLUMNS[section]?.columns || []
      allMarkdownParts.push('| ' + cols.map(c => c.title).join(' | ') + ' |')
      allMarkdownParts.push('|' + cols.map(() => '---').join('|') + '|')
      for (const row of rows) {
        allMarkdownParts.push('| ' + cols.map(c => {
        const raw = row[c.dataIndex]
        // 百分比字段格式化
        if (['activity_rate', 'code_ratio', 'commit_ratio'].includes(c.dataIndex)) {
          return fmtPct(raw)
        }
        if (c.dataIndex === 'name' && row.url) {
          return `[${raw}](${row.url})`
        }
        // 描述字段清洗：换行→空格，|→全角｜，避免破坏 Markdown 表格
        if (c.dataIndex === 'description' && typeof raw === 'string') {
          return raw.replace(/\n/g, ' ').replace(/\|/g, '｜')
        }
        // 所有字段清洗换行和 | 以防万一
        const val = (raw ?? '-') + ''
        return val.replace(/\n/g, ' ').replace(/\|/g, '｜')
      }).join(' | ') + ' |')
      }
      allMarkdownParts.push('')
    }

    const fullMd = allMarkdownParts.join('\n')
    setWriting(true)
    try {
      const title = `算法平台 AI 编程周报（${dateRange[0]?.format('YYYY-MM-DD')} ~ ${dateRange[1]?.format('YYYY-MM-DD')}）`
      const result = await writeToFeishu({ title, content: fullMd })
      if (result.doc_url) {
        setDocUrl(result.doc_url)
        message.success('已写入飞书文档')
      } else {
        message.error(result.error || '写入失败')
      }
    } catch (e: any) {
      message.error(e?.message || '写入异常')
    } finally {
      setWriting(false)
    }
  }

  /** 复制报告 */
  const handleCopy = () => {
    const allMd = Object.values(sectionRows).flat()
    const txt = JSON.stringify(allMd, null, 2)
    navigator.clipboard.writeText(txt)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const reportDate = dateRange[0] && dateRange[1]
    ? `${dateRange[0].format('YYYY-MM-DD')} ~ ${dateRange[1].format('YYYY-MM-DD')}`
    : ''

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: 24 }}>
      <Title level={3}>
        <ThunderboltOutlined /> AI 编程数据报告
      </Title>

      {/* ── 配置区 ── */}
      <Card title="配置" size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {/* Token */}
          <div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>
              <KeyOutlined /> Access Token
            </div>
            <Space.Compact style={{ width: '100%' }}>
              <Input.Password
                placeholder="输入 EP Token..."
                value={token}
                onChange={e => {
                  setToken(e.target.value)
                  if (tokenStatus !== 'untested') setTokenStatus('untested')
                }}
                style={{ width: '65%' }}
              />
              <Button
                onClick={handleTestToken}
                loading={tokenStatus === 'testing'}
                style={{ width: '35%' }}
              >
                {tokenStatus === 'untested' ? '测试连接' :
                 tokenStatus === 'testing' ? '测试中...' :
                 tokenStatus === 'valid' ? '✓ 有效' : '✗ 无效'}
              </Button>
            </Space.Compact>
            {tokenMessage && (
              <div style={{ marginTop: 4 }}>
                <Tag color={tokenStatus === 'valid' ? 'success' : 'error'}>{tokenMessage}</Tag>
              </div>
            )}
          </div>

          {/* Pilot names */}
          <div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>
              <UserOutlined /> 试点人员名单（域账号）
            </div>
            <TextArea
              rows={3}
              placeholder="逗号分隔，如：daguaishou,pengyuhang,guansha"
              value={pilotNames}
              onChange={e => setPilotNames(e.target.value)}
              style={{ width: '100%' }}
            />
            <Space style={{ marginTop: 6 }}>
              <Button onClick={() => navigator.clipboard.writeText(pilotNames)}>
                复制试点名单
              </Button>
              <Button type="primary" onClick={async () => {
                try {
                  await savePilotNames(pilotNames)
                  message.success('试点名单已保存')
                } catch {
                  message.error('保存失败')
                }
              }}>
                <SaveOutlined /> 保存试点名单
              </Button>
            </Space>
          </div>

          {/* TL names */}
          <div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>
              <UserOutlined /> TL 名单（域账号）
            </div>
            <TextArea
              rows={2}
              placeholder="逗号分隔的域账号"
              value={tlNames}
              onChange={e => setTlNames(e.target.value)}
              style={{ width: '100%' }}
            />
            <Space style={{ marginTop: 6 }}>
              <Button onClick={() => navigator.clipboard.writeText(tlNames)}>
                复制TL名单
              </Button>
              <Button type="primary" onClick={async () => {
                try {
                  await saveTlNames(tlNames)
                  message.success('TL 名单已保存')
                } catch {
                  message.error('保存失败')
                }
              }}>
                <SaveOutlined /> 保存TL名单
              </Button>
            </Space>
          </div>

          {/* Date range + sections */}
          <Space align="end" wrap>
            <div>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                <CalendarOutlined /> 时间范围
              </div>
              <RangePicker
                value={dateRange}
                onChange={dates => setDateRange(dates as [dayjs.Dayjs | null, dayjs.Dayjs | null])}
                style={{ width: 240 }}
              />
            </div>
            <div>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>报告模块</div>
              <Checkbox.Group
                options={REPORT_SECTIONS.map(s => ({ label: s.label, value: s.key }))}
                value={selectedSections}
                onChange={vals => setSelectedSections(vals as string[])}
              />
            </div>
            <Button
              type="primary"
              size="large"
              icon={<ThunderboltOutlined />}
              onClick={handleGenerate}
              loading={generating}
              disabled={generating}
            >
              生成报告
            </Button>
          </Space>
        </Space>
      </Card>

      {/* ── 进度区 ── */}
      {Object.keys(steps).length > 0 && (
        <Card title="查询进度" size="small" style={{ marginBottom: 16 }}>
          <Steps
            direction="vertical"
            size="small"
            current={Object.values(steps).filter(s => s === 'finish').length}
            items={REPORT_SECTIONS.filter(s => selectedSections.includes(s.key)).map(s => ({
              key: s.key,
              title: s.label,
              status: steps[s.key] === 'error' ? 'error' : steps[s.key] === 'finish' ? 'finish' : steps[s.key] === 'process' ? 'process' : 'wait',
              description: steps[s.key] === 'finish' && rowCounts[s.key] !== undefined
                ? `共 ${rowCounts[s.key]} 条数据`
                : steps[s.key] === 'error' ? '查询失败'
                : steps[s.key] === 'process' ? '查询中...'
                : '等待中...',
            }))}
          />
        </Card>
      )}

      {/* ── 报告操作按钮（有数据时显示） ── */}
      {Object.keys(sectionRows).length > 0 && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Space>
            <Button
              type="primary"
              icon={<FileAddOutlined />}
              onClick={handleWrite}
              loading={writing}
            >
              写入飞书文档
            </Button>
            <Button
              icon={<CopyOutlined />}
              onClick={handleCopy}
            >
              {copied ? '✓ 已复制' : '复制数据'}
            </Button>
            {docUrl && (
              <Tag color="success" style={{ fontSize: 14 }}>
                <a href={docUrl} target="_blank" rel="noreferrer">📄 查看飞书文档</a>
              </Tag>
            )}
          </Space>
        </Card>
      )}

      {/* ── 报告表格区 ── */}
      {Object.keys(sectionRows).length > 0 && (
        <Collapse
          defaultActiveKey={selectedSections}
          items={selectedSections.map(sk => {
            const rows = sectionRows[sk] || []
            const cols = SECTION_COLUMNS[sk]?.columns || []
            const title = SECTION_COLUMNS[sk]?.title || sk
            const rcount = rowCounts[sk] || rows.length
            return {
              key: sk,
              label: (
                <span>
                  {title}
                  <Tag style={{ marginLeft: 8 }}>{rcount} 条</Tag>
                  <Tag color={steps[sk] === 'error' ? 'error' : 'success'}>
                    {steps[sk] === 'error' ? '失败' : '成功'}
                  </Tag>
                </span>
              ),
              children: steps[sk] === 'error' ? (
                <Alert type="error" message="查询失败" />
              ) : rows.length === 0 ? (
                <Text type="secondary">（无数据）</Text>
              ) : (
                <Table
                  dataSource={rows}
                  columns={cols.map(c => ({
                    key: c.key,
                    title: c.title,
                    dataIndex: c.dataIndex,
                    render: c.render ? c.render : (val: any) => val ?? '-',
                    ellipsis: true,
                  }))}
                  rowKey={(_, i) => `${sk}-${i}`}
                  pagination={false}
                  size="small"
                  scroll={{ x: 'max-content' }}
                />
              ),
            }
          })}
        />
      )}
    </div>
  )
}