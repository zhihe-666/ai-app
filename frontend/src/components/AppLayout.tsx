import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Tag, Tooltip } from 'antd'
import {
  LikeOutlined,
  BarChartOutlined,
  FileTextOutlined,
  WechatOutlined,
  ApartmentOutlined,
  DatabaseOutlined,
  CodeOutlined,
  EditOutlined,
  FormOutlined,
  KeyOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import { useState } from 'react'
import { showComingSoon } from './ComingSoon'
import { useLLMConfig } from './LLMConfigProvider'

const { Sider, Content } = Layout

const SIDER_EXPANDED = 260
const SIDER_COLLAPSED = 80

const activeNavItems = [
  { key: '/meeting-todo', icon: <LikeOutlined />, label: '会议 TODO' },
  { key: '/iteration-stats', icon: <BarChartOutlined />, label: '迭代统计' },
  { key: '/ai-measure', icon: <FileTextOutlined />, label: '数据报告' },
  { key: '/chat', icon: <WechatOutlined />, label: '知识库问答' },
  { key: '/kb-manage', icon: <DatabaseOutlined />, label: '知识库管理' },
  { key: '/code-analyze', icon: <CodeOutlined />, label: '功能变更分析' },
  { key: '/prd-gen', icon: <EditOutlined />, label: 'PRD 智能生成' },
]

const comingSoonItems = [
  { key: '/req-agent', icon: <ApartmentOutlined />, label: '需求理解 Agent' },
  { key: '/weekly-rpt', icon: <FormOutlined />, label: '周报自动生成' },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isConfigured, showConfigModal, config } = useLLMConfig()
  const [collapsed, setCollapsed] = useState(false)

  const handleMenuClick = (info: { key: string }) => {
    const item = comingSoonItems.find(i => i.key === info.key)
    if (item) {
      showComingSoon({
        featureName: item.label,
        expectedDate: '待定',
        description: '此功能正在开发中，敬请期待',
      })
      return
    }
    navigate(info.key)
  }

  const siderWidth = collapsed ? SIDER_COLLAPSED : SIDER_EXPANDED

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={SIDER_EXPANDED}
        collapsedWidth={SIDER_COLLAPSED}
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
        style={{
          background: '#fff',
          borderRight: '1px solid #e2e8f0',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          zIndex: 100,
          overflow: 'auto',
        }}
      >
        {/* Brand + 折叠按钮 */}
        <div
          style={{
            padding: collapsed ? '24px 0' : '24px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'space-between',
            gap: 12,
            borderBottom: '1px solid #e2e8f0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div
              style={{
                width: 36,
                height: 36,
                background: 'linear-gradient(135deg, #6366f1, #a78bfa)',
                borderRadius: 10,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 700,
                fontSize: 16,
                color: '#fff',
                flexShrink: 0,
              }}
            >
              AI
            </div>
            {!collapsed && (
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: '#1a202c' }}>AI 中控台</div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>项目管理 · MVP</div>
              </div>
            )}
          </div>
          {!collapsed && (
            <Tooltip title="收起侧边栏">
              <MenuFoldOutlined
                onClick={() => setCollapsed(true)}
                style={{ fontSize: 16, color: '#94a3b8', cursor: 'pointer' }}
              />
            </Tooltip>
          )}
        </div>

        {/* Menu */}
        <div style={{ padding: '16px 12px' }}>
          {!collapsed && (
            <div style={{ fontSize: 11, color: '#94a3b8', padding: '8px 14px 4px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              核心功能
            </div>
          )}
          <Menu
            mode="inline"
            inlineCollapsed={collapsed}
            selectedKeys={[location.pathname]}
            onClick={handleMenuClick}
            items={activeNavItems}
            style={{ border: 'none', fontSize: 13 }}
          />

          {!collapsed && (
            <>
              <div style={{ height: 1, background: '#e2e8f0', margin: '8px 4px' }} />
              <div style={{ fontSize: 11, color: '#94a3b8', padding: '8px 14px 4px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                规划中
              </div>
              <Menu
                mode="inline"
                onClick={handleMenuClick}
                items={comingSoonItems.map(item => ({
                  ...item,
                  disabled: true,
                }))}
                style={{ border: 'none', fontSize: 13 }}
              />
              <div style={{ marginTop: 24, padding: '0 14px' }}>
                <div style={{ fontSize: 11, color: '#94a3b8', background: '#f0f2f5', borderRadius: 8, padding: '8px 12px', textAlign: 'center' }}>
                  🚀 更多功能即将上线
                </div>
              </div>
            </>
          )}
        </div>

        {/* LLM Config Status */}
        <div
          onClick={showConfigModal}
          style={{
            padding: collapsed ? '12px 0' : '12px 20px',
            justifyContent: collapsed ? 'center' : 'flex-start',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            cursor: 'pointer',
            fontSize: 12,
            color: '#64748b',
            transition: 'background .2s',
          }}
          onMouseEnter={e => (e.currentTarget.style.background = '#f0f2f5')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >
          <KeyOutlined style={{ fontSize: 14, flexShrink: 0 }} />
          {!collapsed && (
            <>
              <span style={{ flex: 1 }}>全局配置</span>
              <Tag
                color={isConfigured ? 'success' : 'warning'}
                style={{ margin: 0, fontSize: 11, lineHeight: '20px' }}
              >
                {isConfigured ? config.model : '未配置'}
              </Tag>
            </>
          )}
        </div>

        {/* 收起态展开按钮（固定底部） */}
        {collapsed && (
          <Tooltip title="展开侧边栏" placement="right">
            <div
              onClick={() => setCollapsed(false)}
              style={{
                position: 'absolute',
                bottom: 60,
                left: 0,
                right: 0,
                display: 'flex',
                justifyContent: 'center',
                padding: '8px 0',
                cursor: 'pointer',
                color: '#94a3b8',
              }}
            >
              <MenuUnfoldOutlined style={{ fontSize: 16 }} />
            </div>
          </Tooltip>
        )}
      </Sider>

      <Layout style={{ marginLeft: siderWidth, background: '#f5f7fa', transition: 'margin-left .2s' }}>
        <Content style={{ padding: 0, minHeight: '100vh', overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}