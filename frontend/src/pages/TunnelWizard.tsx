import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, ChevronLeft, ChevronRight, Rocket } from 'lucide-react'
import { api, errorDetails, errorMessage, type ConfigField, type Paged, type Server, type TunnelType } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { Badge, Button, Field, Input, Panel, Select, Switch, Textarea } from '@/components/ui'
import { cn } from '@/lib/utils'

const STEPS = ['نوع تونل', 'سرور مبدأ', 'سرور مقصد', 'پورت‌ها', 'پیکربندی', 'بازبینی', 'استقرار', 'بررسی سلامت']

export default function TunnelWizard() {
  const navigate = useNavigate()
  const toast = useToast()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [typeKey, setTypeKey] = useState('')
  const [source, setSource] = useState('')
  const [destination, setDestination] = useState('')
  const [config, setConfig] = useState<Record<string, unknown>>({ protocol: 'tcp', role_source: 'client', role_destination: 'server', reconnect: true })
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const [validation, setValidation] = useState<{ valid: boolean; errors: string[]; warnings: string[] } | null>(null)
  const [deploymentId, setDeploymentId] = useState<string | null>(null)

  const types = useQuery({ queryKey: ['tunnel-types'], queryFn: async () => (await api.get<TunnelType[]>('/tunnel-types')).data })
  const servers = useQuery({ queryKey: ['servers', 'all'], queryFn: async () => (await api.get<Paged<Server>>('/servers', { params: { per_page: 200 } })).data.items })

  const selectedType = useMemo(() => types.data?.find((item) => item.key === typeKey), [types.data, typeKey])
  const fields: ConfigField[] = selectedType?.config_schema ?? []
  const secrets = Object.fromEntries(Object.entries(config).filter(([key]) => fields.find((field) => field.key === key)?.secret)) as Record<string, string>
  const payload = { name, type_key: typeKey, source_server_id: source, destination_server_id: destination, config, secrets, deploy_now: true, dry_run: dryRun }

  const validate = useMutation({
    mutationFn: async () => (await api.post('/tunnels/validate', { ...payload, deploy_now: false })).data,
    onSuccess: (result) => setValidation(result),
    onError: (error) => toast.error('اعتبارسنجی ناموفق بود', errorMessage(error)),
  })

  const create = useMutation({
    mutationFn: async () => (await api.post('/tunnels', payload)).data,
    onSuccess: async (tunnel) => {
      toast.success(dryRun ? 'اجرای آزمایشی شروع شد' : 'استقرار تونل شروع شد')
      const deployments = (await api.get<Paged<{ id: string }>>('/deployments', { params: { tunnel_id: tunnel.id, per_page: 1 } })).data
      setDeploymentId(deployments.items[0]?.id ?? null)
      setStep(7)
    },
    onError: (error) => toast.error('ساخت تونل ناموفق بود', [errorMessage(error), ...errorDetails(error)].join(' · ')),
  })

  const canNext = [Boolean(typeKey && name.trim()), Boolean(source), Boolean(destination && destination !== source), true, true, true, true, true][step]

  const renderField = (field: ConfigField) => {
    if (field.advanced && !showAdvanced) return null
    const value = config[field.key] ?? field.default ?? ''
    const set = (next: unknown) => setConfig((prev) => ({ ...prev, [field.key]: next }))
    return (
      <Field key={field.key} label={field.label_fa} hint={field.help_fa} required={field.required} className={field.type === 'text' ? 'sm:col-span-2' : ''}>
        {field.type === 'select' ? (
          <Select value={String(value)} onChange={(event) => set(event.target.value)}>
            {field.options.map((option) => <option key={option} value={option}>{option}</option>)}
          </Select>
        ) : field.type === 'bool' ? (
          <Switch checked={Boolean(value)} onChange={set} />
        ) : field.type === 'text' ? (
          <Textarea value={String(value)} onChange={(event) => set(event.target.value)} rows={6} />
        ) : (
          <Input
            dir="ltr"
            type={field.type === 'secret' ? 'password' : field.type === 'int' || field.type === 'port' ? 'number' : 'text'}
            value={String(value)}
            onChange={(event) => set(field.type === 'int' || field.type === 'port' ? Number(event.target.value) : event.target.value)}
          />
        )}
      </Field>
    )
  }

  return (
    <>
      <header className="mb-6">
        <h1 className="text-[26px] font-extrabold sm:text-[30px]">ویزارد ساخت تونل</h1>
        <p className="mt-1 text-sm text-ink-muted">در ۸ مرحله تونل را بسازید، اعتبارسنجی کنید و مستقر کنید.</p>
      </header>

      <ol className="mb-5 flex flex-wrap gap-1.5 text-[11px]">
        {STEPS.map((label, index) => (
          <li key={label} className={cn(
            'flex items-center gap-1.5 rounded-pill border px-2.5 py-1',
            index === step ? 'border-accent bg-accent-soft/50 font-bold text-ink' : index < step ? 'border-up/40 text-up' : 'border-line text-ink-faint',
          )}>
            {index < step ? <Check size={11} /> : <span className="tabular">{index + 1}</span>}
            {label}
          </li>
        ))}
      </ol>

      <Panel>
        {step === 0 ? (
          <div className="space-y-4">
            <Field label="نام تونل" required><Input value={name} onChange={(event) => setName(event.target.value)} /></Field>
            <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
              {(types.data ?? []).map((item) => (
                <button
                  key={item.key}
                  onClick={() => setTypeKey(item.key)}
                  className={cn('rounded-xl border p-3.5 text-start transition-colors', typeKey === item.key ? 'border-accent bg-accent-soft/30' : 'border-line hover:border-line-strong')}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-bold">{item.display_name_fa}</p>
                    {item.configured ? <Badge tone="up">آماده</Badge> : <Badge tone="degraded">تنظیم‌نشده</Badge>}
                  </div>
                  <p className="mt-1.5 text-[11px] leading-6 text-ink-muted">{item.notes_fa}</p>
                  <p className="mt-1 text-[10px] text-ink-faint">منبع: {item.source_kind === 'binary' ? 'Binary' : 'Repository'}</p>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {step === 1 || step === 2 ? (
          <Field label={step === 1 ? 'سرور مبدأ' : 'سرور مقصد'} required hint="فقط سرورهایی که Agent فعال دارند قابل استفاده‌اند.">
            <Select
              value={step === 1 ? source : destination}
              onChange={(event) => (step === 1 ? setSource(event.target.value) : setDestination(event.target.value))}
            >
              <option value="">انتخاب کنید…</option>
              {(servers.data ?? []).map((server) => (
                <option key={server.id} value={server.id} disabled={step === 2 && server.id === source}>
                  {server.name} — {server.ip_address} {server.agent?.enrolled ? '' : '(بدون Agent)'}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}

        {step === 3 ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {fields.filter((field) => field.type === 'port' || field.key === 'protocol').map(renderField)}
          </div>
        ) : null}

        {step === 4 ? (
          <>
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm font-semibold">پیکربندی اختصاصی {selectedType?.display_name_fa}</p>
              <Switch checked={showAdvanced} onChange={setShowAdvanced} label="تنظیمات پیشرفته" />
            </div>
            <p className="mb-4 rounded-xl border border-line bg-surface-sunken px-3.5 py-3 text-xs leading-6 text-ink-muted">
              پنل هیچ آرگومان یا فرمت configی برای تونل حدس نمی‌زند. «قالب فایل Config» و «آرگومان‌های اجرا» را
              مطابق مستندات خود تونل وارد کنید؛ متغیرهایی مثل <code dir="ltr">$listen_port</code> و{' '}
              <code dir="ltr">$auth_token</code> جایگزین می‌شوند.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              {fields.filter((field) => field.type !== 'port').map(renderField)}
            </div>
          </>
        ) : null}

        {step === 5 ? (
          <div className="space-y-4">
            <dl className="grid gap-3 sm:grid-cols-2">
              {[
                ['نام', name],
                ['نوع', selectedType?.display_name_fa ?? '—'],
                ['مبدأ', servers.data?.find((item) => item.id === source)?.name ?? '—'],
                ['مقصد', servers.data?.find((item) => item.id === destination)?.name ?? '—'],
                ['پروتکل', String(config.protocol ?? '—')],
                ['پورت شنونده', String(config.listen_port ?? '—')],
                ['پورت مقصد', String(config.remote_port ?? '—')],
                ['وابستگی‌ها', (selectedType?.requires ?? []).join('، ') || '—'],
              ].map(([label, value]) => (
                <div key={label} className="flex items-baseline justify-between border-b border-line pb-2">
                  <dt className="text-xs text-ink-faint">{label}</dt>
                  <dd className="text-sm font-medium">{value}</dd>
                </div>
              ))}
            </dl>
            <Switch checked={dryRun} onChange={setDryRun} label="اجرای آزمایشی (هیچ تغییری روی سرورها اعمال نمی‌شود)" />
            <Button variant="secondary" loading={validate.isPending} onClick={() => validate.mutate()}>اعتبارسنجی تنظیمات</Button>
            {validation ? (
              <div className="space-y-2">
                {validation.errors.map((error) => (
                  <p key={error} className="rounded-xl border border-down/40 bg-down/10 px-3.5 py-2 text-xs text-down">{error}</p>
                ))}
                {validation.warnings.map((warning) => (
                  <p key={warning} className="rounded-xl border border-degraded/40 bg-degraded/10 px-3.5 py-2 text-xs text-degraded">{warning}</p>
                ))}
                {validation.valid ? <p className="rounded-xl border border-up/40 bg-up/10 px-3.5 py-2 text-xs text-up">تنظیمات معتبر است.</p> : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {step === 6 ? (
          <div className="py-6 text-center">
            <Rocket size={30} className="mx-auto mb-3 text-accent" />
            <p className="text-sm font-semibold">آماده استقرار</p>
            <p className="mx-auto mt-1.5 max-w-md text-xs leading-6 text-ink-muted">
              مراحل نصب، پیکربندی، راه‌اندازی سرویس و بررسی سلامت روی هر دو سرور اجرا می‌شود. در صورت خطا،
              سیستم تا حد امکان تغییرات را بازمی‌گرداند.
            </p>
            <Button className="mt-5" variant="primary" size="lg" loading={create.isPending} onClick={() => create.mutate()}>
              {dryRun ? 'اجرای آزمایشی' : 'شروع استقرار'}
            </Button>
          </div>
        ) : null}

        {step === 7 ? (
          <div className="py-6 text-center">
            <p className="text-sm font-semibold">استقرار شروع شد</p>
            <p className="mt-1.5 text-xs text-ink-muted">پیشرفت و لاگ زنده را در صفحه استقرارها ببینید.</p>
            <div className="mt-5 flex justify-center gap-2">
              <Button variant="primary" onClick={() => navigate(deploymentId ? `/deployments?id=${deploymentId}` : '/deployments')}>مشاهده پیشرفت</Button>
              <Button onClick={() => navigate('/tunnels')}>لیست تونل‌ها</Button>
            </div>
          </div>
        ) : null}

        {step < 6 ? (
          <div className="mt-6 flex justify-between border-t border-line pt-4">
            <Button variant="ghost" icon={<ChevronRight size={15} />} disabled={step === 0} onClick={() => setStep((value) => value - 1)}>قبلی</Button>
            <Button variant="primary" disabled={!canNext} onClick={() => setStep((value) => value + 1)}>
              بعدی <ChevronLeft size={15} />
            </Button>
          </div>
        ) : null}
      </Panel>
    </>
  )
}
