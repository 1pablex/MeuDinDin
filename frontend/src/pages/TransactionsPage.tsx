import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { errorMessage, fieldErrors } from '../api/client'
import {
  useCategories,
  useDeleteTransaction,
  useSaveTransaction,
  useTransactions,
  type TransactionFilters,
} from '../api/hooks'
import type { Kind, Recurrence, Transaction, TransactionInput } from '../api/types'
import { EditIcon, TrashIcon } from '../components/Icons'
import { MoneyInput } from '../components/MoneyInput'
import { normalizeDecimal } from '../lib/money'
import { Card, Empty, ErrorText, Loading, Segmented } from '../components/ui'
import { dateBR, money, recurrenceLabel, todayISO } from '../lib/format'

const kindFilters = [
  { value: 'all', label: 'Todos' },
  { value: 'expense', label: 'Gastos' },
  { value: 'income', label: 'Entradas' },
] as const

const periodFilters = [
  { value: 'all', label: 'Tudo' },
  { value: 'daily', label: 'Hoje' },
  { value: 'weekly', label: 'Semana' },
  { value: 'monthly', label: 'Mês' },
] as const

const emptyForm = (): TransactionInput => ({
  kind: 'expense',
  description: '',
  amount: '',
  category: null,
  date: todayISO(),
  recurrence: 'none',
})

export function TransactionsPage() {
  const [filters, setFilters] = useState<TransactionFilters>({ kind: 'all', period: 'all', page: 1 })
  const { data, isPending, error } = useTransactions(filters)
  const [editing, setEditing] = useState<Transaction | null>(null)

  const totalPages = data ? Math.max(1, Math.ceil(data.count / 50)) : 1

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="display-lg">Lançamentos</h1>
          <p className="muted">Registre entradas e gastos, avulsos ou recorrentes.</p>
        </div>
      </header>

      <div className="row align-start">
        <TransactionForm key={editing?.id ?? 'new'} editing={editing} onDone={() => setEditing(null)} />

        <Card
          title="Histórico"
          className="grow-2"
          action={
            <div className="filters">
              <Segmented
                options={periodFilters}
                value={filters.period}
                onChange={(period) => setFilters((f) => ({ ...f, period, page: 1 }))}
                label="Período"
              />
              <Segmented
                options={kindFilters}
                value={filters.kind}
                onChange={(kind) => setFilters((f) => ({ ...f, kind, page: 1 }))}
                label="Tipo"
              />
            </div>
          }
        >
          {isPending && <Loading />}
          {error && <ErrorText>{errorMessage(error)}</ErrorText>}
          {data && data.results.length === 0 && <Empty>Nenhum lançamento encontrado.</Empty>}
          {data && data.results.length > 0 && (
            <>
              <ul className="tx-cards" aria-label="Lançamentos">
                {data.results.map((t) => (
                  <TransactionCard key={t.id} tx={t} onEdit={setEditing} />
                ))}
              </ul>
              <div className="table-wrap hide-mobile">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Descrição</th>
                      <th scope="col">Categoria</th>
                      <th scope="col">Recorrência</th>
                      <th scope="col">Data</th>
                      <th scope="col" className="num">Valor</th>
                      <th scope="col"><span className="sr-only">Ações</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((t) => (
                      <TransactionRow key={t.id} tx={t} onEdit={setEditing} />
                    ))}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && (
                <nav className="pager" aria-label="Paginação">
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={!data.previous}
                    onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}
                  >
                    Anterior
                  </button>
                  <span className="muted">
                    Página {filters.page} de {totalPages}
                  </span>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={!data.next}
                    onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}
                  >
                    Próxima
                  </button>
                </nav>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  )
}

type RowProps = { tx: Transaction; onEdit: (t: Transaction) => void }

function recurrenceText(tx: Transaction): string {
  return tx.is_occurrence ? 'Recorrente' : recurrenceLabel[tx.recurrence]
}

function CategoryChip({ tx }: { tx: Transaction }) {
  return (
    <span className="chip">
      <i style={{ background: tx.category_color ?? 'var(--muted)' }} />
      {tx.category_name ?? 'Sem categoria'}
    </span>
  )
}

function Amount({ tx, as: Tag = 'strong', className = '' }: { tx: Transaction; as?: 'strong' | 'td'; className?: string }) {
  return (
    <Tag className={`${className} ${tx.kind === 'income' ? 'text-green' : 'text-orange'}`}>
      {tx.kind === 'income' ? '+ ' : '- '}
      {money(tx.amount)}
    </Tag>
  )
}

/** Editar/excluir com confirmação em duas etapas (sem diálogo do navegador). */
function RowActions({ tx, onEdit }: RowProps) {
  const remove = useDeleteTransaction()
  const [confirming, setConfirming] = useState(false)

  if (confirming) {
    return (
      <>
        <button type="button" className="btn btn-danger btn-sm" onClick={() => remove.mutate(tx.id)} disabled={remove.isPending}>
          Excluir
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirming(false)}>
          Cancelar
        </button>
      </>
    )
  }
  return (
    <>
      <button type="button" className="icon-btn" aria-label={`Editar ${tx.description}`} onClick={() => onEdit(tx)}>
        <EditIcon size={16} />
      </button>
      <button type="button" className="icon-btn" aria-label={`Excluir ${tx.description}`} onClick={() => setConfirming(true)}>
        <TrashIcon size={16} />
      </button>
    </>
  )
}

function TransactionRow({ tx, onEdit }: RowProps) {
  return (
    <tr>
      <td className="strong">{tx.description}</td>
      <td>
        <CategoryChip tx={tx} />
      </td>
      <td className="muted">{recurrenceText(tx)}</td>
      <td className="muted">{dateBR(tx.date)}</td>
      <Amount tx={tx} as="td" className="num strong" />
      <td className="actions">
        <RowActions tx={tx} onEdit={onEdit} />
      </td>
    </tr>
  )
}

function TransactionCard({ tx, onEdit }: RowProps) {
  return (
    <li className="tx-card">
      <div className="tx-card-top">
        <strong>{tx.description}</strong>
        <Amount tx={tx} />
      </div>
      <div className="tx-card-meta">
        <CategoryChip tx={tx} />
        <span className="muted">
          {dateBR(tx.date)} · {recurrenceText(tx)}
        </span>
        <span className="tx-card-actions">
          <RowActions tx={tx} onEdit={onEdit} />
        </span>
      </div>
    </li>
  )
}

function TransactionForm({ editing, onDone }: { editing: Transaction | null; onDone: () => void }) {
  const { data: categories } = useCategories()
  const save = useSaveTransaction()
  const [form, setForm] = useState<TransactionInput>(() =>
    editing
      ? {
          kind: editing.kind,
          description: editing.description,
          amount: normalizeDecimal(editing.amount),
          category: editing.category,
          date: editing.date,
          recurrence: editing.recurrence,
        }
      : emptyForm(),
  )
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)
  // No celular o formulário começa recolhido; ao editar, abre e rola até ele
  const [open, setOpen] = useState(editing !== null)
  const cardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (editing) cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [editing])

  const options = useMemo(() => (categories ?? []).filter((c) => c.kind === form.kind), [categories, form.kind])

  const set = <K extends keyof TransactionInput>(key: K, value: TransactionInput[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    setSaved(false)
  }

  const setKind = (kind: Kind) => setForm((f) => ({ ...f, kind, category: null }))

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const local: Record<string, string> = {}
    if (!form.description.trim()) local.description = 'Informe a descrição.'
    const amount = Number.parseFloat(form.amount.replace(',', '.'))
    if (!(amount > 0)) local.amount = 'Informe um valor maior que zero.'
    setErrors(local)
    if (Object.keys(local).length) return

    save.mutate(
      { id: editing?.id, data: { ...form, description: form.description.trim(), amount: amount.toFixed(2) } },
      {
        onSuccess: () => {
          setErrors({})
          if (editing) onDone()
          else {
            setForm((f) => ({ ...emptyForm(), kind: f.kind, category: f.category, date: f.date }))
            setSaved(true)
          }
        },
        onError: (err) => setErrors({ ...fieldErrors(err), form: errorMessage(err) }),
      },
    )
  }

  return (
    <div ref={cardRef} className="grow-1">
    <Card
      title={editing ? 'Editar lançamento' : 'Novo lançamento'}
      className={`form-card ${open ? 'is-open' : ''}`}
      action={
        <button
          type="button"
          className="btn btn-ghost btn-sm show-mobile"
          aria-expanded={open}
          aria-controls="tx-form"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? 'Fechar' : 'Abrir'}
        </button>
      }
    >
      <form id="tx-form" className="stack form-body" onSubmit={onSubmit} noValidate>
        <div className="kind-toggle" role="radiogroup" aria-label="Tipo">
          <button
            type="button"
            role="radio"
            aria-checked={form.kind === 'expense'}
            className={form.kind === 'expense' ? 'is-expense' : undefined}
            onClick={() => setKind('expense')}
          >
            Gasto
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={form.kind === 'income'}
            className={form.kind === 'income' ? 'is-income' : undefined}
            onClick={() => setKind('income')}
          >
            Entrada
          </button>
        </div>

        <label className="field">
          Descrição
          <input
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="Ex.: Mercado"
            maxLength={120}
          />
          {errors.description && <span className="field-error">{errors.description}</span>}
        </label>

        <div className="grid-2">
          <label className="field">
            Valor
            <MoneyInput value={form.amount} onChange={(v) => set('amount', v)} />
            {errors.amount && <span className="field-error">{errors.amount}</span>}
          </label>
          <label className="field">
            Data
            <input type="date" value={form.date} onChange={(e) => set('date', e.target.value)} />
            {errors.date && <span className="field-error">{errors.date}</span>}
          </label>
        </div>

        <label className="field">
          Categoria
          <select
            value={form.category ?? ''}
            onChange={(e) => set('category', e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Sem categoria</option>
            {options.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {errors.category && <span className="field-error">{errors.category}</span>}
        </label>

        {!editing?.is_occurrence && (
          <label className="field">
            Recorrência
            <select value={form.recurrence} onChange={(e) => set('recurrence', e.target.value as Recurrence)}>
              {(Object.keys(recurrenceLabel) as Recurrence[]).map((r) => (
                <option key={r} value={r}>
                  {recurrenceLabel[r]}
                </option>
              ))}
            </select>
            <span className="field-hint">
              Recorrentes se repetem sozinhos a partir da data escolhida. Volte para “Único” para parar.
            </span>
          </label>
        )}

        {errors.form && !errors.description && !errors.amount && <ErrorText>{errors.form}</ErrorText>}
        {saved && (
          <p className="success-text" role="status">
            Lançamento adicionado.
          </p>
        )}

        <div className="form-actions">
          <button type="submit" className="btn btn-primary btn-lg" disabled={save.isPending}>
            {save.isPending ? 'Salvando…' : editing ? 'Salvar alterações' : 'Adicionar'}
          </button>
          {editing && (
            <button type="button" className="btn btn-ghost btn-lg" onClick={onDone}>
              Cancelar
            </button>
          )}
        </div>
      </form>
    </Card>
    </div>
  )
}
