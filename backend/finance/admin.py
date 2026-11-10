from django.contrib import admin

from .models import Category, Transaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "user"]
    list_filter = ["kind"]
    search_fields = ["name", "user__email"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["description", "kind", "amount", "date", "recurrence", "user"]
    list_filter = ["kind", "recurrence"]
    search_fields = ["description", "user__email"]
    list_select_related = ["user", "category"]
    date_hierarchy = "date"
