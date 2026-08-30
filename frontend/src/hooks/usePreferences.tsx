import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { DigitMode } from '@/lib/utils'

export type Theme = 'dark' | 'light'
export type Calendar = 'jalali' | 'gregorian'

interface Preferences {
  theme: Theme
  digits: DigitMode
  calendar: Calendar
  timezone: string
}

interface PreferencesValue extends Preferences {
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  setDigits: (digits: DigitMode) => void
  setCalendar: (calendar: Calendar) => void
  setTimezone: (tz: string) => void
}

const STORAGE_KEY = 'alfa.prefs'
const DEFAULTS: Preferences = { theme: 'dark', digits: 'fa', calendar: 'jalali', timezone: 'Asia/Tehran' }

const PreferencesContext = createContext<PreferencesValue | null>(null)

function read(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Preferences>) } : DEFAULTS
  } catch {
    return DEFAULTS
  }
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<Preferences>(read)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
    document.documentElement.dataset.theme = prefs.theme
  }, [prefs])

  const update = useCallback((patch: Partial<Preferences>) => setPrefs((prev) => ({ ...prev, ...patch })), [])

  const value = useMemo<PreferencesValue>(
    () => ({
      ...prefs,
      setTheme: (theme) => update({ theme }),
      toggleTheme: () => update({ theme: prefs.theme === 'dark' ? 'light' : 'dark' }),
      setDigits: (digits) => update({ digits }),
      setCalendar: (calendar) => update({ calendar }),
      setTimezone: (timezone) => update({ timezone }),
    }),
    [prefs, update],
  )

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>
}

export function usePreferences() {
  const context = useContext(PreferencesContext)
  if (!context) throw new Error('usePreferences must be used inside PreferencesProvider')
  return context
}

/** میان‌بر قالب‌بندی با احترام به تنظیمات کاربر */
export function useFormatters() {
  const { digits, calendar, timezone } = usePreferences()
  return useMemo(() => ({ digits, calendar, timezone }), [digits, calendar, timezone])
}
