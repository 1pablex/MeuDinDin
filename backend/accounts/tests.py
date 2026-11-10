import re
import time
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import Category

from .models import User

PASSWORD = "Senha#Forte2026"


def last_code() -> str:
    match = re.search(r"\b(\d{6})\b", mail.outbox[-1].subject)
    assert match, "nenhum código no último e-mail"
    return match.group(1)


class AuthBase(APITestCase):
    def setUp(self) -> None:
        cache.clear()

    def post(self, path: str, data: dict | None = None):
        # E-mails saem em on_commit; nos testes a transação não é confirmada,
        # então executamos os callbacks explicitamente
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f"/api/auth/{path}", data or {}, format="json")

    def register(self, email: str = "ana@exemplo.com", password: str = PASSWORD, name: str = "Ana"):
        return self.post("register/", {"name": name, "email": email, "password": password})

    def make_verified(self, email: str = "ana@exemplo.com") -> User:
        return User.objects.create_user(email, PASSWORD, name="Ana", email_verified=True)


class RegisterAndVerifyTests(AuthBase):
    def test_register_sends_code_and_does_not_log_in(self) -> None:
        res = self.register()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("access", res.data)
        self.assertNotIn(settings.REFRESH_COOKIE_NAME, res.cookies)
        user = User.objects.get(email="ana@exemplo.com")
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@exemplo.com"])
        self.assertEqual(mail.outbox[0].extra_headers["X-Mailin-Tag"], "meudindin")
        self.assertTrue(Category.objects.filter(user=user).exists())

    def test_code_is_not_stored_in_plain_text(self) -> None:
        self.register()
        code = last_code()
        stored = User.objects.get().email_codes.get().code_hash
        self.assertNotIn(code, stored)

    def test_verify_with_correct_code_logs_in(self) -> None:
        self.register()
        res = self.post("verify-email/", {"email": "ANA@exemplo.com", "code": last_code()})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertTrue(res.cookies[settings.REFRESH_COOKIE_NAME]["httponly"])
        self.assertTrue(User.objects.get().email_verified)

    def test_code_is_single_use(self) -> None:
        self.register()
        code = last_code()
        self.post("verify-email/", {"email": "ana@exemplo.com", "code": code})
        res = self.post("verify-email/", {"email": "ana@exemplo.com", "code": code})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_codes_burn_the_code(self) -> None:
        self.register()
        code = last_code()
        wrong = "000000" if code != "000000" else "111111"
        first = self.post("verify-email/", {"email": "ana@exemplo.com", "code": wrong})
        self.assertIn("Restam 4", first.data["detail"])
        for _ in range(4):
            self.post("verify-email/", {"email": "ana@exemplo.com", "code": wrong})
        res = self.post("verify-email/", {"email": "ana@exemplo.com", "code": code})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.get().email_verified)

    def test_expired_code_is_rejected(self) -> None:
        self.register()
        code = last_code()
        User.objects.get().email_codes.update(expires_at="2000-01-01T00:00:00Z")
        res = self.post("verify-email/", {"email": "ana@exemplo.com", "code": code})
        self.assertIn("expirado", res.data["detail"])

    def test_resend_invalidates_old_code_and_has_cooldown(self) -> None:
        self.register()
        old = last_code()
        User.objects.get().email_codes.update(created_at="2000-01-01T00:00:00Z")
        self.post("resend-code/", {"email": "ana@exemplo.com"})
        self.assertEqual(len(mail.outbox), 2)
        self.post("resend-code/", {"email": "ana@exemplo.com"})  # dentro do intervalo: não reenvia
        self.assertEqual(len(mail.outbox), 2)
        if old != last_code():
            res = self.post("verify-email/", {"email": "ana@exemplo.com", "code": old})
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resend_does_not_reveal_accounts(self) -> None:
        res = self.post("resend-code/", {"email": "ninguem@exemplo.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_cannot_register_verified_email_but_can_redo_pending(self) -> None:
        self.register()
        res = self.register(name="Outro Nome")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get().name, "Outro Nome")
        self.post("verify-email/", {"email": "ana@exemplo.com", "code": last_code()})
        self.assertEqual(self.register().status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_rejects_weak_password(self) -> None:
        self.assertEqual(self.register(password="123").status_code, status.HTTP_400_BAD_REQUEST)


class LoginTests(AuthBase):
    def test_login_verified_user_case_insensitive(self) -> None:
        self.make_verified()
        res = self.post("login/", {"email": "Ana@Exemplo.com", "password": PASSWORD})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)

    def test_unverified_user_gets_403_and_new_code(self) -> None:
        self.register()
        User.objects.get().email_codes.update(created_at="2000-01-01T00:00:00Z")
        res = self.post("login/", {"email": "ana@exemplo.com", "password": PASSWORD})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "email_not_verified")
        self.assertEqual(len(mail.outbox), 2)

    def test_wrong_password_shows_attempts_and_same_message_for_unknown_email(self) -> None:
        self.make_verified()
        bad = self.post("login/", {"email": "ana@exemplo.com", "password": "errada123"})
        unknown = self.post("login/", {"email": "nao@existe.com", "password": "errada123"})
        self.assertEqual(bad.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(bad.data, unknown.data)
        self.assertEqual(bad.data["attempts_left"], 4)

    def test_five_failures_lock_for_five_minutes(self) -> None:
        self.make_verified()
        codes = [self.post("login/", {"email": "ana@exemplo.com", "password": "errada123"}).status_code for _ in range(5)]
        self.assertEqual(codes, [401, 401, 401, 401, 429])
        # Mesmo com a senha certa continua bloqueado
        locked = self.post("login/", {"email": "ana@exemplo.com", "password": PASSWORD})
        self.assertEqual(locked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("5 minutos", locked.data["detail"])
        # Depois de 5 minutos libera (relógio simulado; o limite por IP é zerado à parte)
        later = time.time() + settings.LOGIN_LOCKOUT_SECONDS + 1
        cache.delete_many([k for k in ["throttle_login_127.0.0.1"]])
        with mock.patch("accounts.security.time.time", return_value=later):
            ok = self.post("login/", {"email": "ana@exemplo.com", "password": PASSWORD})
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    def test_lock_remaining_uses_clock(self) -> None:
        from . import security

        for _ in range(5):
            security.register_failure("x@exemplo.com")
        self.assertGreater(security.lock_remaining("x@exemplo.com"), 290)
        with mock.patch("accounts.security.time.time", return_value=time.time() + 301):
            self.assertEqual(security.lock_remaining("x@exemplo.com"), 0)

    def test_success_resets_failure_counter(self) -> None:
        self.make_verified()
        for _ in range(4):
            self.post("login/", {"email": "ana@exemplo.com", "password": "errada123"})
        self.post("login/", {"email": "ana@exemplo.com", "password": PASSWORD})
        res = self.post("login/", {"email": "ana@exemplo.com", "password": "errada123"})
        self.assertEqual(res.data["attempts_left"], 4)

    def test_ip_rate_limit(self) -> None:
        codes = [
            self.post("login/", {"email": f"x{i}@exemplo.com", "password": "errada123"}).status_code for i in range(22)
        ]
        self.assertIn(status.HTTP_429_TOO_MANY_REQUESTS, codes)


class PasswordResetTests(AuthBase):
    def test_full_reset_flow_revokes_old_sessions(self) -> None:
        self.make_verified()
        self.post("login/", {"email": "ana@exemplo.com", "password": PASSWORD})
        old_refresh = self.client.cookies[settings.REFRESH_COOKIE_NAME].value

        res = self.post("password-reset/", {"email": "ana@exemplo.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        code = last_code()
        new_password = "OutraSenha#2027"
        res = self.post("password-reset/confirm/", {"email": "ana@exemplo.com", "code": code, "password": new_password})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.client.cookies[settings.REFRESH_COOKIE_NAME] = old_refresh
        self.assertEqual(self.post("refresh/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.post("login/", {"email": "ana@exemplo.com", "password": PASSWORD}).status_code, 401)
        self.assertEqual(
            self.post("login/", {"email": "ana@exemplo.com", "password": new_password}).status_code, 200
        )

    def test_reset_still_works_after_many_login_attempts(self) -> None:
        self.make_verified()
        for i in range(12):
            self.post("login/", {"email": f"y{i}@exemplo.com", "password": "errada123"})
        res = self.post("password-reset/", {"email": "ana@exemplo.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_reset_request_is_generic_for_unknown_email(self) -> None:
        res = self.post("password-reset/", {"email": "nao@existe.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_with_wrong_code_or_weak_password(self) -> None:
        self.make_verified()
        self.post("password-reset/", {"email": "ana@exemplo.com"})
        code = last_code()
        weak = self.post("password-reset/confirm/", {"email": "ana@exemplo.com", "code": code, "password": "123"})
        self.assertEqual(weak.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", weak.data)
        wrong = "000000" if code != "000000" else "111111"
        res = self.post("password-reset/confirm/", {"email": "ana@exemplo.com", "code": wrong, "password": "OutraSenha#2027"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_clears_login_lock_and_verifies_email(self) -> None:
        self.register()
        for _ in range(5):
            self.post("login/", {"email": "ana@exemplo.com", "password": "errada123"})
        User.objects.get().email_codes.update(created_at="2000-01-01T00:00:00Z")
        self.post("password-reset/", {"email": "ana@exemplo.com"})
        self.post("password-reset/confirm/", {"email": "ana@exemplo.com", "code": last_code(), "password": "OutraSenha#2027"})
        res = self.post("login/", {"email": "ana@exemplo.com", "password": "OutraSenha#2027"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class SessionTests(AuthBase):
    def login(self) -> str:
        self.make_verified()
        return self.post("login/", {"email": "ana@exemplo.com", "password": PASSWORD}).data["access"]

    def test_refresh_rotates_and_old_token_is_blacklisted(self) -> None:
        self.login()
        old = self.client.cookies[settings.REFRESH_COOKIE_NAME].value
        res = self.post("refresh/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.client.cookies[settings.REFRESH_COOKIE_NAME] = old
        self.assertEqual(self.post("refresh/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalidates_refresh(self) -> None:
        self.login()
        token = self.client.cookies[settings.REFRESH_COOKIE_NAME].value
        self.assertEqual(self.post("logout/").status_code, status.HTTP_204_NO_CONTENT)
        self.client.cookies[settings.REFRESH_COOKIE_NAME] = token
        self.assertEqual(self.post("refresh/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_auth(self) -> None:
        self.assertEqual(self.client.get("/api/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.login()}")
        self.assertEqual(self.client.get("/api/auth/me/").data["email"], "ana@exemplo.com")
