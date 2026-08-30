import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, type Me } from '@/lib/api'

interface AuthValue {
  user: Me | null
  loading: boolean
  totpRequired: boolean
  login: (username: string, password: string, totp?: string) => Promise<Me | null>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  can: (permission: string) => boolean
  isRole: (...roles: Me['role'][]) => boolean
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [totpRequired, setTotpRequired] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get<Me>('/auth/me')
      setUser(data)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    void refresh()
  }, [refresh])

  const login = useCallback(async (username: string, password: string, totp?: string) => {
    const { data } = await api.post('/auth/login', {
      username,
      password,
      totp_code: totp || null,
    })
    if (data.totp_required) {
      setTotpRequired(true)
      return null
    }
    setTotpRequired(false)
    setUser(data.user)
    return data.user as Me
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      setUser(null)
    }
  }, [])

  const value = useMemo<AuthValue>(
    () => ({
      user,
      loading,
      totpRequired,
      login,
      logout,
      refresh,
      can: (permission) => Boolean(user?.permissions.includes(permission)),
      isRole: (...roles) => Boolean(user && roles.includes(user.role)),
    }),
    [user, loading, totpRequired, login, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
