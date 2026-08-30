import { useState } from 'react'
import { Network, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useI18n } from '@/i18n'
import { errorMessage } from '@/lib/api'
import { Button, Field, Input } from '@/components/ui'

export function LoginPage() {
  const { t } = useI18n()
  const { login, totpRequired } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username.trim(), password, totp.trim() || undefined)
    } catch (exception) {
      setError(errorMessage(exception))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      {/* ستون معرفی: فقط دسکتاپ */}
      <aside className="grid-bg relative hidden overflow-hidden border-e border-line bg-surface-sunken p-12 lg:grid lg:content-center">
        <div className="relative max-w-lg">
          <span className="inline-flex items-center gap-2 rounded-pill border border-line bg-surface-raised px-3 py-1 text-[11px] font-semibold text-ink-muted">
            <ShieldCheck size={13} className="text-accent" /> ارتباط امن با Agent، بدون SSH باز
          </span>
          <h1 className="mt-6 text-4xl font-extrabold leading-[1.25]">
            مدیریت متمرکز سرورها و تونل‌ها
          </h1>
          <p className="mt-4 text-sm leading-7 text-ink-muted">
            مانیتورینگ زنده CPU، رم، دیسک و ترافیک، ساخت و کنترل تونل بین سرورهای ایران و خارج، هشدار
            هوشمند، Audit کامل و پشتیبان‌گیری خودکار.
          </p>
          <dl className="mt-9 grid grid-cols-3 gap-6 border-t border-line pt-6 text-center">
            <div>
              <dt className="text-[11px] text-ink-faint">تونل پشتیبانی‌شده</dt>
              <dd className="mt-1 text-2xl font-extrabold text-accent">۶</dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-faint">به‌روزرسانی زنده</dt>
              <dd className="mt-1 text-2xl font-extrabold text-accent">WS</dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-faint">نقش دسترسی</dt>
              <dd className="mt-1 text-2xl font-extrabold text-accent">۴</dd>
            </div>
          </dl>
        </div>
      </aside>

      <main className="flex items-center justify-center px-5 py-12">
        <form onSubmit={submit} className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-accent-soft text-accent">
              <Network size={20} />
            </span>
            <div>
              <p className="text-base font-extrabold leading-5">Alfa VpnTunnel Managment</p>
              <p className="text-[11px] text-ink-faint">{t('app.tagline')}</p>
            </div>
          </div>

          <h2 className="text-xl font-bold">{t('auth.signIn')}</h2>
          <p className="mt-1 text-xs text-ink-faint">
            نام کاربری و پسورد را از خروجی نصب (install.sh) بردارید.
          </p>

          <div className="mt-6 space-y-4">
            <Field label={t('auth.username')} required>
              <Input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                dir="ltr"
                required
                autoFocus
              />
            </Field>
            <Field label={t('auth.password')} required>
              <Input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                dir="ltr"
                required
              />
            </Field>
            {totpRequired ? (
              <Field label={t('auth.totp')} hint="کد ۶ رقمی برنامه Authenticator" required>
                <Input value={totp} onChange={(event) => setTotp(event.target.value)} dir="ltr" inputMode="numeric" maxLength={8} />
              </Field>
            ) : null}
          </div>

          {error ? (
            <p className="mt-4 rounded-xl border border-down/40 bg-down/10 px-3.5 py-2.5 text-xs leading-6 text-down">
              {error}
            </p>
          ) : null}

          <Button type="submit" variant="primary" size="lg" loading={loading} className="mt-6 w-full justify-center">
            {t('auth.signIn')}
          </Button>

          <p className="mt-6 text-center text-[11px] leading-6 text-ink-faint">
            تلاش‌های ناموفق ثبت و محدود می‌شوند. پس از چند تلاش اشتباه، حساب موقتاً قفل می‌شود.
          </p>
        </form>
      </main>
    </div>
  )
}
