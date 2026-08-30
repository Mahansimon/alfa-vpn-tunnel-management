import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { AppShell } from '@/components/layout/AppShell'
import { Spinner } from '@/components/ui'
import { LoginPage } from '@/pages/Login'

// Code Splitting: هر صفحه جدا بارگذاری می‌شود
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Servers = lazy(() => import('@/pages/Servers'))
const ServerDetail = lazy(() => import('@/pages/ServerDetail'))
const Tunnels = lazy(() => import('@/pages/Tunnels'))
const TunnelWizard = lazy(() => import('@/pages/TunnelWizard'))
const TunnelDetail = lazy(() => import('@/pages/TunnelDetail'))
const Topology = lazy(() => import('@/pages/Topology'))
const ServerMap = lazy(() => import('@/pages/ServerMap'))
const Traffic = lazy(() => import('@/pages/Traffic'))
const Monitoring = lazy(() => import('@/pages/Monitoring'))
const Logs = lazy(() => import('@/pages/Logs'))
const Alerts = lazy(() => import('@/pages/Alerts'))
const NotificationsPage = lazy(() => import('@/pages/Notifications'))
const Deployments = lazy(() => import('@/pages/Deployments'))
const Users = lazy(() => import('@/pages/Users'))
const Audit = lazy(() => import('@/pages/Audit'))
const Settings = lazy(() => import('@/pages/Settings'))
const Backups = lazy(() => import('@/pages/Backups'))
const Health = lazy(() => import('@/pages/Health'))
const About = lazy(() => import('@/pages/About'))
const Profile = lazy(() => import('@/pages/Profile'))
const ChangePassword = lazy(() => import('@/pages/ChangePassword'))

function FullPageLoader() {
  return (
    <div className="grid min-h-screen place-items-center">
      <Spinner className="h-6 w-6" />
    </div>
  )
}

function NotFound() {
  return (
    <div className="grid place-items-center py-24 text-center">
      <p className="text-5xl font-extrabold text-accent">۴۰۴</p>
      <p className="mt-3 text-sm text-ink-muted">صفحه‌ای که دنبالش هستید وجود ندارد.</p>
    </div>
  )
}

export function App() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <FullPageLoader />

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace state={{ from: location.pathname }} />} />
      </Routes>
    )
  }

  if (user.must_change_password) {
    return (
      <Suspense fallback={<FullPageLoader />}>
        <Routes>
          <Route path="*" element={<ChangePassword forced />} />
        </Routes>
      </Suspense>
    )
  }

  return (
    <Suspense fallback={<FullPageLoader />}>
      <Routes>
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/servers" element={<Servers />} />
          <Route path="/servers/:id" element={<ServerDetail />} />
          <Route path="/tunnels" element={<Tunnels />} />
          <Route path="/tunnels/new" element={<TunnelWizard />} />
          <Route path="/tunnels/:id" element={<TunnelDetail />} />
          <Route path="/topology" element={<Topology />} />
          <Route path="/map" element={<ServerMap />} />
          <Route path="/traffic" element={<Traffic />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/deployments" element={<Deployments />} />
          <Route path="/users" element={<Users />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/backups" element={<Backups />} />
          <Route path="/health" element={<Health />} />
          <Route path="/about" element={<About />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/change-password" element={<ChangePassword />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
