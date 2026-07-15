import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import { LLMConfigProvider } from './components/LLMConfigProvider'
import './chat-markdown.css'

const theme = {
  token: {
    colorPrimary: '#6366f1',
    borderRadius: 8,
  },
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider theme={theme} locale={zhCN}>
      <BrowserRouter basename={import.meta.env.BASE_URL}>
        <LLMConfigProvider>
          <App />
        </LLMConfigProvider>
      </BrowserRouter>
    </ConfigProvider>
  </StrictMode>,
)