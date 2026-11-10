import type { AuthResponse } from './types'

/**
 * Cliente HTTP. O access token fica só em memória (não em localStorage);
 * o refresh token vive num cookie httpOnly que o JS não consegue ler.
 */
let accessToken: string | null = null
let refreshing: Promise<AuthResponse | null> | null = null
let onSessionExpired: (() => void) | null = null

let accessIssuedAt = 0

export function setAccessToken(token: string | null): void {
  accessToken = token
  accessIssuedAt = token ? Date.now() : 0
}

/** Há quantos ms o access token atual foi emitido (0 se não houver). */
export function accessTokenAge(): number {
  return accessIssuedAt ? Date.now() - accessIssuedAt : 0
}

export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler
}

export class ApiError extends Error {
  readonly status: number
  readonly data: unknown

  constructor(status: number, data: unknown) {
    super(extractMessage(data) ?? `Erro ${status}`)
    this.status = status
    this.data = data
  }
}

function extractMessage(data: unknown): string | null {
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return data.map(extractMessage).filter(Boolean).join(' ') || null
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    if ('detail' in record) return extractMessage(record.detail)
    const parts = Object.values(record).map(extractMessage).filter(Boolean)
    return parts.length ? parts.join(' ') : null
  }
  return null
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    // O bloqueio de login manda uma mensagem própria; o limite por IP não
    if (err.status === 429 && !errorField(err, 'retry_after')) {
      return 'Muitas tentativas. Aguarde um minuto e tente de novo.'
    }
    return err.message
  }
  if (err instanceof Error) return err.message
  return 'Algo deu errado. Tente novamente.'
}

/** Lê um campo extra do corpo de erro (ex.: retry_after, code). */
export function errorField(err: unknown, key: string): unknown {
  if (!(err instanceof ApiError) || !err.data || typeof err.data !== 'object') return undefined
  return (err.data as Record<string, unknown>)[key]
}

/** Erros por campo devolvidos pelo DRF ({campo: ["msg"]}). */
export function fieldErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || !err.data || typeof err.data !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(err.data as Record<string, unknown>)) {
    const msg = extractMessage(value)
    if (msg) out[key] = msg
  }
  return out
}

async function parse(res: Response): Promise<unknown> {
  if (res.status === 204) return null
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

async function doRefresh(): Promise<AuthResponse | null> {
  const res = await fetch('/api/auth/refresh/', { method: 'POST', credentials: 'same-origin' })
  if (!res.ok) {
    setAccessToken(null)
    return null
  }
  const data = (await res.json()) as AuthResponse
  setAccessToken(data.access)
  return data
}

/**
 * O refresh token é rotacionado (o antigo vai pra blacklist), então chamadas
 * simultâneas precisam compartilhar a mesma requisição.
 */
export function refreshSession(): Promise<AuthResponse | null> {
  refreshing ??= doRefresh().finally(() => {
    refreshing = null
  })
  return refreshing
}

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'

export async function api<T>(path: string, method: Method = 'GET', body?: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (res.status === 401 && retry && !path.startsWith('/auth/')) {
    if (await refreshSession()) return api<T>(path, method, body, false)
    onSessionExpired?.()
  }

  const data = await parse(res)
  if (!res.ok) throw new ApiError(res.status, data)
  return data as T
}
