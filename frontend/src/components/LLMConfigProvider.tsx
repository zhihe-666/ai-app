import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { Modal, Button, Input, Select, Space, message, Tag, Typography, Alert } from 'antd'
import { KeyOutlined, CheckCircleOutlined, CloseCircleOutlined, SettingOutlined, CodeOutlined } from '@ant-design/icons'
import client from '../api/client'
import { API_BASE } from '../utils/apiBase'

const { Text } = Typography

interface LLMConfig {
  apiKey: string
  baseUrl: string
  model: string
  providerName: string
  gitToken: string
}

interface ProviderPreset {
  name: string
  base_url: string
  models: string[]
}

interface LLMConfigContextValue {
  config: LLMConfig
  setConfig: (c: LLMConfig) => void
  isConfigured: boolean
  showConfigModal: () => void
}

const DEFAULT_CONFIG: LLMConfig = {
  apiKey: '',
  baseUrl: 'https://api.openai.com/v1',
  model: 'gpt-4o',
  providerName: '',
  gitToken: '',
}

const STORAGE_KEY = 'ai_center_llm_config'

const LLMConfigContext = createContext<LLMConfigContextValue>({
  config: DEFAULT_CONFIG,
  setConfig: () => {},
  isConfigured: false,
  showConfigModal: () => {},
})

export function useLLMConfig() {
  return useContext(LLMConfigContext)
}

function loadLocalConfig(): LLMConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return { ...DEFAULT_CONFIG, ...parsed }
    }
  } catch {}
  return DEFAULT_CONFIG
}

function saveLocalConfig(c: LLMConfig) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(c))
}

function applyConfigToAxios(config: LLMConfig) {
  client.defaults.headers.common['X-Api-Key'] = config.apiKey
  client.defaults.headers.common['X-Base-Url'] = config.baseUrl
  client.defaults.headers.common['X-Model'] = config.model
  client.defaults.headers.common['X-Git-Token'] = config.gitToken
}

const FALLBACK_PRESETS: Record<string, ProviderPreset> = {
  openai: { name: 'OpenAI', base_url: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4', 'gpt-3.5-turbo'] },
  deepseek: { name: 'DeepSeek', base_url: 'https://api.deepseek.com', models: ['deepseek-chat', 'deepseek-reasoner'] },
  qwen: { name: '通义千问', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-plus', 'qwen-max', 'qwen-turbo'] },
  siliconflow: { name: '硅基流动', base_url: 'https://api.siliconflow.cn/v1', models: ['Qwen/Qwen2.5-7B-Instruct', 'deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-R1'] },
}

export function LLMConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfigState] = useState<LLMConfig>(loadLocalConfig)
  const [modalOpen, setModalOpen] = useState(false)
  const [editConfig, setEditConfig] = useState<LLMConfig>(loadLocalConfig)
  const [presets, setPresets] = useState<Record<string, ProviderPreset>>({})
  const [selectedProvider, setSelectedProvider] = useState<string>('')
  const [verifying, setVerifying] = useState(false)
  const [verifyResult, setVerifyResult] = useState<{ valid: boolean; message: string } | null>(null)
  const [initialized, setInitialized] = useState(false)

  const isConfigured = Boolean(config.apiKey)

  // 1. 加载预设
  useEffect(() => {
    fetch(`${API_BASE}/auth/presets`)
      .then(r => r.json())
      .then(data => setPresets(data.presets || FALLBACK_PRESETS))
      .catch(() => setPresets(FALLBACK_PRESETS))
  }, [])

  // 2. 启动时从后端拉取已保存的配置
  useEffect(() => {
    fetch(`${API_BASE}/auth/config`)
      .then(r => r.json())
      .then(data => {
        if (data.configured) {
          // 后端有完整配置（含 api_key）→ 持久化到 localStorage + 注入 axios
          const merged: LLMConfig = {
            apiKey: data.api_key || '',
            baseUrl: data.base_url || '',
            model: data.model || '',
            providerName: data.provider_name || '',
            gitToken: data.git_token || '',
          }
          setConfigState(merged)
          setEditConfig(merged)
          applyConfigToAxios(merged)
          // ⚡ 关键：同步写入 localStorage，后续自动弹窗检测直接用存好的值
          saveLocalConfig(merged)
        }
      })
      .catch(() => {})
      .finally(() => setInitialized(true))
  }, [])

  // 3. 自动弹窗：等后端初始化完 → 无 apiKey → 弹一次
  useEffect(() => {
    if (!initialized) return
    const local = loadLocalConfig()
    if (!local.apiKey) {
      const timer = setTimeout(() => setModalOpen(true), 500)
      return () => clearTimeout(timer)
    }
  }, [initialized])

  const setConfig = useCallback((c: LLMConfig) => {
    setConfigState(c)
    saveLocalConfig(c)
    applyConfigToAxios(c)
  }, [])

  const showConfigModal = useCallback(() => {
    setEditConfig({ ...config })
    const found = Object.entries(FALLBACK_PRESETS).find(([, p]) => p.name === config.providerName)
    setSelectedProvider(found ? found[0] : '')
    setVerifyResult(null)
    setModalOpen(true)
  }, [config])

  const handleProviderSelect = (providerKey: string) => {
    if (providerKey === 'custom') {
      setSelectedProvider('custom')
      setEditConfig(p => ({ ...p, providerName: '', baseUrl: '', model: '' }))
      return
    }
    setSelectedProvider(providerKey)
    const preset = presets[providerKey]
    if (preset) {
      setEditConfig(p => ({
        ...p,
        providerName: preset.name,
        baseUrl: preset.base_url,
        model: preset.models[0] || p.model,
      }))
    }
  }

  const handleSave = async () => {
    if (!editConfig.apiKey.trim()) {
      message.warning('请输入 API Key')
      return
    }
    if (!editConfig.baseUrl.trim()) {
      message.warning('请输入 Base URL')
      return
    }
    if (!editConfig.model.trim()) {
      message.warning('请输入 Model')
      return
    }
    if (selectedProvider === 'custom' && !editConfig.providerName.trim()) {
      message.warning('请选择"其他"后填写 Provider 名称')
      return
    }
    try {
      // 保存到后端数据库
      await client.post('/auth/config', {
        provider_name: editConfig.providerName,
        api_key: editConfig.apiKey,
        base_url: editConfig.baseUrl,
        model: editConfig.model,
        git_token: editConfig.gitToken,
      })
      setConfig(editConfig)
      setModalOpen(false)
      message.success(`LLM 配置已保存 · ${editConfig.providerName || '自定义'}`)
    } catch {
      message.error('保存失败，请重试')
    }
  }

  const handleVerify = async () => {
    if (!editConfig.apiKey.trim()) {
      message.warning('请先输入 API Key')
      return
    }
    setVerifying(true)
    setVerifyResult(null)
    try {
      const resp = await client.post('/auth/verify', {
        api_key: editConfig.apiKey,
        base_url: editConfig.baseUrl,
        model: editConfig.model,
      })
      setVerifyResult(resp.data)
    } catch (err: any) {
      setVerifyResult({ valid: false, message: err?.response?.data?.message || '验证请求失败' })
    } finally {
      setVerifying(false)
    }
  }

  const presetOptions = Object.entries(presets).map(([key, p]) => ({ label: p.name, value: key }))

  return (
    <LLMConfigContext.Provider value={{ config, setConfig, isConfigured, showConfigModal }}>
      {children}

      <Modal
        title={
          <Space>
            <SettingOutlined style={{ color: '#6366f1' }} />
            <span>LLM 全局配置</span>
          </Space>
        }
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={
          <Space>
            <Button onClick={handleVerify} loading={verifying}>验证连接</Button>
            <Button type="primary" onClick={handleSave}>保存</Button>
          </Space>
        }
        width={520}
      >
        <Text type="secondary" style={{ fontSize: 12 }}>
          所有功能模块共用此配置，只需填写一次，后续刷新自动沿用。
        </Text>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 16 }}>
          <div>
            <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>
              LLM 服务商
            </Text>
            <Select
              style={{ width: '100%' }}
              placeholder="选择服务商（自动填入 Base URL 和推荐模型）"
              value={selectedProvider || undefined}
              onChange={handleProviderSelect}
              allowClear
              onClear={() => setSelectedProvider('')}
              options={[
                ...presetOptions,
                { label: '其他（自定义）', value: 'custom' },
              ]}
            />
          </div>

          <div>
            <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>
              API Key <Text type="danger">*</Text>
            </Text>
            <Input.Password
              placeholder="sk-xxx..."
              value={editConfig.apiKey}
              onChange={e => setEditConfig(p => ({ ...p, apiKey: e.target.value }))}
            />
          </div>

          {selectedProvider === 'custom' && (
            <div>
              <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>
                Provider 名称 <Text type="danger">*</Text>
              </Text>
              <Input
                placeholder="例如：Ollama、LMStudio、LocalAI"
                value={editConfig.providerName}
                onChange={e => setEditConfig(p => ({ ...p, providerName: e.target.value }))}
              />
            </div>
          )}

          <div>
            <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>
              Base URL <Text type="danger">*</Text>
            </Text>
            <Input
              placeholder="https://api.openai.com/v1"
              value={editConfig.baseUrl}
              onChange={e => setEditConfig(p => ({ ...p, baseUrl: e.target.value }))}
            />
          </div>

          <div>
            <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>
              Model <Text type="danger">*</Text>
            </Text>
            <Select
              style={{ width: '100%' }}
              mode="tags"
              placeholder="输入或选择模型名称"
              value={editConfig.model ? [editConfig.model] : []}
              onChange={vals => setEditConfig(p => ({ ...p, model: vals[0] || '' }))}
              maxCount={1}
              options={
                selectedProvider && presets[selectedProvider]
                  ? presets[selectedProvider].models.map(m => ({ label: m, value: m }))
                  : [
                      { label: 'gpt-4o', value: 'gpt-4o' },
                      { label: 'gpt-4o-mini', value: 'gpt-4o-mini' },
                      { label: 'gpt-4', value: 'gpt-4' },
                      { label: 'deepseek-chat', value: 'deepseek-chat' },
                      { label: 'deepseek-reasoner', value: 'deepseek-reasoner' },
                      { label: 'qwen-plus', value: 'qwen-plus' },
                      { label: 'qwen-max', value: 'qwen-max' },
                    ]
              }
            />
          </div>

          {verifyResult && (
            <Alert
              type={verifyResult.valid ? 'success' : 'error'}
              message={verifyResult.message}
              showIcon
              closable
              onClose={() => setVerifyResult(null)}
            />
          )}
        </div>

        {/* ── Git Token ── */}
        <div style={{ borderTop: '1px solid #e2e8f0', marginTop: 20, paddingTop: 16 }}>
          <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 4 }}>
            <CodeOutlined style={{ marginRight: 6 }} />Git 令牌
          </Text>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 10 }}>
            用于 Git 仓库拉取身份验证，所有功能变更分析共享此令牌。
          </Text>
          <Input.Password
            placeholder="GitLab / GitHub Personal Access Token"
            value={editConfig.gitToken}
            onChange={e => setEditConfig(p => ({ ...p, gitToken: e.target.value }))}
          />
        </div>
      </Modal>
    </LLMConfigContext.Provider>
  )
}
