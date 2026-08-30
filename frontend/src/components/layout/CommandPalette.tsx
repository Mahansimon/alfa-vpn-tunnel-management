import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FileClock, Network, Search, Server } from 'lucide-react'
import { api } from '@/lib/api'
import { useDebouncedValue } from '@/hooks/useLive'
import { Modal } from '@/components/ui'
import { truncate } from '@/lib/utils'

interface SearchResult {
  servers: { id: string; name: string; ip: string; status: string }[]
  tunnels: { id: string; name: string; health: string; type: string }[]
  logs: { id: string; message: string; ts: string; source: string }[]
}

const SHORTCUTS = [
  { label: 'داشبورد', to: '/' },
  { label: 'سرورها', to: '/servers' },
  { label: 'تونل‌ها', to: '/tunnels' },
  { label: 'ساخت تونل جدید', to: '/tunnels/new' },
  { label: 'توپولوژی شبکه', to: '/topology' },
  { label: 'گزارش ترافیک', to: '/traffic' },
  { label: 'لاگ‌ها', to: '/logs' },
  { label: 'تنظیمات', to: '/settings' },
  { label: 'سلامت سیستم', to: '/health' },
]

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const debounced = useDebouncedValue(query, 250)
  const navigate = useNavigate()

  useEffect(() => {
    if (open) setQuery('')
  }, [open])

  const { data, isFetching } = useQuery({
    queryKey: ['search', debounced],
    queryFn: async () => (await api.get<SearchResult>('/search', { params: { q: debounced } })).data,
    enabled: open && debounced.trim().length > 1,
  })

  const go = (to: string) => {
    onClose()
    navigate(to)
  }

  const filteredShortcuts = SHORTCUTS.filter((item) => item.label.includes(query.trim()))

  return (
    <Modal open={open} onClose={onClose} title="جستجوی سراسری" description="سرور، تونل، لاگ یا صفحه را پیدا کنید" size="md">
      <div className="flex items-center gap-2.5 rounded-xl border border-line bg-surface-sunken px-3.5">
        <Search size={16} className="text-ink-faint" />
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="نام سرور، IP، تونل یا متن لاگ…"
          className="h-11 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-faint"
        />
        {isFetching ? <span className="text-[10px] text-ink-faint">…</span> : null}
      </div>

      <div className="mt-4 space-y-4">
        {filteredShortcuts.length ? (
          <section>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-ink-faint">صفحه‌ها</p>
            <ul className="space-y-0.5">
              {filteredShortcuts.slice(0, 5).map((item) => (
                <li key={item.to}>
                  <button
                    onClick={() => go(item.to)}
                    className="w-full rounded-lg px-3 py-2 text-start text-sm hover:bg-surface-overlay"
                  >
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {data?.servers.length ? (
          <section>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-ink-faint">سرورها</p>
            <ul className="space-y-0.5">
              {data.servers.map((server) => (
                <li key={server.id}>
                  <button
                    onClick={() => go(`/servers/${server.id}`)}
                    className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-start text-sm hover:bg-surface-overlay"
                  >
                    <Server size={14} className="text-ink-faint" />
                    <span className="flex-1 truncate">{server.name}</span>
                    <code dir="ltr" className="font-mono text-[11px] text-ink-faint">
                      {server.ip}
                    </code>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {data?.tunnels.length ? (
          <section>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-ink-faint">تونل‌ها</p>
            <ul className="space-y-0.5">
              {data.tunnels.map((tunnel) => (
                <li key={tunnel.id}>
                  <button
                    onClick={() => go(`/tunnels/${tunnel.id}`)}
                    className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-start text-sm hover:bg-surface-overlay"
                  >
                    <Network size={14} className="text-ink-faint" />
                    <span className="flex-1 truncate">{tunnel.name}</span>
                    <span className="text-[11px] text-ink-faint">{tunnel.type}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {data?.logs.length ? (
          <section>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-ink-faint">لاگ‌ها</p>
            <ul className="space-y-0.5">
              {data.logs.map((log) => (
                <li key={log.id}>
                  <button
                    onClick={() => go('/logs')}
                    className="flex w-full items-start gap-2.5 rounded-lg px-3 py-2 text-start text-xs hover:bg-surface-overlay"
                  >
                    <FileClock size={13} className="mt-0.5 text-ink-faint" />
                    <span className="flex-1" dir="auto">
                      {truncate(log.message, 90)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {debounced.trim().length > 1 && !isFetching && !data?.servers.length && !data?.tunnels.length && !data?.logs.length ? (
          <p className="py-6 text-center text-xs text-ink-faint">نتیجه‌ای یافت نشد.</p>
        ) : null}
      </div>
    </Modal>
  )
}
