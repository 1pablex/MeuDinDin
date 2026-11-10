from collections.abc import Callable

from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse

HEALTH_PATH = "/api/health/"


class HealthCheckMiddleware:
    """Responde o health check do Render antes da validação de ALLOWED_HOSTS e do
    redirecionamento para HTTPS (a checagem interna chega por HTTP, com outro host)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == HEALTH_PATH and request.method in ("GET", "HEAD"):
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            except Exception:
                return JsonResponse({"status": "db_unavailable"}, status=503)
            response = JsonResponse({"status": "ok"})
            response["Cache-Control"] = "no-store"
            return response
        return self.get_response(request)
