import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { RefreshCw, Wrench } from 'lucide-react'
import { api, errorMessage, type MetricPoint, type Server } from '@/lib/api'
import { usePreferences } from '@/hooks/usePreferences'
import { useToast } from '@/hooks/useToast'
import { useI18n } from '@/i18n'
import { Badge, Button, CopyField, EmptyState, ErrorState, KeyValue, Panel, Select, Skeleton, TabPanel, Tabs } from '@/components/ui'
import { NetworkChart, UsageChart } from '@/components/charts'
import { formatBytes, formatDuration, formatPercent, healthTone, relativeTime } from '@/lib/utils'
import { Stat, LevelBadge } from './_shared'

interface MetricsResponse {
  points: MetricPoint[]
  latest: Record<string, number>
  system: Record<string, string | number | null>
}

export default function ServerDetail() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const { digits } = usePreferences()
  const toast = useToast()
  const [tab, setTab] = useState('overview')
  const [range, setRange] = useState('1h')
  const [token, setToken] = useState('')

  const server = useQuery({ queryKey: ['server', id], queryFn: async () => (await api.get<Server>(`/servers/${id}`)).data })
  const metrics = useQuery({
    queryKey: ['server-metrics', id, range],
    queryFn: async () => (await api.get<MetricsResponse>(`/servers/${id}/metrics`, { params: { range } })).data,
    refetchInterval: 20000,
  })
  const events = useQuery({
    queryKey: ['server-events', id],
    queryFn: async () => (await api.get<{ id: string; kind: string; title: string; detail: string; severity: string; created_at: string }[]>(`/servers/${id}/events`)).data,
    enabled: tab === 'events',
  })
  const processes = useQuery({
    queryKey: ['server-processes', id],
    queryFn: async () => (await api.get<{ items: { pid: string; name: string; cpu: string; memory: string; elapsed: string }[] }>(`/servers/${id}/processes`)).data,
    enabled: tab === 'processes',
    retry: false,
  })
  const logs = useQuery({
    queryKey: ['server-logs', id],
    queryFn: async () => (await api.get<{ items: { id: string; ts: string; level: string; source: string; message: string }[] }>('/logs', { params: { server_id: id, per_page: 100 } })).data,
    enabled: tab === 'logs',
  })

  const action = useMutation({
    mutationFn: async (name: string) => (await api.post(`/servers/${id}/actions/${name}`)).data,
    onSuccess: (result) => {
      if (result.ok) toast.success('انجام شد', result.output?.slice(0, 160) || undefined)
      else toast.error('ناموفق', result.error || undefined)
      void metrics.refetch()
      void server.refetch()
    },
    onError: (error) => toast.error('ارتباط با Agent برقرار نشد', errorMessage(error)),
  })

  const newToken = useMutation({
    mutationFn: async () => (await api.post<{ install_command: string }>(`/servers/${id}/enrollment-token`)).data,
    onSuccess: (result) => setToken(result.install_command),
  })

  if (server.isLoading) return <Skeleton className="h-64" />
  if (server.isError || !server.data) return <ErrorState message={t('errors.loadFailed')} onRetry={() => void server.refetch()} />

  const row = server.data
  const latest = metrics.data?.latest ?? {}

  return (
    <>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-[26px] font-extrabold sm:text-[30px]">{row.name}</h1>
            <Badge tone={healthTone(row.status) as 'up'} dot pulse={row.status === 'online'}>{t(`states.${row.status}`)}</Badge>
          </div>
          <p className="mt-1 font-mono text-xs text-ink-faint" dir="ltr">
            {row.ip_address} · {row.operating_system || '—'} · {row.architecture || '—'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button icon={<RefreshCw size={15} />} loading={action.isPending} onClick={() => action.mutate('refresh')}>
            بازخوانی اطلاعات
          </Button>
          <Button icon={<Wrench size={15} />} onClick={() => action.mutate('ping')}>تست ارتباط</Button>
          {!row.agent?.enrolled ? (
            <Button variant="primary" loading={newToken.isPending} onClick={() => newToken.mutate()}>
              {t('servers.installAgent')}
            </Button>
          ) : null}
        </div>
      </header>

      {token ? (
        <Panel className="mb-4" title={t('servers.installCommand')} description={t('servers.installHint')}>
          <CopyField value={token} multiline />
        </Panel>
      ) : null}

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="CPU" value={formatPercent(latest.cpu_percent ?? 0, digits)} />
        <Stat label="RAM" value={`${formatBytes(latest.ram_used ?? 0, digits, 1)} / ${formatBytes(latest.ram_total ?? 0, digits, 0)}`} />
        <Stat label="دیسک" value={`${formatBytes(latest.disk_used ?? 0, digits, 1)} / ${formatBytes(latest.disk_total ?? 0, digits, 0)}`} />
        <Stat label="مدت روشن بودن" value={formatDuration(latest.uptime_seconds ?? row.uptime_seconds ?? 0, digits)} />
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: 'overview', label: t('servers.overview') },
          { value: 'metrics', label: t('servers.metrics') },
          { value: 'network', label: t('servers.network') },
          { value: 'processes', label: t('servers.processes') },
          { value: 'logs', label: t('nav.logs') },
          { value: 'events', label: t('servers.events') },
        ]}
      >
        <TabPanel value="overview">
          <Panel title="مشخصات سیستم">
            <KeyValue
              items={[
                { label: 'Hostname', value: row.hostname || '—' },
                { label: 'سیستم‌عامل', value: row.operating_system || '—' },
                { label: 'Kernel', value: row.kernel || '—' },
                { label: 'معماری', value: row.architecture || '—' },
                { label: 'CPU', value: `${row.cpu_model || '—'} (${row.cpu_cores ?? '—'} هسته)` },
                { label: 'RAM کل', value: formatBytes(row.ram_total_bytes, digits, 0) },
                { label: 'IP عمومی', value: row.ip_address },
                { label: 'IP داخلی', value: row.private_ip || '—' },
                { label: 'کشور / منطقه', value: `${row.country || '—'} ${row.region ? `· ${row.region}` : ''}` },
                { label: 'ارائه‌دهنده', value: row.provider || '—' },
                { label: 'نسخه Agent', value: row.agent?.enrolled ? `v${row.agent.version}` : t('servers.agentMissing') },
                { label: 'آخرین Heartbeat', value: relativeTime(row.agent?.last_heartbeat_at ?? row.last_seen_at, digits) },
                { label: 'امتیاز سلامت', value: `${row.health_score}` },
                { label: 'برچسب‌ها', value: row.tags.join('، ') || '—' },
              ]}
            />
          </Panel>
        </TabPanel>

        <TabPanel value="metrics">
          <Panel
            title="مصرف منابع"
            action={
              <Select value={range} onChange={(event) => setRange(event.target.value)} className="h-8 w-28 text-xs">
                <option value="1h">۱ ساعت</option>
                <option value="6h">۶ ساعت</option>
                <option value="24h">۲۴ ساعت</option>
                <option value="7d">۷ روز</option>
                <option value="30d">۳۰ روز</option>
              </Select>
            }
          >
            {metrics.data?.points.length ? <UsageChart data={metrics.data.points} digits={digits} height={280} /> : <EmptyState title="داده متریکی ثبت نشده است." description="اگر Agent تازه نصب شده، چند دقیقه صبر کنید." />}
          </Panel>
        </TabPanel>

        <TabPanel value="network">
          <Panel title="ترافیک شبکه">
            {metrics.data?.points.length ? <NetworkChart data={metrics.data.points} digits={digits} height={280} /> : <EmptyState title="داده شبکه‌ای موجود نیست." />}
          </Panel>
        </TabPanel>

        <TabPanel value="processes">
          <Panel title="پروسه‌های فعال" description="پرمصرف‌ترین پروسه‌ها بر اساس CPU">
            {processes.isError ? (
              <ErrorState message="دریافت پروسه‌ها ناموفق بود؛ Agent در دسترس نیست." onRetry={() => void processes.refetch()} />
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] uppercase text-ink-faint">
                    <th className="py-2 text-start">PID</th><th className="py-2 text-start">نام</th>
                    <th className="py-2 text-start">CPU</th><th className="py-2 text-start">RAM</th><th className="py-2 text-start">مدت</th>
                  </tr>
                </thead>
                <tbody>
                  {(processes.data?.items ?? []).map((item) => (
                    <tr key={item.pid} className="border-t border-line">
                      <td className="py-2 font-mono text-xs">{item.pid}</td>
                      <td className="py-2">{item.name}</td>
                      <td className="tabular py-2">{item.cpu}٪</td>
                      <td className="tabular py-2">{item.memory}٪</td>
                      <td className="py-2 font-mono text-xs">{item.elapsed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </TabPanel>

        <TabPanel value="logs">
          <Panel title="لاگ‌های سرور">
            <div className="max-h-[28rem] space-y-1.5 overflow-y-auto font-mono text-xs" dir="ltr">
              {(logs.data?.items ?? []).map((item) => (
                <p key={item.id} className="flex gap-2 border-b border-line pb-1.5">
                  <span className="text-ink-faint">{item.ts.slice(11, 19)}</span>
                  <LevelBadge level={item.level} />
                  <span className="flex-1 break-all">{item.message}</span>
                </p>
              ))}
              {!logs.data?.items.length ? <p className="py-8 text-center text-ink-faint">{t('empty.logs')}</p> : null}
            </div>
          </Panel>
        </TabPanel>

        <TabPanel value="events">
          <Panel title="خط زمانی رخدادها">
            <ul className="space-y-3">
              {(events.data ?? []).map((event) => (
                <li key={event.id} className="border-b border-line pb-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold">{event.title}</p>
                    <Badge tone={event.severity === 'critical' ? 'down' : event.severity === 'warning' ? 'degraded' : 'neutral'}>{event.severity}</Badge>
                  </div>
                  {event.detail ? <p className="mt-1 text-xs text-ink-muted">{event.detail}</p> : null}
                  <p className="mt-1 text-[11px] text-ink-faint">{relativeTime(event.created_at, digits)}</p>
                </li>
              ))}
              {!events.data?.length ? <p className="py-8 text-center text-xs text-ink-faint">رخدادی ثبت نشده است.</p> : null}
            </ul>
          </Panel>
        </TabPanel>
      </Tabs>
    </>
  )
}
