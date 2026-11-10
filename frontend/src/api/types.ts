/** Valores monetários chegam do DRF como string decimal ("120.50") ou número. */
export type Money = string | number

export type Kind = 'income' | 'expense'
export type Recurrence = 'none' | 'daily' | 'weekly' | 'monthly'
export type Period = 'daily' | 'weekly' | 'monthly'

export interface User {
  id: number
  email: string
  name: string
  two_factor_enabled: boolean
}

export interface AuthResponse {
  access: string
  user: User
  /** Segundos sem uso até a sessão expirar */
  idle_timeout: number
}

/** Resposta do login quando o 2FA está ativo: falta o código do app. */
export interface MfaChallenge {
  mfa_required: true
  mfa_token: string
}

export interface TwoFactorStatus {
  enabled: boolean
  recovery_codes_left: number
}

export interface TwoFactorSetup {
  secret: string
  otpauth_uri: string
  qr_svg: string
  expires_in: number
}

export interface Category {
  id: number
  name: string
  kind: Kind
  color: string
}

export interface Transaction {
  id: number
  kind: Kind
  description: string
  amount: Money
  category: number | null
  category_name: string | null
  category_color: string | null
  date: string
  recurrence: Recurrence
  is_occurrence: boolean
  created_at: string
}

export interface TransactionInput {
  kind: Kind
  description: string
  amount: string
  category: number | null
  date: string
  recurrence: Recurrence
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface GoalSummary {
  id: number
  name: string
  target_amount: Money
  saved: Money
  missing: Money
  percent: number
  shared: boolean
}

export interface Dashboard {
  period: Period
  range: { start: string; end: string }
  balance: Money
  available: Money
  saved_in_goals: Money
  missing_for_goals: Money
  income: Money
  expense: Money
  transactions_count: number
  series: { label: string; income: Money; expense: Money }[]
  by_category: { name: string; color: string; total: Money }[]
  recent: Transaction[]
  goals: GoalSummary[]
}

export interface GoalProgress {
  saved: Money
  missing: Money
  percent: number
  months_left: number | null
  monthly_needed: Money | null
}

export interface Goal {
  id: number
  name: string
  target_amount: Money
  deadline: string | null
  owner_name: string
  is_owner: boolean
  members_count: number
  progress: GoalProgress
  created_at: string
}

export interface GoalMember {
  user_id: number
  name: string
  email: string
  role: 'owner' | 'member'
  joined_at: string
  contributed: Money
}

export interface GoalInvite {
  id: number
  email: string
  status: 'pending' | 'accepted' | 'declined' | 'canceled'
  created_at: string
}

export interface GoalDetail extends Goal {
  members: GoalMember[]
  invites: GoalInvite[]
}

export interface GoalInput {
  name: string
  target_amount: string
  deadline: string | null
}

export interface Contribution {
  id: number
  amount: Money
  note: string
  date: string
  user_name: string
  created_at: string
}

export interface MyInvite {
  id: number
  goal_name: string
  invited_by_name: string
  target_amount: Money
  created_at: string
}
