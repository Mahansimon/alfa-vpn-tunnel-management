import { useQuery } from '@tanstack/react-query'
import { api, type Dashboard } from '@/lib/api'
import { PageHeader, Panel } from '@/components/ui'
import { UsageChart, NetworkChart } from '@/components/charts'

export default function MonitoringPage() {
  const { data } = useQuery({ queryKey: ['dashboard'], queryFn: async () => (await api.get<Dashboard>('/dashboard')).data })
  const series = (data?.top_servers ?? []).map((item, i) => ({ ts: `${i}`, cpu_percent: item.cpu_percent, ram_percent: item.ram_percent, disk_percent: item.disk_percent, rx_rate: item.rx_rate, tx_rate: item.tx_rate }))
  return <><PageHeader title="مانیتورینگ" description="نمای زنده منابع سیستم" /><div className="grid gap-4 lg:grid-cols-2"><Panel title="مصرف منابع"><UsageChart data={series} /></Panel><Panel title="ترافیک"><NetworkChart data={series} /></Panel></div></>
}
