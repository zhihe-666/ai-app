import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import MeetingTodo from './pages/MeetingTodo'
import IterationStats from './pages/IterationStats'
import AiMeasure from './pages/AiMeasure'
import KbManage from './pages/KbManage'
import Chat from './pages/Chat'
import CodeAnalyze from './pages/CodeAnalyze'

function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/meeting-todo" replace />} />
        <Route path="/meeting-todo" element={<MeetingTodo />} />
        <Route path="/iteration-stats" element={<IterationStats />} />
        <Route path="/ai-measure" element={<AiMeasure />} />
        <Route path="/kb-manage" element={<KbManage />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/code-analyze" element={<CodeAnalyze />} />
      </Route>
    </Routes>
  )
}

export default App