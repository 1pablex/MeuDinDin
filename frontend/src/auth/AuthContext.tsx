import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { accessTokenAge, api, refreshSession, setAccessToken, setSessionExpiredHandler } from '../api/client'
import type { AuthResponse, MfaChallenge, User } from '../api/types'
import { AuthContext, type AuthState, type LoginResult } from './useAuth'

const DEFAULT_IDLE_MS = 15 * 60 * 1000
const WARN_BEFORE_MS = 60 * 1000
/** O access token dura 5 min: renova antes disso enquanto houver uso. */
const REFRESH_AFTER_MS = 4 * 60 * 1000
const TICK_MS = 5 * 1000
const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll'] as const

// Compartilhado entre abas via localStorage (só timestamps, nada sensível)
const LAST_ACTIVITY_KEY = 'mdd:last-activity'
const LOGOUT_KEY = 'mdd:logout'

function readShared(key: string): number {
  try {
    return Number(window.localStorage.getItem(key)) || 0
  } catch {
    return 0
  }
}

function writeShared(key: string, value: number): void {
  try {
    window.localStorage.setItem(key, String(value))
  } catch {
    // Modo privado / storage bloqueado: segue só com o estado desta aba
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' })
  const [idleWarning, setIdleWarning] = useState<number | null>(null)
  const idleMs = useRef(DEFAULT_IDLE_MS)
  const lastActivity = useRef(0) // definido em applySession
  const lastRefresh = useRef(0)
  const queryClient = useQueryClient()

  const applySession = useCallback((data: AuthResponse) => {
    setAccessToken(data.access)
    idleMs.current = (data.idle_timeout || DEFAULT_IDLE_MS / 1000) * 1000
    const now = Date.now()
    lastActivity.current = now
    lastRefresh.current = now
    writeShared(LAST_ACTIVITY_KEY, now)
    setIdleWarning(null)
    setState({ status: 'authenticated', user: data.user })
  }, [])

  const clearSession = useCallback(
    (reason?: 'idle' | 'expired') => {
      setAccessToken(null)
      queryClient.clear()
      setIdleWarning(null)
      setState({ status: 'anonymous', reason })
    },
    [queryClient],
  )

  /** Encerra no servidor, avisa as outras abas e limpa o estado local. */
  const endSession = useCallback(
    async (reason?: 'idle' | 'expired') => {
      try {
        await api<null>('/auth/logout/', 'POST')
      } catch {
        // Mesmo sem rede, a sessão local é encerrada
      } finally {
        writeShared(LOGOUT_KEY, Date.now())
        clearSession(reason)
      }
    },
    [clearSession],
  )

  // Ao abrir o app, tenta restaurar a sessão pelo cookie de refresh
  useEffect(() => {
    let active = true
    refreshSession()
      .then((data) => {
        if (!active) return
        if (data) applySession(data)
        else setState({ status: 'anonymous' })
      })
      .catch(() => active && setState({ status: 'anonymous' }))
    return () => {
      active = false
    }
  }, [applySession])

  useEffect(() => {
    setSessionExpiredHandler(() => clearSession('expired'))
    return () => setSessionExpiredHandler(null)
  }, [clearSession])

  const authenticated = state.status === 'authenticated'

  // Controle de inatividade: só roda com sessão ativa
  useEffect(() => {
    if (!authenticated) return

    const markActivity = () => {
      const now = Date.now()
      if (now - lastActivity.current < 2000) return // no máximo a cada 2s
      lastActivity.current = now
      writeShared(LAST_ACTIVITY_KEY, now)
    }

    const tick = () => {
      const now = Date.now()
      const last = Math.max(lastActivity.current, readShared(LAST_ACTIVITY_KEY))
      const idle = now - last
      if (idle >= idleMs.current) {
        void endSession('idle')
        return
      }
      if (idle >= idleMs.current - WARN_BEFORE_MS) {
        setIdleWarning(Math.ceil((idleMs.current - idle) / 1000))
        return
      }
      setIdleWarning(null)
      // Renova só se houve uso desde a última renovação: parado, o refresh
      // token (15 min) vence no servidor também
      if (accessTokenAge() > REFRESH_AFTER_MS && last > lastRefresh.current) {
        lastRefresh.current = now
        void refreshSession().then((data) => {
          if (!data) clearSession('expired')
        })
      }
    }

    const onStorage = (e: StorageEvent) => {
      if (e.key === LOGOUT_KEY) clearSession()
    }
    const onVisible = () => document.visibilityState === 'visible' && tick()

    ACTIVITY_EVENTS.forEach((ev) => window.addEventListener(ev, markActivity, { passive: true }))
    window.addEventListener('storage', onStorage)
    document.addEventListener('visibilitychange', onVisible)
    const id = window.setInterval(tick, TICK_MS)
    return () => {
      ACTIVITY_EVENTS.forEach((ev) => window.removeEventListener(ev, markActivity))
      window.removeEventListener('storage', onStorage)
      document.removeEventListener('visibilitychange', onVisible)
      window.clearInterval(id)
    }
  }, [authenticated, clearSession, endSession])

  const stayActive = useCallback(() => {
    const now = Date.now()
    lastActivity.current = now
    writeShared(LAST_ACTIVITY_KEY, now)
    setIdleWarning(null)
  }, [])

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      const res = await api<AuthResponse | MfaChallenge>('/auth/login/', 'POST', { email, password })
      if ('mfa_required' in res) return { status: 'mfa', token: res.mfa_token }
      applySession(res)
      return { status: 'ok' }
    },
    [applySession],
  )

  const verifyMfa = useCallback(
    async (token: string, code: string) => {
      applySession(await api<AuthResponse>('/auth/login/2fa/', 'POST', { mfa_token: token, code }))
    },
    [applySession],
  )

  const register = useCallback(async (name: string, email: string, password: string) => {
    const res = await api<{ email: string }>('/auth/register/', 'POST', { name, email, password })
    return res.email
  }, [])

  const verifyEmail = useCallback(
    async (email: string, code: string) => {
      applySession(await api<AuthResponse>('/auth/verify-email/', 'POST', { email, code }))
    },
    [applySession],
  )

  const setUser = useCallback((user: User) => setState({ status: 'authenticated', user }), [])
  const logout = useCallback(() => endSession(), [endSession])

  const value = useMemo(
    () => ({ state, idleWarning, login, verifyMfa, register, verifyEmail, setUser, stayActive, logout }),
    [state, idleWarning, login, verifyMfa, register, verifyEmail, setUser, stayActive, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
