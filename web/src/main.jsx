import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import './index.css'
import './clean.css'

// 루트 에러 바운더리 — 셸(네비/검색 등) 크래시에도 백지 대신 안내를 띄운다.
// 페이지 단위 격리는 App.jsx 의 라우트 바운더리가 담당.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>,
)
