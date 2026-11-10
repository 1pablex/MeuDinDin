from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra) -> "User":
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("email_verified", True)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Usuário autenticado por e-mail em vez de username."""

    username = None
    email = models.EmailField("e-mail", unique=True)
    name = models.CharField("nome", max_length=120)
    email_verified = models.BooleanField("e-mail confirmado", default=False)
    # 2FA por app autenticador (TOTP). O segredo fica criptografado (Fernet).
    totp_enabled = models.BooleanField("2FA ativo", default=False)
    totp_secret_enc = models.TextField(blank=True, editable=False)
    # Último passo de 30s aceito: impede reutilizar o mesmo código (replay)
    totp_last_step = models.BigIntegerField(null=True, blank=True, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    def __str__(self) -> str:
        return self.email


class EmailCode(models.Model):
    """Código de 6 dígitos enviado por e-mail. Só o hash fica no banco."""

    class Purpose(models.TextChoices):
        VERIFY = "verify", "Confirmar e-mail"
        RESET = "reset", "Redefinir senha"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_codes")
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "created_at"])]
        verbose_name = "código por e-mail"


class RecoveryCode(models.Model):
    """Código de recuperação do 2FA (uso único). Só o hash fica no banco."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "code_hash"])]
        verbose_name = "código de recuperação"
