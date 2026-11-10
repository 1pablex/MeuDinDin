import { errorMessage } from '../api/client'
import { useGoalAction, useMyInvites } from '../api/hooks'
import { money } from '../lib/format'
import { ErrorText } from './ui'

/** Convites pendentes para metas em conjunto, com aceitar/recusar. */
export function InvitesBanner({ onAccepted }: { onAccepted?: (goalId: number) => void }) {
  const { data } = useMyInvites()
  const action = useGoalAction()
  if (!data?.length) return null

  const respond = (id: number, accept: boolean) =>
    action.mutate(
      { path: `/invites/${id}/${accept ? 'accept' : 'decline'}/` },
      {
        onSuccess: (res) => {
          const goalId = (res as { goal_id?: number } | null)?.goal_id
          if (accept && goalId) onAccepted?.(goalId)
        },
      },
    )

  return (
    <section className="invites" aria-label="Convites para metas">
      {data.map((inv) => (
        <div key={inv.id} className="invite">
          <p>
            <strong>{inv.invited_by_name}</strong> convidou você para a meta <strong>{inv.goal_name}</strong> (
            {money(inv.target_amount)}).
          </p>
          <div className="invite-actions">
            <button type="button" className="btn btn-primary" disabled={action.isPending} onClick={() => respond(inv.id, true)}>
              Participar
            </button>
            <button type="button" className="btn btn-ghost" disabled={action.isPending} onClick={() => respond(inv.id, false)}>
              Recusar
            </button>
          </div>
        </div>
      ))}
      {action.error && <ErrorText>{errorMessage(action.error)}</ErrorText>}
    </section>
  )
}
