import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const FA_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']

/** تبدیل ارقام لاتین به فارسی (قابل تنظیم از تنظیمات پنل) */
export function toFaDigits(value: string | number): string {
  return String(value).replace(/\d/g, (d) => FA_DIGITS[Number(d)])
}

export type DigitMode = 'fa' | 'en'

export function formatNumber(value: number | null | undefined, digits: DigitMode = 'fa', fraction = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const text = value.toLocaleString('en-US', {
    minimumFractionDigits: fraction,
    maximumFractionDigits: fraction,
  })
  return digits === 'fa' ? toFaDigits(text) : text
}

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

export function formatBytes(bytes: number | null | undefined, digits: DigitMode = 'fa', fraction = 2) {
  if (!bytes || bytes < 0) return digits === 'fa' ? '۰ B' : '0 B'
  let size = bytes
  let index = 0
  while (size >= 1024 && index < UNITS.length - 1) {
    size /= 1024
    index += 1
  }
  const value = size.toFixed(index === 0 ? 0 : fraction)
  return `${digits === 'fa' ? toFaDigits(value) : value} ${UNITS[index]}`
}

export function formatRate(bytesPerSecond: number | null | undefined, digits: DigitMode = 'fa') {
  return `${formatBytes(bytesPerSecond, digits, 1)}/s`
}

export function formatPercent(value: number | null | undefined, digits: DigitMode = 'fa') {
  if (value === null || value === undefined) return '—'
  return `${formatNumber(Math.round(value * 10) / 10, digits, value % 1 === 0 ? 0 : 1)}٪`
}

export function formatMs(value: number | null | undefined, digits: DigitMode = 'fa') {
  if (value === null || value === undefined) return '—'
  return `${formatNumber(Math.round(value), digits)} ms`
}

export function formatDuration(seconds: number | null | undefined, digits: DigitMode = 'fa') {
  if (!seconds || seconds < 0) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const parts: string[] = []
  if (days) parts.push(`${formatNumber(days, digits)} روز`)
  if (hours) parts.push(`${formatNumber(hours, digits)} ساعت`)
  if (!days && minutes) parts.push(`${formatNumber(minutes, digits)} دقیقه`)
  if (!parts.length) parts.push(`${formatNumber(seconds, digits)} ثانیه`)
  return parts.join(' و ')
}

export interface DateOptions {
  calendar?: 'jalali' | 'gregorian'
  timeZone?: string
  digits?: DigitMode
  withTime?: boolean
}

/** تاریخ شمسی/میلادی با Intl (بدون وابستگی خارجی) */
export function formatDate(input: string | number | Date | null | undefined, options: DateOptions = {}) {
  if (!input) return '—'
  const { calendar = 'jalali', timeZone = 'Asia/Tehran', digits = 'fa', withTime = true } = options
  const date = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(date.getTime())) return '—'
  const locale = calendar === 'jalali' ? 'fa-IR-u-ca-persian-nu-latn' : 'en-GB'
  const text = new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
    timeZone,
    hour12: false,
  }).format(date)
  return digits === 'fa' ? toFaDigits(text) : text
}

export function relativeTime(input: string | number | Date | null | undefined, digits: DigitMode = 'fa') {
  if (!input) return '—'
  const date = input instanceof Date ? input : new Date(input)
  const diff = Math.round((date.getTime() - Date.now()) / 1000)
  const abs = Math.abs(diff)
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['second', 60],
    ['minute', 3600],
    ['hour', 86400],
    ['day', 2592000],
    ['month', 31536000],
  ]
  let unit: Intl.RelativeTimeFormatUnit = 'year'
  let divisor = 31536000
  for (const [candidate, limit] of units) {
    if (abs < limit) {
      unit = candidate
      divisor = limit === 60 ? 1 : limit / (candidate === 'minute' ? 60 : candidate === 'hour' ? 24 : 30)
      break
    }
  }
  const formatter = new Intl.RelativeTimeFormat('fa', { numeric: 'auto' })
  const text = formatter.format(Math.round(diff / divisor), unit)
  return digits === 'fa' ? text : text
}

export function healthTone(health: string) {
  switch (health) {
    case 'up':
    case 'online':
    case 'success':
    case 'ok':
      return 'up'
    case 'degraded':
    case 'warning':
    case 'maintenance':
      return 'degraded'
    case 'down':
    case 'offline':
    case 'failed':
    case 'critical':
      return 'down'
    default:
      return 'unknown'
  }
}

export function debounce<T extends (...args: never[]) => void>(fn: T, delay = 300) {
  let timer: ReturnType<typeof setTimeout>
  return (...args: Parameters<T>) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), delay)
  }
}

export function truncate(text: string, length = 80) {
  return text.length > length ? `${text.slice(0, length)}…` : text
}
