import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Network, Play, Plus, RotateCw, Square, Trash2 } from 'lucide-react'
import { api, errorMessage, type Paged, type Tunnel, type TunnelType } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { usePreferences } from '@/hooks/usePreferences'
import { useToast } from '@/hooks/useToast'
import { useI18n } from '@/i18n'
import { Badge, Button, ConfirmDialog, DataTable, EmptyState, Pagination, Panel, Select, type Column } from '@/components/ui'
import { formatMs, formatNumber, healthTone } from '@/lib/utils'

const HEALTH_ICON: Record<string, string> = { up: '🟢', degraded: '🟡', down: '🔴', unknown: '⚪' }

export default function Tunnels() {
  const { t } = useI18n()
  const { can } = useAuth()
  const { digits } = usePreferences()
  const toast = useToast()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [typeKey, setTypeKey] = useState('')
  const [health, setHealth] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [deleteTarget, setDeleteTarget] = useState<Tunnel | null>(null)

  const types = useQuery({ queryKey: ['tunnel-types'], queryFn: async () => (await api.get<TunnelType[]>('/tunnel-types')).data })
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['tunnels', page, typeKey, health],
    queryFn: async () =>
      (await api.get<Paged<Tunnel>>('/tunnels', { params: { page, per_page: 20, type_key: typeKey || undefined, health: health || undefined } })).data,
    refetchInterval: 30000,
  })

  const act = useMutation({
    mutationFn: async ({ id, action }: { id: string; action: string }) => api.post(`/tunnels/${id}/actions/${action}`),
    onSuccess: () => { toast.success('دستور اجرا شد'); void refetch() },
    onError: (error) => toast.error('اجرا ناموفق بود', errorMessage(error)),
  })
  const remove = useMutation({
    mutationFn: async (id: string) => api.delete(`/tunnels/${id}`),
    onSuccess: () => { toast.success('تونل حذف شد'); setDeleteTarget(null); void client.invalidateQueries({ queryKey: ['tunnels'] }) },
    onError: (error) => toast.error('حذف ناموفق بود', errorMessage(error)),
  })
  const bulk = useMutation({
    mutationFn: async (action: string) => api.post('/tunnels/bulk', { ids: selected, action }),
    onSuccess: () => { toast.success('عملیات گروهی انجام شد'); setSelected([]); void refetch() },
    onError: (error) => toast.error('عملیات ناموفق بود', errorMessage(error)),
  })

  const columns: Column<Tunnel>[] = [
    {
      key: 'name', header: 'نام تونل',
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate font-semibold">{HEALTH_ICON[row.health]} {row.name}</p>
          <p className="truncate text-[11px] text-ink-faint">
            {row.source_server_name} ← {row.destination_server_name}
          </p>
        </div>
      ),
    },
    { key: 'type', header: 'نوع', hideOnMobile: true, render: (row) => types.data?.find((item) => item.key === row.type_key)?.display_name_fa ?? row.type_key },
    { key: 'state', header: 'وضعیت', render: (row) => <Badge tone={row.state === 'deployed' ? 'up' : row.state === 'failed' ? 'down' : 'neutral'}>{t(`states.${row.state}`)}</Badge> },
    { key: 'health', header: 'سلامت', render: (row) => <Badge tone={healthTone(row.health) as 'up'} dot>{t(`states.${row.health}`)}</Badge> },
    { key: 'latency', header: 'تأخیر', hideOnMobile: true, render: (row) => <span className="tabular text-xs">{formatMs(row.latency_ms, digits)}</span> },
    {
      key: 'actions', header: '',
      render: (row) => can('tunnels.modify') ? (
        <div className="flex gap-1" onClick={(event) => event.stopPropagation()}>
          <Button size="icon" variant="ghost" title={t('tunnels.start')} onClick={() => act.mutate({ id: row.id, action: 'start' })}><Play size={14} /></Button>
          <Button size="icon" variant="ghost" title={t('tunnels.stop')} onClick={() => act.mutate({ id: row.id, action: 'stop' })}><Square size={14} /></Button>
          <Button size="icon" variant="ghost" title={t('tunnels.restart')} onClick={() => act.mutate({ id: row.id, action: 'restart' })}><RotateCw size={14} /></Button>
          {can('tunnels.delete') ? (
            <Button size="icon" variant="ghost" title={t('app.delete')} onClick={() => setDeleteTarget(row)}><Trash2 size={14} className="text-down" /></Button>
          ) : null}
        </div>
      ) : null,
    },
  ]

  const unconfigured = (types.data ?? []).filter((item) => !item.configured)

  return (
    <>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold sm:text-[30px]">{t('nav.tunnels')}</h1>
          <p className="mt-1 text-sm text-ink-muted">ساخت، کنترل و پایش تونل‌ها بین سرورها</p>
        </div>
        {can('tunnels.create') ? (
          <Link to="/tunnels/new"><Button variant="primary" icon={<Plus size={16} />}>{t('tunnels.add')}</Button></Link>
        ) : null}
      </header>

      {unconfigured.length ? (
        <Panel className="mb-4" title="تونل‌های تنظیم‌نشده" description="برای این تونل‌ها مسیر Binary یا آدرس Repository وارد نشده است.">
          <ul className="flex flex-wrap gap-2">
            {unconfigured.map((item) => (
              <li key={item.key}>
                <Link to="/settings?tab=tunnel" className="inline-flex items-center gap-2 rounded-pill border border-degraded/40 bg-degraded/10 px-3 py-1 text-xs font-semibold text-degraded hover:bg-degraded/20">
                  {item.display_name_fa} · {t('tunnels.configure')}
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <Panel bodyClassName="px-0 pb-0 pt-0">
        <div className="flex flex-wrap items-center gap-2.5 px-5 py-4">
          <Select value={typeKey} onChange={(event) => { setTypeKey(event.target.value); setPage(1) }} className="max-w-[12rem]">
            <option value="">همه انواع</option>
            {(types.data ?? []).map((item) => <option key={item.key} value={item.key}>{item.display_name_fa}</option>)}
          </Select>
          <Select value={health} onChange={(event) => { setHealth(event.target.value); setPage(1) }} className="max-w-[10rem]">
            <option value="">همه وضعیت‌ها</option>
            <option value="up">{t('states.up')}</option>
            <option value="degraded">{t('states.degraded')}</option>
            <option value="down">{t('states.down')}</option>
            <option value="unknown">{t('states.unknown')}</option>
          </Select>
          {selected.length ? (
            <div className="ms-auto flex items-center gap-2">
              <span className="text-xs text-ink-faint">{formatNumber(selected.length, digits)} انتخاب‌شده</span>
              <Button size="sm" onClick={() => bulk.mutate('start')}>شروع</Button>
              <Button size="sm" onClick={() => bulk.mutate('stop')}>توقف</Button>
              <Button size="sm" onClick={() => bulk.mutate('restart')}>ری‌استارت</Button>
            </div>
          ) : null}
        </div>
        <div className="px-5 pb-4">
          <DataTable
            columns={columns}
            rows={data?.items ?? []}
            loading={isLoading}
            selectable={can('tunnels.modify')}
            selected={selected}
            onSelectedChange={setSelected}
            onRowClick={(row) => navigate(`/tunnels/${row.id}`)}
            empty={<EmptyState icon={<Network size={28} />} title={t('tunnels.empty')} description={t('tunnels.emptyHint')} action={can('tunnels.create') ? <Link to="/tunnels/new"><Button variant="primary">{t('tunnels.add')}</Button></Link> : undefined} />}
            mobileCard={(row) => (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate font-semibold">{HEALTH_ICON[row.health]} {row.name}</p>
                  <Badge tone={healthTone(row.health) as 'up'}>{t(`states.${row.health}`)}</Badge>
                </div>
                <p className="text-xs text-ink-muted">{row.source_server_name} ← {row.destination_server_name}</p>
                <p className="tabular text-xs text-ink-faint">{formatMs(row.latency_ms, digits)}</p>
              </div>
            )}
          />
          {data ? <Pagination page={data.page} pages={data.pages} total={data.total} onChange={setPage} /> : null}
        </div>
      </Panel>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && remove.mutate(deleteTarget.id)}
        title="حذف تونل"
        message={`${t('tunnels.deleteWarning')} تونل: ${deleteTarget?.name ?? ''}`}
        confirmLabel="حذف تونل"
        danger
        requireText={deleteTarget?.name}
        loading={remove.isPending}
      />
    </>
  )
}
