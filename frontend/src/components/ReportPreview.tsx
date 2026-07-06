/**
 * ReportPreview — 报告预览面板
 * 按模块折叠面板展示，支持 Markdown 渲染
 */
import React from 'react'
import { Card, Collapse, Badge, Space, Button, Typography, Empty, Tag } from 'antd'
import {
  FileTextOutlined,
  CopyOutlined,
  CheckOutlined,
  EditOutlined,
  FileAddOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'

const { Text, Title } = Typography

const SECTION_LABELS: Record<string, { label: string; color: string }> = {
  active_rate: { label: '试点人员活跃率', color: '#6366f1' },
  inactive: { label: '不活跃人员名单', color: '#d97706' },
  skills: { label: 'Skills 技能列表', color: '#059669' },
  tl_usage: { label: 'TL 使用情况', color: '#0891b2' },
}

interface SectionData {
  section: string
  title: string
  row_count: number
  markdown: string
  status: 'complete' | 'error'
  errorMessage?: string
}

interface ReportPreviewProps {
  sections: SectionData[]
  fullMarkdown: string
  onWriteToFeishu: () => void
  onCopyMarkdown: () => void
  writing?: boolean
  copied?: boolean
}

export default function ReportPreview({
  sections,
  fullMarkdown,
  onWriteToFeishu,
  onCopyMarkdown,
  writing = false,
  copied = false,
}: ReportPreviewProps) {
  if (!fullMarkdown) {
    return null
  }

  const collapseItems = sections
    .filter(s => s.status === 'complete')
    .map(s => ({
      key: s.section,
      label: (
        <Space>
          <Badge
            count={s.row_count}
            style={{
              backgroundColor: SECTION_LABELS[s.section]?.color || '#6366f1',
              fontSize: 11,
            }}
            overflowCount={999}
          />
          <Text strong>{s.title}</Text>
          {s.status === 'error' && <Tag color="red">失败</Tag>}
        </Space>
      ),
      children: (
        <div className="markdown-body" style={{ fontSize: 14, lineHeight: 1.7 }}>
          <ReactMarkdown>{s.markdown}</ReactMarkdown>
        </div>
      ),
    }))

  return (
    <Card
      title={
        <Space>
          <FileTextOutlined />
          <span>报告预览</span>
          {sections.filter(s => s.status === 'complete').length > 0 && (
            <Text type="secondary" style={{ fontSize: 13 }}>
              {sections.filter(s => s.status === 'complete').length} / {sections.length} 模块完成
            </Text>
          )}
        </Space>
      }
      extra={
        <Space>
          <Button
            icon={copied ? <CheckOutlined /> : <CopyOutlined />}
            onClick={onCopyMarkdown}
            disabled={!fullMarkdown}
          >
            {copied ? '已复制' : '复制 Markdown'}
          </Button>
          <Button
            type="primary"
            icon={<FileAddOutlined />}
            onClick={onWriteToFeishu}
            loading={writing}
            disabled={!fullMarkdown}
          >
            写入飞书文档
          </Button>
        </Space>
      }
      style={{ marginTop: 24 }}
    >
      {sections.filter(s => s.status === 'complete').length === 0 ? (
        <Empty description="暂无模块完成" />
      ) : (
        <Collapse
          items={collapseItems}
          defaultActiveKey={sections.filter(s => s.status === 'complete').map(s => s.section)}
          style={{ background: 'transparent' }}
        />
      )}
    </Card>
  )
}