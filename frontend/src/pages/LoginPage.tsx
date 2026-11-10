import { useState, type FormEvent, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { api, errorField, errorMessage, fieldErrors } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { ChartIcon, TargetIcon, UsersIcon } from '../components/Icons'
import { Brand } from '../components/Layout'
import { ErrorText, Segmented } from '../components/ui'
import { mmss, useCountdown } from '../lib/useCountdown'

/**
 * Fluxos de acesso:
 *  login  -> (2FA ativo) -> mfa -> dentro do app
 *  login  -> (e-mail não confirmado) -> verify
 *  signup -> verify -> dentro do app
 *  forgot -> reset  -> login
 */
type Step = 'login' | 'signup' | 'verify' | 'mfa' | 'forgot' | 'reset'

const tabs = [
  { value: 'login', label: 'Entrar' },
  { value: 'signup', label: 'Criar conta' },
] as const

const RESEND_SECONDS = 60

export function LoginPage() {
  const { state, login, verifyMfa, register, verifyEmail } = useAuth()
  const [step, setStep] = useState<Step>('login')
  const [mfaToken, setMfaToken] = useState('')
  const [useRecovery, setUseRecovery] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(() =>
    state.status === 'anonymous' && state.reason === 'idle'
      ? 'Sua sessão foi encerrada após 15 minutos sem uso. Entre de novo.'
      : state.status === 'anonymous' && state.reason === 'expired'
        ? 'Sua sessão expirou. Entre de novo.'
        : null,
  )
  const [fields, setFields] = useState<Record<string, string>>({})
  const [pending, setPending] = useState(false)
  const [lockedUntil, setLockedUntil] = useState<number | null>(null)
  const [resendAt, setResendAt] = useState<number | null>(null)
  const lockLeft = useCountdown(lockedUntil)
  const resendLeft = useCountdown(resendAt)

  if (state.status === 'authenticated') return <Navigate to="/" replace />

  const go = (next: Step, message: string | null = null) => {
    setStep(next)
    setError(null)
    setFields({})
    setNotice(message)
    setCode('')
    if (next === 'verify' || next === 'reset') setResendAt(Date.now() + RESEND_SECONDS * 1000)
  }

  const fail = (err: unknown) => {
    const byField = fieldErrors(err)
    const retry = errorField(err, 'retry_after')
    if (typeof retry === 'number') setLockedUntil(Date.now() + retry * 1000)
    const { detail, non_field_errors, ...rest } = byField
    setFields(rest)
    setError(detail ?? non_field_errors ?? (Object.keys(rest).length ? null : errorMessage(err)))
  }

  const run = async (fn: () => Promise<void>) => {
    setPending(true)
    setError(null)
    setNotice(null)
    setFields({})
    try {
      await fn()
    } catch (err) {
      fail(err)
    } finally {
      setPending(false)
    }
  }

  const onLogin = () =>
    run(async () => {
      try {
        const result = await login(email.trim(), password)
        if (result.status === 'mfa') {
          setMfaToken(result.token)
          setUseRecovery(false)
          go('mfa')
        }
      } catch (err) {
        if (errorField(err, 'code') === 'email_not_verified') {
          go('verify', 'Sua conta ainda não foi confirmada. Enviamos um código para o seu e-mail.')
          return
        }
        throw err
      }
    })

  const onSignup = () =>
    run(async () => {
      const normalized = await register(name.trim(), email.trim(), password)
      setEmail(normalized)
      go('verify')
    })

  const onVerify = () => run(() => verifyEmail(email.trim(), code))

  const onMfa = () =>
    run(async () => {
      try {
        await verifyMfa(mfaToken, code)
      } catch (err) {
        // Desafio vencido ou esgotado: volta para e-mail e senha
        if (errorField(err, 'code') === 'mfa_expired') {
          setPassword('')
          go('login')
        }
        throw err
      }
    })

  const onForgot = () =>
    run(async () => {
      await api('/auth/password-reset/', 'POST', { email: email.trim() })
      go('reset')
    })

  const onReset = () =>
    run(async () => {
      if (password !== password2) {
        setFields({ password2: 'As senhas não conferem.' })
        return
      }
      await api('/auth/password-reset/confirm/', 'POST', { email: email.trim(), code, password })
      setPassword('')
      setPassword2('')
      go('login', 'Senha alterada. Entre com a nova senha.')
    })

  const resend = () =>
    run(async () => {
      const path = step === 'reset' ? '/auth/password-reset/' : '/auth/resend-code/'
      await api(path, 'POST', { email: email.trim() })
      setResendAt(Date.now() + RESEND_SECONDS * 1000)
      setNotice('Enviamos um novo código. Confira também a caixa de spam.')
    })

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const handlers: Record<Step, () => Promise<void>> = {
      login: onLogin,
      signup: onSignup,
      verify: onVerify,
      mfa: onMfa,
      forgot: onForgot,
      reset: onReset,
    }
    void handlers[step]()
  }

  const isTab = step === 'login' || step === 'signup'
  const locked = step === 'login' && lockLeft > 0

  return (
    <div className="auth">
      <section className="auth-hero">
        <Brand />
        <div className="auth-hero-text">
          <h1>Seu dinheiro num lugar só, sem abrir o app do banco.</h1>
          <p>
            Registre gastos do dia, da semana e do mês, acompanhe quanto já guardou e quanto falta para cada meta.
            Divida metas com quem divide a vida com você.
          </p>
        </div>
        <ul className="auth-pills">
          <li><ChartIcon /> Dashboards claros</li>
          <li><TargetIcon /> Metas com progresso</li>
          <li><UsersIcon /> Metas em conjunto</li>
        </ul>
      </section>

      <main className="auth-main">
        <div className="auth-box">
          {isTab && <Segmented options={tabs} value={step} onChange={(s) => go(s)} label="Acesso" />}

          <form className="stack" onSubmit={submit} noValidate>
            <Heading step={step} email={email} />

            {notice && (
              <p className="success-text" role="status">
                {notice}
              </p>
            )}

            {step === 'signup' && (
              <Field label="Nome" error={fields.name}>
                <input
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Como quer ser chamado"
                  maxLength={120}
                />
              </Field>
            )}

            {(step === 'login' || step === 'signup' || step === 'forgot') && (
              <Field label="E-mail" error={fields.email}>
                <input
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="voce@email.com"
                  maxLength={254}
                />
              </Field>
            )}

            {(step === 'verify' || step === 'reset') && (
              <Field label="Código de 6 dígitos" error={fields.code}>
                <input
                  className="code-input"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="\d{6}"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  maxLength={6}
                  autoFocus
                />
              </Field>
            )}

            {step === 'mfa' && !useRecovery && (
              <Field label="Código do app autenticador" error={fields.code}>
                <input
                  className="code-input"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  maxLength={6}
                  autoFocus
                />
              </Field>
            )}

            {step === 'mfa' && useRecovery && (
              <Field label="Código de recuperação" error={fields.code}>
                <input
                  className="code-input code-input-sm"
                  autoComplete="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  value={code}
                  onChange={(e) => setCode(e.target.value.slice(0, 20))}
                  placeholder="xxxxx-xxxxx"
                  maxLength={20}
                  autoFocus
                />
              </Field>
            )}

            {(step === 'login' || step === 'signup' || step === 'reset') && (
              <Field label={step === 'reset' ? 'Nova senha' : 'Senha'} error={fields.password}>
                <input
                  type="password"
                  autoComplete={step === 'login' ? 'current-password' : 'new-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={step === 'login' ? 'Sua senha' : 'Mínimo de 8 caracteres'}
                  maxLength={128}
                />
              </Field>
            )}

            {step === 'reset' && (
              <Field label="Repita a nova senha" error={fields.password2}>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={password2}
                  onChange={(e) => setPassword2(e.target.value)}
                  maxLength={128}
                />
              </Field>
            )}

            {step === 'login' && (
              <div className="auth-links">
                <button type="button" className="link-btn" onClick={() => go('forgot')}>
                  Esqueci a senha
                </button>
              </div>
            )}

            <ErrorText>{locked ? `Login bloqueado por excesso de tentativas. Tente novamente em ${mmss(lockLeft)}.` : error}</ErrorText>

            <button
              type="submit"
              className="btn btn-primary btn-lg"
              disabled={
                pending ||
                locked ||
                ((step === 'verify' || step === 'reset' || (step === 'mfa' && !useRecovery)) && code.length !== 6) ||
                (step === 'mfa' && useRecovery && code.trim().length < 10)
              }
            >
              {pending ? 'Aguarde…' : submitLabel[step]}
            </button>

            {(step === 'verify' || step === 'reset') && (
              <div className="auth-links">
                <button type="button" className="link-btn" disabled={resendLeft > 0 || pending} onClick={() => void resend()}>
                  {resendLeft > 0 ? `Reenviar código em ${mmss(resendLeft)}` : 'Reenviar código'}
                </button>
                <button type="button" className="link-btn" onClick={() => go('login')}>
                  Voltar para o login
                </button>
              </div>
            )}

            {step === 'mfa' && (
              <div className="auth-links">
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => {
                    setUseRecovery((v) => !v)
                    setCode('')
                    setError(null)
                  }}
                >
                  {useRecovery ? 'Usar o código do app' : 'Perdeu o celular? Usar código de recuperação'}
                </button>
                <button type="button" className="link-btn" onClick={() => go('login')}>
                  Voltar
                </button>
              </div>
            )}

            {step === 'forgot' && (
              <div className="auth-links">
                <button type="button" className="link-btn" onClick={() => go('login')}>
                  Voltar para o login
                </button>
              </div>
            )}
          </form>
        </div>
      </main>
    </div>
  )
}

const submitLabel: Record<Step, string> = {
  login: 'Entrar',
  signup: 'Criar conta',
  verify: 'Confirmar e entrar',
  mfa: 'Verificar e entrar',
  forgot: 'Enviar código',
  reset: 'Salvar nova senha',
}

function Heading({ step, email }: { step: Step; email: string }) {
  const content: Record<Step, [string, ReactNode]> = {
    login: ['Bem-vindo de volta', 'Entre para ver seu saldo e suas metas.'],
    signup: ['Crie sua conta', 'Vamos enviar um código para confirmar seu e-mail.'],
    verify: [
      'Confirme seu e-mail',
      <>
        Digite o código de 6 dígitos que enviamos para <strong>{email}</strong>.
      </>,
    ],
    mfa: ['Verificação em duas etapas', 'Abra o app autenticador no celular e digite o código do MeuDinDin.'],
    forgot: ['Esqueceu a senha?', 'Informe seu e-mail e enviaremos um código para criar uma nova senha.'],
    reset: [
      'Crie uma nova senha',
      <>
        Se existir uma conta com <strong>{email}</strong>, enviamos um código para ela.
      </>,
    ],
  }
  const [title, text] = content[step]
  return (
    <div className="stack-xs">
      <h2 className="display-md">{title}</h2>
      <p className="muted">{text}</p>
    </div>
  )
}

function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <label className="field">
      {label}
      {children}
      {error && <span className="field-error">{error}</span>}
    </label>
  )
}
