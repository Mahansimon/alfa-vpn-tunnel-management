import axios, { AxiosError } from 'axios'

/** خطای استاندارد سمت کلاینت با پیام فارسی قابل نمایش */
export interface ApiError {
  code: string
  message: string
  details?: unknown
  status?: number
}

function readCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : ''
}

export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// توکن CSRF از کوکی خوانده و روی درخواست‌های تغییردهنده ست می‌شود
api.interceptors.request.use((config) => {
  const method = (config.method || 'get').toLowerCase()
  if (!['get', 'head', 'options'].includes(method)) {
    const token = readCookie('alfa_csrf')
    if (token) config.headers.set('X-CSRF-Token', token)
  }
  return config
})

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ error?: ApiError }>) => {
    const status = error.response?.status
    const payload = error.response?.data?.error
    const normalized: ApiError = {
      code: payload?.code || 'network_error',
      message:
        payload?.message ||
        (status === 0 || !status
          ? 'ارتباط با سرور برقرار نشد. اتصال شبکه را بررسی کنید.'
          : 'خطای غیرمنتظره‌ای رخ داد.'),
      details: payload?.details,
      status,
    }
    if (status === 401 && !error.config?.url?.includes('/auth/login')) {
      onUnauthorized?.()
    }
    return Promise.reject(normalized)
  },
)

export function errorMessage(error: unknown): string {
  const candidate = error as ApiError
  if (candidate?.message) return candidate.message
  return 'خطای غیرمنتظره‌ای رخ داد.'
}

export function errorDetails(error: unknown): string[] {
  const details = (error as ApiError)?.details
  if (Array.isArray(details)) {
    return details.map((item) =>
      typeof item === 'string' ? item : `${(item as { field?: string }).field ?? ''} ${(item as { message?: string }).message ?? ''}`.trim(),
    )
  }
  return []
}

/* ------------------------------ انواع داده ------------------------------ */

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface Me {
  id: string
  username: string
  full_name: string
  email?: string | null
  role: 'owner' | 'admin' | 'operator' | 'viewer'
  permissions: string[]
  must_change_password: boolean
  totp_enabled: boolean
  theme: 'dark' | 'light'
  locale: 'fa' | 'en'
  timezone: string
}

export interface Server {
  id: string
  name: string
  ip_address: string
  private_ip?: string | null
  hostname?: string | null
  country: string
  country_code: string
  region: string
  provider: string
  operating_system: string
  kernel: string
  architecture: string
  ssh_port: number
  agent_port: number
  tags: string[]
  description: string
  group_id?: string | null
  status: 'online' | 'offline' | 'warning' | 'maintenance' | 'pending'
  maintenance: boolean
  health_score: number
  cpu_cores?: number | null
  cpu_model?: string | null
  ram_total_bytes?: number | null
  disk_total_bytes?: number | null
  uptime_seconds?: number | null
  last_seen_at?: string | null
  latitude?: number | null
  longitude?: number | null
  created_at: string
  agent?: { enrolled: boolean; version: string; compatible: boolean; last_heartbeat_at?: string | null } | null
}

export interface Tunnel {
  id: string
  name: string
  type_key: string
  source_server_id: string
  destination_server_id: string
  source_server_name?: string | null
  destination_server_name?: string | null
  state: 'draft' | 'deploying' | 'deployed' | 'failed' | 'stopped' | 'disabled' | 'maintenance'
  health: 'up' | 'degraded' | 'down' | 'unknown'
  enabled: boolean
  maintenance: boolean
  tags: string[]
  description: string
  latency_ms?: number | null
  packet_loss?: number | null
  jitter_ms?: number | null
  uptime_seconds?: number | null
  last_health_at?: string | null
  version: number
  service_name: string
  created_at: string
  config: Record<string, unknown>
}

export interface ConfigField {
  key: string
  label_fa: string
  type: 'string' | 'text' | 'int' | 'port' | 'bool' | 'select' | 'secret' | 'list'
  required: boolean
  default: unknown
  help_fa: string
  options: string[]
  minimum: number | null
  maximum: number | null
  advanced: boolean
  secret: boolean
}

export interface TunnelType {
  key: string
  display_name: string
  display_name_fa: string
  source_kind: 'binary' | 'repository'
  configured: boolean
  requires: string[]
  capabilities: string[]
  config_schema: ConfigField[]
  notes_fa: string
  version: string
}

export interface Dashboard {
  servers_total: number
  servers_online: number
  servers_offline: number
  servers_warning: number
  tunnels_total: number
  tunnels_active: number
  tunnels_failed: number
  tunnels_degraded: number
  cpu_avg: number
  ram_avg: number
  disk_avg: number
  rx_rate: number
  tx_rate: number
  traffic_today_bytes: number
  traffic_month_bytes: number
  panel_uptime_seconds: number
  health_score: number
  unread_notifications: number
  mock_mode: boolean
  traffic_series: { bucket: string; bytes_rx: number; bytes_tx: number }[]
  top_servers: {
    id: string
    name: string
    country: string
    status: string
    cpu_percent: number
    ram_percent: number
    disk_percent: number
    rx_rate: number
    tx_rate: number
    health_score: number
  }[]
  tunnel_health_breakdown: Record<string, number>
}

export interface MetricPoint {
  ts: string
  cpu_percent: number
  ram_percent: number
  disk_percent: number
  rx_rate: number
  tx_rate: number
  packets_rx_rate: number
  packets_tx_rate: number
  load_1: number
}

export interface Notification {
  id: string
  kind: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  body: string
  target_type?: string | null
  target_id?: string | null
  read: boolean
  created_at: string
}

export interface LogEntry {
  id: string
  server_id?: string | null
  tunnel_id?: string | null
  source: string
  level: string
  ts: string
  message: string
}

export interface AuditLog {
  id: string
  username: string
  user_id?: string | null
  action: string
  server_id?: string | null
  tunnel_id?: string | null
  target: string
  result: 'success' | 'failure'
  error: string
  ip?: string | null
  created_at: string
}

export interface Deployment {
  id: string
  kind: string
  tunnel_id?: string | null
  server_id?: string | null
  status: 'pending' | 'running' | 'success' | 'failed' | 'rolled_back' | 'cancelled'
  phase: string
  progress: number
  dry_run: boolean
  started_at?: string | null
  finished_at?: string | null
  error: string
  created_at: string
  logs?: { seq: number; ts: string; level: string; message: string }[]
}

export interface AlertRule {
  id: string
  name: string
  metric: string
  operator: string
  threshold: number
  duration_seconds: number
  target_type: 'server' | 'tunnel' | 'any'
  target_id?: string | null
  severity: 'info' | 'warning' | 'critical'
  enabled: boolean
  channels: string[]
  cooldown_seconds: number
  created_at: string
}

export interface Alert {
  id: string
  rule_id?: string | null
  target_type: string
  target_id?: string | null
  state: 'firing' | 'resolved'
  severity: string
  title: string
  message: string
  value?: number | null
  breach_since?: string | null
  resolved_at?: string | null
  created_at: string
}

export interface User {
  id: string
  username: string
  full_name: string
  email?: string | null
  role: string
  is_active: boolean
  totp_enabled: boolean
  must_change_password: boolean
  last_login_at?: string | null
  created_at: string
}

export interface SettingRow {
  key: string
  value: unknown
  category: string
  is_secret: boolean
  description_fa: string
}

export interface HealthOverview {
  status: 'ok' | 'degraded' | 'down'
  components: { name: string; status: string; detail: string; latency_ms?: number | null }[]
  panel_version: string
  checked_at: string
}

export interface Topology {
  nodes: { id: string; label: string; kind: string; country: string; status: string; health_score: number; tunnels: number }[]
  edges: {
    id: string
    source: string
    target: string
    label: string
    type_key: string
    health: string
    state: string
    latency_ms?: number | null
    bytes_total: number
  }[]
}

export interface TrafficSummary {
  scope: string
  scope_id?: string | null
  bytes_rx: number
  bytes_tx: number
  bytes_total: number
  points: { bucket: string; bytes_rx: number; bytes_tx: number }[]
}
