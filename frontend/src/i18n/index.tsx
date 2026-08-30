import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { fa, type Dictionary } from './fa'
import { en } from './en'

export type Locale = 'fa' | 'en'

const DICTIONARIES: Record<Locale, Dictionary> = { fa, en }
const STORAGE_KEY = 'alfa.locale'

type Path = string

function lookup(dictionary: Dictionary, path: Path): string {
  const parts = path.split('.')
  let current: unknown = dictionary
  for (const part of parts) {
    if (current && typeof current === 'object' && part in (current as Record<string, unknown>)) {
      current = (current as Record<string, unknown>)[part]
    } else {
      return path
    }
  }
  return typeof current === 'string' ? current : path
}

interface I18nValue {
  locale: Locale
  dir: 'rtl' | 'ltr'
  setLocale: (locale: Locale) => void
  t: (path: Path, vars?: Record<string, string | number>) => string
}

const I18nContext = createContext<I18nValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(
    () => (localStorage.getItem(STORAGE_KEY) as Locale) || 'fa',
  )

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next)
    localStorage.setItem(STORAGE_KEY, next)
    document.documentElement.lang = next
    document.documentElement.dir = next === 'fa' ? 'rtl' : 'ltr'
  }, [])

  const t = useCallback(
    (path: Path, vars?: Record<string, string | number>) => {
      let text = lookup(DICTIONARIES[locale], path)
      if (vars) {
        for (const [key, value] of Object.entries(vars)) {
          text = text.replace(new RegExp(`\\{${key}\\}`, 'g'), String(value))
        }
      }
      return text
    },
    [locale],
  )

  const value = useMemo<I18nValue>(
    () => ({ locale, dir: locale === 'fa' ? 'rtl' : 'ltr', setLocale, t }),
    [locale, setLocale, t],
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const context = useContext(I18nContext)
  if (!context) throw new Error('useI18n must be used inside I18nProvider')
  return context
}
