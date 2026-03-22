import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AppShell from './components/layout/AppShell'
import { PromptLayout } from './components/layout/PromptLayout'
import PromptsPage from './pages/PromptsPage'
import PromptTemplatePage from './pages/PromptTemplatePage'
import PromptDatasetPage from './pages/PromptDatasetPage'
import PromptEvolutionPage from './pages/PromptEvolutionPage'
import PromptConfigPage from './pages/PromptConfigPage'
import PromptHistoryPage from './pages/PromptHistoryPage'
import RunDetailPage from './pages/RunDetailPage'
import PromptPlaygroundPage from './pages/PromptPlaygroundPage'
import WizardPage from './pages/WizardPage'

const SettingsPage = lazy(() => import('./pages/SettingsPage'))

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/prompts" element={<PromptsPage />} />
            <Route path="/wizard" element={<WizardPage />} />
            <Route path="/settings" element={<Suspense fallback={null}><SettingsPage /></Suspense>} />
            <Route path="/prompts/:promptId" element={<PromptLayout />}>
              <Route index element={<Navigate to="template" replace />} />
              <Route path="template" element={<PromptTemplatePage />} />
              <Route path="dataset" element={<PromptDatasetPage />} />
              <Route path="config" element={<PromptConfigPage />} />
              <Route path="evolution" element={<PromptEvolutionPage />} />
              <Route path="history" element={<PromptHistoryPage />} />
              <Route path="history/:runId" element={<RunDetailPage />} />
              <Route path="playground" element={<PromptPlaygroundPage />} />
            </Route>
            {/* Redirects from old routes */}
            <Route path="/datasets" element={<Navigate to="/prompts" replace />} />
            <Route path="/evolution" element={<Navigate to="/prompts" replace />} />
            <Route path="/history" element={<Navigate to="/prompts" replace />} />
            <Route path="/history/:runId" element={<Navigate to="/prompts" replace />} />
            <Route path="/" element={<Navigate to="/prompts" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
