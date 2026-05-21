import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom'
import AppHeader from './components/AppHeader'
import BatchToast from './components/BatchToast'
import SettingsPanel from './components/SettingsPanel'
import KeywordEditorModal from './components/KeywordEditorModal'
import ScheduleModal from './components/ScheduleModal'
import HomePage from './pages/HomePage'
import BatchPage from './pages/BatchPage'
import { AppContextProvider, useAppContext } from './context/AppContext'

function Layout() {
  const ctx = useAppContext()
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#F8FAFC] text-slate-900 text-[13px]">
      <AppHeader />
      <BatchToast />
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
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <AppContextProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/batch" element={<BatchPage />} />
          </Route>
        </Routes>
      </AppContextProvider>
    </BrowserRouter>
  )
}
