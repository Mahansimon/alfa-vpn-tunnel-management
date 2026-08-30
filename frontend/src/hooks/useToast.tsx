import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

export type ToastTone = 'success' | 'error' | 'warning' | 'info'

interface Toast {
  id: number
  tone: ToastTone
  title: string
  body?: string
}

interface ToastValue {
  push: (tone: ToastTone, title: string, body?: string) => void
  success: (title: string, body?: string) => void
  error: (title: string, body?: string) => void
  warning: (title: string, body?: string) => void
  info: (title: string, body?: string) => void
}

const ToastContext = createContext<ToastValue | null>(null)

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}

const TONES: Record<ToastTone, string> = {
  success: 'text-up',
  error: 'text-down',
  warning: 'text-degraded',
  info: 'text-accent',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const remove = useCallback((id: number) => setToasts((prev) => prev.filter((t) => t.id !== id)), [])

  const push = useCallback(
    (tone: ToastTone, title: string, body?: string) => {
      const id = Date.now() + Math.random()
      setToasts((prev) => [...prev.slice(-3), { id, tone, title, body }])
      window.setTimeout(() => remove(id), tone === 'error' ? 9000 : 5000)
    },
    [remove],
  )

  const value = useMemo<ToastValue>(
    () => ({
      push,
      success: (title, body) => push('success', title, body),
      error: (title, body) => push('error', title, body),
      warning: (title, body) => push('warning', title, body),
      info: (title, body) => push('info', title, body),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-5 left-5 z-[70] flex w-[min(24rem,calc(100vw-2.5rem))] flex-col gap-2"
        role="status"
        aria-live="polite"
      >
        {toasts.map((toast) => {
          const Icon = ICONS[toast.tone]
          return (
            <div
              key={toast.id}
              className="panel pointer-events-auto animate-fade-up shadow-pop flex items-start gap-3 p-3.5"
            >
              <Icon size={18} className={cn('mt-0.5 shrink-0', TONES[toast.tone])} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold leading-6">{toast.title}</p>
                {toast.body ? <p className="mt-0.5 text-xs text-ink-muted">{toast.body}</p> : null}
              </div>
              <button
                onClick={() => remove(toast.id)}
                className="rounded-md p-1 text-ink-faint transition-colors hover:text-ink"
                aria-label="بستن"
              >
                <X size={14} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside ToastProvider')
  return context
}
