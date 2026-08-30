import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Server as ServerIcon, Trash2 } from 'lucide-react'
import { api, errorDetails, errorMessage, type Paged, type Server } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { usePreferences } from '@/hooks/usePreferences'
import { useDebouncedValue, useLiveMetrics } from '@/hooks/useLive'
import { useToast } from '@/hooks/useToast'
import { useI18n } from '@/i18n'
import {
  Badge, Button, ConfirmDialog, CopyField, DataTable, EmptyState, Field, Input, Modal,
  Pagination, Panel, Select, type Column,
} from '@/components/ui'
import { formatBytes, formatNumber, formatPercent, healthTone, relativeTime } from '@/lib/utils'

export default function Servers() {
  const { t } = useI18n()
  const { can } = useAuth()
  const { digits } = usePreferences()
  const toast = useToast()
  const client = useQueryClient()
  const navigate = useNavigate()
  const { metrics } = useLiveMetrics()

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const debounced = useDebouncedValue(search, 300)
  const [selected, setSelected] = useState<string[]>([])
  const [addOpen, setAddOpen] = useState(false)
  const [install, setInstall] = useState<{ command: string; token: string } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Server | null>(null)
  const [form, setForm] = useState({ name: '', ip_address: '', country: '', provider: '', agent_port: 9443, tags: '' })
  const [formErrors, setFormErrors] = useState<string[]>([])

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['servers', page, debounced, status],
    queryFn: async () =>
      (await api.get<Paged<Server>>('/servers', {
        params: { page, per_page: 20, search: debounced || undefined, status: status || undefined },
      })).data,
  })

  const create = useMutation({
    mutationFn: async () => {
      const payload = {
        ...form,
        agent_port: Number(form.agent_port),
        tags: form.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
      }
      return (await api.post('/servers', payload)).data
    },
    onSuccess: (result) => {
      setAddOpen(false)
      setForm({ name: '', ip_address: '', country: '', provider: '', agent_port: 9443, tags: '' })
      setFormErrors([])
      setInstall({ command: result.install_command, token: result.enrollment_token })
      toast.success('سرور ثبت شد', 'دستور نصب Agent را روی سرور اجرا کنید.')
      void client.invalidateQueries({ queryKey: ['servers'] })
    },
    onError: (error) => setFormErrors([errorMessage(error), ...errorDetails(error)]),
  })

  const remove = useMutation({
    mutationFn: async (id: string) => api.delete(`/servers/${id}`),
    onSuccess: () => {
      toast.success('سرور حذف شد')
      setDeleteTarget(null)
      void client.invalidateQueries({ queryKey: ['servers'] })
    },
    onError: (error) => toast.error('حذف ناموفق بود', errorMessage(error)),
  })

  const bulk = useMutation({
    mutationFn: async (action: string) => api.post('/servers/bulk', { ids: selected, action }),
    onSuccess: () => {
      toast.success('عملیات گروهی انجام شد')
      setSelected([])
      void refetch()
    },
    onError: (error) => toast.error('عملیات ناموفق بود', errorMessage(error)),
  })

  const columns: Column<Server>[] = [
    {
      key: 'name',
      header: t('servers.name'),
      sortable: true,
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate font-semibold">{row.name}</p>
          <code dir="ltr" className="font-mono text-[11px] text-ink-faint">{row.ip_address}</code>
        </div>
      ),
    },
    {
      key: 'status',
      header: t('servers.status'),
      render: (row) => {
        const liveStatus = metrics[row.id]?.status ?? row.status
        return <Badge tone={healthTone(liveStatus) as 'up'} dot pulse={liveStatus === 'online'}>{t(`states.${liveStatus}`)}</Badge>
      },
    },
    { key: 'country', header: t('servers.country'), hideOnMobile: true, render: (row) => row.country || '—' },
    {
      key: 'cpu',
      header: 'CPU',
      render: (row) => <span className="tabular text-xs">{formatPercent(metrics[row.id]?.cpu_percent ?? null, digits)}</span>,
    },
    {
      key: 'ram',
      header: 'RAM',
      hideOnMobile: true,
      render: (row) => (
        <span className="tabular text-xs">
          {formatPercent(metrics[row.id]?.ram_percent ?? null, digits)}
          <span className="text-ink-faint"> / {formatBytes(row.ram_total_bytes, digits, 0)}</span>
        </span>
      ),
    },
    {
      key: 'agent',
      header: t('servers.agent'),
      render: (row) =>
        row.agent?.enrolled ? (
          <span className="text-xs text-ink-muted">v{row.agent.version || '?'}</span>
        ) : (
          <Badge tone="degraded">{t('servers.agentMissing')}</Badge>
        ),
    },
    {
      key: 'seen',
      header: t('servers.lastSeen'),
      hideOnMobile: true,
      render: (row) => <span className="text-xs text-ink-faint">{relativeTime(row.last_seen_at, digits)}</span>,
    },
    {
      key: 'actions',
      header: '',
      render: (row) =>
        can('servers.delete') ? (
          <Button
            size="icon"
            variant="ghost"
            onClick={(event) => {
              event.stopPropagation()
              setDeleteTarget(row)
            }}
            title={t('app.delete')}
          >
            <Trash2 size={15} className="text-down" />
          </Button>
        ) : null,
    },
  ]

  return (
    <>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold sm:text-[30px]">{t('nav.servers')}</h1>
          <p className="mt-1 text-sm text-ink-muted">
            مدیریت سرورها، نصب Agent و پایش زنده منابع
          </p>
        </div>
        {can('servers.write') ? (
          <Button variant="primary" icon={<Plus size={16} />} onClick={() => setAddOpen(true)}>
            {t('servers.add')}
          </Button>
        ) : null}
      </header>

      <Panel bodyClassName="px-0 pb-0 pt-0">
        <div className="flex flex-wrap items-center gap-2.5 px-5 py-4">
          <Input
            placeholder="جستجو بر اساس نام، IP یا کشور…"
            value={search}
            onChange={(event) => { setSearch(event.target.value); setPage(1) }}
            className="max-w-xs"
          />
          <Select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }} className="max-w-[10rem]">
            <option value="">همه وضعیت‌ها</option>
            <option value="online">{t('states.online')}</option>
            <option value="offline">{t('states.offline')}</option>
            <option value="maintenance">{t('states.maintenance')}</option>
            <option value="pending">{t('states.pending')}</option>
          </Select>
          {selected.length ? (
            <div className="ms-auto flex items-center gap-2">
              <span className="text-xs text-ink-faint">{formatNumber(selected.length, digits)} انتخاب‌شده</span>
              <Button size="sm" onClick={() => bulk.mutate('maintenance_on')}>نگهداری</Button>
              <Button size="sm" onClick={() => bulk.mutate('maintenance_off')}>خروج از نگهداری</Button>
              <Button size="sm" onClick={() => bulk.mutate('restart')}>ری‌استارت Agent</Button>
            </div>
          ) : null}
        </div>

        <div className="px-5 pb-4">
          <DataTable
            columns={columns}
            rows={data?.items ?? []}
            loading={isLoading}
            selectable={can('servers.write')}
            selected={selected}
            onSelectedChange={setSelected}
            onRowClick={(row) => navigate(`/servers/${row.id}`)}
            empty={
              <EmptyState
                icon={<ServerIcon size={28} />}
                title={t('servers.empty')}
                description={t('servers.emptyHint')}
                action={can('servers.write') ? <Button variant="primary" onClick={() => setAddOpen(true)}>{t('servers.add')}</Button> : undefined}
              />
            }
            mobileCard={(row) => (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate font-semibold">{row.name}</p>
                  <Badge tone={healthTone(metrics[row.id]?.status ?? row.status) as 'up'} dot>
                    {t(`states.${metrics[row.id]?.status ?? row.status}`)}
                  </Badge>
                </div>
                <code dir="ltr" className="block font-mono text-[11px] text-ink-faint">{row.ip_address}</code>
                <p className="text-xs text-ink-muted">
                  CPU {formatPercent(metrics[row.id]?.cpu_percent ?? null, digits)} · RAM{' '}
                  {formatPercent(metrics[row.id]?.ram_percent ?? null, digits)}
                </p>
              </div>
            )}
          />
          {data ? <Pagination page={data.page} pages={data.pages} total={data.total} onChange={setPage} /> : null}
        </div>
      </Panel>

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title={t('servers.add')}
        description="بعد از ثبت، دستور نصب Agent به شما داده می‌شود."
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>{t('app.cancel')}</Button>
            <Button variant="primary" loading={create.isPending} onClick={() => create.mutate()}>{t('app.create')}</Button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('servers.name')} required className="sm:col-span-2">
            <Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          </Field>
          <Field label={t('servers.ip')} required hint="IPv4 یا IPv6">
            <Input dir="ltr" value={form.ip_address} onChange={(event) => setForm({ ...form, ip_address: event.target.value })} />
          </Field>
          <Field label={t('servers.agentPort')}>
            <Input dir="ltr" type="number" value={form.agent_port} onChange={(event) => setForm({ ...form, agent_port: Number(event.target.value) })} />
          </Field>
          <Field label={t('servers.country')}>
            <Input value={form.country} onChange={(event) => setForm({ ...form, country: event.target.value })} />
          </Field>
          <Field label={t('servers.provider')}>
            <Input value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })} />
          </Field>
          <Field label={t('servers.tags')} hint="با کاما جدا کنید: iran, production" className="sm:col-span-2">
            <Input value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} />
          </Field>
        </div>
        {formErrors.length ? (
          <ul className="mt-4 space-y-1 rounded-xl border border-down/40 bg-down/10 px-3.5 py-2.5 text-xs text-down">
            {formErrors.filter(Boolean).map((item) => <li key={item}>{item}</li>)}
          </ul>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(install)}
        onClose={() => setInstall(null)}
        title={t('servers.installCommand')}
        description={t('servers.installHint')}
        size="lg"
        footer={<Button variant="primary" onClick={() => setInstall(null)}>متوجه شدم</Button>}
      >
        <CopyField label="دستور نصب (روی سرور مقصد اجرا کنید)" value={install?.command ?? ''} multiline />
        <div className="mt-4">
          <CopyField label="توکن نصب (فقط یک بار نمایش داده می‌شود)" value={install?.token ?? ''} />
        </div>
        <p className="mt-4 rounded-xl border border-line bg-surface-sunken px-3.5 py-3 text-xs leading-6 text-ink-muted">
          پس از اجرای دستور، Agent خودش را ثبت می‌کند و وضعیت سرور به «آنلاین» تغییر می‌کند. اگر توکن منقضی شد،
          از صفحه جزئیات سرور توکن جدید بگیرید.
        </p>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && remove.mutate(deleteTarget.id)}
        title="حذف سرور"
        message={`${t('servers.deleteWarning')} سرور: ${deleteTarget?.name ?? ''}`}
        confirmLabel="حذف سرور"
        danger
        requireText={deleteTarget?.name}
        loading={remove.isPending}
      />
    </>
  )
}
