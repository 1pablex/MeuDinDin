import type { Money, Recurrence } from '../api/types'

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

export function toNumber(value: Money | null | undefined): number {
  if (value === null || value === undefined) return 0
  const n = typeof value === 'number' ? value : Number.parseFloat(value)
  return Number.isFinite(n) ? n : 0
}

export function money(value: Money | null | undefined): string {
  return brl.format(toNumber(value))
}

/** "2026-11-10" -> "10/11/2026" sem passar por Date (evita erro de fuso). */
export function dateBR(iso: string): string {
  const [y, m, d] = iso.split('-')
  return y && m && d ? `${d}/${m}/${y}` : iso
}

export function todayISO(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export const recurrenceLabel: Record<Recurrence, string> = {
  none: 'Único',
  daily: 'Diário',
  weekly: 'Semanal',
  monthly: 'Mensal',
}

export function initials(name: string): string {
  return name.trim().charAt(0).toUpperCase() || '?'
}
