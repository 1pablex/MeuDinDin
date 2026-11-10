import logging
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from accounts import emails
from accounts.models import User

from .models import Contribution, Goal, GoalInvite, GoalMember
from .permissions import IsGoalOwnerForManagement
from .serializers import (
    ContributionSerializer,
    GoalDetailSerializer,
    GoalSerializer,
    InviteCreateSerializer,
    InviteSerializer,
    MyInviteSerializer,
)
from .services import goals_for, with_members

security_log = logging.getLogger("security")


class GoalViewSet(viewsets.ModelViewSet):
    """Metas do usuário. Metas de outras pessoas retornam 404 (o queryset
    só contém metas em que ele participa)."""

    permission_classes = [permissions.IsAuthenticated, IsGoalOwnerForManagement]
    pagination_class = None

    def get_queryset(self):
        return with_members(goals_for(self.request.user))

    def get_serializer_class(self):
        if self.action == "retrieve":
            return GoalDetailSerializer
        return GoalSerializer

    @transaction.atomic
    def perform_create(self, serializer) -> None:
        goal = serializer.save(owner=self.request.user)
        GoalMember.objects.create(goal=goal, user=self.request.user, role=GoalMember.Role.OWNER)

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        goal = self.get_queryset().get(pk=serializer.instance.pk)
        return Response(GoalSerializer(goal, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"])
    def contributions(self, request: Request, pk: str | None = None) -> Response:
        goal = self.get_object()
        if request.method == "GET":
            qs = goal.contributions.select_related("user")[:100]
            return Response(ContributionSerializer(qs, many=True).data)

        serializer = ContributionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount: Decimal = serializer.validated_data["amount"]
        if amount < 0:
            mine = goal.contributions.filter(user=request.user).aggregate(t=Sum("amount"))["t"] or Decimal("0")
            if mine + amount < 0:
                raise ValidationError({"amount": "Você não pode retirar mais do que guardou nesta meta."})
        serializer.save(goal=goal, user=request.user, date=serializer.validated_data.get("date") or timezone.localdate())
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def invite(self, request: Request, pk: str | None = None) -> Response:
        goal = self.get_object()
        serializer = InviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        if goal.memberships.filter(user__email__iexact=email).exists():
            raise ValidationError({"email": "Essa pessoa já participa da meta."})
        try:
            with transaction.atomic():
                invite = GoalInvite.objects.create(goal=goal, email=email, invited_by=request.user)
        except IntegrityError as exc:
            raise ValidationError({"email": "Já existe um convite pendente para esse e-mail."}) from exc

        has_account = User.objects.filter(email__iexact=email, is_active=True).exists()
        target = f"{goal.target_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        transaction.on_commit(
            lambda: emails.send_goal_invite(email, request.user.name, goal.name, target, has_account)
        )
        return Response(InviteSerializer(invite).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"invites/(?P<invite_id>\d+)/cancel")
    def cancel_invite(self, request: Request, pk: str | None = None, invite_id: str | None = None) -> Response:
        goal = self.get_object()
        invite = get_object_or_404(goal.invites, pk=invite_id, status=GoalInvite.Status.PENDING)
        invite.status = GoalInvite.Status.CANCELED
        invite.responded_at = timezone.now()
        invite.save(update_fields=["status", "responded_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["delete"], url_path=r"members/(?P<user_id>\d+)")
    def remove_member(self, request: Request, pk: str | None = None, user_id: str | None = None) -> Response:
        goal = self.get_object()
        membership = get_object_or_404(goal.memberships, user_id=user_id)
        if membership.role == GoalMember.Role.OWNER:
            raise ValidationError({"detail": "O dono não pode ser removido."})
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def leave(self, request: Request, pk: str | None = None) -> Response:
        goal = self.get_object()
        if goal.owner_id == request.user.id:
            raise ValidationError({"detail": "O dono não pode sair da própria meta. Exclua a meta se quiser."})
        goal.memberships.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyInviteViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Convites pendentes enviados para o e-mail do usuário logado."""

    serializer_class = MyInviteSerializer
    pagination_class = None

    def get_queryset(self):
        return GoalInvite.objects.filter(
            email__iexact=self.request.user.email, status=GoalInvite.Status.PENDING
        ).select_related("goal", "invited_by")

    def _respond(self, pk: str | None, accept: bool) -> Response:
        invite = get_object_or_404(self.get_queryset(), pk=pk)
        with transaction.atomic():
            invite.status = GoalInvite.Status.ACCEPTED if accept else GoalInvite.Status.DECLINED
            invite.responded_at = timezone.now()
            invite.save(update_fields=["status", "responded_at"])
            if accept:
                GoalMember.objects.get_or_create(goal=invite.goal, user=self.request.user)
        security_log.info(
            "Convite %s %s por user_id=%s", invite.pk, invite.status, self.request.user.pk
        )
        return Response({"goal_id": invite.goal_id, "status": invite.status})

    @action(detail=True, methods=["post"])
    def accept(self, request: Request, pk: str | None = None) -> Response:
        return self._respond(pk, accept=True)

    @action(detail=True, methods=["post"])
    def decline(self, request: Request, pk: str | None = None) -> Response:
        return self._respond(pk, accept=False)
