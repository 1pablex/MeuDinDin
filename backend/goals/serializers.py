from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from .models import Contribution, Goal, GoalInvite, GoalMember
from .services import progress


class MemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    contributed = serializers.SerializerMethodField()

    class Meta:
        model = GoalMember
        fields = ["user_id", "name", "email", "role", "joined_at", "contributed"]

    def get_contributed(self, obj: GoalMember) -> Decimal:
        totals: dict[int, Decimal] = self.context.get("contrib_by_user", {})
        return totals.get(obj.user_id, Decimal("0"))


class InviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalInvite
        fields = ["id", "email", "status", "created_at"]


class GoalSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.name", read_only=True)
    is_owner = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    members_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Goal
        fields = [
            "id", "name", "target_amount", "deadline", "owner_name", "is_owner",
            "members_count", "progress", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_is_owner(self, obj: Goal) -> bool:
        return obj.owner_id == self.context["request"].user.id

    def get_progress(self, obj: Goal) -> dict:
        if not hasattr(obj, "saved"):
            obj.saved = obj.contributions.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        return progress(obj)

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Dê um nome para a meta.")
        return value


class GoalDetailSerializer(GoalSerializer):
    members = serializers.SerializerMethodField()
    invites = serializers.SerializerMethodField()

    class Meta(GoalSerializer.Meta):
        fields = [*GoalSerializer.Meta.fields, "members", "invites"]

    def get_members(self, obj: Goal) -> list[dict]:
        rows = obj.contributions.values("user_id").annotate(total=Sum("amount"))
        ctx = {**self.context, "contrib_by_user": {r["user_id"]: r["total"] for r in rows}}
        return MemberSerializer(obj.memberships.all(), many=True, context=ctx).data

    def get_invites(self, obj: Goal) -> list[dict]:
        if obj.owner_id != self.context["request"].user.id:
            return []
        pending = obj.invites.filter(status=GoalInvite.Status.PENDING)
        return InviteSerializer(pending, many=True).data


class ContributionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)

    class Meta:
        model = Contribution
        fields = ["id", "amount", "note", "date", "user_name", "created_at"]
        read_only_fields = ["id", "user_name", "created_at"]
        extra_kwargs = {"date": {"required": False}}

    def validate_amount(self, value: Decimal) -> Decimal:
        if value == 0:
            raise serializers.ValidationError("Informe um valor diferente de zero.")
        if abs(value) > Decimal("9999999999"):
            raise serializers.ValidationError("Valor muito alto.")
        return value


class InviteCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class MyInviteSerializer(serializers.ModelSerializer):
    goal_name = serializers.CharField(source="goal.name", read_only=True)
    invited_by_name = serializers.CharField(source="invited_by.name", read_only=True)
    target_amount = serializers.DecimalField(source="goal.target_amount", max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = GoalInvite
        fields = ["id", "goal_name", "invited_by_name", "target_amount", "created_at"]
