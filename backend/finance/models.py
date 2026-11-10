from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Kind(models.TextChoices):
    INCOME = "income", "Entrada"
    EXPENSE = "expense", "Gasto"


class Recurrence(models.TextChoices):
    NONE = "none", "Único"
    DAILY = "daily", "Diário"
    WEEKLY = "weekly", "Semanal"
    MONTHLY = "monthly", "Mensal"


class Category(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    color = models.CharField(max_length=7, default="#17663F")

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name", "kind"], name="uniq_category_per_user"),
        ]
        verbose_name = "categoria"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_kind_display()})"


class Transaction(models.Model):
    """Lançamento. Se `recurrence` != none e `parent` é nulo, é o modelo da
    recorrência; as ocorrências seguintes são geradas com `parent` apontando
    para ele (ver services.materialize_recurring)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    description = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions")
    date = models.DateField()
    recurrence = models.CharField(max_length=10, choices=Recurrence.choices, default=Recurrence.NONE)
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="occurrences")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "kind", "date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "date"],
                condition=models.Q(parent__isnull=False),
                name="uniq_occurrence_per_date",
            ),
        ]
        verbose_name = "lançamento"

    def __str__(self) -> str:
        return f"{self.description} R$ {self.amount}"
