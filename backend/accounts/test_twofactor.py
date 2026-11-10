import time
from unittest import mock

import pyotp
from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User

PASSWORD = "Senha#Forte2026"


class TwoFactorTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user("ana@exemplo.com", PASSWORD, name="Ana", email_verified=True)
        self.clock = time.time()

    # -- helpers
    def at(self, offset_steps: int = 0):
        """Simula o relógio do servidor `offset_steps` passos de 30s à frente."""
        return mock.patch("accounts.twofactor.time.time", return_value=self.clock + offset_steps * 30)

    def code(self, secret: str, offset_steps: int = 0) -> str:
        return pyotp.TOTP(secret).at(self.clock + offset_steps * 30)

    def enable_2fa(self) -> tuple[str, list[str]]:
        self.client.force_authenticate(self.user)
        secret = self.client.post("/api/auth/2fa/setup/").data["secret"]
        with self.at(0):
            res = self.client.post("/api/auth/2fa/enable/", {"code": self.code(secret)}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.client.force_authenticate(None)
        return secret, res.data["recovery_codes"]

    def login(self):
        return self.client.post("/api/auth/login/", {"email": "ana@exemplo.com", "password": PASSWORD}, format="json")

    def mfa(self, token: str, code: str):
        return self.client.post("/api/auth/login/2fa/", {"mfa_token": token, "code": code}, format="json")

    # -- cadastro
    def test_setup_returns_qr_and_secret_is_encrypted_after_enable(self) -> None:
        self.client.force_authenticate(self.user)
        setup = self.client.post("/api/auth/2fa/setup/").data
        self.assertTrue(setup["qr_svg"].startswith("data:image/svg+xml"))
        self.assertIn("otpauth://totp/MeuDinDin", setup["otpauth_uri"])
        with self.at(0):
            wrong = self.client.post("/api/auth/2fa/enable/", {"code": "000000"}, format="json")
        self.assertEqual(wrong.status_code, status.HTTP_400_BAD_REQUEST)
        with self.at(0):
            ok = self.client.post("/api/auth/2fa/enable/", {"code": self.code(setup["secret"])}, format="json")
        self.assertEqual(len(ok.data["recovery_codes"]), 10)
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)
        self.assertNotIn(setup["secret"], self.user.totp_secret_enc)
        self.assertEqual(self.client.get("/api/auth/2fa/").data, {"enabled": True, "recovery_codes_left": 10})
        self.assertTrue(self.client.get("/api/auth/me/").data["two_factor_enabled"])

    def test_setup_requires_auth(self) -> None:
        self.assertEqual(self.client.post("/api/auth/2fa/setup/").status_code, status.HTTP_401_UNAUTHORIZED)

    # -- login
    def test_login_requires_second_step(self) -> None:
        secret, _ = self.enable_2fa()
        first = self.login()
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data["mfa_required"])
        self.assertNotIn("access", first.data)
        self.assertNotIn(settings.REFRESH_COOKIE_NAME, first.cookies)
        with self.at(1):
            res = self.mfa(first.data["mfa_token"], self.code(secret, 1))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertEqual(res.data["idle_timeout"], 15 * 60)

    def test_code_cannot_be_reused(self) -> None:
        secret, _ = self.enable_2fa()
        with self.at(1):
            ok = self.mfa(self.login().data["mfa_token"], self.code(secret, 1))
            again = self.mfa(self.login().data["mfa_token"], self.code(secret, 1))
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(again.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_challenge_is_single_use(self) -> None:
        secret, _ = self.enable_2fa()
        token = self.login().data["mfa_token"]
        with self.at(1):
            self.mfa(token, self.code(secret, 1))
        with self.at(2):
            res = self.mfa(token, self.code(secret, 2))
        self.assertEqual(res.data["code"], "mfa_expired")

    def test_invalid_challenge(self) -> None:
        res = self.mfa("token-falso", "123456")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res.data["code"], "mfa_expired")

    def test_recovery_code_works_once(self) -> None:
        _, codes = self.enable_2fa()
        ok = self.mfa(self.login().data["mfa_token"], codes[0].upper())
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        again = self.mfa(self.login().data["mfa_token"], codes[0])
        self.assertEqual(again.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_codes_lock_the_account(self) -> None:
        self.enable_2fa()
        token = self.login().data["mfa_token"]
        codes = [self.mfa(token, "000000").status_code for _ in range(5)]
        self.assertEqual(codes[-1], status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(self.login().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_correct_password_does_not_reset_failures_when_2fa_on(self) -> None:
        self.enable_2fa()
        for _ in range(4):
            self.mfa(self.login().data["mfa_token"], "000000")
        res = self.mfa(self.login().data["mfa_token"], "000000")
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    # -- desativar
    def test_disable_requires_password_and_code(self) -> None:
        secret, _ = self.enable_2fa()
        self.client.force_authenticate(self.user)
        with self.at(1):
            bad = self.client.post("/api/auth/2fa/disable/", {"password": "errada", "code": self.code(secret, 1)}, format="json")
            ok = self.client.post("/api/auth/2fa/disable/", {"password": PASSWORD, "code": self.code(secret, 1)}, format="json")
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)
        self.assertEqual(self.user.totp_secret_enc, "")
        self.assertFalse(self.user.recovery_codes.exists())
        self.client.force_authenticate(None)
        self.assertIn("access", self.login().data)

    def test_regenerate_recovery_codes_invalidates_old(self) -> None:
        secret, old = self.enable_2fa()
        self.client.force_authenticate(self.user)
        with self.at(1):
            new = self.client.post("/api/auth/2fa/recovery-codes/", {"code": self.code(secret, 1)}, format="json")
        self.assertEqual(len(new.data["recovery_codes"]), 10)
        self.client.force_authenticate(None)
        self.assertEqual(self.mfa(self.login().data["mfa_token"], old[0]).status_code, 401)
        self.assertEqual(self.mfa(self.login().data["mfa_token"], new.data["recovery_codes"][0]).status_code, 200)

    def test_password_reset_does_not_bypass_2fa(self) -> None:
        self.enable_2fa()
        self.user.set_password("OutraSenha#2027")
        self.user.save()
        res = self.client.post(
            "/api/auth/login/", {"email": "ana@exemplo.com", "password": "OutraSenha#2027"}, format="json"
        )
        self.assertTrue(res.data["mfa_required"])


class IdleSessionTests(APITestCase):
    def test_refresh_token_lasts_15_minutes_and_is_renewed(self) -> None:
        cache.clear()
        User.objects.create_user("bia@exemplo.com", PASSWORD, name="Bia", email_verified=True)
        res = self.client.post("/api/auth/login/", {"email": "bia@exemplo.com", "password": PASSWORD}, format="json")
        cookie = res.cookies[settings.REFRESH_COOKIE_NAME]
        self.assertEqual(int(cookie["max-age"]), 15 * 60)
        token = RefreshToken(cookie.value)
        self.assertEqual(token["exp"] - token["iat"], 15 * 60)
        renewed = self.client.post("/api/auth/refresh/")
        self.assertEqual(renewed.status_code, status.HTTP_200_OK)
        self.assertNotEqual(renewed.cookies[settings.REFRESH_COOKIE_NAME].value, cookie.value)
