/** قطعات مشترک صفحه‌ها: هدر فیلتر، جدول لاگ و کارت آماری */
import type { ReactNode } from 'react'
import { Badge, Panel } from '@/components/ui'
import { cn, formatNumber } from '@/lib/utils'
import { usePreferences } from '@/hooks/usePreferences'

export function Stat({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: 'up' | 'down' | 'degraded'; hint?: string }) {
  return (
    <div className="panel-quiet p-4">
      <p className="text-xs text-ink-faint">{label}</p>
      <p className={cn('tabular mt-1.5 text-2xl font-bold', tone === 'up' && 'text-up', tone === 'down' && 'text-down', tone === 'degraded' && 'text-degraded')}>
        {value}
      </p>
      {hint ? <p className="mt-1 text-[11px] text-ink-faint">{hint}</p> : null}
    </div>
  )
}

export function LevelBadge({ level }: { level: string }) {
  const tone = level === 'error' || level === 'critical' ? 'down' : level === 'warning' ? 'degraded' : 'neutral'
  return <Badge tone={tone}>{level}</Badge>
}

export function CountBar({ items }: { items: { label: string; value: number }[] }) {
  const { digits } = usePreferences()
  return (
    <Panel bodyClassName="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {items.map((item) => (
        <div key={item.label}>
          <p className="text-xs text-ink-faint">{item.label}</p>
          <p className="tabular mt-1 text-xl font-bold">{formatNumber(item.value, digits)}</p>
        </div>
      ))}
    </Panel>
  )
}
