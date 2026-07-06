/**
 * TranscriptPanel — 逐字稿展示面板
 *
 * 左侧面板：展示会议信息 + 逐字稿内容
 * 支持折叠、滚动查看
 */
import { Typography, Card, Tag, Flex, Collapse } from 'antd'
import {
  ClockCircleOutlined,
  LinkOutlined,
  FileTextOutlined,
} from '@ant-design/icons'

const { Text, Paragraph } = Typography

interface MeetingInfo {
  title: string
  time: string
  minutes_link: string
  minute_token: string
}

interface TranscriptPanelProps {
  meetingInfo: MeetingInfo | null
  content: string
  loading: boolean
}

export default function TranscriptPanel({
  meetingInfo,
  content,
  loading,
}: TranscriptPanelProps) {
  if (!meetingInfo) return null

  return (
    <Card
      title={
        <Flex align="center" gap={8}>
          <FileTextOutlined />
          <span>逐字稿</span>
          {loading && <Tag color="processing">加载中...</Tag>}
        </Flex>
      }
      size="small"
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{ flex: 1, overflow: 'auto', padding: 12 }}
    >
      {/* Meeting Info */}
      <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f9fafb', borderRadius: 6 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>
          {meetingInfo.title}
        </div>
        <Flex gap={16} wrap>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <ClockCircleOutlined /> {meetingInfo.time}
          </Text>
          <a
            href={meetingInfo.minutes_link}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 12 }}
          >
            <LinkOutlined /> 打开妙记
          </a>
        </Flex>
      </div>

      {/* Transcript Content */}
      {loading ? (
        <div style={{ padding: '24px 0', textAlign: 'center' }}>
          <Text type="secondary">正在提取逐字稿...</Text>
        </div>
      ) : (
        <div
          style={{
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontSize: 13,
            lineHeight: 1.8,
            color: '#333',
            fontFamily: "'SF Mono', 'Monaco', 'Menlo', 'Consolas', monospace",
          }}
        >
          {content}
        </div>
      )}
    </Card>
  )
}