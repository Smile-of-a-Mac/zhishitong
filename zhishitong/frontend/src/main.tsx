import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import AuroraBackground from './components/AuroraBackground'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{
      token: {
        colorPrimary: '#007aff',
        borderRadius: 8,
        fontFamily: `-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', 'Helvetica Neue', sans-serif`,
      },
    }}>
      <BrowserRouter>
        <AuroraBackground />
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>
)
