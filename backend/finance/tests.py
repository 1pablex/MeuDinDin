from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from . import services
from .models import Category, Transaction


class FinanceBase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("bia@exemplo.com", "Senha#Forte2026", name="Bia")
        self.other = User.objects.create_user("caio@exemplo.com", "Senha#Forte2026", name="Caio")
        services.create_default_categories(self.user)
        services.create_default_categories(self.other)
        self.food = Category.objects.get(user=self.user, name="Alimentação")
        self.salary = Category.objects.get(user=self.user, name="Salário")
        self.client.force_authenticate(self.user)


class TransactionTests(FinanceBase):
    def test_create_and_list_only_own(self) -> None:
        Transaction.objects.create(
            user=self.other, kind="expense", description="Alheio", amount=10, date=date.today()
        )
        res = self.client.post(
            "/api/transactions/",
            {"kind": "expense", "description": " Mercado ", "amount": "120.50",
             "category": self.food.id, "date": str(date.today())},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["description"], "Mercado")
        listing = self.client.get("/api/transactions/")
        self.assertEqual([t["description"] for t in listing.data["results"]], ["Mercado"])

    def test_cannot_use_category_of_another_user(self) -> None:
        foreign = Category.objects.get(user=self.other, name="Alimentação")
        res = self.client.post(
            "/api/transactions/",
            {"kind": "expense", "description": "X", "amount": "1", "category": foreign.id, "date": "2026-01-01"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_category_kind_must_match(self) -> None:
        res = self.client.post(
            "/api/transactions/",
            {"kind": "expense", "description": "X", "amount": "1", "category": self.salary.id, "date": "2026-01-01"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_amount_must_be_positive(self) -> None:
        res = self.client.post(
            "/api/transactions/",
            {"kind": "expense", "description": "X", "amount": "-5", "date": "2026-01-01"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_touch_other_users_transaction(self) -> None:
        t = Transaction.objects.create(user=self.other, kind="expense", description="A", amount=1, date=date.today())
        self.assertEqual(self.client.get(f"/api/transactions/{t.id}/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(f"/api/transactions/{t.id}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_filters_by_kind(self) -> None:
        Transaction.objects.create(user=self.user, kind="expense", description="G", amount=1, date=date.today())
        Transaction.objects.create(user=self.user, kind="income", description="E", amount=1, date=date.today())
        res = self.client.get("/api/transactions/?kind=income")
        self.assertEqual([t["description"] for t in res.data["results"]], ["E"])


class RecurrenceTests(FinanceBase):
    def test_monthly_recurrence_clamps_day_and_is_idempotent(self) -> None:
        Transaction.objects.create(
            user=self.user, kind="expense", description="Aluguel", amount=1000,
            date=date(2026, 1, 31), recurrence="monthly",
        )
        services.materialize_recurring(self.user, until=date(2026, 4, 30))
        services.materialize_recurring(self.user, until=date(2026, 4, 30))
        dates = list(
            Transaction.objects.filter(description="Aluguel").order_by("date").values_list("date", flat=True)
        )
        self.assertEqual(dates, [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)])

    def test_weekly_and_daily(self) -> None:
        start = date(2026, 3, 1)
        Transaction.objects.create(user=self.user, kind="expense", description="Feira", amount=50,
                                   date=start, recurrence="weekly")
        Transaction.objects.create(user=self.user, kind="expense", description="Café", amount=5,
                                   date=start, recurrence="daily")
        services.materialize_recurring(self.user, until=start + timedelta(days=14))
        self.assertEqual(Transaction.objects.filter(description="Feira").count(), 3)
        self.assertEqual(Transaction.objects.filter(description="Café").count(), 15)

    def test_stopping_recurrence_stops_generation(self) -> None:
        tpl = Transaction.objects.create(user=self.user, kind="expense", description="Streaming", amount=40,
                                         date=date(2026, 1, 10), recurrence="monthly")
        services.materialize_recurring(self.user, until=date(2026, 2, 15))
        tpl.recurrence = "none"
        tpl.save()
        services.materialize_recurring(self.user, until=date(2026, 6, 15))
        self.assertEqual(Transaction.objects.filter(description="Streaming").count(), 2)


class DashboardTests(FinanceBase):
    def test_dashboard_totals_by_period(self) -> None:
        ref = date(2026, 11, 10)  # terça-feira
        Transaction.objects.create(user=self.user, kind="income", description="Salário", amount=Decimal("5000"),
                                   date=date(2026, 11, 1), category=self.salary)
        Transaction.objects.create(user=self.user, kind="expense", description="Mercado", amount=Decimal("200"),
                                   date=ref, category=self.food)
        Transaction.objects.create(user=self.user, kind="expense", description="Antigo", amount=Decimal("300"),
                                   date=date(2026, 10, 5))
        Transaction.objects.create(user=self.other, kind="expense", description="Outro", amount=Decimal("999"),
                                   date=ref)

        with mock.patch.object(services, "today", return_value=ref):
            monthly = self.client.get("/api/dashboard/?period=monthly").data
            daily = self.client.get("/api/dashboard/?period=daily").data
            weekly = self.client.get("/api/dashboard/?period=weekly").data

        self.assertEqual(monthly["income"], Decimal("5000"))
        self.assertEqual(monthly["expense"], Decimal("200"))
        self.assertEqual(monthly["balance"], Decimal("4500"))
        self.assertEqual(len(monthly["series"]), 6)
        self.assertEqual(monthly["by_category"][0]["name"], "Alimentação")
        self.assertEqual(daily["expense"], Decimal("200"))
        self.assertEqual(daily["income"], Decimal("0"))
        self.assertEqual(len(daily["series"]), 7)
        self.assertEqual(len(weekly["series"]), 8)

    def test_invalid_period(self) -> None:
        self.assertEqual(self.client.get("/api/dashboard/?period=yearly").status_code, 400)

    def test_requires_auth(self) -> None:
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 401)
