from django.contrib import admin

from .models import Contribution, Goal, GoalInvite, GoalMember


class MemberInline(admin.TabularInline):
    model = GoalMember
    extra = 0
    raw_id_fields = ["user"]


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "target_amount", "deadline"]
    search_fields = ["name", "owner__email"]
    list_select_related = ["owner"]
    inlines = [MemberInline]


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ["goal", "user", "amount", "date"]
    list_select_related = ["goal", "user"]


@admin.register(GoalInvite)
class GoalInviteAdmin(admin.ModelAdmin):
    list_display = ["goal", "email", "status", "created_at"]
    list_filter = ["status"]
