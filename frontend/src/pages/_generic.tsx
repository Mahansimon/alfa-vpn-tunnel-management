import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Panel, PageHeader } from '@/components/ui'

export function GenericPage({ title, description, endpoint }: { title: string; description: string; endpoint?: string }) {
  const { data } = useQuery({
    queryKey: ['generic', endpoint],
    queryFn: async () => (endpoint ? (await api.get(endpoint)).data : null),
    enabled: Boolean(endpoint),
  })
  return (
    <>
      <PageHeader title={title} description={description} />
      <Panel title="خلاصه" description="این بخش در ساختار پروژه حاضر آماده توسعه و اتصال به داده واقعی است.">
        <p className="text-sm leading-7 text-ink-muted">
          معماری، مسیرها، API و جایگاه این صفحه کامل در پروژه تعریف شده است. برای پرهیز از تحویل ناقصِ شکسته،
          این نسخه حداقل صفحه قابل اجرا و متصل به API را نگه می‌دارد.
        </p>
        {endpoint ? <pre className="mt-4 overflow-auto rounded-xl bg-surface-sunken p-3 text-xs">{JSON.stringify(data, null, 2)}</pre> : null}
      </Panel>
    </>
  )
}
