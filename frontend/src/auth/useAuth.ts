import { createContext, useContext } from 'react'
import type { User } from '../api/types'

export type AuthState =
  | { status: 'loading' }
  | { status: 'anonymous'; reason?: 'idle' | 'expired' }
  | { status: 'authenticated'; user: User }

/** Resultado da primeira etapa do login. */
export type LoginResult = { status: 'ok' } | { status: 'mfa'; token: string }

export interface AuthContextValue {
  state: AuthState
  /** Segundos até a sessão expirar por inatividade, quando faltar pouco (aviso). */
  idleWarning: number | null
  login: (email: string, password: string) => Promise<LoginResult>
  /** Segunda etapa: código do app autenticador ou de recuperação. */
  verifyMfa: (token: string, code: string) => Promise<void>
  /** Cria a conta pendente; o código de confirmação vai por e-mail. Retorna o e-mail normalizado. */
  register: (name: string, email: string, password: string) => Promise<string>
  /** Confirma o e-mail com o código e já entra na conta. */
  verifyEmail: (email: string, code: string) => Promise<void>
  /** Atualiza os dados do usuário logado (ex.: depois de ativar o 2FA). */
  setUser: (user: User) => void
  /** Marca atividade e afasta o aviso de inatividade. */
  stayActive: () => void
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth precisa estar dentro de <AuthProvider>')
  return ctx
}

export function useCurrentUser(): User {
  const { state } = useAuth()
  if (state.status !== 'authenticated') throw new Error('Usuário não autenticado')
  return state.user
}
