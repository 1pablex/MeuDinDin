import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { mmss } from '../lib/useCountdown'
import { DashboardIcon, ListIcon, LogoIcon, LogoutIcon, MenuIcon, ShieldIcon, TargetIcon, XIcon } from './Icons'

const links = [
  { to: '/', label: 'Dashboard', icon: DashboardIcon, end: true },
  { to: '/lancamentos', label: 'Lançamentos', icon: ListIcon, end: false },
  { to: '/metas', label: 'Metas', icon: TargetIcon, end: false },
  { to: '/seguranca', label: 'Segurança', icon: ShieldIcon, end: false },
] as const

/** Aviso um minuto antes de encerrar a sessão por inatividade. */
function IdleBanner() {
  const { idleWarning, stayActive, logout } = useAuth()
  if (idleWarning === null) return null
  return (
    <div className="idle-banner" role="alertdialog" aria-live="assertive" aria-label="Sessão prestes a expirar">
      <p>
        <strong>Você ainda está aí?</strong> Por segurança, sua sessão será encerrada em{' '}
        <strong>{mmss(idleWarning)}</strong> por inatividade.
      </p>
      <div className="invite-actions">
        <button type="button" className="btn btn-primary" onClick={stayActive}>
          Continuar conectado
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => void logout()}>
          Sair agora
        </button>
      </div>
    </div>
  )
}

export function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <LogoIcon size={18} />
      </span>
      <span className="brand-name">MeuDinDin</span>
    </div>
  )
}

export function Layout() {
  const { logout } = useAuth()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const [lastPath, setLastPath] = useState(location.pathname)

  // Fecha o menu mobile ao trocar de página
  if (lastPath !== location.pathname) {
    setLastPath(location.pathname)
    setOpen(false)
  }

  return (
    <div className="shell">
      <nav className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Principal">
        <div className="sidebar-top">
          <Brand />
          <button
            type="button"
            className="icon-btn menu-toggle"
            aria-label={open ? 'Fechar menu' : 'Abrir menu'}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <XIcon /> : <MenuIcon />}
          </button>
        </div>
        <div className="nav-links">
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className="nav-link">
              <Icon />
              {label}
            </NavLink>
          ))}
          <button type="button" className="nav-link nav-logout" onClick={() => void logout()}>
            <LogoutIcon />
            Sair
          </button>
        </div>
      </nav>
      <main className="content">
        <Outlet />
      </main>
      <IdleBanner />
    </div>
  )
}
