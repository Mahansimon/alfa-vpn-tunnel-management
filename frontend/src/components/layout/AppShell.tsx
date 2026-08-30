import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Activity,
  Bell,
  ChevronLeft,
  Database,
  FileClock,
  Gauge,
  Globe2,
  HeartPulse,
  Info,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Network,
  Search,
  Server,
  Settings,
  ShieldCheck,
  Siren,
  Sun,
  Terminal,
  Users,
  X,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api, type Notification } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { usePreferences } from '@/hooks/usePreferences'
import { useI18n } from '@/i18n'
import { cn, formatNumber, relativeTime } from '@/lib/utils'
import { Badge, Button } from '@/components/ui'
import { CommandPalette } from '@/components/layout/CommandPalette'

interface NavItem {
  to: string
  label: string
  icon: typeof Server
  permission?: string
}

export function AppShell() {
  const { t } = useI18n()
  const { user, logout, can } = useAuth()
  const { theme, toggleTheme, digits } = usePreferences()
  const location = useLocation()
  const navigate = useNavigate()
  const [drawer, setDrawer] = useState(false)
  const [palette, setPalette] = useState(false)
  const [bell, setBell] = useState(false)

  useEffect(() => setDrawer(false), [location.pathname])

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPalette(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const groups: { title: string; items: NavItem[] }[] = [
    {
      title: 'پایش',
      items: [
        { to: '/', label: t('nav.dashboard'), icon: LayoutDashboard },
        { to: '/monitoring', label: t('nav.monitoring'), icon: Activity, permission: 'metrics.read' },
        { to: '/traffic', label: t('nav.traffic'), icon: Gauge, permission: 'traffic.read' },
      ],
    },
    {
      title: 'زیرساخت',
      items: [
        { to: '/servers', label: t('nav.servers'), icon: Server, permission: 'servers.read' },
        { to: '/tunnels', label: t('nav.tunnels'), icon: Network, permission: 'tunnels.read' },
        { to: '/topology', label: t('nav.topology'), icon: Network, permission: 'tunnels.read' },
        { to: '/map', label: t('nav.map'), icon: Globe2, permission: 'servers.read' },
        { to: '/deployments', label: t('nav.deployments'), icon: Terminal, permission: 'tunnels.read' },
      ],
    },
    {
      title: 'رخدادها',
      items: [
        { to: '/logs', label: t('nav.logs'), icon: FileClock, permission: 'logs.read' },
        { to: '/alerts', label: t('nav.alerts'), icon: Siren, permission: 'metrics.read' },
        { to: '/notifications', label: t('nav.notifications'), icon: Bell },
        { to: '/audit', label: t('nav.audit'), icon: ShieldCheck, permission: 'audit.read' },
      ],
    },
    {
      title: 'مدیریت',
      items: [
        { to: '/users', label: t('nav.users'), icon: Users, permission: 'users.manage' },
        { to: '/backups', label: t('nav.backup'), icon: Database, permission: 'backup.manage' },
        { to: '/health', label: t('nav.health'), icon: HeartPulse },
        { to: '/settings', label: t('nav.settings'), icon: Settings, permission: 'settings.read' },
        { to: '/about', label: t('nav.about'), icon: Info },
      ],
    },
  ]

  const { data: unread } = useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: async () => (await api.get<{ count: number }>('/notifications/unread-count')).data.count,
    refetchInterval: 30000,
  })

  const { data: recent } = useQuery({
    queryKey: ['notifications', 'recent'],
    queryFn: async () =>
      (await api.get<{ items: Notification[] }>('/notifications', { params: { per_page: 8 } })).data.items,
    enabled: bell,
  })

  const crumbs = location.pathname.split('/').filter(Boolean)

  const sidebar = (
    <nav className="flex h-full flex-col gap-6 overflow-y-auto px-3 py-5">
      <Link to="/" className="flex items-center gap-2.5 px-2">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent-soft text-accent">
          <Network size={18} />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[13px] font-extrabold leading-5">Alfa VpnTunnel</span>
          <span className="block text-[10px] uppercase tracking-widest text-ink-faint">Managment</span>
        </span>
      </Link>

      {groups.map((group) => {
        const items = group.items.filter((item) => !item.permission || can(item.permission))
        if (!items.length) return null
        return (
          <div key={group.title}>
            <p className="mb-1.5 px-3 text-[10px] font-bold uppercase tracking-widest text-ink-faint">
              {group.title}
            </p>
            <ul className="space-y-0.5">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm transition-colors duration-150',
                        isActive
                          ? 'bg-accent-soft/60 font-semibold text-ink'
                          : 'text-ink-muted hover:bg-surface-overlay hover:text-ink',
                      )
                    }
                  >
                    <item.icon size={16} className="shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        )
      })}

      <div className="mt-auto rounded-xl border border-line bg-surface-sunken p-3">
        <p className="truncate text-xs font-semibold">{user?.full_name || user?.username}</p>
        <p className="mt-0.5 text-[11px] text-ink-faint">{t(`roles.${user?.role ?? 'viewer'}`)}</p>
        <div className="mt-2.5 flex gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => navigate('/profile')}>
            {t('auth.profile')}
          </Button>
          <Button size="sm" variant="ghost" icon={<LogOut size={14} />} onClick={() => void logout()}>
            {t('auth.logout')}
          </Button>
        </div>
      </div>
    </nav>
  )

  return (
    <div className="min-h-screen bg-surface-base">
      <aside className="fixed inset-y-0 start-0 z-30 hidden w-[248px] border-e border-line bg-surface-raised lg:block">
        {sidebar}
      </aside>

      {drawer ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-surface-sunken/80" onClick={() => setDrawer(false)} role="presentation" />
          <aside className="absolute inset-y-0 start-0 w-[272px] animate-fade-up border-e border-line bg-surface-raised">
            <button
              onClick={() => setDrawer(false)}
              className="absolute end-3 top-4 rounded-lg p-1.5 text-ink-faint hover:text-ink"
              aria-label={t('app.close')}
            >
              <X size={16} />
            </button>
            {sidebar}
          </aside>
        </div>
      ) : null}

      <div className="lg:ms-[248px]">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-surface-base/90 px-4 backdrop-blur-sm sm:px-6">
          <Button size="icon" variant="ghost" className="lg:hidden" onClick={() => setDrawer(true)} aria-label="منو">
            <Menu size={18} />
          </Button>

          <ol className="hidden min-w-0 items-center gap-1.5 text-xs text-ink-faint sm:flex">
            <li>
              <Link to="/" className="hover:text-ink">
                {t('nav.dashboard')}
              </Link>
            </li>
            {crumbs.map((crumb, index) => (
              <li key={`${crumb}-${index}`} className="flex items-center gap-1.5">
                <ChevronLeft size={12} />
                <span className={cn(index === crumbs.length - 1 && 'text-ink-muted')}>
                  {t(`nav.${crumb}`) === `nav.${crumb}` ? crumb : t(`nav.${crumb}`)}
                </span>
              </li>
            ))}
          </ol>

          <div className="ms-auto flex items-center gap-1.5">
            <button
              onClick={() => setPalette(true)}
              className="hidden items-center gap-2 rounded-xl border border-line bg-surface-sunken px-3 py-1.5 text-xs text-ink-faint transition-colors hover:border-line-strong hover:text-ink-muted md:flex"
            >
              <Search size={14} />
              {t('app.search')}
              <kbd className="rounded border border-line px-1 font-mono text-[10px]">Ctrl K</kbd>
            </button>

            <div className="relative">
              <Button size="icon" variant="ghost" onClick={() => setBell((value) => !value)} aria-label={t('nav.notifications')}>
                <Bell size={17} />
                {unread ? (
                  <span className="absolute -end-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-pill bg-down px-1 text-[10px] font-bold text-ink-inverse">
                    {formatNumber(unread, digits)}
                  </span>
                ) : null}
              </Button>
              {bell ? (
                <div className="panel shadow-pop absolute end-0 top-11 z-30 w-[min(22rem,calc(100vw-2rem))] animate-fade-up">
                  <div className="hairline flex items-center justify-between px-4 py-2.5">
                    <p className="text-sm font-bold">{t('nav.notifications')}</p>
                    <button
                      className="text-xs text-accent hover:underline"
                      onClick={async () => {
                        await api.post('/notifications/read-all')
                        setBell(false)
                      }}
                    >
                      خواندن همه
                    </button>
                  </div>
                  <ul className="max-h-80 divide-y divide-line overflow-y-auto">
                    {(recent ?? []).map((item) => (
                      <li key={item.id} className={cn('px-4 py-3', !item.read && 'bg-accent-soft/20')}>
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-[13px] font-semibold leading-6">{item.title}</p>
                          <Badge tone={item.severity === 'critical' ? 'down' : item.severity === 'warning' ? 'degraded' : 'accent'}>
                            {item.severity}
                          </Badge>
                        </div>
                        {item.body ? <p className="mt-0.5 text-xs text-ink-muted">{item.body}</p> : null}
                        <p className="mt-1 text-[10px] text-ink-faint">{relativeTime(item.created_at, digits)}</p>
                      </li>
                    ))}
                    {!recent?.length ? (
                      <li className="px-4 py-8 text-center text-xs text-ink-faint">{t('empty.notifications')}</li>
                    ) : null}
                  </ul>
                  <div className="border-t border-line px-4 py-2.5 text-center">
                    <Link to="/notifications" className="text-xs text-accent hover:underline" onClick={() => setBell(false)}>
                      همه اعلان‌ها
                    </Link>
                  </div>
                </div>
              ) : null}
            </div>

            <Button size="icon" variant="ghost" onClick={toggleTheme} aria-label={t('settings.theme')}>
              {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
            </Button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 sm:py-8">
          <Outlet />
        </main>
      </div>

      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  )
}
