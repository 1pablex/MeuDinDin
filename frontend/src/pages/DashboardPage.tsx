import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { errorMessage } from '../api/client'
import { useDashboard } from '../api/hooks'
import type { Period } from '../api/types'
import { useCurrentUser } from '../auth/useAuth'
import { InvitesBanner } from '../components/InvitesBanner'
import { Card, Empty, ErrorText, Loading, ProgressBar, Segmented } from '../components/ui'
import { dateBR, money, toNumber } from '../lib/format'

const periods = [
  { value: 'daily', label: 'Diário' },
  { value: 'weekly', label: 'Semanal' },
  { value: 'monthly', label: 'Mensal' },
] as const

const periodName: Record<Period, string> = { daily: 'hoje', weekly: 'semana', monthly: 'mês' }

export function DashboardPage() {
  const user = useCurrentUser()
  const [period, setPeriod] = useState<Period>('monthly')
  const { data, isPending, error } = useDashboard(period)

  const firstName = user.name.split(' ')[0] ?? user.name

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="display-lg">Olá, {firstName}</h1>
          <p className="muted">Resumo das suas finanças</p>
        </div>
        <Segmented options={periods} value={period} onChange={setPeriod} label="Período" />
      </header>

      <InvitesBanner />

      {isPending && <Loading />}
      {error && <ErrorText>{errorMessage(error)}</ErrorText>}

      {data && (
        <>
          <section className="stats" aria-label="Indicadores">
            <div className="stat stat-dark">
              <span className="stat-label">Saldo disponível</span>
              <span className="stat-value">{money(data.available)}</span>
              <span className="stat-hint">Entradas menos gastos e o que foi para metas</span>
            </div>
            <div className="stat">
              <span className="stat-label">Entradas ({periodName[period]})</span>
              <span className="stat-value text-green">{money(data.income)}</span>
              <span className="stat-hint">{data.transactions_count} lançamentos no período</span>
            </div>
            <div className="stat">
              <span className="stat-label">Gastos ({periodName[period]})</span>
              <span className="stat-value text-orange">{money(data.expense)}</span>
              <span className="stat-hint">
                {toNumber(data.income) > 0
                  ? `${Math.round((toNumber(data.expense) / toNumber(data.income)) * 100)}% das entradas`
                  : 'Sem entradas no período'}
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Guardado em metas</span>
              <span className="stat-value">{money(data.saved_in_goals)}</span>
              <span className="stat-hint">Faltam {money(data.missing_for_goals)}</span>
            </div>
          </section>

          <div className="row">
            <Card title="Entradas x Gastos" className="grow-2">
              <div className="chart" role="img" aria-label="Gráfico de barras de entradas e gastos por período">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart
                    data={data.series.map((s) => ({
                      label: s.label,
                      Entradas: toNumber(s.income),
                      Gastos: toNumber(s.expense),
                    }))}
                    margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid vertical={false} stroke="var(--line)" />
                    <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      width={64}
                      tick={{ fill: 'var(--muted)', fontSize: 12 }}
                      tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v))}
                    />
                    <Tooltip
                      formatter={(v) => money(Number(v))}
                      cursor={{ fill: 'var(--surface-2)' }}
                      contentStyle={{ borderRadius: 10, border: '1px solid var(--line)' }}
                    />
                    <Bar dataKey="Entradas" fill="var(--green)" radius={[4, 4, 0, 0]} maxBarSize={22} />
                    <Bar dataKey="Gastos" fill="var(--orange-soft)" radius={[4, 4, 0, 0]} maxBarSize={22} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="legend">
                <span><i style={{ background: 'var(--green)' }} />Entradas</span>
                <span><i style={{ background: 'var(--orange-soft)' }} />Gastos</span>
              </div>
            </Card>

            <Card title="Gastos por categoria" className="grow-1">
              {data.by_category.length === 0 ? (
                <Empty>Nenhum gasto no período.</Empty>
              ) : (
                <ul className="cat-list">
                  {data.by_category.map((c) => {
                    const max = toNumber(data.by_category[0]?.total)
                    return (
                      <li key={c.name}>
                        <div className="cat-row">
                          <span>{c.name}</span>
                          <strong>{money(c.total)}</strong>
                        </div>
                        <ProgressBar
                          size="sm"
                          percent={max ? (toNumber(c.total) / max) * 100 : 0}
                          color={c.color}
                          label={`${c.name}: ${money(c.total)}`}
                        />
                      </li>
                    )
                  })}
                </ul>
              )}
            </Card>
          </div>

          <div className="row">
            <Card title="Últimos lançamentos" action={<Link to="/lancamentos">Ver todos</Link>} className="grow-2">
              {data.recent.length === 0 ? (
                <Empty>
                  Nada registrado ainda. <Link to="/lancamentos">Adicione seu primeiro lançamento</Link>.
                </Empty>
              ) : (
                <ul className="tx-list">
                  {data.recent.map((t) => (
                    <li key={t.id}>
                      <span>
                        {t.description}
                        <span className="muted"> · {t.category_name ?? 'Sem categoria'} · {dateBR(t.date)}</span>
                      </span>
                      <strong className={t.kind === 'income' ? 'text-green' : 'text-orange'}>
                        {t.kind === 'income' ? '+ ' : '- '}
                        {money(t.amount)}
                      </strong>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Metas" action={<Link to="/metas">Abrir</Link>} className="grow-1">
              {data.goals.length === 0 ? (
                <Empty>
                  Você ainda não tem metas. <Link to="/metas">Criar uma</Link>.
                </Empty>
              ) : (
                <ul className="goal-mini-list">
                  {data.goals.map((g) => (
                    <li key={g.id}>
                      <div className="cat-row">
                        <strong>{g.name}</strong>
                        <span>{g.percent}%</span>
                      </div>
                      <ProgressBar percent={g.percent} label={`Progresso de ${g.name}`} />
                      <span className="muted small">
                        Faltam {money(g.missing)}
                        {g.shared && ' · em conjunto'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

