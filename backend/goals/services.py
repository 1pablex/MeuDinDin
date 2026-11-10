from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, IntegerField, OuterRef, Prefetch, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Contribution, Goal, GoalMember

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2))
CENT = Decimal("0.01")


def goals_for(user) -> QuerySet[Goal]:
    """Metas em que o usuário participa (dono ou membro), já com totais."""
    # Subqueries evitam que os JOINs de membros e aportes multipliquem os totais
    saved_sq = (
        Contribution.objects.filter(goal=OuterRef("pk"))
        .values("goal")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    members_sq = (
        GoalMember.objects.filter(goal=OuterRef("pk")).values("goal").annotate(c=Count("id")).values("c")
    )
    return (
        Goal.objects.filter(pk__in=GoalMember.objects.filter(user=user).values("goal_id"))
        .select_related("owner")
        .annotate(
            saved=Coalesce(Subquery(saved_sq, output_field=DecimalField(max_digits=14, decimal_places=2)), ZERO),
            members_count=Coalesce(Subquery(members_sq, output_field=IntegerField()), Value(0)),
        )
    )


def with_members(qs: QuerySet[Goal]) -> QuerySet[Goal]:
    return qs.prefetch_related(
        Prefetch("memberships", queryset=GoalMember.objects.select_related("user").order_by("joined_at"))
    )


def months_until(deadline: date | None, ref: date) -> int | None:
    if deadline is None:
        return None
    months = (deadline.year - ref.year) * 12 + (deadline.month - ref.month)
    if deadline.day >= ref.day:
        months += 1
    return max(months, 0)


def progress(goal: Goal) -> dict:
    saved = max(goal.saved, Decimal("0"))
    missing = max(goal.target_amount - saved, Decimal("0"))
    pct = min(int(saved / goal.target_amount * 100), 100) if goal.target_amount else 0
    months = months_until(goal.deadline, timezone.localdate())
    monthly = None
    if missing > 0 and months:
        monthly = (missing / months).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "saved": saved,
        "missing": missing,
        "percent": pct,
        "months_left": months,
        "monthly_needed": monthly,
    }


def goals_summary_for(user) -> list[dict]:
    result = []
    for goal in goals_for(user):
        p = progress(goal)
        result.append(
            {
                "id": goal.id,
                "name": goal.name,
                "target_amount": goal.target_amount,
                "saved": p["saved"],
                "missing": p["missing"],
                "percent": p["percent"],
                "shared": goal.members_count > 1,
            }
        )
    return result
