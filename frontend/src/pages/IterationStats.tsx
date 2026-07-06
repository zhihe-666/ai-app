import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import {
  Typography,
  Card,
  Upload,
  Button,
  Select,
  Space,
  Alert,
  Table,
  Tag,
  Empty,
  Spin,
  message,
  Statistic,
  Row as AntRow,
  Col,
  Divider,
  Modal,
  Input,
  Tabs,
} from 'antd'
import {
  UploadOutlined,
  CloudUploadOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { uploadStats, writeBitable, exportStatsXlsx, normalizeRows, computeSummary, computeRawSummary, type StatsRow, type UploadResult } from '../api/iterationStats'

const { Title, Text } = Typography
const { Dragger } = Upload

/** 占位行的样式 */
const ratioRender = (val: string) => {
  const num = parseFloat(val)
  if (isNaN(num)) return <Tag>{val}</Tag>
  if (num >= 80) return <Tag color="green">{val}</Tag>
  if (num >= 50) return <Tag color="orange">{val}</Tag>
  return <Tag color="red">{val}</Tag>
}

/** 统计表格列定义 */
const STATS_COLUMNS = [
  {
    title: '项目名称',
    dataIndex: 'project',
    key: 'project',
    fixed: 'left' as const,
    width: 200,
    render: (_: string, record: StatsRow) =>
      record.project_link ? (
        <a href={record.project_link} target="_blank" rel="noopener noreferrer">
          {record.project}
        </a>
      ) : (
        <Text strong>{record.project}</Text>
      ),
  },
  { title: 'TL', dataIndex: 'tl', key: 'tl', width: 140 },
  {
    title: '总需求数【完全排期】',
    dataIndex: 'total',
    key: 'total',
    width: 120,
    align: 'right' as const,
    render: (v: number) => (v !== undefined ? v.toLocaleString() : '-'),
  },
  {
    title: '算法工程需求',
    dataIndex: 'engineering',
    key: 'engineering',
    width: 110,
    align: 'right' as const,
    render: (v: number) => v.toLocaleString(),
  },
  {
    title: 'AIcoding需求数',
    dataIndex: 'aicoding',
    key: 'aicoding',
    width: 110,
    align: 'right' as const,
    render: (v: number) => v.toLocaleString(),
  },
  {
    title: 'AICoding占比',
    dataIndex: 'aicoding_ratio',
    key: 'aicoding_ratio',
    width: 110,
    align: 'right' as const,
    render: (v: string) => ratioRender(v),
  },
  {
    title: 'SDD需求数',
    dataIndex: 'sdd',
    key: 'sdd',
    width: 100,
    align: 'right' as const,
    render: (v: number) => v.toLocaleString(),
  },
  {
    title: 'SDD占比',
    dataIndex: 'sdd_ratio',
    key: 'sdd_ratio',
    width: 100,
    align: 'right' as const,
    render: (v: string) => ratioRender(v),
  },
  {
    title: '端到端需求数',
    dataIndex: 'e2e',
    key: 'e2e',
    width: 110,
    align: 'right' as const,
    render: (v: number) => v.toLocaleString(),
  },
]

export default function IterationStats() {
  const [loading, setLoading] = useState(false)
  const [version, setVersion] = useState('5.94')
  const [fileList, setFileList] = useState<any[]>([])
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [writing, setWriting] = useState(false)
  const [writeResult, setWriteResult] = useState<{ success: boolean; count: number; errors: string[] } | null>(null)

  /** 本地归一化后的展示行 */
  const displayRows = useMemo(() => (result ? normalizeRows(result.rows) : []), [result])
  /** 本地计算的汇总行 */
  const summaryRow = useMemo(() => (displayRows.length > 0 ? computeSummary(displayRows) : null), [displayRows])

  /** 上传文件列表变化 */
  const handleFileChange = useCallback((info: any) => {
    setFileList(info.fileList.slice(-20)) // 最多 20 个文件
    setError(null)
    setWriteResult(null)
  }, [])

  /** 开始统计 */
  const handleStart = useCallback(async () => {
    if (fileList.length === 0) {
      message.warning('请先上传 xlsx 文件')
      return
    }
    if (!version.trim()) {
      message.warning('请输入迭代版本号')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)
    setWriteResult(null)

    try {
      const files = fileList.map((f: any) => f.originFileObj)
      const data = await uploadStats(files, version.trim())
      setResult(data)
      message.success(`统计完成，共 ${data.rows.length} 个项目`)
    } catch (err: any) {
      const msg = err?.response?.data?.error || err?.message || '统计失败，请检查文件格式'
      setError(msg)
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }, [fileList, version])

  /** 写入飞书多维表格 */
  const handleWriteBitable = useCallback(async () => {
    if (!result || result.rows.length === 0) {
      message.warning('请先完成统计')
      return
    }

    setWriting(true)
    setWriteResult(null)

    try {
      // 追加合计行（bitable 中也尝试匹配"合计"记录）
      const rowsWithSummary = [...result.rows, computeRawSummary(result.rows)]
      const res = await writeBitable(result.version, rowsWithSummary)
      setWriteResult({
        success: res.success,
        count: res.updated_count,
        errors: res.errors,
      })
      if (res.success) {
        message.success(`成功更新 ${res.updated_count} 条记录`)
      } else {
        message.warning(`更新完成，但有 ${res.errors.length} 个错误`)
      }
    } catch (err: any) {
      const msg = err?.response?.data?.error || err?.message || '写入失败'
      message.error(msg)
      setWriteResult({ success: false, count: 0, errors: [msg] })
    } finally {
      setWriting(false)
    }
  }, [result])

  /** 导出 xlsx */
  const handleExport = useCallback(async () => {
    if (!result || result.rows.length === 0) {
      message.warning('请先完成统计')
      return
    }

    try {
      const rowsWithSummary = [...result.rows, computeRawSummary(result.rows)]
      const blob = await exportStatsXlsx(rowsWithSummary, result.version)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `迭代统计_${result.version || 'unknown'}.xlsx`
      a.click()
      window.URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (err: any) {
      message.error(err?.message || '导出失败')
    }
  }, [result])

  /** 重置 */
  const handleReset = useCallback(() => {
    setResult(null)
    setError(null)
    setWriteResult(null)
    setFileList([])
  }, [])

  const resultRef = useRef<HTMLDivElement>(null)

  /** 统计完成后自动滚动到结果区域 */
  useEffect(() => {
    if (result && resultRef.current) {
      resultRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [result])

  /** 表格数据 — 普通行 + 汇总行 */
  const tableData = displayRows.length > 0 && summaryRow
    ? [
        ...displayRows.map((r, i) => ({ ...r, key: `row-${i}` })),
        { ...summaryRow, project: '合计', key: 'summary', project_link: '' },
      ]
    : []

  return (
    <div style={{ padding: 24, height: '100vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          迭代数据统计
        </Title>
        <Text type="secondary">
          上传 RDC 导出的 xlsx 文件，自动统计各项目的工程/AIcoding/SDD 数据
        </Text>
      </div>

      {/* 上传 & 配置区 — 紧凑版 */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Text strong style={{ whiteSpace: 'nowrap' }}>迭代版本</Text>
          <Input
            placeholder="例如 5.94"
            value={version}
            onChange={e => setVersion(e.target.value)}
            style={{ width: 120 }}
            size="small"
          />
          <Dragger
            multiple
            accept=".xlsx,.xls"
            fileList={fileList}
            onChange={handleFileChange}
            beforeUpload={() => false}
            showUploadList={false}
            style={{
              background: '#fafafa',
              flex: 1,
              minWidth: 160,
              height: 48,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <UploadOutlined style={{ fontSize: 18, color: '#999' }} />
              <span style={{ color: '#666', fontSize: 13 }}>
                {fileList.length > 0
                  ? `已选 ${fileList.length} 个文件`
                  : '点击或拖拽 xlsx 文件（支持多个）'}
              </span>
            </div>
          </Dragger>
          <Space size={4}>
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              loading={loading}
              onClick={handleStart}
              size="small"
              style={{ background: '#6366f1', borderColor: '#6366f1' }}
            >
              统计
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleReset} size="small">
              重置
            </Button>
          </Space>
        </div>
        {/* 已选文件列表 — 紧凑 Tag 行 */}
        {fileList.length > 0 && (
          <div style={{ marginTop: 6, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {fileList.map((f, i) => (
              <Tag key={i} closable onClose={() => {
                const newList = [...fileList]
                newList.splice(i, 1)
                setFileList(newList)
              }}>
                {f.name || `文件 ${i + 1}`}
              </Tag>
            ))}
          </div>
        )}
      </Card>

      {/* 错误提示 */}
      {error && (
        <Alert
          type="error"
          message="统计出错"
          description={error}
          closable
          showIcon
          style={{ marginBottom: 8 }}
          onClose={() => setError(null)}
        />
      )}

      {/* 写入结果提示 */}
      {writeResult && (
        <Alert
          type={writeResult.success ? 'success' : 'warning'}
          message={
            writeResult.success
              ? `✅ 成功更新飞书多维表格 — ${writeResult.count} 条记录`
              : `⚠️ 写入完成，但有 ${writeResult.errors.length} 个错误`
          }
          description={
            <div>
              {writeResult.success && (
                <div style={{ marginBottom: 4 }}>
                  <a
                    href="https://poizon.feishu.cn/base/B5exbr9CpafAW9sMEFkcydvvnRg?table=tbllFUFZyqhcUKZP"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    🔗 打开飞书多维表格查看
                  </a>
                </div>
              )}
              {writeResult.errors.length > 0 && (
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {writeResult.errors.map((e, i) => (
                    <li key={i}>{typeof e === 'string' ? e : JSON.stringify(e)}</li>
                  ))}
                </ul>
              )}
            </div>
          }
          closable
          showIcon
          style={{ marginBottom: 8 }}
          onClose={() => setWriteResult(null)}
        />
      )}

      {/* 内容主体区域 — 加载中/结果/空状态 */}
      <div ref={resultRef} style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {loading && (
          <div
            style={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 16,
            }}
          >
            <Spin size="large" />
            <Text type="secondary">正在解析 xlsx 文件并计算统计数据...</Text>
          </div>
        )}

        {!loading && result && (
          <>
            {/* 快速统计卡片 */}
            <AntRow gutter={12} style={{ marginBottom: 12 }}>
              <Col span={4}>
                <Card size="small">
                  <Statistic title="项目数" value={result.rows.length} suffix="个" valueStyle={{ fontSize: 20 }} />
                </Card>
              </Col>
              <Col span={5}>
                <Card size="small">
                  <Statistic
                    title="总需求数"
                    value={summaryRow!.total}
                    suffix={`(工程: ${summaryRow!.engineering})`}
                    valueStyle={{ fontSize: 20 }}
                  />
                </Card>
              </Col>
              <Col span={5}>
                <Card size="small">
                  <Statistic
                    title="AIcoding 需求"
                    value={summaryRow!.aicoding}
                    suffix={`(${summaryRow!.aicoding_ratio})`}
                    valueStyle={{ fontSize: 20 }}
                  />
                </Card>
              </Col>
              <Col span={5}>
                <Card size="small">
                  <Statistic
                    title="SDD 需求"
                    value={summaryRow!.sdd}
                    suffix={`(${summaryRow!.sdd_ratio})`}
                    valueStyle={{ fontSize: 20 }}
                  />
                </Card>
              </Col>
              <Col span={5}>
                <Card size="small">
                  <Statistic title="端到端" value={summaryRow!.e2e} valueStyle={{ fontSize: 20 }} />
                </Card>
              </Col>
            </AntRow>

            {/* 操作按钮区 */}
            <div style={{ marginBottom: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
              <Text type="secondary" style={{ fontSize: 13 }}>
                版本: <Text strong>{result.version}</Text>
              </Text>
              <Button
                type="primary"
                icon={<FileExcelOutlined />}
                onClick={handleWriteBitable}
                loading={writing}
                size="small"
                style={{ background: '#22c55e', borderColor: '#22c55e' }}
              >
                写入飞书多维表格
              </Button>
              <Button icon={<DownloadOutlined />} onClick={handleExport} size="small">
                导出 xlsx
              </Button>
            </div>

            {/* 统计表格 */}
            <div style={{ borderRadius: 8, border: '1px solid #f0f0f0' }}>
              <Table
                dataSource={tableData}
                columns={STATS_COLUMNS}
                pagination={false}
                size="small"
                bordered
                scroll={{ x: 1200, y: 360 }}
                summary={() => (
                  <Table.Summary fixed>
                    <Table.Summary.Row style={{ background: '#f5f5f5', fontWeight: 700 }}>
                      {STATS_COLUMNS.map((col, i) => {
                        const val = summaryRow!
                        let display: any = ''
                        switch (col.dataIndex) {
                          case 'project':
                            display = <Text strong>合计 ({result.version})</Text>
                            break
                          case 'tl':
                            display = ''
                            break
                          case 'total':
                            display = val.total.toLocaleString()
                            break
                          case 'engineering':
                            display = val.engineering.toLocaleString()
                            break
                          case 'aicoding':
                            display = val.aicoding.toLocaleString()
                            break
                          case 'aicoding_ratio':
                            display = ratioRender(val.aicoding_ratio)
                            break
                          case 'sdd':
                            display = val.sdd.toLocaleString()
                            break
                          case 'sdd_ratio':
                            display = ratioRender(val.sdd_ratio)
                            break
                          case 'e2e':
                            display = val.e2e.toLocaleString()
                            break
                        }
                        return <Table.Summary.Cell key={i} index={i}>{display}</Table.Summary.Cell>
                      })}
                    </Table.Summary.Row>
                  </Table.Summary>
                )}
              />
            </div>
          </>
        )}

        {!loading && !result && !error && (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={'上传 xlsx 文件后点击"开始统计"'}
            />
          </div>
        )}
      </div>
    </div>
  )
}