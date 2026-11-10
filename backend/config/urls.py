from django.contrib import admin
from django.urls import include, path, re_path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("finance.urls")),
    path("api/", include("goals.urls")),
    # Qualquer outra rota é do React (precisa vir por último)
    re_path(r"^(?!api/|admin/|static/).*$", views.spa, name="spa"),
]
