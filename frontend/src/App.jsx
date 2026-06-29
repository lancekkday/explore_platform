import { Component } from 'react'
import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom'
import AppHeader from './components/AppHeader'
import BaselineStatusBanner from './components/BaselineStatusBanner'
import SettingsPanel from './components/SettingsPanel'
import KeywordEditorModal from './components/KeywordEditorModal'
import ScheduleModal from './components/ScheduleModal'
import HomePage from './pages/HomePage'
import BatchPage from './pages/BatchPage'
import { AppContextProvider, useAppContext } from './context/AppContext'

// Normalize Vite's BASE_URL for react-router basename:
// - 必有 leading slash (Vite 在 .env 漏了會 warn 但仍 serve)
// - 拿掉 trailing slash (react-router basename 用 leading-only)
function normalizeBasename(raw) {
  let v = raw || '/'
  if (!v.startsWith('/')) v = '/' + v
  if (v.length > 1 && v.endsWith('/')) v = v.slice(0, -1)
  return v
}

class ErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  componentDidCatch(error, info) { console.error('[App ErrorBoundary]', error, info) }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 24, fontFamily: 'monospace', color: '#991b1b' }}>
          <h2 style={{ marginBottom: 12 }}>⚠ 前端 render 失敗</h2>
          <pre style={{ whiteSpace: 'pre-wrap', background: '#fef2f2', padding: 12, border: '1px solid #fecaca', borderRadius: 6, fontSize: 12 }}>
            {String(this.state.error?.stack || this.state.error)}
          </pre>
          <p style={{ marginTop: 12, fontSize: 12, color: '#64748b' }}>
            重新整理頁面 (Cmd+Shift+R) 或檢查 console 看細節。
          </p>
        </div>
      )
    }
    return this.props.children
  }
}

function Layout() {
  const ctx = useAppContext()
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#F8FAFC] text-slate-900 text-[13px]">
      <AppHeader />
      <BaselineStatusBanner />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Outlet />
      </div>

      {/* Global modals (rendered once at Layout level so they work on every route) */}
      <SettingsPanel
        visible={ctx.settingsVisible}
        onClose={() => ctx.setSettingsVisible(false)}
        versionA={ctx.versionA} setVersionA={ctx.setVersionA}
        versionB={ctx.versionB} setVersionB={ctx.setVersionB}
        enableAB={ctx.enableAB} setEnableAB={ctx.setEnableAB}
        searchApi={ctx.searchApi} setSearchApi={ctx.setSearchApi}
        aiEnabled={ctx.aiEnabled} setAiEnabled={ctx.setAiEnabled}
        channel={ctx.channel} setChannel={ctx.setChannel}
        cookieInfo={ctx.cookieInfo}
        onRefreshCookie={ctx.autoFetchCookie}
        onOpenKeywordEditor={ctx.openKeywordEditor}
        onOpenScheduleModal={() => ctx.openScheduleModal(null)}
        schedules={ctx.schedules}
        onToggleSchedule={ctx.handleToggleSchedule}
        onDeleteSchedule={ctx.handleDeleteSchedule}
      />
      <KeywordEditorModal
        visible={ctx.kwEditorVisible}
        kwInputText={ctx.kwInputText}
        onInputChange={ctx.setKwInputText}
        onSave={ctx.saveKeywords}
        onClose={() => ctx.setKwEditorVisible(false)}
      />
      <ScheduleModal
        visible={ctx.scheduleModalVisible}
        schedule={ctx.editingSchedule}
        onSave={ctx.handleSaveSchedule}
        onClose={() => { ctx.setScheduleModalVisible(false); ctx.setEditingSchedule(null) }}
      />
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter basename={normalizeBasename(import.meta.env.BASE_URL)}>
        <AppContextProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<HomePage />} />
              <Route path="/batch" element={<BatchPage />} />
            </Route>
          </Routes>
        </AppContextProvider>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
