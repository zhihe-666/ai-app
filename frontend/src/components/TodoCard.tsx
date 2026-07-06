/**
 * TodoCard — 待办事项卡片
 *
 * 展示单个待办项：描述、DDL、跟进人、不确定标记
 */
import { Card, Tag, Typography, Badge, Flex } from 'antd'
import {
  WarningOutlined,
  CalendarOutlined,
  UserOutlined,
} from '@ant-design/icons'

const { Text } = Typography

interface TodoCardProps {
  id: number
  description: string
  module: string
  ddl: string
  assignee: string
  isUncertain: boolean
  uncertaintyReason: string
}

const MODULE_COLORS: Record<string, string> = {
  '技术类': '#6366f1',
  '运营类': '#f59e0b',
  '其他类': '#6b7280',
}

export default function TodoCard({
  id,
  description,
  module: moduleName,
  ddl,
  assignee,
  isUncertain,
  uncertaintyReason,
}: TodoCardProps) {
  const moduleColor = MODULE_COLORS[moduleName] || '#6366f1'

  return (
    <Card
      size="small"
      style={{
        marginBottom: 8,
        borderLeft: `3px solid ${moduleColor}`,
        opacity: isUncertain ? 0.85 : 1,
      }}
      styles={{
        body: { padding: '10px 14px' },
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div style={{ flex: 1 }}>
          <Flex align="center" gap={6} wrap>
            <Text style={{ fontSize: 13, fontWeight: 500 }}>
              #{id}
            </Text>
            <Tag color={moduleColor} style={{ fontSize: 11, lineHeight: '18px' }}>
              {moduleName}
            </Tag>
            {isUncertain && (
              <Tag color="warning" icon={<WarningOutlined />} style={{ fontSize: 11 }}>
                {uncertaintyReason || '待确认'}
              </Tag>
            )}
          </Flex>
        </div>
      </div>

      <Text style={{
        fontSize: 14,
        lineHeight: 1.6,
        color: isUncertain ? '#d48806' : '#333',
        display: 'block',
        marginBottom: 8,
      }}>
        {isUncertain && <WarningOutlined style={{ marginRight: 4 }} />}
        {description}
      </Text>

      <Flex gap={16} style={{ fontSize: 12, color: '#999' }}>
        {ddl && (
          <span>
            <CalendarOutlined style={{ marginRight: 4 }} />
            DDL: {ddl}
          </span>
        )}
        {assignee && (
          <span>
            <UserOutlined style={{ marginRight: 4 }} />
            @{assignee}
          </span>
        )}
      </Flex>
    </Card>
  )
}