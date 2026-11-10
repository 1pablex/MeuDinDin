from datetime import date
from decimal import Decimal

from django.db.models import Sum
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from goals.services import goals_summary_for

from . import services
from .models import Category, Kind, Transaction
from .serializers import CategorySerializer, TransactionSerializer


def _parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({field: "Data inválida, use AAAA-MM-DD."}) from exc


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        qs = Category.objects.filter(user=self.request.user)
        kind = self.request.query_params.get("kind")
        if kind in Kind.values:
            qs = qs.filter(kind=kind)
        return qs

    def perform_create(self, serializer) -> None:
        serializer.save(user=self.request.user)


class TransactionViewSet(viewsets.ModelViewSet):
    """CRUD de lançamentos. Filtros: kind, category, start, end, period
    (daily|weekly|monthly relativo a hoje) e search."""

    serializer_class = TransactionSerializer

    def get_queryset(self):
        params = self.request.query_params
        qs = Transaction.objects.filter(user=self.request.user).select_related("category")
        if params.get("kind") in Kind.values:
            qs = qs.filter(kind=params["kind"])
        if params.get("category", "").isdigit():
            qs = qs.filter(category_id=int(params["category"]))
        period = params.get("period")
        if period in services.PERIODS:
            start, end = services.period_range(period, services.today())
            qs = qs.filter(date__range=(start, end))
        start = _parse_date(params.get("start"), "start")
        end = _parse_date(params.get("end"), "end")
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        if params.get("search"):
            qs = qs.filter(description__icontains=params["search"][:60])
        return qs

    def list(self, request: Request, *args, **kwargs) -> Response:
        services.materialize_recurring(request.user)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer) -> None:
        serializer.save(user=self.request.user)


class DashboardView(APIView):
    def get(self, request: Request) -> Response:
        period = request.query_params.get("period", "monthly")
        if period not in services.PERIODS:
            raise ValidationError({"period": "Use daily, weekly ou monthly."})

        user = request.user
        services.materialize_recurring(user)
        ref = services.today()
        base = Transaction.objects.filter(user=user)
        start, end = services.period_range(period, ref)
        in_period = base.filter(date__range=(start, end))

        all_time = services.totals(base.filter(date__lte=ref))
        current = services.totals(in_period)
        goals = goals_summary_for(user)
        saved_by_me = user.goal_contributions.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        balance = all_time["income"] - all_time["expense"]

        recent = base.filter(date__lte=ref).select_related("category")[:6]
        return Response(
            {
                "period": period,
                "range": {"start": start, "end": end},
                "balance": balance,
                "available": balance - saved_by_me,
                "saved_in_goals": saved_by_me,
                "missing_for_goals": sum((g["missing"] for g in goals), Decimal("0")),
                "income": current["income"],
                "expense": current["expense"],
                "transactions_count": in_period.count(),
                "series": services.build_series(base, period, ref),
                "by_category": services.expenses_by_category(in_period),
                "recent": TransactionSerializer(recent, many=True, context={"request": request}).data,
                "goals": goals,
            }
        )
