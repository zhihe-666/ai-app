/**
 * KbManage — 知识库管理页面
 *
 * 4 个 Tab：概览 / 浏览 / 导入 / 同步
 * 全部 API 代理到无矩2.0 :8000 微服务
 */
import React, { useState, useCallback, useEffect, useRef } from 'react'
import {
  Typography, Card, Tabs, Table, Statistic, Row as AntRow, Col,
  Select, Input, Button, Space, Tag, Empty, Spin, Alert,
  message, Drawer, Modal, Upload, Switch, Descriptions, Divider,
} from 'antd'
import {
  DatabaseOutlined, FileSearchOutlined, CloudUploadOutlined,
  SyncOutlined, DeleteOutlined, EyeOutlined, FileAddOutlined,
  UploadOutlined, LinkOutlined,
} from '@ant-design/icons'
import type { Collection, BrowseDoc, DocDetail, BrowseResponse } from '../api/kbManage'
import {
  getCollections, browseCollection, getDocument, importText, importFile,
  deleteDocument, triggerSync, getSyncStatus, getSqliteTables,
} from '../api/kbManage'

const { Title, Text } = Typography
const { Dragger } = Upload
const { TextArea } = Input

// ── Collection 类型色码 ─────────────────────────────────────────
const TYPE_COLORS: Record<string, string> = {
  auto_generated: 'purple',
  user_imported: 'blue',
}

// ── 浏览表格列（auto_generated）───────────────────────────────
const BROWSE_COLUMNS = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 160, ellipsis: true },
  {
    title: '预览', dataIndex: 'preview', key: 'preview', ellipsis: true,
    render: (v: string) => v || '-',
  },
  {
    title: '元数据', dataIndex: 'metadata', key: 'metadata', ellipsis: true,
    render: (v: any) => v ? JSON.stringify(v) : '-',
  },
]

// ── 浏览表格列（manual_kb / user_imported）───────────────────
const BROWSE_MANUAL_COLUMNS = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 160, ellipsis: true },
  { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
  { title: '文件名', dataIndex: 'file_name', key: 'file_name', ellipsis: true },
  { title: '格式', dataIndex: 'file_format', key: 'file_format', width: 80 },
  { title: '导入时间', dataIndex: 'imported_at', key: 'imported_at', width: 170 },
  {
    title: '预览', dataIndex: 'preview', key: 'preview', ellipsis: true,
    render: (v: string) => v || '-',
  },
]

export default function KbManage() {
  const [activeTab, setActiveTab] = useState('overview')

  // ── Tab 1: 概览 ──
  const [collections, setCollections] = useState<Collection[]>([])
  const [totalDocs, setTotalDocs] = useState(0)
  const [syncInfo, setSyncInfo] = useState<{ last_sync: string; status: string } | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(false)
  const [overviewError, setOverviewError] = useState<string | null>(null)

  // ── Tab 2: 浏览 ──
  const [browseCollectionName, setBrowseCollectionName] = useState('manual_kb')
  const [browseKeyword, setBrowseKeyword] = useState('')
  const [browsePage, setBrowsePage] = useState(1)
  const [browseData, setBrowseData] = useState<BrowseResponse | null>(null)
  const [loadingBrowse, setLoadingBrowse] = useState(false)
  const [browseError, setBrowseError] = useState<string | null>(null)
  const [drawerDoc, setDrawerDoc] = useState<DocDetail | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerLoading, setDrawerLoading] = useState(false)

  // ── Tab 3: 导入 ──
  const [textTitle, setTextTitle] = useState('')
  const [textContent, setTextContent] = useState('')
  const [textMeta, setTextMeta] = useState('')
  const [importingText, setImportingText] = useState(false)
  const [fileList, setFileList] = useState<any[]>([])
  const [fileTitle, setFileTitle] = useState('')
  const [fileMeta, setFileMeta] = useState('')
  const [importingFile, setImportingFile] = useState(false)

  // ── Tab 4: 同步 ──
  const SYNC_MODES = [
    { key: 'code', label: '仅代码同步', time: '~45s', dryRun: false, rebuildCore: false, rebuildWiki: false },
    { key: 'core', label: '代码 + 核心KB', time: '~3min', dryRun: false, rebuildCore: true, rebuildWiki: false },
    { key: 'wiki', label: '代码 + Wiki', time: '~5min', dryRun: false, rebuildCore: false, rebuildWiki: true },
    { key: 'full', label: '全量更新', time: '~8min', dryRun: false, rebuildCore: true, rebuildWiki: true },
  ]
  const [syncMode, setSyncMode] = useState('code')
  const [syncing, setSyncing] = useState(false)
  const [syncTaskId, setSyncTaskId] = useState<number | null>(null)
  const [syncResult, setSyncResult] = useState<string | null>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── 知识库组成说明 ──
  const KB_COMPOSITION = [
    { data: 'code_method', update: '增量同步', switch: '默认（无开关）' },
    { data: 'code_class', update: '增量同步', switch: '默认（无开关）' },
    { data: 'tech_kb', update: '全量重建', switch: 'rebuild_core' },
    { data: 'ops_kb', update: '全量重建', switch: 'rebuild_core' },
    { data: 'business_kb', update: '全量重建', switch: 'rebuild_core' },
    { data: 'wiki_kb', update: '全量重编', switch: 'rebuild_wiki' },
    { data: 'manual_kb', update: '手动导入', switch: '不参与同步' },
  ]

  // ── 加载概览数据 ──
  const loadOverview = useCallback(async () => {
    setLoadingOverview(true)
    setOverviewError(null)
    try {
      const data = await getCollections()
      setCollections(data.collections || [])
      setTotalDocs(data.total_docs || 0)
      setSyncInfo(data.sync_status || null)
    } catch (err: any) {
      const msg = err?.response?.data?.error || err?.message || '获取知识库概览失败'
      setOverviewError(msg)
    } finally {
      setLoadingOverview(false)
    }
  }, [])

  useEffect(() => { if (activeTab === 'overview') loadOverview() }, [activeTab, loadOverview])

  // ── Tab 切换时加载 ──
  useEffect(() => {
    if (activeTab === 'browse' && !browseData) loadBrowse()
  }, [activeTab])

  // ── 浏览数据加载 ──
  const loadBrowse = useCallback(async (page = browsePage) => {
    if (!browseCollectionName) return
    setLoadingBrowse(true)
    setBrowseError(null)
    try {
      const data = await browseCollection(browseCollectionName, page, 20, browseKeyword)
      setBrowseData(data)
      setBrowsePage(data.page)
    } catch (err: any) {
      const msg = err?.response?.data?.error || err?.message || '浏览失败'
      setBrowseError(msg)
    } finally {
      setLoadingBrowse(false)
    }
  }, [browseCollectionName, browseKeyword, browsePage])

  const handleBrowseSearch = useCallback(() => {
    setBrowsePage(1)
    loadBrowse(1)
  }, [loadBrowse])

  // ── 查看文档全文 ──
  const handleViewDoc = useCallback(async (docId: string) => {
    setDrawerLoading(true)
    setDrawerOpen(true)
    try {
      const doc = await getDocument(browseCollectionName, docId)
      setDrawerDoc(doc)
    } catch (err: any) {
      message.error(err?.response?.data?.error || err?.message || '获取文档失败')
      setDrawerOpen(false)
    } finally {
      setDrawerLoading(false)
    }
  }, [browseCollectionName])

  // ── 删除文档 ──
  const handleDeleteDoc = useCallback((docId: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '删除后不可恢复。ChromaDB 向量和 SQLite 记录将同时清理。',
      okText: '确认删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDocument(browseCollectionName, docId)
          message.success('文档已删除')
          loadBrowse()
        } catch (err: any) {
          message.error(err?.response?.data?.error || err?.message || '删除失败')
        }
      },
    })
  }, [browseCollectionName, loadBrowse])

  // ── 导入文本 ──
  const handleImportText = useCallback(async () => {
    if (!textTitle.trim() || !textContent.trim()) {
      message.warning('请填写标题和内容')
      return
    }
    setImportingText(true)
    try {
      let metadata: Record<string, any> | undefined
      if (textMeta.trim()) {
        try { metadata = JSON.parse(textMeta.trim()) } catch { message.warning('元数据格式不正确，需为 JSON') }
      }
      const result = await importText(textTitle.trim(), textContent.trim(), metadata)
      message.success(`导入成功！共 ${result.chunks} 个段落`)
      setTextTitle('')
      setTextContent('')
      setTextMeta('')
      loadOverview()
    } catch (err: any) {
      message.error(err?.response?.data?.error || err?.message || '导入失败')
    } finally {
      setImportingText(false)
    }
  }, [textTitle, textContent, textMeta, loadOverview])

  // ── 导入文件 ──
  const handleImportFile = useCallback(async () => {
    if (fileList.length === 0) {
      message.warning('请先选择文件')
      return
    }
    setImportingFile(true)
    try {
      const file = fileList[0].originFileObj || fileList[0]
      const result = await importFile(file, fileTitle.trim() || undefined, fileMeta.trim() || undefined)
      message.success(`导入成功！共 ${result.chunks} 个段落`)
      setFileList([])
      setFileTitle('')
      setFileMeta('')
      loadOverview()
    } catch (err: any) {
      message.error(err?.response?.data?.error || err?.message || '导入失败')
    } finally {
      setImportingFile(false)
    }
  }, [fileList, fileTitle, fileMeta, loadOverview])

  // ── 触发同步 ──
  const handleSync = useCallback(async (asDryRun: boolean) => {
    const mode = SYNC_MODES.find(m => m.key === syncMode)!
    setSyncing(true)
    setSyncTaskId(null)
    setSyncResult(null)
    try {
      const result = await triggerSync(asDryRun, mode.rebuildCore, mode.rebuildWiki)
      setSyncTaskId(result.task_id)
      message.success(`${asDryRun ? '差异预览' : '同步'}任务已启动（ID: ${result.task_id}）`)
    } catch (err: any) {
      message.error(err?.response?.data?.error || err?.message || '触发失败')
      setSyncing(false)
    }
  }, [syncMode])

  // ── 轮询状态 → 进度文本 ──
  const syncProgressText = (status: any): string => {
    if (!status) return ''
    if (status.status === 'success' || status.status === 'failed') return '处理完成'
    // 根据后端 result_summary 或 status 推断进度
    const s = (status.result_summary || '').toLowerCase()
    if (s.includes('rebuild_core')) return '重建核心 KB 中…'
    if (s.includes('rebuild_wiki') || s.includes('wiki')) return '重编 Wiki 中…'
    return '代码同步中…'
  }

  // ── 轮询同步状态 ──
  useEffect(() => {
    if (!syncTaskId) return
    setSyncing(true)
    let attempts = 0
    const poll = async () => {
      attempts++
      try {
        const status = await getSyncStatus(syncTaskId)
        if (status.status !== 'running') {
          setSyncResult(status.result_summary || `状态: ${status.status}`)
          setSyncing(false)
          setSyncTaskId(null)
          if (pollingRef.current) clearInterval(pollingRef.current)
        }
      } catch {
        if (attempts >= 20) {
          setSyncResult('轮询超时，请手动刷新')
          setSyncing(false)
          setSyncTaskId(null)
          if (pollingRef.current) clearInterval(pollingRef.current)
        }
      }
    }
    pollingRef.current = setInterval(poll, 3000)
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [syncTaskId])

  // ── 清理轮询 ──
  useEffect(() => () => { if (pollingRef.current) clearInterval(pollingRef.current) }, [])

  // ── 浏览表格数据 ──
  const isManualKb = browseCollectionName === 'manual_kb'
  const browseColumns = isManualKb ? BROWSE_MANUAL_COLUMNS : BROWSE_COLUMNS
  const browseTableData = browseData?.docs?.map((d, i) => ({ ...d, key: `doc-${i}` })) || []

  return (
    <div style={{ padding: 24, height: '100vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          <DatabaseOutlined /> 知识库管理
        </Title>
        <Text type="secondary">管理无矩2.0 知识库集合、文档导入和代码同步</Text>
      </div>

      {/* 主体 */}
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} type="card" items={[
          // ── Tab 1: 概览 ──
          {
            key: 'overview',
            label: <span><DatabaseOutlined /> 知识库概览</span>,
            children: (
              <div>
                {overviewError && (
                  <Alert type="error" message={overviewError} closable showIcon style={{ marginBottom: 12 }}
                    onClose={() => setOverviewError(null)} />
                )}

                {/* 统计卡片 */}
                {!loadingOverview && collections.length > 0 && (
                  <AntRow gutter={12} style={{ marginBottom: 12 }}>
                    <Col span={6}>
                      <Card size="small">
                        <Statistic title="文档总数" value={totalDocs} suffix="篇" valueStyle={{ fontSize: 22 }} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card size="small">
                        <Statistic title="知识库数" value={collections.length} suffix="个" valueStyle={{ fontSize: 22 }} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card size="small">
                        <Statistic title="最后同步" value={syncInfo?.last_sync || '-'} valueStyle={{ fontSize: 14 }} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card size="small">
                        <Statistic title="同步状态" value={syncInfo?.status || '-'}
                          valueStyle={{ fontSize: 14, color: syncInfo?.status === 'success' ? '#22c55e' : '#ef4444' }} />
                      </Card>
                    </Col>
                  </AntRow>
                )}

                {/* 数据表 */}
                <Card size="small" title="Collection 列表" extra={
                  <Button size="small" icon={<SyncOutlined />} onClick={loadOverview} loading={loadingOverview}>刷新</Button>
                }>
                  {loadingOverview ? (
                    <div style={{ textAlign: 'center', padding: 40 }}><Spin /><div style={{ marginTop: 8 }}>加载中...</div></div>
                  ) : collections.length === 0 ? (
                    <Empty description="暂无知识库数据" />
                  ) : (
                    <Table
                      dataSource={collections.map((c, i) => ({ ...c, key: `col-${i}` }))}
                      columns={[
                        {
                          title: '名称', dataIndex: 'name', key: 'name',
                          render: (v: string) => (
                            <a onClick={() => { setBrowseCollectionName(v); setActiveTab('browse') }} style={{ cursor: 'pointer' }}>
                              {v}
                            </a>
                          ),
                        },
                        { title: '类型', dataIndex: 'type', key: 'type', render: (v: string) => <Tag color={TYPE_COLORS[v] || 'default'}>{v}</Tag> },
                        { title: '文档数', dataIndex: 'count', key: 'count', width: 100, align: 'right' as const },
                        { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
                      ]}
                      pagination={false} size="small" bordered
                    />
                  )}
                </Card>
              </div>
            ),
          },

          // ── Tab 2: 浏览 ──
          {
            key: 'browse',
            label: <span><FileSearchOutlined /> 浏览集合</span>,
            children: (
              <div>
                {/* 控制栏 */}
                <Card size="small" style={{ marginBottom: 12 }}>
                  <Space wrap>
                    <Text strong>Collection:</Text>
                    <Select value={browseCollectionName} onChange={v => { setBrowseCollectionName(v); setBrowseData(null) }}
                      style={{ width: 180 }} options={collections.map(c => ({ label: c.name, value: c.name }))} />
                    <Input placeholder="关键词搜索" value={browseKeyword}
                      onChange={e => setBrowseKeyword(e.target.value)} style={{ width: 200 }}
                      onPressEnter={handleBrowseSearch} />
                    <Button type="primary" icon={<FileSearchOutlined />} onClick={handleBrowseSearch}
                      loading={loadingBrowse} style={{ background: '#6366f1', borderColor: '#6366f1' }}>
                      搜索
                    </Button>
                    <Button icon={<SyncOutlined />} onClick={() => loadBrowse()} size="small">刷新</Button>
                  </Space>
                </Card>

                {browseError && (
                  <Alert type="error" message={browseError} closable showIcon style={{ marginBottom: 12 }}
                    onClose={() => setBrowseError(null)} />
                )}

                {/* 文档列表 */}
                {browseData && (
                  <Card size="small" title={`${browseCollectionName} - 共 ${browseData.total} 条`}>
                    <Table
                      dataSource={browseTableData}
                      columns={[
                        ...browseColumns,
                        {
                          title: '操作', key: 'action', width: 150,
                          render: (_: any, record: any) => (
                            <Space>
                              <Button type="link" size="small" icon={<EyeOutlined />}
                                onClick={() => handleViewDoc(record.id)}>查看</Button>
                              <Button type="link" size="small" danger icon={<DeleteOutlined />}
                                onClick={() => handleDeleteDoc(record.id)}>删除</Button>
                            </Space>
                          ),
                        },
                      ]}
                      pagination={{
                        current: browseData.page,
                        pageSize: browseData.page_size,
                        total: browseData.total,
                        onChange: p => loadBrowse(p),
                        showSizeChanger: false,
                      }}
                      size="small" bordered
                      loading={loadingBrowse}
                    />
                  </Card>
                )}
              </div>
            ),
          },

          // ── Tab 3: 导入 ──
          {
            key: 'import',
            label: <span><CloudUploadOutlined /> 导入文档</span>,
            children: (
              <AntRow gutter={16}>
                {/* 文本导入 */}
                <Col span={12}>
                  <Card size="small" title={<><FileAddOutlined /> 文本导入</>}>
                    <Space direction="vertical" style={{ width: '100%' }} size="small">
                      <Input placeholder="文档标题" value={textTitle} onChange={e => setTextTitle(e.target.value)} />
                      <TextArea rows={8} placeholder="Markdown 或纯文本内容（自动按 ## 标题切分段落）"
                        value={textContent} onChange={e => setTextContent(e.target.value)} />
                      <Input placeholder='元数据（可选，JSON 格式如 {"author":"张三"}）'
                        value={textMeta} onChange={e => setTextMeta(e.target.value)} />
                      <Button type="primary" icon={<CloudUploadOutlined />} onClick={handleImportText}
                        loading={importingText} style={{ background: '#6366f1', borderColor: '#6366f1' }}>
                        导入文本
                      </Button>
                    </Space>
                  </Card>
                </Col>

                {/* 文件导入 */}
                <Col span={12}>
                  <Card size="small" title={<><UploadOutlined /> 文件上传</>}>
                    <Space direction="vertical" style={{ width: '100%' }} size="small">
                      <Input placeholder="文档标题（可选，默认使用文件名）" value={fileTitle}
                        onChange={e => setFileTitle(e.target.value)} />
                      <Input placeholder='元数据（可选，JSON 字符串）' value={fileMeta}
                        onChange={e => setFileMeta(e.target.value)} />
                      <Dragger
                        multiple={false}
                        accept=".pdf,.docx,.doc,.md,.markdown,.txt,.xlsx,.pptx"
                        fileList={fileList}
                        onChange={info => setFileList(info.fileList.slice(-1))}
                        beforeUpload={() => false}
                        showUploadList={true}
                        style={{ background: '#fafafa' }}
                      >
                        <p className="ant-upload-drag-icon"><UploadOutlined /></p>
                        <p className="ant-upload-text">点击或拖拽文件到此区域</p>
                        <p className="ant-upload-hint">支持 PDF / Word / Markdown / TXT / Excel / PPT</p>
                      </Dragger>
                      <Button type="primary" icon={<CloudUploadOutlined />} onClick={handleImportFile}
                        loading={importingFile} style={{ background: '#6366f1', borderColor: '#6366f1' }}>
                        上传导入
                      </Button>
                    </Space>
                  </Card>
                </Col>
              </AntRow>
            ),
          },

          // ── Tab 4: 同步 ──
          {
            key: 'sync',
            label: <span><SyncOutlined /> 代码同步</span>,
            children: (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {/* 模式选择 + 操作 */}
                <Card size="small">
                  <Space direction="vertical" style={{ width: '100%' }} size="middle">
                    <Text strong><SyncOutlined /> 同步模式</Text>
                    {SYNC_MODES.map(m => (
                      <div key={m.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input type="radio" name="syncMode" checked={syncMode === m.key}
                          onChange={() => setSyncMode(m.key)}
                          style={{ accentColor: '#6366f1', width: 16, height: 16 }} />
                        <Text>{m.label}</Text>
                        <Tag>{m.time}</Tag>
                      </div>
                    ))}
                    <div style={{ display: 'flex', gap: 8, paddingTop: 4 }}>
                      <Button type="primary" icon={<SyncOutlined />} onClick={() => handleSync(false)}
                        loading={syncing && !syncTaskId}
                        style={{ background: '#6366f1', borderColor: '#6366f1' }}>
                        执行{syncTaskId ? '中' : '同步'}
                      </Button>
                      <Button icon={<FileSearchOutlined />} onClick={() => handleSync(true)}>
                        dry-run 预览差异
                      </Button>
                      {syncTaskId && <Text code>任务 ID: {syncTaskId}</Text>}
                    </div>
                  </Space>
                </Card>

                {/* 进度 + 结果 */}
                {syncTaskId && syncing && (
                  <Card size="small">
                    <Space><Spin /><Text>执行中，每 3s 轮询…</Text></Space>
                  </Card>
                )}
                {syncResult && (
                  <Card size="small" title="同步结果">
                    <Descriptions column={1} size="small">
                      <Descriptions.Item label="摘要">{syncResult}</Descriptions.Item>
                    </Descriptions>
                    <Space style={{ marginTop: 8 }}>
                      <Button icon={<SyncOutlined />} onClick={() => { setSyncResult(null); loadOverview() }}>
                        刷新概览
                      </Button>
                    </Space>
                  </Card>
                )}

                {/* 知识库组成说明 */}
                <Card size="small" title={<><LinkOutlined /> 知识库组成说明</>}>
                  <Table
                    dataSource={KB_COMPOSITION.map((r, i) => ({ ...r, key: `kb-${i}` }))}
                    columns={[
                      { title: '数据', dataIndex: 'data', key: 'data' },
                      { title: '更新方式', dataIndex: 'update', key: 'update' },
                      { title: '新增开关', dataIndex: 'switch', key: 'switch' },
                    ]}
                    pagination={false} size="small" bordered
                  />
                </Card>
              </div>
            ),
          },
        ]} />
      </div>

      {/* ── 文档全文 Drawer ── */}
      <Drawer
        title={drawerDoc?.metadata?.title || '文档全文'}
        placement="right"
        width={640}
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setDrawerDoc(null) }}
        loading={drawerLoading}
      >
        {drawerDoc && (
          <div>
            {drawerDoc.metadata && Object.keys(drawerDoc.metadata).length > 0 && (
              <>
                <Descriptions column={1} size="small" bordered>
                  {Object.entries(drawerDoc.metadata).map(([k, v]) => (
                    <Descriptions.Item key={k} label={k}>{String(v)}</Descriptions.Item>
                  ))}
                </Descriptions>
                <Divider />
              </>
            )}
            <pre style={{
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              background: '#f8fafc', padding: 16, borderRadius: 8,
              fontSize: 13, lineHeight: 1.6, maxHeight: 500, overflow: 'auto',
            }}>
              {drawerDoc.content}
            </pre>
          </div>
        )}
      </Drawer>
    </div>
  )
}