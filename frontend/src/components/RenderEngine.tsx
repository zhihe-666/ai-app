/**
 * RenderEngine — PRD 原型动态渲染引擎
 *
 * 读取 Agent4 spec.uiSpec 数组，递归渲染为 React 组件。
 *
 * 渲染策略：
 *   antd 组件 → 从 antd 导入，直接渲染（Table / Form / Modal / Button / Select 等）
 *   project/business 组件 → 降级占位卡（显示组件名 + props + 复用信息）
 *   未知组件 → Alert warning
 *
 * Registry（component_registry.json）是可选增强：
 *   有 registry → 显示 category/reuse_count/used_in_pages 等丰富信息
 *   无 registry → antd 原生正常渲染，非 antd 组件显示通用占位卡
 */
import React from 'react'
import {
  Table, Form, Modal, Button, Select, Input, DatePicker, Tabs,
  Tag, Space, Card, Empty, Alert, Radio, Checkbox, Switch,
  Upload, Progress, Spin, Badge, Tooltip, Popover, Drawer,
  List, Descriptions, Divider, InputNumber, Slider, Rate,
} from 'antd'
import type { RegistryComponent } from '../api/kbManage'

// ── Antd 组件映射（支持渲染的 antd 原生组件）──

const COMPONENT_MAP: Record<string, React.ComponentType<any>> = {
  Table, Form, Modal, Button, Select, Input, DatePicker, Tabs,
  Tag, Space, Card, Empty, Alert, Radio, Checkbox, Switch,
  Upload, Progress, Spin, Badge, Tooltip, Popover, Drawer,
  List, Descriptions, Divider, InputNumber, Slider, Rate,
}

// ── Props 默认转换（将 spec 中简写 props 映射为 antd 合法 props）──

function normalizeProps(component: string, props: Record<string, any>): Record<string, any> {
  if (!props) return {}

  // columns 从简单数组转 antd Table columns 格式
  if (component === 'Table' && Array.isArray(props.columns)) {
    props.columns = (props.columns as any[]).map((col: any) =>
      typeof col === 'string' ? { title: col, dataIndex: col, key: col } : col,
    )
  }
  return props
}

// ── 渲染节点（递归）──

interface UiSpecNode {
  component: string
  props?: Record<string, any>
  children?: UiSpecNode[]
  label?: string  // 区块标题/描述
}

interface RegistryInfo {
  [name: string]: RegistryComponent
}

interface RenderNodeProps {
  node: UiSpecNode
  registry: RegistryInfo
  depth?: number
}

function RenderNode({ node, registry, depth = 0 }: RenderNodeProps) {
  const { component, props = {}, children, label } = node
  const regEntry = registry[component]

  // 已知非 antd 组件（project/business）→ 占位卡
  if (regEntry && regEntry.category !== 'antd') {
    return (
      <Card
        title={label || component}
        size="small"
        style={{
          margin: 8,
          border: '2px dashed #6366f1',
          background: '#f8f9ff',
        }}
      >
        <Space direction="vertical" size="small">
          <Space>
            <Tag color="purple">{regEntry.category}</Tag>
            <Text code>{component}</Text>
            {regEntry.reuse_count > 1 && (
              <Text type="secondary">复用 {regEntry.reuse_count} 次</Text>
            )}
          </Space>
          {regEntry.props && regEntry.props.length > 0 && (
            <div style={{ fontSize: 12 }}>
              <Text type="secondary">props: </Text>
              {regEntry.props.map((p, i) => (
                <Tag key={i} style={{ fontSize: 11 }}>
                  {p.name}: {p.type}{p.required ? '*' : ''}
                </Tag>
              ))}
            </div>
          )}
          {regEntry.subcomponents && regEntry.subcomponents.length > 0 && (
            <div style={{ fontSize: 12 }}>
              <Text type="secondary">子组件: </Text>
              {regEntry.subcomponents.map((sc, i) => (
                <Tag key={i} style={{ fontSize: 11 }}>{sc}</Tag>
              ))}
            </div>
          )}
        </Space>
        {children && children.length > 0 && (
          <div style={{ marginTop: 8, paddingLeft: 16, borderLeft: '2px solid #e8eaff' }}>
            {children.map((child, i) => (
              <RenderNode key={i} node={child} registry={registry} depth={depth + 1} />
            ))}
          </div>
        )}
      </Card>
    )
  }

  // 无 registry 信息 + 非 antd 已知 → 未知组件警告 / 占位
  if (!COMPONENT_MAP[component] && !regEntry) {
    if (children && children.length > 0) {
      // 有子元素,渲染子元素
      return (
        <div style={{ margin: 8 }}>
          {label && <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>{label}</div>}
          {children.map((child, i) => (
            <RenderNode key={i} node={child} registry={registry} depth={depth + 1} />
          ))}
        </div>
      )
    }
    return (
      <Alert
        type="warning"
        message={`未知组件: ${component}`}
        style={{ margin: 8, fontSize: 12 }}
        showIcon
      />
    )
  }

  // antd 原生组件 → 直接渲染
  const Comp = COMPONENT_MAP[component]
  const normalizedProps = normalizeProps(component, props)

  const childElements = children?.map((child, i) => (
    <RenderNode key={i} node={child} registry={registry} depth={depth + 1} />
  )) || []

  try {
    // label 作为区块标题
    const wrappedChildren = (
      <>
        {label && <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8, color: '#333' }}>{label}</div>}
        {childElements}
      </>
    )
    return React.createElement(Comp, { ...normalizedProps, key: component + depth }, wrappedChildren)
  } catch {
    // 渲染失败 → 降级显示组件名 + props
    return (
      <Card size="small" style={{ margin: 8, background: '#fffbe6' }} title={`${component}（渲染降级）`}>
        <pre style={{ fontSize: 11, margin: 0, maxHeight: 160, overflow: 'auto' }}>
          {JSON.stringify(props, null, 2)}
        </pre>
      </Card>
    )
  }
}

import { Typography } from 'antd'
const { Text } = Typography

// ── RenderEngine 主组件 ──

export interface RenderEngineProps {
  uiSpec: UiSpecNode[]
  registry: RegistryComponent[] | null
}

export default function RenderEngine({ uiSpec, registry }: RenderEngineProps) {
  // 搭建 registry 查找索引
  const regIndex: RegistryInfo = {}
  if (registry) {
    for (const c of registry) {
      regIndex[c.name] = c
    }
  }

  if (!uiSpec || uiSpec.length === 0) {
    return (
      <Card size="small" style={{ background: '#fafafa' }}>
        <Empty description="暂无原型规格（Agent4 未输出 uiSpec）" />
      </Card>
    )
  }

  return (
    <div style={{ padding: 16, background: '#fff', border: '1px solid #f0f0f0', borderRadius: 8 }}>
      {uiSpec.map((node, i) => (
        <RenderNode key={i} node={node} registry={regIndex} />
      ))}
    </div>
  )
}