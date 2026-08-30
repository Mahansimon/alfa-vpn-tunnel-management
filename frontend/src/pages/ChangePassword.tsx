import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { KeyRound } from 'lucide-react'
import { api, errorDetails, errorMessage } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { Button, Field, Input, Panel } from '@/components/ui'

export default function ChangePassword({ forced = false }: { forced?: boolean }) {
  const { refresh, logout } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [errors, setErrors] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setErrors([])
    if (next !== repeat) {
      setErrors(['تکرار پسورد با پسورد جدید یکسان نیست.'])
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/change-password', { current_password: current, new_password: next })
      toast.success('پسورد تغییر کرد', 'با پسورد جدید وارد شده‌اید.')
      await refresh()
      if (!forced) navigate('/profile')
    } catch (exception) {
      setErrors([errorMessage(exception), ...errorDetails(exception)])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={forced ? 'mx-auto grid min-h-screen max-w-lg place-items-center px-5' : 'max-w-lg'}>
      <Panel
        title="تغییر پسورد"
        description={forced ? 'برای ادامه باید پسورد اولیه را عوض کنید.' : 'حداقل ۱۲ کاراکتر با حرف بزرگ، کوچک، عدد و کاراکتر ویژه.'}
        className="w-full"
      >
        <form onSubmit={submit} className="space-y-4">
          <Field label="پسورد فعلی" required>
            <Input type="password" value={current} onChange={(event) => setCurrent(event.target.value)} dir="ltr" required />
          </Field>
          <Field label="پسورد جدید" required>
            <Input type="password" value={next} onChange={(event) => setNext(event.target.value)} dir="ltr" required minLength={12} />
          </Field>
          <Field label="تکرار پسورد جدید" required>
            <Input type="password" value={repeat} onChange={(event) => setRepeat(event.target.value)} dir="ltr" required />
          </Field>
          {errors.length ? (
            <ul className="space-y-1 rounded-xl border border-down/40 bg-down/10 px-3.5 py-2.5 text-xs leading-6 text-down">
              {errors.filter(Boolean).map((item) => <li key={item}>{item}</li>)}
            </ul>
          ) : null}
          <div className="flex gap-2 pt-1">
            <Button type="submit" variant="primary" loading={loading} icon={<KeyRound size={15} />}>
              ذخیره پسورد
            </Button>
            {forced ? (
              <Button variant="ghost" onClick={() => void logout()}>
                خروج
              </Button>
            ) : null}
          </div>
        </form>
      </Panel>
    </div>
  )
}
