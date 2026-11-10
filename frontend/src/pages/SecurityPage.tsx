import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { api, errorMessage } from '../api/client'
import type { TwoFactorSetup, TwoFactorStatus } from '../api/types'
import { useAuth, useCurrentUser } from '../auth/useAuth'
import { ShieldIcon } from '../components/Icons'
import { Card, ErrorText, Loading } from '../components/ui'

const statusKey = ['2fa'] as const

export function SecurityPage() {
  const status = useQuery({ queryKey: statusKey, queryFn: () => api<TwoFactorStatus>('/auth/2fa/') })
  const [codes, setCodes] = useState<string[] | null>(null)

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="display-lg">Segurança</h1>
          <p className="muted">Proteja sua conta com a verificação em duas etapas.</p>
        </div>
      </header>

      {status.isPending && <Loading />}
      {status.error && <ErrorText>{errorMessage(status.error)}</ErrorText>}

      {codes && <RecoveryCodes codes={codes} onClose={() => setCodes(null)} />}

      {status.data && !codes && (
        status.data.enabled ? <Enabled info={status.data} onCodes={setCodes} /> : <Setup onEnabled={setCodes} />
      )}

      <Card title="Sessão">
        <p className="muted">
          Por segurança, você é desconectado automaticamente depois de 15 minutos sem usar o MeuDinDin. Um aviso
          aparece um minuto antes.
        </p>
      </Card>
    </div>
  )
}

function useRefreshUser() {
  const qc = useQueryClient()
  const { setUser } = useAuth()
  return async () => {
    void qc.invalidateQueries({ queryKey: statusKey })
    setUser(await api('/auth/me/'))
  }
}

function Setup({ onEnabled }: { onEnabled: (codes: string[]) => void }) {
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const refreshUser = useRefreshUser()

  const start = async () => {
    setPending(true)
    setError(null)
    try {
      setSetup(await api<TwoFactorSetup>('/auth/2fa/setup/', 'POST'))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPending(false)
    }
  }

  const confirm = async (e: FormEvent) => {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      const res = await api<{ recovery_codes: string[] }>('/auth/2fa/enable/', 'POST', { code })
      await refreshUser()
      onEnabled(res.recovery_codes)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPending(false)
    }
  }

  if (!setup) {
    return (
      <Card>
        <div className="sec-intro">
          <span className="sec-icon off" aria-hidden="true">
            <ShieldIcon size={22} />
          </span>
          <div className="stack-xs">
            <h2 className="sec-title">Verificação em duas etapas desativada</h2>
            <p className="muted">
              Com ela ativa, além da senha o login pede um código do app autenticador do seu celular (Google
              Authenticator, Microsoft Authenticator, Authy…). Mesmo que alguém descubra sua senha, não entra.
            </p>
          </div>
        </div>
        <ErrorText>{error}</ErrorText>
        <div>
          <button type="button" className="btn btn-primary" onClick={() => void start()} disabled={pending}>
            {pending ? 'Aguarde…' : 'Ativar verificação em duas etapas'}
          </button>
        </div>
      </Card>
    )
  }

  return (
    <Card title="Ativar verificação em duas etapas">
      <ol className="steps">
        <li>
          <strong>Instale um app autenticador</strong> no celular, se ainda não tiver (Google Authenticator, Microsoft
          Authenticator ou Authy).
        </li>
        <li>
          <strong>Escaneie o QR code</strong> no app (botão “+” ou “Adicionar conta”).
          <div className="qr-box">
            <img src={setup.qr_svg} width={220} height={220} alt="QR code para cadastrar o MeuDinDin no app autenticador" />
            <button type="button" className="link-btn" onClick={() => setShowKey((v) => !v)}>
              {showKey ? 'Ocultar chave' : 'Não consegue escanear? Digite a chave'}
            </button>
            {showKey && (
              <code className="secret" aria-label="Chave para digitar no app">
                {setup.secret.match(/.{1,4}/g)?.join(' ')}
              </code>
            )}
          </div>
        </li>
        <li>
          <strong>Digite o código de 6 dígitos</strong> que aparece no app para confirmar.
          <form className="inline-form" onSubmit={(e) => void confirm(e)}>
            <label className="field">
              <span className="sr-only">Código do app</span>
              <input
                className="code-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                maxLength={6}
              />
            </label>
            <button type="submit" className="btn btn-primary" disabled={pending || code.length !== 6}>
              {pending ? 'Confirmando…' : 'Confirmar e ativar'}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setSetup(null)}>
              Cancelar
            </button>
          </form>
        </li>
      </ol>
      <ErrorText>{error}</ErrorText>
    </Card>
  )
}

function Enabled({ info, onCodes }: { info: TwoFactorStatus; onCodes: (codes: string[]) => void }) {
  const user = useCurrentUser()
  const refreshUser = useRefreshUser()
  const [mode, setMode] = useState<'idle' | 'disable' | 'codes'>('idle')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const reset = (next: typeof mode) => {
    setMode(next)
    setPassword('')
    setCode('')
    setError(null)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      if (mode === 'disable') {
        await api('/auth/2fa/disable/', 'POST', { password, code })
        await refreshUser()
        reset('idle')
      } else {
        const res = await api<{ recovery_codes: string[] }>('/auth/2fa/recovery-codes/', 'POST', { code })
        await refreshUser()
        onCodes(res.recovery_codes)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <Card>
      <div className="sec-intro">
        <span className="sec-icon on" aria-hidden="true">
          <ShieldIcon size={22} />
        </span>
        <div className="stack-xs">
          <h2 className="sec-title">Verificação em duas etapas ativa</h2>
          <p className="muted">
            O login de <strong>{user.email}</strong> pede o código do app autenticador. Você tem{' '}
            <strong>{info.recovery_codes_left}</strong> código{info.recovery_codes_left === 1 ? '' : 's'} de
            recuperação disponíve{info.recovery_codes_left === 1 ? 'l' : 'is'}.
          </p>
        </div>
      </div>

      {info.recovery_codes_left <= 3 && (
        <p className="warn-text" role="status">
          Restam poucos códigos de recuperação. Gere novos para não ficar sem acesso se perder o celular.
        </p>
      )}

      {mode === 'idle' ? (
        <div className="form-actions-inline">
          <button type="button" className="btn btn-ghost" onClick={() => reset('codes')}>
            Gerar novos códigos de recuperação
          </button>
          <button type="button" className="btn btn-ghost text-danger" onClick={() => reset('disable')}>
            Desativar
          </button>
        </div>
      ) : (
        <form className="inline-form" onSubmit={(e) => void submit(e)}>
          {mode === 'disable' && (
            <label className="field grow">
              Sua senha
              <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
          )}
          <label className="field grow">
            {mode === 'disable' ? 'Código do app ou de recuperação' : 'Código do app'}
            <input
              inputMode={mode === 'codes' ? 'numeric' : undefined}
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(mode === 'codes' ? e.target.value.replace(/\D/g, '').slice(0, 6) : e.target.value.slice(0, 20))}
              placeholder={mode === 'codes' ? '000000' : '000000 ou xxxxx-xxxxx'}
            />
          </label>
          <button
            type="submit"
            className={`btn ${mode === 'disable' ? 'btn-danger' : 'btn-primary'}`}
            disabled={pending || !code || (mode === 'disable' && !password)}
          >
            {pending ? 'Aguarde…' : mode === 'disable' ? 'Desativar 2FA' : 'Gerar códigos'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => reset('idle')}>
            Cancelar
          </button>
        </form>
      )}
      <ErrorText>{error}</ErrorText>
    </Card>
  )
}

function RecoveryCodes({ codes, onClose }: { codes: string[]; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const text = `MeuDinDin: códigos de recuperação\nCada código funciona uma única vez.\n\n${codes.join('\n')}\n`

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(codes.join('\n'))
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'meudindin-codigos-recuperacao.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Card title="Guarde seus códigos de recuperação">
      <p className="muted">
        Se perder o celular, use um destes códigos no lugar do código do app. <strong>Cada um funciona uma vez</strong> e
        eles não serão mostrados de novo. Guarde num lugar seguro (gerenciador de senhas, papel guardado).
      </p>
      <ul className="recovery-grid">
        {codes.map((c) => (
          <li key={c}>
            <code>{c}</code>
          </li>
        ))}
      </ul>
      <div className="form-actions-inline">
        <button type="button" className="btn btn-ghost" onClick={() => void copy()}>
          {copied ? 'Copiado!' : 'Copiar'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={download}>
          Baixar .txt
        </button>
        <button type="button" className="btn btn-primary" onClick={onClose}>
          Já guardei
        </button>
      </div>
    </Card>
  )
}
