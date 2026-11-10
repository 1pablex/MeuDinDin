"""Configurações do MeuDinDin. Segredos vêm de variáveis de ambiente (.env)."""
import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-nao-use-em-producao"
    else:
        raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY no ambiente.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

# Render informa o domínio público do serviço nesta variável
RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOST}")

# Build do React servido pelo próprio Django em produção (mesmo domínio da API)
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", BASE_DIR / "frontend_dist"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "accounts",
    "finance",
    "goals",
]

MIDDLEWARE = [
    "config.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"

# Testes sempre em SQLite local: nunca criam banco de teste no Neon
if os.getenv("DATABASE_URL") and not RUNNING_TESTS:
    # PostgreSQL (Neon). SSL obrigatório; conexões reaproveitadas com health check.
    DATABASES = {
        "default": dj_database_url.parse(
            os.environ["DATABASE_URL"],
            conn_max_age=60,
            conn_health_checks=True,
            ssl_require=True,
        )
    }
    # O endpoint "-pooler" do Neon usa PgBouncer em modo transação,
    # que não suporta server-side cursors
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG and not RUNNING_TESTS
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}
# WhiteNoise serve o build do React na raiz (/assets/..., /favicon.svg).
# Os arquivos de /assets têm hash no nome, então podem ficar em cache "para sempre".
if FRONTEND_DIST.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST
WHITENOISE_IMMUTABLE_FILE_TEST = r"^.+[.-][0-9a-zA-Z_-]{8,12}\..+$"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # Limites por IP, separados por rota: errar a senha não impede de usar
    # "esqueci a senha". A proteção da conta é o bloqueio por e-mail (LOGIN_*).
    "DEFAULT_THROTTLE_RATES": {
        "login": "20/min",
        "register": "5/min",
        "code": "10/min",
        "refresh": "30/min",
    },
    # Atrás do proxy do Render o IP real vem no X-Forwarded-For
    "NUM_PROXIES": int(os.environ["TRUSTED_PROXY_COUNT"]) if os.getenv("TRUSTED_PROXY_COUNT") else None,
}

# Sessão expira após 15 min sem uso. O refresh token dura 15 min e é renovado
# a cada uso (rotação); o front renova enquanto houver atividade do usuário.
SESSION_IDLE_SECONDS = 15 * 60

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(seconds=SESSION_IDLE_SECONDS),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Refresh token fica em cookie httpOnly, nunca acessível ao JavaScript
REFRESH_COOKIE_NAME = "mdd_refresh"
REFRESH_COOKIE_PATH = "/api/auth/"
REFRESH_COOKIE_SECURE = not DEBUG
REFRESH_COOKIE_SAMESITE = "Strict"

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CORS_ALLOW_CREDENTIALS = True

# Cache no banco: compartilhado entre processos (bloqueio de login e rate limit
# continuam valendo com vários workers). Criar com: manage.py createcachetable
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# Bloqueio de login: N erros seguidos no mesmo e-mail bloqueiam por X segundos
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 5 * 60

# Códigos enviados por e-mail (confirmação de conta e redefinição de senha)
EMAIL_CODE_TTL_SECONDS = 10 * 60
EMAIL_CODE_MAX_ATTEMPTS = 5
EMAIL_CODE_RESEND_SECONDS = 60

# Chave dos dados protegidos no banco (segredo do 2FA, hash de códigos). Precisa ser
# IGUAL em todo ambiente que usa o mesmo banco (local e Render no mesmo Neon).
# Vazia = usa o SECRET_KEY. Trocar invalida os 2FA e códigos já cadastrados.
DATA_ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY", "") or SECRET_KEY

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# E-mail pelo Brevo. Prioridade: API HTTP (funciona no Render free, que bloqueia
# SMTP) > SMTP (bom localmente) > console (sem chave, aparece no terminal).
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
BREVO_SMTP_KEY = os.getenv("BREVO_SMTP_KEY", "")
if BREVO_API_KEY:
    EMAIL_BACKEND = "accounts.brevo.BrevoAPIBackend"
elif BREVO_SMTP_KEY:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp-relay.brevo.com"
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.getenv("BREVO_SMTP_LOGIN", "")
    EMAIL_HOST_PASSWORD = BREVO_SMTP_KEY
    EMAIL_TIMEOUT = 15
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.getenv("EMAIL_FROM", "MeuDinDin <nao-responda@localhost>")
# Tag enviada no cabeçalho X-Mailin-Tag para filtrar os logs do Brevo por projeto
EMAIL_TAG = os.getenv("EMAIL_TAG", "meudindin")

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:
    # O Render termina o HTTPS no proxy e avisa pelo cabeçalho
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "security": {"handlers": ["console"], "level": "INFO"},
        "mail": {"handlers": ["console"], "level": "INFO"},
    },
}
