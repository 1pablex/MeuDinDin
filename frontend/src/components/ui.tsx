import type { ReactNode } from 'react'

export function ProgressBar({ percent, color = 'var(--green)', label, size = 'md' }: {
  percent: number
  color?: string
  label: string
  size?: 'sm' | 'md' | 'lg'
}) {
  const value = Math.max(0, Math.min(100, percent))
  return (
    <div
      className={`progress progress-${size}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
    >
      <div className="progress-fill" style={{ width: `${value}%`, background: color }} />
    </div>
  )
}

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: readonly { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div className="segmented" role="tablist" aria-label={label}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="tab"
          aria-selected={opt.value === value}
          className={opt.value === value ? 'is-active' : undefined}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

export function Card({ title, action, children, className = '' }: {
  title?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="card-header">
          {title && <h2>{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

export function Loading({ label = 'Carregando…' }: { label?: string }) {
  return (
    <p className="muted loading" role="status">
      {label}
    </p>
  )
}

export function ErrorText({ children }: { children: ReactNode }) {
  if (!children) return null
  return (
    <p className="error-text" role="alert">
      {children}
    </p>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>
}
