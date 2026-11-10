from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Goal(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_goals")
    name = models.CharField(max_length=80)
    target_amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("1.00"))]
    )
    deadline = models.DateField(null=True, blank=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through="GoalMember", related_name="goals")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["deadline", "-created_at"]
        verbose_name = "meta"

    def __str__(self) -> str:
        return self.name


class GoalMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Dono"
        MEMBER = "member", "Participante"

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goal_memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["goal", "user"], name="uniq_goal_member")]
        indexes = [models.Index(fields=["user", "goal"])]
        verbose_name = "participante"


class Contribution(models.Model):
    """Valor guardado na meta. Valores negativos representam retiradas."""

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="contributions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goal_contributions"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=120, blank=True)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["goal", "user"])]
        verbose_name = "aporte"


class GoalInvite(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        ACCEPTED = "accepted", "Aceito"
        DECLINED = "declined", "Recusado"
        CANCELED = "canceled", "Cancelado"

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField()
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_invites")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["email", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["goal", "email"],
                condition=models.Q(status="pending"),
                name="uniq_pending_invite",
            ),
        ]
        verbose_name = "convite"
