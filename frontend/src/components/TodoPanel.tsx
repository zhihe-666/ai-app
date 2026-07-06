/**
 * TodoPanel — 待办事项展示与编辑面板
 *
 * 右侧面板：展示 AI 提取的待办事项 + 模块分组
 * 支持编辑 + 确认后生成飞书文档
 */
import { useState } from 'react'
import {
  Typography,
  Card,
  Tag,
  Flex,
  Button,
  Empty,
  Tooltip,
  Modal,
  Input,
  Select,
  Space,
  message,
} from 'antd'
import {
  CheckCircleOutlined,
  WarningOutlined,
  EditOutlined,
  FileTextOutlined,
  PlusOutlined,
  DeleteOutlined,
  SaveOutlined,
} from '@ant-design/icons'

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

interface TodoPanelProps {
  meetingInfo: MeetingInfo | null
  moduleGroups: ModuleGroup[]
  loading: boolean
  onGenerateDoc: (info: MeetingInfo, groups: ModuleGroup[]) => Promise<void>
  generating: boolean
}

export default function TodoPanel({
  meetingInfo,
  moduleGroups,
  loading,
  onGenerateDoc,
  generating,
}: TodoPanelProps) {
  const [editingTodo, setEditingTodo] = useState<TodoItem | null>(null)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editDescription, setEditDescription] = useState('')
  const [editDdl, setEditDdl] = useState('')
  const [editAssignee, setEditAssignee] = useState('')
  const [editModule, setEditModule] = useState('')
  const [editUncertain, setEditUncertain] = useState(false)
  const [editUncertainReason, setEditUncertainReason] = useState('')
  const [localGroups, setLocalGroups] = useState<ModuleGroup[]>([])

  // Sync localGroups from props when data arrives
  const hasSynced = localGroups.length > 0 && moduleGroups.length > 0
  const displayGroups = localGroups.length > 0 ? localGroups : moduleGroups

  // Sync when moduleGroups changes
  if (moduleGroups.length > 0 && !hasSynced) {
    setLocalGroups(JSON.parse(JSON.stringify(moduleGroups)))
  }

  const openEditModal = (todo: TodoItem) => {
    setEditingTodo(todo)
    setEditDescription(todo.description)
    setEditDdl(todo.ddl)
    setEditAssignee(todo.assignee)
    setEditModule(todo.module)
    setEditUncertain(todo.is_uncertain)
    setEditUncertainReason(todo.uncertainty_reason)
    setEditModalOpen(true)
  }

  const saveEdit = () => {
    if (!editingTodo) return

    setLocalGroups(prev => prev.map(mg => ({
      ...mg,
      todos: mg.todos.map(t => t.id === editingTodo.id ? {
        ...t,
        description: editDescription,
        ddl: editDdl,
        assignee: editAssignee,
        module: editModule,
        is_uncertain: editUncertain,
        uncertainty_reason: editUncertainReason,
      } : t),
    })))

    setEditModalOpen(false)
    setEditingTodo(null)
    message.success('已更新')
  }

  const deleteTodo = (todoId: number) => {
    setLocalGroups(prev => {
      const newGroups = prev.map(mg => ({
        ...mg,
        todos: mg.todos.filter(t => t.id !== todoId),
      }))
      return newGroups.filter(mg => mg.todos.length > 0)
    })
    message.success('已删除')
  }

  const handleGenerate = () => {
    if (!meetingInfo) return
    onGenerateDoc(meetingInfo, displayGroups)
  }

  const totalItems = displayGroups.reduce((sum, mg) => sum + mg.todos.length, 0)
  const uncertainCount = displayGroups.reduce(
    (sum, mg) => sum + mg.todos.filter(t => t.is_uncertain).length, 0
  )

  return (
    <Card
      title={
        <Flex align="center" gap={8}>
          <CheckCircleOutlined />
          <span>待办事项</span>
          {loading && <Tag color="processing">分析中...</Tag>}
          {!loading && totalItems > 0 && (
            <Tag color={uncertainCount > 0 ? 'warning' : 'success'}>
              {totalItems} 项{uncertainCount > 0 ? ` (⚠️ ${uncertainCount})` : ''}
            </Tag>
          )}
        </Flex>
      }
      size="small"
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{ flex: 1, overflow: 'auto', padding: 12 }}
      extra={
        !loading && totalItems > 0 ? (
          <Button
            type="primary"
            size="small"
            icon={<FileTextOutlined />}
            onClick={handleGenerate}
            loading={generating}
            style={{ background: '#6366f1', borderColor: '#6366f1' }}
          >
            生成文档
          </Button>
        ) : undefined
      }
    >
      {loading && !totalItems && (
        <div style={{ paddingTop: 80, textAlign: 'center' }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="AI 正在分析待办事项..."
          />
        </div>
      )}

      {!loading && totalItems === 0 && (
        <div style={{ paddingTop: 80, textAlign: 'center' }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无待办事项"
          />
        </div>
      )}

      {/* Module Groups */}
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        {displayGroups.map((mg, mgIdx) => (
          <div key={mgIdx}>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: '#374151' }}>
              📦 {mg.name}
              <Tag style={{ marginLeft: 8 }}>{mg.todos.length} 项</Tag>
            </div>

            <Space direction="vertical" style={{ width: '100%' }} size={4}>
              {mg.todos.map(todo => (
                <Card
                  key={todo.id}
                  size="small"
                  style={{
                    background: todo.is_uncertain ? '#fffbeb' : '#f9fafb',
                    border: todo.is_uncertain ? '1px solid #fde68a' : '1px solid #e5e7eb',
                  }}
                  bodyStyle={{ padding: '8px 12px' }}
                >
                  <Flex justify="space-between" align="flex-start" gap={8}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Flex align="center" gap={6}>
                        {todo.is_uncertain && (
                          <Tooltip title={todo.uncertainty_reason || 'AI 无法确定'}>
                            <WarningOutlined style={{ color: '#f59e0b' }} />
                          </Tooltip>
                        )}
                        <Text style={{ fontSize: 13, lineHeight: 1.5 }}>
                          {todo.description}
                        </Text>
                      </Flex>

                      <Flex gap={8} style={{ marginTop: 4 }} wrap>
                        {todo.ddl && (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            📅 {todo.ddl}
                          </Text>
                        )}
                        {todo.assignee && (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            👤 {todo.assignee}
                          </Text>
                        )}
                        {todo.is_uncertain && (
                          <Text type="warning" style={{ fontSize: 11 }}>
                            ⚠️ {todo.uncertainty_reason}
                          </Text>
                        )}
                      </Flex>
                    </div>

                    <Flex gap={4}>
                      <Tooltip title="编辑">
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => openEditModal(todo)}
                        />
                      </Tooltip>
                      <Tooltip title="删除">
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => deleteTodo(todo.id)}
                        />
                      </Tooltip>
                    </Flex>
                  </Flex>
                </Card>
              ))}
            </Space>
          </div>
        ))}
      </Space>

      {/* Edit Modal */}
      <Modal
        title="编辑待办事项"
        open={editModalOpen}
        onOk={saveEdit}
        onCancel={() => setEditModalOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <div>
            <Text style={{ fontSize: 12, marginBottom: 4, display: 'block' }}>待办描述</Text>
            <Input.TextArea
              value={editDescription}
              onChange={e => setEditDescription(e.target.value)}
              rows={3}
            />
          </div>
          <Flex gap={12}>
            <div style={{ flex: 1 }}>
              <Text style={{ fontSize: 12, marginBottom: 4, display: 'block' }}>DDL</Text>
              <Input
                value={editDdl}
                onChange={e => setEditDdl(e.target.value)}
                placeholder="如：5月30日"
              />
            </div>
            <div style={{ flex: 1 }}>
              <Text style={{ fontSize: 12, marginBottom: 4, display: 'block' }}>跟进人</Text>
              <Input
                value={editAssignee}
                onChange={e => setEditAssignee(e.target.value)}
                placeholder="如：张三"
              />
            </div>
          </Flex>
          <Flex gap={12}>
            <div style={{ flex: 1 }}>
              <Text style={{ fontSize: 12, marginBottom: 4, display: 'block' }}>模块</Text>
              <Input
                value={editModule}
                onChange={e => setEditModule(e.target.value)}
                placeholder="如：技术类-模型训练"
              />
            </div>
          </Flex>
        </Space>
      </Modal>
    </Card>
  )
}