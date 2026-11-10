"""Regras de negócio de finanças: categorias padrão, recorrência e dashboard."""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import DecimalField, Max, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Category, Kind, Recurrence, Transaction

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2))
MAX_OCCURRENCES_PER_RUN = 1000

DEFAULT_CATEGORIES: list[tuple[str, str, str]] = [
    ("Alimentação", Kind.EXPENSE, "#E07A2E"),
    ("Transporte", Kind.EXPENSE, "#2C6FB7"),
    ("Moradia", Kind.EXPENSE, "#7A4CB0"),
    ("Contas", Kind.EXPENSE, "#B4471A"),
    ("Lazer", Kind.EXPENSE, "#D4A017"),
    ("Saúde", Kind.EXPENSE, "#C2416B"),
    ("Educação", Kind.EXPENSE, "#3A8C8C"),
    ("Outros", Kind.EXPENSE, "#6B7A72"),
    ("Salário", Kind.INCOME, "#17663F"),
    ("Renda extra", Kind.INCOME, "#3DDC84"),
    ("Outros", Kind.INCOME, "#6B7A72"),
]


def create_default_categories(user) -> None:
    Category.objects.bulk_create(
        [Category(user=user, name=n, kind=k, color=c) for n, k, c in DEFAULT_CATEGORIES],
        ignore_conflicts=True,
    )


def today() -> date:
    return timezone.localdate()


def add_months(d: date, months: int, anchor_day: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor_day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_date(current: date, recurrence: str, anchor_day: int) -> date:
    if recurrence == Recurrence.DAILY:
        return current + timedelta(days=1)
    if recurrence == Recurrence.WEEKLY:
        return current + timedelta(weeks=1)
    if recurrence == Recurrence.MONTHLY:
        return add_months(current, 1, anchor_day)
    raise ValueError(f"Recorrência inválida: {recurrence}")


def materialize_recurring(user, until: date | None = None) -> int:
    """Gera as ocorrências de lançamentos recorrentes até `until` (hoje).
    Idempotente: a constraint (parent, date) evita duplicatas."""
    until = until or today()
    templates = (
        Transaction.objects.filter(user=user, parent__isnull=True, date__lt=until)
        .exclude(recurrence=Recurrence.NONE)
        .annotate(last_date=Max("occurrences__date"))
    )
    created = 0
    for tpl in templates:
        last = tpl.last_date or tpl.date
        to_create: list[Transaction] = []
        current = next_date(last, tpl.recurrence, tpl.date.day)
        while current <= until and len(to_create) < MAX_OCCURRENCES_PER_RUN:
            to_create.append(
                Transaction(
                    user=user,
                    kind=tpl.kind,
                    description=tpl.description,
                    amount=tpl.amount,
                    category_id=tpl.category_id,
                    date=current,
                    recurrence=Recurrence.NONE,
                    parent=tpl,
                )
            )
            current = next_date(current, tpl.recurrence, tpl.date.day)
        if to_create:
            Transaction.objects.bulk_create(to_create, ignore_conflicts=True)
            created += len(to_create)
    return created


def totals(qs: QuerySet[Transaction]) -> dict[str, Decimal]:
    agg = qs.aggregate(
        income=Coalesce(Sum("amount", filter=Q(kind=Kind.INCOME)), ZERO),
        expense=Coalesce(Sum("amount", filter=Q(kind=Kind.EXPENSE)), ZERO),
    )
    return {"income": agg["income"], "expense": agg["expense"]}


PERIODS = ("daily", "weekly", "monthly")


def period_range(period: str, ref: date) -> tuple[date, date]:
    if period == "daily":
        return ref, ref
    if period == "weekly":
        start = ref - timedelta(days=ref.weekday())
        return start, start + timedelta(days=6)
    start = ref.replace(day=1)
    return start, add_months(start, 1, 1) - timedelta(days=1)


def series_buckets(period: str, ref: date) -> list[tuple[str, date, date]]:
    """Janelas do gráfico: 7 dias, 8 semanas ou 6 meses terminando em `ref`."""
    buckets: list[tuple[str, date, date]] = []
    if period == "daily":
        for i in range(6, -1, -1):
            d = ref - timedelta(days=i)
            buckets.append((d.strftime("%d/%m"), d, d))
    elif period == "weekly":
        current_start = ref - timedelta(days=ref.weekday())
        for i in range(7, -1, -1):
            s = current_start - timedelta(weeks=i)
            buckets.append((s.strftime("%d/%m"), s, s + timedelta(days=6)))
    else:
        month_names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        first = ref.replace(day=1)
        for i in range(5, -1, -1):
            s = add_months(first, -i, 1)
            e = add_months(s, 1, 1) - timedelta(days=1)
            buckets.append((month_names[s.month - 1], s, e))
    return buckets


def build_series(qs: QuerySet[Transaction], period: str, ref: date) -> list[dict]:
    buckets = series_buckets(period, ref)
    start, end = buckets[0][1], buckets[-1][2]
    rows = (
        qs.filter(date__range=(start, end))
        .values("date", "kind")
        .annotate(total=Sum("amount"))
    )
    result = [{"label": label, "income": Decimal("0"), "expense": Decimal("0")} for label, _, _ in buckets]
    for row in rows:
        for idx, (_, s, e) in enumerate(buckets):
            if s <= row["date"] <= e:
                result[idx][row["kind"]] += row["total"]
                break
    return result


def expenses_by_category(qs: QuerySet[Transaction]) -> list[dict]:
    rows = (
        qs.filter(kind=Kind.EXPENSE)
        .values("category__name", "category__color")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    return [
        {
            "name": r["category__name"] or "Sem categoria",
            "color": r["category__color"] or "#6B7A72",
            "total": r["total"],
        }
        for r in rows
    ]
