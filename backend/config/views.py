from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
def spa(request: HttpRequest) -> FileResponse:
    """Devolve o index.html do React para qualquer rota do front (/metas, /login...).
    Os arquivos estáticos (/assets/...) são servidos antes pelo WhiteNoise."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise Http404("Build do frontend não encontrado. Em desenvolvimento, use o Vite (npm run dev).")
    return FileResponse(index.open("rb"), content_type="text/html; charset=utf-8")
