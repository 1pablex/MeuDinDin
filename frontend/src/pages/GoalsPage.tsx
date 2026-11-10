import { useRef, useState, type FormEvent } from 'react'
import { errorMessage, fieldErrors } from '../api/client'
import { useContributions, useGoal, useGoalAction, useGoals, useSaveGoal } from '../api/hooks'
import type { Goal, GoalDetail, GoalInput } from '../api/types'
import { useCurrentUser } from '../auth/useAuth'
import { EditIcon, PlusIcon, TrashIcon, XIcon } from '../components/Icons'
import { InvitesBanner } from '../components/InvitesBanner'
import { Card, Empty, ErrorText, Loading, ProgressBar } from '../components/ui'
import { dateBR, initials, money, toNumber } from '../lib/format'

const memberColors = ['#17663F', '#2C6FB7', '#B4471A', '#7A4CB0', '#3A8C8C', '#C2416B']

export function GoalsPage() {
  const { data: goals, isPending, error } = useGoals()
  const [selected, setSelected] = useState<number | null>(null)
  const [formMode, setFormMode] = useState<'closed' | 'new' | 'edit'>('closed')

  const current = selected ?? goals?.[0]?.id ?? null
  const detail = useGoal(current)
  const detailRef = useRef<HTMLDivElement>(null)

  // No celular o detalhe fica abaixo da lista: rola até ele ao escolher uma meta
  const selectGoal = (id: number) => {
    setSelected(id)
    if (window.matchMedia('(max-width: 820px)').matches) {
      requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="display-lg">Metas</h1>
          <p className="muted">Quanto já guardou e quanto falta, sozinho ou junto.</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setFormMode('new')}>
          <PlusIcon size={16} /> Nova meta
        </button>
      </header>

      <InvitesBanner onAccepted={setSelected} />

      {formMode !== 'closed' && (
        <GoalForm
          goal={formMode === 'edit' ? detail.data ?? null : null}
          onClose={() => setFormMode('closed')}
          onCreated={(g) => setSelected(g.id)}
        />
      )}

      {isPending && <Loading />}
      {error && <ErrorText>{errorMessage(error)}</ErrorText>}
      {goals && goals.length === 0 && formMode === 'closed' && (
        <Card>
          <Empty>
            Nenhuma meta ainda. Crie a primeira: uma viagem, uma reserva de emergência, um notebook novo…
          </Empty>
        </Card>
      )}

      {goals && goals.length > 0 && (
        <div className="row align-start">
          <section aria-label="Suas metas" className="goal-list grow-1">
            {goals.map((g) => (
              <button
                key={g.id}
                type="button"
                className={`goal-card ${g.id === current ? 'is-selected' : ''}`}
                aria-pressed={g.id === current}
                onClick={() => selectGoal(g.id)}
              >
                <span className="goal-card-top">
                  <strong>{g.name}</strong>
                  {g.members_count > 1 && <span className="badge">Em conjunto</span>}
                </span>
                <ProgressBar size="sm" percent={g.progress.percent} label={`Progresso de ${g.name}`} />
                <span className="goal-card-bottom">
                  <span>
                    {money(g.progress.saved)} de {money(g.target_amount)}
                  </span>
                  <strong>{g.progress.percent}%</strong>
                </span>
              </button>
            ))}
          </section>

          <div className="grow-2" ref={detailRef}>
            {detail.isPending && <Loading />}
            {detail.error && <ErrorText>{errorMessage(detail.error)}</ErrorText>}
            {detail.data && (
              <GoalDetailCard
                goal={detail.data}
                onEdit={() => setFormMode('edit')}
                onGone={() => setSelected(null)}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function GoalDetailCard({ goal, onEdit, onGone }: { goal: GoalDetail; onEdit: () => void; onGone: () => void }) {
  const me = useCurrentUser()
  const action = useGoalAction()
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [invite, setInvite] = useState('')
  const [msg, setMsg] = useState<{ type: 'ok' | 'error'; text: string } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const contributions = useContributions(goal.id)

  const p = goal.progress
  const saved = toNumber(p.saved)

  const run = (path: string, body: unknown, ok: string, method: 'POST' | 'DELETE' = 'POST', after?: () => void) =>
    action.mutate(
      { path, body, method },
      {
        onSuccess: () => {
          setMsg({ type: 'ok', text: ok })
          after?.()
        },
        onError: (err) => setMsg({ type: 'error', text: errorMessage(err) }),
      },
    )

  const contribute = (sign: 1 | -1) => (e?: FormEvent) => {
    e?.preventDefault()
    const v = Number.parseFloat(amount.replace(',', '.'))
    if (!(v > 0)) {
      setMsg({ type: 'error', text: 'Informe um valor maior que zero.' })
      return
    }
    run(
      `/goals/${goal.id}/contributions/`,
      { amount: (v * sign).toFixed(2), note: note.trim() },
      sign > 0 ? `${money(v)} guardados na meta.` : `${money(v)} retirados da meta.`,
      'POST',
      () => {
        setAmount('')
        setNote('')
      },
    )
  }

  const sendInvite = (e: FormEvent) => {
    e.preventDefault()
    const email = invite.trim()
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setMsg({ type: 'error', text: 'Informe um e-mail válido.' })
      return
    }
    run(`/goals/${goal.id}/invite/`, { email }, `Convite enviado para ${email}. A pessoa verá o convite ao entrar no MeuDinDin.`, 'POST', () =>
      setInvite(''),
    )
  }

  return (
    <Card className="goal-detail">
      <div className="goal-detail-head">
        <div className="stack-xs">
          <h2 className="display-md">{goal.name}</h2>
          <span className="muted">
            {goal.deadline ? `Prazo: ${dateBR(goal.deadline)}` : 'Sem prazo definido'}
            {!goal.is_owner && ` · criada por ${goal.owner_name}`}
          </span>
        </div>
        <div className="goal-missing">
          <span className="muted small">Falta</span>
          <strong className="text-orange">{money(p.missing)}</strong>
        </div>
      </div>

      <div className="stack-sm">
        <ProgressBar size="lg" percent={p.percent} label={`Progresso de ${goal.name}`} />
        <div className="cat-row">
          <span>
            <strong>{money(p.saved)}</strong> guardados ({p.percent}%)
          </span>
          <span className="muted">meta de {money(goal.target_amount)}</span>
        </div>
        <span className="muted">
          {toNumber(p.missing) === 0
            ? 'Meta atingida. Parabéns!'
            : p.monthly_needed
              ? `Guardando ${money(p.monthly_needed)} por mês você chega lá no prazo (${p.months_left} ${p.months_left === 1 ? 'mês' : 'meses'}).`
              : goal.deadline
                ? 'O prazo já passou. Que tal definir um novo?'
                : 'Defina um prazo para saber quanto guardar por mês.'}
        </span>
      </div>

      <form className="inline-form" onSubmit={contribute(1)}>
        <label className="field grow">
          Valor (R$)
          <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0,00" />
        </label>
        <label className="field grow">
          Observação (opcional)
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={120} placeholder="Ex.: 13º salário" />
        </label>
        <button type="submit" className="btn btn-primary" disabled={action.isPending}>
          Guardar
        </button>
        <button type="button" className="btn btn-ghost" disabled={action.isPending} onClick={() => contribute(-1)()}>
          Retirar
        </button>
      </form>

      {msg && (
        <p className={msg.type === 'ok' ? 'success-text' : 'error-text'} role={msg.type === 'ok' ? 'status' : 'alert'}>
          {msg.text}
        </p>
      )}

      <div className="section">
        <h3>Participantes</h3>
        <ul className="members">
          {goal.members.map((m, i) => {
            const share = saved > 0 ? (Math.max(0, toNumber(m.contributed)) / saved) * 100 : 0
            const color = memberColors[i % memberColors.length] ?? '#17663F'
            const isMe = m.user_id === me.id
            return (
              <li key={m.user_id}>
                <span className="avatar" style={{ background: color }} aria-hidden="true">
                  {initials(m.name)}
                </span>
                <div className="member-body">
                  <div className="cat-row">
                    <span>
                      <strong>{isMe ? 'Você' : m.name}</strong>{' '}
                      <span className="muted">{m.role === 'owner' ? 'dono' : 'participante'}</span>
                    </span>
                    <span>{money(m.contributed)}</span>
                  </div>
                  <ProgressBar size="sm" percent={share} color={color} label={`Parte de ${m.name}`} />
                </div>
                {goal.is_owner && m.role !== 'owner' && (
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`Remover ${m.name} da meta`}
                    onClick={() => run(`/goals/${goal.id}/members/${m.user_id}/`, undefined, `${m.name} removido da meta.`, 'DELETE')}
                  >
                    <XIcon size={16} />
                  </button>
                )}
              </li>
            )
          })}
          {goal.invites.map((inv) => (
            <li key={`inv-${inv.id}`} className="pending">
              <span className="avatar avatar-pending" aria-hidden="true">
                {initials(inv.email)}
              </span>
              <div className="member-body">
                <div className="cat-row">
                  <span>
                    <strong>{inv.email}</strong> <span className="muted">convite pendente</span>
                  </span>
                  <span className="muted">aguardando</span>
                </div>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label={`Cancelar convite para ${inv.email}`}
                onClick={() => run(`/goals/${goal.id}/invites/${inv.id}/cancel/`, undefined, 'Convite cancelado.')}
              >
                <XIcon size={16} />
              </button>
            </li>
          ))}
        </ul>

        {goal.is_owner && (
          <form className="inline-form invite-form" onSubmit={sendInvite}>
            <label className="field grow">
              Convidar pessoa para a meta
              <input
                type="email"
                value={invite}
                onChange={(e) => setInvite(e.target.value)}
                placeholder="email@da.pessoa"
                maxLength={254}
              />
            </label>
            <button type="submit" className="btn btn-outline" disabled={action.isPending}>
              Enviar convite
            </button>
          </form>
        )}
      </div>

      <div className="section">
        <h3>Histórico de aportes</h3>
        {contributions.data && contributions.data.length === 0 && <Empty>Nenhum valor guardado ainda.</Empty>}
        {contributions.data && contributions.data.length > 0 && (
          <ul className="tx-list">
            {contributions.data.slice(0, 10).map((c) => (
              <li key={c.id}>
                <span>
                  {c.user_name}
                  <span className="muted">
                    {' '}
                    · {dateBR(c.date)}
                    {c.note && ` · ${c.note}`}
                  </span>
                </span>
                <strong className={toNumber(c.amount) >= 0 ? 'text-green' : 'text-orange'}>
                  {toNumber(c.amount) >= 0 ? '+ ' : '- '}
                  {money(Math.abs(toNumber(c.amount)))}
                </strong>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="goal-footer">
        {goal.is_owner ? (
          <>
            <button type="button" className="btn btn-ghost" onClick={onEdit}>
              <EditIcon size={16} /> Editar meta
            </button>
            {confirmDelete ? (
              <span className="confirm">
                Excluir a meta e todo o histórico?
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={() => run(`/goals/${goal.id}/`, undefined, 'Meta excluída.', 'DELETE', onGone)}
                >
                  Excluir
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(false)}>
                  Cancelar
                </button>
              </span>
            ) : (
              <button type="button" className="btn btn-ghost text-danger" onClick={() => setConfirmDelete(true)}>
                <TrashIcon size={16} /> Excluir
              </button>
            )}
          </>
        ) : (
          <button
            type="button"
            className="btn btn-ghost text-danger"
            onClick={() => run(`/goals/${goal.id}/leave/`, undefined, 'Você saiu da meta.', 'POST', onGone)}
          >
            Sair da meta
          </button>
        )}
      </div>
    </Card>
  )
}

function GoalForm({ goal, onClose, onCreated }: {
  goal: Goal | null
  onClose: () => void
  onCreated: (g: Goal) => void
}) {
  const save = useSaveGoal()
  const [form, setForm] = useState<GoalInput>({
    name: goal?.name ?? '',
    target_amount: goal ? String(goal.target_amount) : '',
    deadline: goal?.deadline ?? null,
  })
  const [errors, setErrors] = useState<Record<string, string>>({})

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const local: Record<string, string> = {}
    if (!form.name.trim()) local.name = 'Dê um nome para a meta.'
    const target = Number.parseFloat(form.target_amount.replace(',', '.'))
    if (!(target >= 1)) local.target_amount = 'Informe um valor de pelo menos R$ 1,00.'
    setErrors(local)
    if (Object.keys(local).length) return
    save.mutate(
      { id: goal?.id, data: { name: form.name.trim(), target_amount: target.toFixed(2), deadline: form.deadline || null } },
      {
        onSuccess: (g) => {
          if (!goal) onCreated(g)
          onClose()
        },
        onError: (err) => setErrors({ ...fieldErrors(err), form: errorMessage(err) }),
      },
    )
  }

  return (
    <Card title={goal ? 'Editar meta' : 'Nova meta'}>
      <form className="inline-form" onSubmit={onSubmit} noValidate>
        <label className="field grow">
          Nome
          <input
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Ex.: Viagem para o Nordeste"
            maxLength={80}
            autoFocus
          />
          {errors.name && <span className="field-error">{errors.name}</span>}
        </label>
        <label className="field">
          Valor da meta (R$)
          <input
            inputMode="decimal"
            value={form.target_amount}
            onChange={(e) => setForm((f) => ({ ...f, target_amount: e.target.value }))}
            placeholder="0,00"
          />
          {errors.target_amount && <span className="field-error">{errors.target_amount}</span>}
        </label>
        <label className="field">
          Prazo (opcional)
          <input
            type="date"
            value={form.deadline ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, deadline: e.target.value || null }))}
          />
        </label>
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>
          {save.isPending ? 'Salvando…' : goal ? 'Salvar' : 'Criar meta'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          Cancelar
        </button>
      </form>
      {errors.form && !errors.name && !errors.target_amount && <ErrorText>{errors.form}</ErrorText>}
    </Card>
  )
}
