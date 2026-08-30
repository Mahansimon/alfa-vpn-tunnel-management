/** نمودارهای پنل روی Recharts با تم پنل. */
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { formatBytes, formatDate, formatPercent, type DigitMode } from '@/lib/utils'

const AXIS = { stroke: 'var(--ink-faint)', fontSize: 11 }
const GRID = 'var(--line)'
const TOOLTIP_STYLE = {
  background: 'var(--surface-overlay)', border: '1px solid var(--line-strong)',
  borderRadius: 12, fontSize: 12, color: 'var(--ink)', direction: 'rtl' as const,
}
const timeLabel = (value: string) => formatDate(value, { withTime: true, digits: 'en' }).split(' ').slice(-1)[0]

export function UsageChart({ data, digits = 'fa', height = 240 }: {
  data: { ts: string; cpu_percent: number; ram_percent: number; disk_percent: number }[]
  digits?: DigitMode; height?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="cpuFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} strokeDasharray="3 6" vertical={false} />
        <XAxis dataKey="ts" tickFormatter={timeLabel} {...AXIS} tickLine={false} minTickGap={40} />
        <YAxis domain={[0, 100]} unit="%" {...AXIS} tickLine={false} width={44} />
        <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v) => formatDate(String(v), { digits })}
          formatter={(v: number, n) => [formatPercent(v, digits), String(n)]} />
        <Area type="monotone" dataKey="cpu_percent" name="CPU" stroke="var(--accent)" fill="url(#cpuFill)" strokeWidth={2} />
        <Line type="monotone" dataKey="ram_percent" name="RAM" stroke="var(--state-degraded)" dot={false} strokeWidth={1.6} />
        <Line type="monotone" dataKey="disk_percent" name="Disk" stroke="var(--state-up)" dot={false} strokeWidth={1.4} strokeDasharray="4 4" />
        <Legend wrapperStyle={{ fontSize: 11, color: 'var(--ink-faint)' }} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function NetworkChart({ data, digits = 'fa', height = 240 }: {
  data: { ts: string; rx_rate: number; tx_rate: number }[]; digits?: DigitMode; height?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 6" vertical={false} />
        <XAxis dataKey="ts" tickFormatter={timeLabel} {...AXIS} tickLine={false} minTickGap={40} />
        <YAxis tickFormatter={(v: number) => formatBytes(v, 'en', 0)} {...AXIS} tickLine={false} width={70} />
        <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v) => formatDate(String(v), { digits })}
          formatter={(v: number, n) => [`${formatBytes(v, digits, 1)}/s`, String(n)]} />
        <Area type="monotone" dataKey="rx_rate" name="دانلود" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.16} strokeWidth={2} />
        <Area type="monotone" dataKey="tx_rate" name="آپلود" stroke="var(--state-up)" fill="var(--state-up)" fillOpacity={0.12} strokeWidth={2} />
        <Legend wrapperStyle={{ fontSize: 11, color: 'var(--ink-faint)' }} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function TrafficBars({ data, digits = 'fa', height = 220 }: {
  data: { bucket: string; bytes_rx: number; bytes_tx: number }[]; digits?: DigitMode; height?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 6" vertical={false} />
        <XAxis dataKey="bucket" tickFormatter={timeLabel} {...AXIS} tickLine={false} minTickGap={32} />
        <YAxis tickFormatter={(v: number) => formatBytes(v, 'en', 0)} {...AXIS} tickLine={false} width={70} />
        <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v) => formatDate(String(v), { digits })}
          formatter={(v: number, n) => [formatBytes(v, digits), String(n)]} />
        <Bar dataKey="bytes_rx" name="دریافت" fill="var(--accent)" radius={[4, 4, 0, 0]} maxBarSize={22} />
        <Bar dataKey="bytes_tx" name="ارسال" fill="var(--state-up)" radius={[4, 4, 0, 0]} maxBarSize={22} />
        <Legend wrapperStyle={{ fontSize: 11, color: 'var(--ink-faint)' }} />
      </BarChart>
    </ResponsiveContainer>
  )
}

const HEALTH_COLORS: Record<string, string> = {
  up: 'var(--state-up)', degraded: 'var(--state-degraded)',
  down: 'var(--state-down)', unknown: 'var(--state-unknown)',
}

export function HealthDonut({ data, height = 200 }: { data: Record<string, number>; height?: number }) {
  const items = Object.entries(data).filter(([, v]) => v > 0).map(([key, value]) => ({ name: key, value }))
  if (!items.length) return <p className="py-10 text-center text-xs text-ink-faint">داده‌ای برای نمایش نیست.</p>
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={items} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="86%" paddingAngle={3} stroke="none">
          {items.map((item) => <Cell key={item.name} fill={HEALTH_COLORS[item.name] ?? 'var(--state-unknown)'} />)}
        </Pie>
        <Tooltip contentStyle={TOOLTIP_STYLE} />
      </PieChart>
    </ResponsiveContainer>
  )
}
