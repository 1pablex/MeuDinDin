"""Autenticação em dois fatores por app autenticador (TOTP, RFC 6238).

- O segredo é criptografado com Fernet antes de ir para o banco.
- Cada código de 30s só pode ser usado uma vez (proteção contra replay).
- No login, depois da senha, o servidor devolve um "desafio" assinado que
  vale 5 minutos e aceita poucas tentativas; só então a sessão é criada.
"""
import base64
import hashlib
import hmac
import secrets
import time

import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import RecoveryCode, User

ISSUER = "MeuDinDin"
STEP = 30
CHALLENGE_SALT = "meudindin.mfa"
CHALLENGE_MAX_AGE = 5 * 60
CHALLENGE_MAX_TRIES = 5
SETUP_TTL = 10 * 60
RECOVERY_COUNT = 10


# ------------------------------------------------------------------ segredo


def _fernet() -> Fernet:
    # Chave Fernet derivada de DATA_ENCRYPTION_KEY: trocar esse valor invalida os 2FA cadastrados
    material = f"totp:{settings.DATA_ENCRYPTION_KEY}".encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


# ------------------------------------------------------------------ cadastro do app


def _setup_key(user: User) -> str:
    return f"2fa:setup:{user.pk}"


def start_setup(user: User) -> dict:
    """Gera um segredo provisório (10 min) e o QR code para o app autenticador."""
    secret = pyotp.random_base32()
    cache.set(_setup_key(user), encrypt(secret), SETUP_TTL)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    qr = segno.make(uri, error="m")
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "qr_svg": qr.svg_data_uri(scale=5, border=2, dark="#13201A"),
        "expires_in": SETUP_TTL,
    }


def pending_secret(user: User) -> str | None:
    token = cache.get(_setup_key(user))
    return decrypt(token) if token else None


def matching_step(secret: str, code: str, last_step: int | None) -> int | None:
    """Passo de tempo do código, aceitando 30s de tolerância de relógio."""
    code = code.strip().replace(" ", "")
    if not (len(code) == 6 and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret)
    now_step = int(time.time()) // STEP
    for step in (now_step - 1, now_step, now_step + 1):
        if hmac.compare_digest(totp.at(step * STEP), code) and (last_step is None or step > last_step):
            return step
    return None


@transaction.atomic
def enable(user: User, code: str) -> list[str] | None:
    secret = pending_secret(user)
    if not secret:
        return None
    step = matching_step(secret, code, None)
    if step is None:
        return None
    user.totp_secret_enc = encrypt(secret)
    user.totp_enabled = True
    user.totp_last_step = step
    user.save(update_fields=["totp_secret_enc", "totp_enabled", "totp_last_step"])
    cache.delete(_setup_key(user))
    return regenerate_recovery_codes(user)


@transaction.atomic
def disable(user: User) -> None:
    user.totp_enabled = False
    user.totp_secret_enc = ""
    user.totp_last_step = None
    user.save(update_fields=["totp_enabled", "totp_secret_enc", "totp_last_step"])
    user.recovery_codes.all().delete()


# ------------------------------------------------------------------ verificação


def verify_totp(user: User, code: str) -> bool:
    """Confere o código do app e grava o passo usado (cada código vale uma vez)."""
    if not user.totp_enabled:
        return False
    secret = decrypt(user.totp_secret_enc)
    if not secret:
        return False
    with transaction.atomic():
        locked = User.objects.select_for_update().only("totp_last_step").get(pk=user.pk)
        step = matching_step(secret, code, locked.totp_last_step)
        if step is None:
            return False
        User.objects.filter(pk=user.pk).update(totp_last_step=step)
        user.totp_last_step = step
    return True


def _recovery_hash(user: User, code: str) -> str:
    normalized = code.strip().lower().replace("-", "").replace(" ", "")
    return hmac.new(settings.DATA_ENCRYPTION_KEY.encode(), f"rc:{user.pk}:{normalized}".encode(), hashlib.sha256).hexdigest()


def regenerate_recovery_codes(user: User) -> list[str]:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # sem 0/o/1/l/i para não confundir
    codes = ["".join(secrets.choice(alphabet) for _ in range(10)) for _ in range(RECOVERY_COUNT)]
    user.recovery_codes.all().delete()
    RecoveryCode.objects.bulk_create([RecoveryCode(user=user, code_hash=_recovery_hash(user, c)) for c in codes])
    return [f"{c[:5]}-{c[5:]}" for c in codes]


def use_recovery_code(user: User, code: str) -> bool:
    updated = RecoveryCode.objects.filter(
        user=user, code_hash=_recovery_hash(user, code), used_at__isnull=True
    ).update(used_at=timezone.now())
    return updated == 1


def verify_any(user: User, code: str) -> bool:
    """Código do app (6 dígitos) ou código de recuperação."""
    cleaned = code.strip().replace(" ", "")
    if cleaned.isdigit():
        return verify_totp(user, cleaned)
    return use_recovery_code(user, cleaned)


def recovery_codes_left(user: User) -> int:
    return user.recovery_codes.filter(used_at__isnull=True).count()


# ------------------------------------------------------------------ desafio no login


def create_challenge(user: User) -> str:
    nonce = secrets.token_urlsafe(16)
    return signing.dumps({"uid": user.pk, "n": nonce}, salt=CHALLENGE_SALT)


def read_challenge(token: str) -> tuple[User, str] | None:
    try:
        data = signing.loads(token, salt=CHALLENGE_SALT, max_age=CHALLENGE_MAX_AGE)
    except signing.BadSignature:
        return None
    if cache.get(f"2fa:used:{data['n']}"):
        return None
    user = User.objects.filter(pk=data["uid"], is_active=True, totp_enabled=True).first()
    return (user, data["n"]) if user else None


def challenge_failed(nonce: str) -> bool:
    """Conta uma tentativa errada. Retorna True se o desafio foi esgotado."""
    key = f"2fa:tries:{nonce}"
    tries = (cache.get(key) or 0) + 1
    cache.set(key, tries, CHALLENGE_MAX_AGE)
    if tries >= CHALLENGE_MAX_TRIES:
        cache.set(f"2fa:used:{nonce}", True, CHALLENGE_MAX_AGE)
        return True
    return False


def challenge_done(nonce: str) -> None:
    cache.set(f"2fa:used:{nonce}", True, CHALLENGE_MAX_AGE)
