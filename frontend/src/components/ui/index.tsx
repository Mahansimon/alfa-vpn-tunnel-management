/**
 * مجموعه کامپوننت‌های پایه پنل.
 * همه با Tailwind و توکن‌های رنگ OKLCH ساخته شده‌اند، RTL-first و دسترس‌پذیر.
 */
import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { AlertCircle, Check, ChevronLeft, ChevronRight, Copy, Loader2, X } from 'lucide-react'
import { cn } from '@/lib/utils'

/* ------------------------------- Button ------------------------------- */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'quiet'
type Size = 'sm' | 'md' | 'lg' | 'icon'

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-accent text-ink-inverse hover:bg-accent-strong active:translate-y-px disabled:bg-accent-soft disabled:text-ink-faint',
  secondary:
    'bg-surface-overlay text-ink border border-line-strong hover:border-accent hover:text-accent',
  ghost: 'text-ink-muted hover:bg-surface-overlay hover:text-ink',
  danger: 'bg-down text-ink-inverse hover:opacity-90',
  quiet: 'text-ink-faint hover:text-ink',
}

const SIZES: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-lg',
  md: 'h-10 px-4 text-sm gap-2 rounded-xl',
  lg: 'h-12 px-6 text-base gap-2.5 rounded-xl',
  icon: 'h-9 w-9 rounded-lg justify-center',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cn(
        'inline-flex select-none items-center font-semibold transition-[background-color,border-color,color,transform] duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-70',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
    >
      {loading ? <Loader2 size={15} className="animate-spin" /> : icon}
      {children}
    </button>
  )
}

/* -------------------------------- Field -------------------------------- */

export function Field({
  label,
  hint,
  error,
  required,
  children,
  className,
}: {
  label?: string
  hint?: string
  error?: string
  required?: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <label className={cn('block', className)}>
      {label ? (
        <span className="mb-1.5 flex items-center gap-1 text-[13px] font-medium text-ink-muted">
          {label}
          {required ? <span className="text-down">*</span> : null}
        </span>
      ) : null}
      {children}
      {error ? (
        <span className="mt-1.5 flex items-center gap-1 text-xs text-down">
          <AlertCircle size={12} /> {error}
        </span>
      ) : hint ? (
        <span className="mt-1.5 block text-xs leading-6 text-ink-faint">{hint}</span>
      ) : null}
    </label>
  )
}

const CONTROL =
  'w-full bg-surface-sunken border border-line rounded-xl px-3.5 h-10 text-sm text-ink placeholder:text-ink-faint transition-colors duration-150 hover:border-line-strong focus:border-accent focus:outline-none disabled:opacity-60'

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cn(CONTROL, className)} />
}

export function Textarea({ className, rows = 4, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      rows={rows}
      className={cn(CONTROL, 'h-auto py-2.5 font-mono text-xs leading-6', className)}
      dir="ltr"
    />
  )
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={cn(CONTROL, 'cursor-pointer appearance-none pe-9', className)}>
      {children}
    </select>
  )
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label?: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2.5 text-sm disabled:opacity-60"
    >
      <span
        className={cn(
          'relative h-5 w-9 rounded-pill border transition-colors duration-200 ease-out',
          checked ? 'border-accent bg-accent' : 'border-line-strong bg-surface-sunken',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 h-4 w-4 rounded-full bg-surface-raised transition-transform duration-200 ease-out',
            checked ? 'end-0.5' : 'end-4',
          )}
        />
      </span>
      {label ? <span className="text-ink-muted">{label}</span> : null}
    </button>
  )
}

/* ------------------------------- Badges ------------------------------- */

type Tone = 'up' | 'degraded' | 'down' | 'unknown' | 'accent' | 'neutral'

const TONE_STYLES: Record<Tone, string> = {
  up: 'text-up border-up/35 bg-up/10',
  degraded: 'text-degraded border-degraded/35 bg-degraded/10',
  down: 'text-down border-down/35 bg-down/10',
  unknown: 'text-ink-faint border-line-strong bg-surface-sunken',
  accent: 'text-accent border-accent/40 bg-accent/10',
  neutral: 'text-ink-muted border-line bg-surface-sunken',
}

export function Badge({
  tone = 'neutral',
  children,
  className,
  dot = false,
  pulse = false,
}: {
  tone?: Tone
  children: ReactNode
  className?: string
  dot?: boolean
  pulse?: boolean
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-[11px] font-semibold',
        TONE_STYLES[tone],
        className,
      )}
    >
      {dot ? (
        <span className={cn('h-1.5 w-1.5 rounded-full bg-current', pulse && 'animate-pulse-dot')} />
      ) : null}
      {children}
    </span>
  )
}

/* -------------------------------- Panels ------------------------------- */

export function Panel({
  title,
  description,
  action,
  children,
  className,
  bodyClassName,
  quiet = false,
}: {
  title?: ReactNode
  description?: string
  action?: ReactNode
  children?: ReactNode
  className?: string
  bodyClassName?: string
  quiet?: boolean
}) {
  return (
    <section className={cn(quiet ? 'panel-quiet' : 'panel shadow-panel', 'overflow-hidden', className)}>
      {title || action ? (
        <header className="hairline flex items-start justify-between gap-4 px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-[15px] font-bold">{title}</h2>
            {description ? <p className="mt-0.5 text-xs text-ink-faint">{description}</p> : null}
          </div>
          {action}
        </header>
      ) : null}
      <div className={cn('px-5 py-4', bodyClassName)}>{children}</div>
    </section>
  )
}

export function PageHeader({
  title,
  description,
  actions,
  children,
}: {
  title: string
  description?: string
  actions?: ReactNode
  children?: ReactNode
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[26px] font-extrabold leading-tight tracking-tight sm:text-[30px]">{title}</h1>
        {description ? <p className="mt-1 text-sm text-ink-muted">{description}</p> : null}
        {children}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  )
}

/* ------------------------------- States ------------------------------- */

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden rounded-lg bg-surface-overlay', className)}>
      <div className="absolute inset-0 animate-shimmer bg-gradient-to-l from-transparent via-white/5 to-transparent" />
    </div>
  )
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className={cn('h-11', index % 3 === 1 && 'opacity-80')} />
      ))}
    </div>
  )
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon ? <div className="mb-4 text-ink-faint">{icon}</div> : null}
      <p className="text-base font-bold">{title}</p>
      {description ? <p className="mt-1.5 max-w-md text-sm text-ink-muted">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <AlertCircle size={26} className="mb-3 text-down" />
      <p className="text-sm font-semibold">{message}</p>
      {onRetry ? (
        <Button className="mt-4" size="sm" onClick={onRetry}>
          تلاش مجدد
        </Button>
      ) : null}
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('animate-spin text-accent', className)} size={18} />
}

export function ProgressBar({ value, tone = 'accent' }: { value: number; tone?: Tone }) {
  const clamped = Math.max(0, Math.min(100, value))
  const color =
    tone === 'down'
      ? 'bg-down'
      : tone === 'degraded'
        ? 'bg-degraded'
        : tone === 'up'
          ? 'bg-up'
          : 'bg-accent'
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-pill bg-surface-sunken">
      <div
        className={cn('h-full rounded-pill transition-[width] duration-500 ease-out', color)}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}

/* -------------------------------- Modal -------------------------------- */

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}) {
  useEffect(() => {
    if (!open) return
    const handler = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    document.addEventListener('keydown', handler)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handler)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null
  const widths = { sm: 'max-w-md', md: 'max-w-xl', lg: 'max-w-3xl', xl: 'max-w-5xl' }
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center p-0 sm:items-center sm:p-6">
      <div
        className="absolute inset-0 bg-surface-sunken/80"
        onClick={onClose}
        role="presentation"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'panel shadow-pop relative z-10 max-h-[92vh] w-full animate-fade-up overflow-hidden rounded-b-none sm:rounded-panel',
          widths[size],
        )}
      >
        <header className="hairline flex items-start justify-between gap-4 px-5 py-4">
          <div>
            <h2 className="text-base font-bold">{title}</h2>
            {description ? <p className="mt-0.5 text-xs text-ink-faint">{description}</p> : null}
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-ink-faint hover:text-ink" aria-label="بستن">
            <X size={16} />
          </button>
        </header>
        <div className="max-h-[calc(92vh-9rem)] overflow-y-auto px-5 py-4">{children}</div>
        {footer ? <footer className="flex justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</footer> : null}
      </div>
    </div>
  )
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'تأیید و انجام',
  danger = false,
  requireText,
  loading = false,
}: {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  requireText?: string
  loading?: boolean
}) {
  const [typed, setTyped] = useState('')
  useEffect(() => {
    if (open) setTyped('')
  }, [open])
  const blocked = Boolean(requireText) && typed.trim() !== requireText

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            انصراف
          </Button>
          <Button
            variant={danger ? 'danger' : 'primary'}
            onClick={onConfirm}
            disabled={blocked}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-sm leading-7 text-ink-muted">{message}</p>
      {requireText ? (
        <Field
          className="mt-4"
          label={`برای تأیید، عبارت «${requireText}» را تایپ کنید`}
        >
          <Input value={typed} onChange={(event) => setTyped(event.target.value)} dir="ltr" />
        </Field>
      ) : null}
    </Modal>
  )
}

/* -------------------------------- Tabs -------------------------------- */

interface TabsContextValue {
  active: string
  setActive: (value: string) => void
}
const TabsContext = createContext<TabsContextValue | null>(null)

export function Tabs({
  tabs,
  value,
  onChange,
  children,
}: {
  tabs: { value: string; label: string; badge?: ReactNode }[]
  value: string
  onChange: (value: string) => void
  children?: ReactNode
}) {
  return (
    <TabsContext.Provider value={{ active: value, setActive: onChange }}>
      <div className="mb-5 flex gap-1 overflow-x-auto border-b border-line pb-px">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => onChange(tab.value)}
            className={cn(
              'relative whitespace-nowrap px-3.5 py-2.5 text-sm font-semibold transition-colors',
              value === tab.value ? 'text-ink' : 'text-ink-faint hover:text-ink-muted',
            )}
          >
            <span className="flex items-center gap-2">
              {tab.label}
              {tab.badge}
            </span>
            {value === tab.value ? (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-pill bg-accent" />
            ) : null}
          </button>
        ))}
      </div>
      {children}
    </TabsContext.Provider>
  )
}

export function TabPanel({ value, children }: { value: string; children: ReactNode }) {
  const context = useContext(TabsContext)
  if (!context || context.active !== value) return null
  return <div className="animate-fade-up">{children}</div>
}

/* ------------------------------ DataTable ------------------------------ */

export interface Column<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  sortable?: boolean
  className?: string
  hideOnMobile?: boolean
}

export function DataTable<T extends { id: string }>({
  columns,
  rows,
  loading,
  empty,
  onRowClick,
  selectable,
  selected,
  onSelectedChange,
  sort,
  onSortChange,
  mobileCard,
}: {
  columns: Column<T>[]
  rows: T[]
  loading?: boolean
  empty?: ReactNode
  onRowClick?: (row: T) => void
  selectable?: boolean
  selected?: string[]
  onSelectedChange?: (ids: string[]) => void
  sort?: { key: string; order: 'asc' | 'desc' }
  onSortChange?: (key: string) => void
  mobileCard?: (row: T) => ReactNode
}) {
  if (loading) return <SkeletonRows rows={6} />
  if (!rows.length) return <>{empty}</>

  const allSelected = Boolean(selected && selected.length === rows.length && rows.length > 0)
  const toggleAll = () => onSelectedChange?.(allSelected ? [] : rows.map((row) => row.id))
  const toggleOne = (id: string) =>
    onSelectedChange?.(selected?.includes(id) ? selected.filter((item) => item !== id) : [...(selected ?? []), id])

  return (
    <>
      {/* موبایل: تبدیل جدول به کارت */}
      {mobileCard ? (
        <div className="grid gap-2.5 md:hidden">
          {rows.map((row) => (
            <div
              key={row.id}
              onClick={() => onRowClick?.(row)}
              className={cn('panel-quiet p-3.5', onRowClick && 'cursor-pointer active:scale-[0.995]')}
            >
              {mobileCard(row)}
            </div>
          ))}
        </div>
      ) : null}

      <div className={cn('overflow-x-auto', mobileCard && 'hidden md:block')}>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-start text-[11px] uppercase tracking-wider text-ink-faint">
              {selectable ? (
                <th className="w-10 px-3 py-2.5">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    className="h-4 w-4 accent-[var(--accent)]"
                    aria-label="انتخاب همه"
                  />
                </th>
              ) : null}
              {columns.map((column) => (
                <th
                  key={column.key}
                  className={cn('px-3 py-2.5 text-start font-semibold', column.className)}
                >
                  {column.sortable && onSortChange ? (
                    <button
                      onClick={() => onSortChange(column.key)}
                      className="inline-flex items-center gap-1 hover:text-ink"
                    >
                      {column.header}
                      {sort?.key === column.key ? <span>{sort.order === 'asc' ? '↑' : '↓'}</span> : null}
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => onRowClick?.(row)}
                className={cn(
                  'border-t border-line transition-colors',
                  onRowClick && 'cursor-pointer hover:bg-surface-overlay',
                )}
              >
                {selectable ? (
                  <td className="px-3 py-3" onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={Boolean(selected?.includes(row.id))}
                      onChange={() => toggleOne(row.id)}
                      className="h-4 w-4 accent-[var(--accent)]"
                      aria-label="انتخاب ردیف"
                    />
                  </td>
                ) : null}
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn('px-3 py-3 align-middle', column.hideOnMobile && 'hidden lg:table-cell')}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export function Pagination({
  page,
  pages,
  total,
  onChange,
}: {
  page: number
  pages: number
  total: number
  onChange: (page: number) => void
}) {
  if (pages <= 1) return null
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-1 pt-3.5 text-xs text-ink-faint">
      <span className="tabular">
        صفحه {page} از {pages} · {total} مورد
      </span>
      <div className="flex items-center gap-1.5">
        <Button size="icon" variant="ghost" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          <ChevronRight size={16} />
        </Button>
        <Button size="icon" variant="ghost" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          <ChevronLeft size={16} />
        </Button>
      </div>
    </div>
  )
}

/* ------------------------------ CopyField ------------------------------ */

export function CopyField({ value, label, multiline }: { value: string; label?: string; multiline?: boolean }) {
  const [copied, setCopied] = useState(false)
  const id = useId()
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      const helper = document.createElement('textarea')
      helper.value = value
      document.body.appendChild(helper)
      helper.select()
      document.execCommand('copy')
      helper.remove()
    }
    setCopied(true)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div>
      {label ? (
        <label htmlFor={id} className="mb-1.5 block text-[13px] font-medium text-ink-muted">
          {label}
        </label>
      ) : null}
      <div className="flex items-stretch gap-2">
        <code
          id={id}
          dir="ltr"
          className={cn(
            'flex-1 rounded-xl border border-line bg-surface-sunken px-3 py-2.5 font-mono text-xs leading-6 text-ink',
            multiline ? 'whitespace-pre-wrap break-all' : 'truncate',
          )}
        >
          {value}
        </code>
        <Button size="icon" variant="secondary" onClick={copy} title="کپی">
          {copied ? <Check size={15} className="text-up" /> : <Copy size={15} />}
        </Button>
      </div>
    </div>
  )
}

export function KeyValue({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map((item) => (
        <div key={item.label} className="flex items-baseline justify-between gap-3 border-b border-line pb-2">
          <dt className="text-xs text-ink-faint">{item.label}</dt>
          <dd className="min-w-0 truncate text-sm font-medium">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}
