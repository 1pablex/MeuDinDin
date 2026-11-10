import { lazy, Suspense } from 'react'
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/useAuth'
import { Layout } from './components/Layout'
import { Loading } from './components/ui'
import { LoginPage } from './pages/LoginPage'

// Páginas internas carregadas sob demanda (o recharts fica fora do bundle do login)
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const TransactionsPage = lazy(() =>
  import('./pages/TransactionsPage').then((m) => ({ default: m.TransactionsPage })),
)
const GoalsPage = lazy(() => import('./pages/GoalsPage').then((m) => ({ default: m.GoalsPage })))
const SecurityPage = lazy(() => import('./pages/SecurityPage').then((m) => ({ default: m.SecurityPage })))

function RequireAuth() {
  const { state } = useAuth()
  if (state.status === 'loading') {
    return (
      <div className="splash">
        <Loading label="Abrindo o MeuDinDin…" />
      </div>
    )
  }
  if (state.status === 'anonymous') return <Navigate to="/login" replace />
  return (
    <Suspense fallback={<Loading />}>
      <Outlet />
    </Suspense>
  )
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="lancamentos" element={<TransactionsPage />} />
          <Route path="metas" element={<GoalsPage />} />
          <Route path="seguranca" element={<SecurityPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
