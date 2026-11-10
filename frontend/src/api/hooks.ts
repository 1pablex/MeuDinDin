import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type {
  Category,
  Contribution,
  Dashboard,
  Goal,
  GoalDetail,
  GoalInput,
  Kind,
  MyInvite,
  Paginated,
  Period,
  Transaction,
  TransactionInput,
} from './types'

export const keys = {
  dashboard: (period: Period) => ['dashboard', period] as const,
  categories: ['categories'] as const,
  transactions: (filters: TransactionFilters) => ['transactions', filters] as const,
  goals: ['goals'] as const,
  goal: (id: number) => ['goals', id] as const,
  contributions: (id: number) => ['goals', id, 'contributions'] as const,
  invites: ['invites'] as const,
}

export function useDashboard(period: Period) {
  return useQuery({
    queryKey: keys.dashboard(period),
    queryFn: () => api<Dashboard>(`/dashboard/?period=${period}`),
  })
}

export function useCategories() {
  return useQuery({ queryKey: keys.categories, queryFn: () => api<Category[]>('/categories/') })
}

export interface TransactionFilters {
  kind: Kind | 'all'
  period: Period | 'all'
  page: number
}

export function useTransactions(filters: TransactionFilters) {
  const params = new URLSearchParams({ page: String(filters.page) })
  if (filters.kind !== 'all') params.set('kind', filters.kind)
  if (filters.period !== 'all') params.set('period', filters.period)
  return useQuery({
    queryKey: keys.transactions(filters),
    queryFn: () => api<Paginated<Transaction>>(`/transactions/?${params.toString()}`),
    placeholderData: (prev) => prev,
  })
}

/** Toda escrita em finanças invalida dashboard e listas. */
function useInvalidateFinance() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: ['transactions'] })
    void qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
}

export function useSaveTransaction() {
  const invalidate = useInvalidateFinance()
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: TransactionInput }) =>
      id ? api<Transaction>(`/transactions/${id}/`, 'PATCH', data) : api<Transaction>('/transactions/', 'POST', data),
    onSuccess: invalidate,
  })
}

export function useDeleteTransaction() {
  const invalidate = useInvalidateFinance()
  return useMutation({
    mutationFn: (id: number) => api<null>(`/transactions/${id}/`, 'DELETE'),
    onSuccess: invalidate,
  })
}

export function useGoals() {
  return useQuery({ queryKey: keys.goals, queryFn: () => api<Goal[]>('/goals/') })
}

export function useGoal(id: number | null) {
  return useQuery({
    queryKey: keys.goal(id ?? 0),
    queryFn: () => api<GoalDetail>(`/goals/${id}/`),
    enabled: id !== null,
  })
}

export function useContributions(id: number | null) {
  return useQuery({
    queryKey: keys.contributions(id ?? 0),
    queryFn: () => api<Contribution[]>(`/goals/${id}/contributions/`),
    enabled: id !== null,
  })
}

export function useMyInvites() {
  return useQuery({ queryKey: keys.invites, queryFn: () => api<MyInvite[]>('/invites/') })
}

function useInvalidateGoals() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: ['goals'] })
    void qc.invalidateQueries({ queryKey: ['dashboard'] })
    void qc.invalidateQueries({ queryKey: keys.invites })
  }
}

export function useSaveGoal() {
  const invalidate = useInvalidateGoals()
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: GoalInput }) =>
      id ? api<Goal>(`/goals/${id}/`, 'PATCH', data) : api<Goal>('/goals/', 'POST', data),
    onSuccess: invalidate,
  })
}

export function useGoalAction() {
  const invalidate = useInvalidateGoals()
  return useMutation({
    mutationFn: ({ path, method = 'POST', body }: { path: string; method?: 'POST' | 'DELETE'; body?: unknown }) =>
      api<unknown>(path, method, body),
    onSuccess: invalidate,
  })
}
