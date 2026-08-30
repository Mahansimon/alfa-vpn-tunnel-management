import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Activity, ArrowUpRight, Cpu, HardDrive, Network, Server, Wifi } from 'lucide-react'
import { api, type Dashboard as DashboardData } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { usePreferences } from '@/hooks/usePreferences'
import { useLiveMetrics } from '@/hooks/useLive'
import { useI18n } from '@/i18n'
import { Badge, Button, EmptyState, ErrorState, Panel, ProgressBar, Skeleton } from '@/components/ui'
import { HealthDonut, TrafficBars } from '@/components/charts'
import { formatBytes, formatDuration, formatNumber, formatPercent, formatRate, healthTone } from '@/lib/utils'

export default function Dashboard() {
  const { t } = useI18n()
  const { user } = useAuth()
  const { digits } = usePreferences()
  const { metrics, connected } = useLiveMetrics()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get<DashboardData>('/dashboard')).data,
    refetchInterval: connected ? 60000 : 15000,
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-64 lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </div>
    )
  }
  if (isError || !data) return <ErrorState message={t('errors.loadFailed')} onRetry={() => void refetch()} />

  const live = Object.values(metrics)
  const liveRx = live.reduce((sum, item) => sum + (item.rx_rate ?? 0), 0) || data.rx_rate
  const liveTx = live.reduce((sum, item) => sum + (item.tx_rate ?? 0), 0) || data.tx_rate

  if (!data.servers_total) {
    return (
      <>
        <h1 className="text-[28px] font-extrabold">{t('dashboard.greeting', { name: user?.full_name || user?.username || '' })}</h1>
        <Panel className="mt-6">
          <EmptyState
            icon={<Server size={30} />}
            title={t('servers.empty')}
            description={t('servers.emptyHint')}
            action={<Link to="/servers"><Button variant="primary">{t('servers.add')}</Button></Link>}
          />
        </Panel>
      </>
    )
  }

  return (
    <>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold leading-tight sm:text-[30px]">
            {t('dashboard.greeting', { name: user?.full_name || user?.username || '' })}
          </h1>
          <p className="mt-1 text-sm text-ink-muted">{t('dashboard.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={connected ? 'up' : 'degraded'} dot pulse={connected}>
            {connected ? 'اتصال زنده' : 'حالت بازخوانی دوره‌ای'}
          </Badge>
          {data.mock_mode ? <Badge tone="degraded">{t('dashboard.mockMode')}</Badge> : null}
        </div>
      </header>

      {/* نوار وضعیت: چیدمان نامتقارن، نه شبکه‌ای از کارت‌های یک‌شکل */}
      <section className="panel shadow-panel mb-4 grid divide-y divide-line md:grid-cols-[1.4fr_1fr_1fr] md:divide-x md:divide-y-0 md:rtl:divide-x-reverse">
        <div className="p-5">
          <p className="text-xs text-ink-faint">{t('dashboard.healthScore')}</p>
          <div className="mt-2 flex items-end gap-3">
            <span className="tabular text-4xl font-extrabold leading-none">{formatNumber(data.health_score, digits, 1)}</span>
            <span className="pb-1 text-xs text-ink-faint">/ ۱۰۰</span>
          </div>
          <ProgressBar value={data.health_score} tone={data.health_score > 75 ? 'up' : data.health_score > 45 ? 'degraded' : 'down'} />
          <p className="mt-2.5 text-[11px] text-ink-faint">
            {t('dashboard.uptime')}: {formatDuration(data.panel_uptime_seconds, digits)}
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-4 p-5">
          <div>
            <dt className="text-xs text-ink-faint">{t('dashboard.totalServers')}</dt>
            <dd className="tabular mt-1 text-2xl font-bold">{formatNumber(data.servers_total, digits)}</dd>
            <p className="mt-1 text-[11px]">
              <span className="text-up">{formatNumber(data.servers_online, digits)} {t('dashboard.online')}</span>
              {' · '}
              <span className="text-down">{formatNumber(data.servers_offline, digits)} {t('dashboard.offline')}</span>
            </p>
          </div>
          <div>
            <dt className="text-xs text-ink-faint">{t('dashboard.totalTunnels')}</dt>
            <dd className="tabular mt-1 text-2xl font-bold">{formatNumber(data.tunnels_total, digits)}</dd>
            <p className="mt-1 text-[11px]">
              <span className="text-up">{formatNumber(data.tunnels_active, digits)} فعال</span>
              {' · '}
              <span className="text-down">{formatNumber(data.tunnels_failed, digits)} مشکل‌دار</span>
            </p>
          </div>
        </dl>
        <dl className="grid grid-cols-2 gap-4 p-5">
          <div>
            <dt className="flex items-center gap-1.5 text-xs text-ink-faint"><Wifi size={12} /> {t('dashboard.download')}</dt>
            <dd className="tabular mt-1 text-lg font-bold">{formatRate(liveRx, digits)}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-xs text-ink-faint"><ArrowUpRight size={12} /> {t('dashboard.upload')}</dt>
            <dd className="tabular mt-1 text-lg font-bold">{formatRate(liveTx, digits)}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-faint">{t('dashboard.trafficToday')}</dt>
            <dd className="tabular mt-1 text-lg font-bold text-accent">{formatBytes(data.traffic_today_bytes, digits)}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-faint">{t('dashboard.trafficMonth')}</dt>
            <dd className="tabular mt-1 text-lg font-bold">{formatBytes(data.traffic_month_bytes, digits)}</dd>
          </div>
        </dl>
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title={t('dashboard.liveTraffic')} description="مجموع ترافیک همه سرورها در ۲۴ ساعت گذشته" className="lg:col-span-2">
          {data.traffic_series.length ? (
            <TrafficBars data={data.traffic_series} digits={digits} />
          ) : (
            <p className="py-12 text-center text-xs text-ink-faint">هنوز داده ترافیکی ثبت نشده است.</p>
          )}
        </Panel>

        <Panel title={t('dashboard.tunnelHealth')}>
          <HealthDonut data={data.tunnel_health_breakdown} />
          <ul className="mt-3 space-y-1.5 text-xs">
            {Object.entries(data.tunnel_health_breakdown).map(([key, value]) => (
              <li key={key} className="flex items-center justify-between">
                <Badge tone={healthTone(key) as 'up'} dot>{t(`states.${key}`)}</Badge>
                <span className="tabular font-semibold">{formatNumber(value, digits)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {[
          { label: t('dashboard.cpu'), value: data.cpu_avg, icon: Cpu },
          { label: t('dashboard.ram'), value: data.ram_avg, icon: Activity },
          { label: t('dashboard.disk'), value: data.disk_avg, icon: HardDrive },
        ].map((item) => (
          <div key={item.label} className="panel-quiet p-4">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 text-xs text-ink-faint"><item.icon size={13} /> {item.label}</p>
              <span className="tabular text-sm font-bold">{formatPercent(item.value, digits)}</span>
            </div>
            <div className="mt-2.5">
              <ProgressBar value={item.value} tone={item.value > 85 ? 'down' : item.value > 65 ? 'degraded' : 'accent'} />
            </div>
          </div>
        ))}
      </div>

      <Panel
        className="mt-4"
        title={t('dashboard.topServers')}
        action={<Link to="/servers" className="text-xs text-accent hover:underline">همه سرورها</Link>}
        bodyClassName="px-0 py-0"
      >
        <ul className="divide-y divide-line">
          {data.top_servers.map((server) => {
            const liveItem = metrics[server.id]
            const cpu = liveItem?.cpu_percent ?? server.cpu_percent
            return (
              <li key={server.id}>
                <Link to={`/servers/${server.id}`} className="flex items-center gap-4 px-5 py-3 transition-colors hover:bg-surface-overlay">
                  <Badge tone={healthTone(liveItem?.status ?? server.status) as 'up'} dot pulse>
                    {t(`states.${liveItem?.status ?? server.status}`)}
                  </Badge>
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold">{server.name}</span>
                  <span className="hidden text-xs text-ink-faint sm:block">{server.country}</span>
                  <span className="tabular w-16 text-end text-xs">{formatPercent(cpu, digits)}</span>
                  <span className="tabular hidden w-24 text-end text-xs text-ink-muted md:block">
                    {formatRate(liveItem?.rx_rate ?? server.rx_rate, digits)}
                  </span>
                  <Network size={14} className="text-ink-faint" />
                </Link>
              </li>
            )
          })}
        </ul>
      </Panel>
    </>
  )
}
