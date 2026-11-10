"""Bloqueio de login por e-mail e códigos de verificação por e-mail."""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from . import emails
from .models import EmailCode, User

# ---------------------------------------------------------------- bloqueio de login


def _key(kind: str, email: str) -> str:
    # Hash do e-mail: não grava o endereço em texto puro na tabela de cache
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]
    return f"login:{kind}:{digest}"


def lock_remaining(email: str) -> int:
    """Segundos restantes de bloqueio (0 = liberado)."""
    until = cache.get(_key("lock", email))
    return max(0, int(until - time.time())) if until else 0


def register_failure(email: str) -> tuple[int, int]:
    """Registra uma senha errada. Retorna (tentativas restantes, segundos de bloqueio).
    Vale também para e-mails inexistentes, então a resposta não revela se a conta existe."""
    window = settings.LOGIN_LOCKOUT_SECONDS
    count_key = _key("fail", email)
    count = (cache.get(count_key) or 0) + 1
    if count >= settings.LOGIN_MAX_ATTEMPTS:
        cache.set(_key("lock", email), time.time() + window, window)
        cache.delete(count_key)
        return 0, window
    cache.set(count_key, count, window)
    return settings.LOGIN_MAX_ATTEMPTS - count, 0


def clear_failures(email: str) -> None:
    cache.delete_many([_key("fail", email), _key("lock", email)])


# ---------------------------------------------------------------- códigos por e-mail


class CodeResult(Enum):
    OK = "ok"
    WRONG = "wrong"
    EXPIRED = "expired"
    TOO_MANY = "too_many"


@dataclass
class CodeCheck:
    result: CodeResult
    attempts_left: int = 0


def _hash(user: User, purpose: str, code: str) -> str:
    msg = f"{user.pk}:{purpose}:{code}".encode()
    return hmac.new(settings.DATA_ENCRYPTION_KEY.encode(), msg, hashlib.sha256).hexdigest()


def resend_wait(user: User, purpose: str) -> int:
    """Segundos até poder pedir outro código."""
    last = (
        EmailCode.objects.filter(user=user, purpose=purpose).order_by("-created_at").values_list("created_at", flat=True).first()
    )
    if not last:
        return 0
    elapsed = (timezone.now() - last).total_seconds()
    return max(0, int(settings.EMAIL_CODE_RESEND_SECONDS - elapsed))


def issue_code(user: User, purpose: str, *, respect_cooldown: bool = True) -> bool:
    """Gera um novo código (invalidando os anteriores) e envia por e-mail.
    Retorna False se ainda estiver no intervalo mínimo entre envios."""
    if respect_cooldown and resend_wait(user, purpose) > 0:
        return False
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = timezone.now()
    with transaction.atomic():
        EmailCode.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(used_at=now)
        EmailCode.objects.create(
            user=user,
            purpose=purpose,
            code_hash=_hash(user, purpose, code),
            expires_at=now + timedelta(seconds=settings.EMAIL_CODE_TTL_SECONDS),
        )
    transaction.on_commit(lambda: emails.send_code(user.email, user.name, code, purpose))
    return True


def check_code(user: User, purpose: str, code: str) -> CodeCheck:
    """Confere o código. Cada código aceita poucas tentativas e é de uso único."""
    now = timezone.now()
    with transaction.atomic():
        obj = (
            EmailCode.objects.select_for_update()
            .filter(user=user, purpose=purpose, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if obj is None or obj.expires_at <= now:
            return CodeCheck(CodeResult.EXPIRED)
        EmailCode.objects.filter(pk=obj.pk).update(attempts=F("attempts") + 1)
        obj.refresh_from_db(fields=["attempts"])
        if hmac.compare_digest(obj.code_hash, _hash(user, purpose, code.strip())):
            EmailCode.objects.filter(pk=obj.pk).update(used_at=now)
            return CodeCheck(CodeResult.OK)
        left = settings.EMAIL_CODE_MAX_ATTEMPTS - obj.attempts
        if left <= 0:
            EmailCode.objects.filter(pk=obj.pk).update(used_at=now)
            return CodeCheck(CodeResult.TOO_MANY)
        return CodeCheck(CodeResult.WRONG, left)


CODE_ERRORS = {
    CodeResult.EXPIRED: "Código expirado ou inválido. Peça um novo código.",
    CodeResult.TOO_MANY: "Muitas tentativas com este código. Peça um novo código.",
}


def code_error_message(check: CodeCheck) -> str:
    if check.result is CodeResult.WRONG:
        plural = "tentativa" if check.attempts_left == 1 else "tentativas"
        return f"Código incorreto. Resta{'' if check.attempts_left == 1 else 'm'} {check.attempts_left} {plural}."
    return CODE_ERRORS[check.result]
