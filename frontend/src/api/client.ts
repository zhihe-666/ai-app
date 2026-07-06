import axios from 'axios'
import { API_BASE } from '../utils/apiBase'

const LLM_CONFIG_KEY = 'ai_center_llm_config'

const client = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
})

// 请求拦截器：自动注入 LLM 配置（与 sse.ts 的 getLlmHeaders 保持一致）
client.interceptors.request.use(
  config => {
    try {
      const raw = localStorage.getItem(LLM_CONFIG_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed.apiKey) config.headers['X-Api-Key'] = parsed.apiKey
        if (parsed.baseUrl) config.headers['X-Base-Url'] = parsed.baseUrl
        if (parsed.model) config.headers['X-Model'] = parsed.model
      }
    } catch {
      // ignore
    }
    return config
  },
  err => Promise.reject(err)
)

client.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      console.error('认证失败，请检查 Token')
    }
    return Promise.reject(err)
  }
)

export default client