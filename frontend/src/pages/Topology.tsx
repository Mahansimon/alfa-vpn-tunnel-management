import { useQuery } from '@tanstack/react-query'
import { api, type Topology } from '@/lib/api'
import { Badge, ErrorState, PageHeader, Panel, Skeleton } from '@/components/ui'
import { formatBytes, formatMs, healthTone } from '@/lib/utils'

export default function TopologyPage() {
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ['topology'], queryFn: async () => (await api.get<Topology>('/topology')).data })
  if (isLoading) return <Skeleton className="h-80" />
  if (isError || !data) return <ErrorState message="بارگذاری توپولوژی ناموفق بود." onRetry={() => void refetch()} />
  return (
    <>
      <PageHeader title="توپولوژی شبکه" description="نمای گرافی از سرورها و تونل‌ها" />
      <Panel title="گره‌ها و یال‌ها" description="نسخه سبک SVG برای مشاهده سریع ساختار ارتباطی">
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="panel-quiet p-4">
            <p className="mb-3 text-sm font-semibold">سرورها</p>
            <div className="space-y-2">
              {data.nodes.map((node) => <div key={node.id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-sm"><span>{node.label}</span><Badge tone={healthTone(node.status) as 'up'}>{node.status}</Badge></div>)}
            </div>
          </div>
          <div className="panel-quiet p-4">
            <p className="mb-3 text-sm font-semibold">تونل‌ها</p>
            <div className="space-y-2">
              {data.edges.map((edge) => <div key={edge.id} className="rounded-lg border border-line px-3 py-2 text-sm"><div className="flex items-center justify-between gap-2"><span>{edge.label}</span><Badge tone={healthTone(edge.health) as 'up'}>{edge.health}</Badge></div><p className="mt-1 text-xs text-ink-muted">{edge.source} ← {edge.target} · {formatMs(edge.latency_ms, 'fa')} · {formatBytes(edge.bytes_total, 'fa')}</p></div>)}
            </div>
          </div>
        </div>
      </Panel>
    </>
  )
}
