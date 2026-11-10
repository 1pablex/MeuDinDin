"""Autenticação JWT. O access token vai no corpo (fica só em memória no front);
o refresh token vai em cookie httpOnly com path restrito a /api/auth/.

Fluxos: cadastro -> código por e-mail -> conta ativa; login (senha e, se ativo,
2FA por app autenticador) com bloqueio após erros seguidos; redefinição de senha
por código enviado ao e-mail. A sessão expira após 15 min sem uso."""
import logging

from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import generics, permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from finance.services import create_default_categories

from . import security, twofactor
from .models import EmailCode, User
from .serializers import (
    CodeSerializer,
    EmailSerializer,
    LoginSerializer,
    MfaLoginSerializer,
    PasswordResetConfirmSerializer,
    RegisterSerializer,
    TotpCodeSerializer,
    TwoFactorConfirmSerializer,
    UserSerializer,
)

security_log = logging.getLogger("security")


def _client_ip(request: Request) -> str:
    return request.META.get("REMOTE_ADDR", "?")


def _set_refresh_cookie(response: Response, refresh: str) -> None:
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path=settings.REFRESH_COOKIE_PATH,
    )


def _token_response(user: User, status_code: int = status.HTTP_200_OK) -> Response:
    refresh = RefreshToken.for_user(user)
    response = Response(
        {
            "access": str(refresh.access_token),
            "user": UserSerializer(user).data,
            # O front encerra a sessão após esse tempo sem atividade
            "idle_timeout": settings.SESSION_IDLE_SECONDS,
        },
        status=status_code,
    )
    _set_refresh_cookie(response, str(refresh))
    return response


def _locked_response(seconds: int) -> Response:
    return Response(
        {"detail": f"Login bloqueado por excesso de tentativas. Tente novamente em {_minutes(seconds)}.",
         "retry_after": seconds},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


def _failure_response(request: Request, email: str, message: str) -> Response:
    """Conta um erro para o bloqueio do e-mail e monta a resposta."""
    left, lock = security.register_failure(email)
    security_log.warning("Falha de login ip=%s restantes=%s", _client_ip(request), left)
    if lock:
        security_log.warning("Login bloqueado por %ss ip=%s", lock, _client_ip(request))
        return Response(
            {"detail": f"Muitas tentativas erradas. Login bloqueado por {_minutes(lock)}.", "retry_after": lock},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    plural = "tentativa" if left == 1 else "tentativas"
    return Response(
        {"detail": f"{message} Resta{'' if left == 1 else 'm'} {left} {plural}.", "attempts_left": left},
        status=status.HTTP_401_UNAUTHORIZED,
    )


def _revoke_all_sessions(user: User) -> None:
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


def _minutes(seconds: int) -> str:
    minutes = max(1, -(-seconds // 60))
    return f"{minutes} minuto{'s' if minutes > 1 else ''}"


class AuthView(APIView):
    """Base das rotas públicas de autenticação (com limite por IP)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "code"


class RegisterView(AuthView):
    """Cria a conta pendente e envia o código de confirmação. Não faz login."""
    throttle_scope = "register"


    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            user = User.objects.filter(email__iexact=data["email"], email_verified=False).first()
            if user is None:
                user = User.objects.create_user(email=data["email"], password=data["password"], name=data["name"])
                create_default_categories(user)
            else:
                user.name = data["name"]
                user.set_password(data["password"])
                user.save(update_fields=["name", "password"])
            security.issue_code(user, EmailCode.Purpose.VERIFY, respect_cooldown=False)
        security_log.info("Cadastro pendente user_id=%s ip=%s", user.pk, _client_ip(request))
        return Response(
            {"detail": "Enviamos um código de 6 dígitos para o seu e-mail.", "email": user.email},
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(AuthView):
    def post(self, request: Request) -> Response:
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email, code = serializer.validated_data["email"], serializer.validated_data["code"]
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is None or user.email_verified:
            return Response({"detail": security.CODE_ERRORS[security.CodeResult.EXPIRED]}, status=400)
        check = security.check_code(user, EmailCode.Purpose.VERIFY, code)
        if check.result is not security.CodeResult.OK:
            return Response({"detail": security.code_error_message(check)}, status=400)
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        security_log.info("E-mail confirmado user_id=%s", user.pk)
        return _token_response(user)


class ResendCodeView(AuthView):
    """Reenvia o código de confirmação. Resposta sempre igual (não revela contas)."""

    def post(self, request: Request) -> Response:
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"], is_active=True, email_verified=False
        ).first()
        if user:
            security.issue_code(user, EmailCode.Purpose.VERIFY)
        return Response(
            {
                "detail": "Se o e-mail estiver aguardando confirmação, enviamos um novo código.",
                "cooldown": settings.EMAIL_CODE_RESEND_SECONDS,
            }
        )


class LoginView(AuthView):
    throttle_scope = "login"

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()

        locked = security.lock_remaining(email)
        if locked:
            return _locked_response(locked)

        user = authenticate(request, email=email, password=serializer.validated_data["password"])
        if user is None:
            # Mensagem genérica: não revela se o e-mail existe
            return _failure_response(request, email, "E-mail ou senha inválidos.")

        if not user.email_verified:
            security.clear_failures(email)
            security.issue_code(user, EmailCode.Purpose.VERIFY)
            return Response(
                {"detail": "Confirme seu e-mail para entrar. Enviamos um código para você.",
                 "code": "email_not_verified", "email": user.email},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.totp_enabled:
            # Senha certa não zera os erros: só o 2FA correto zera. Assim quem
            # tem a senha não ganha tentativas infinitas no código do app.
            return Response({"mfa_required": True, "mfa_token": twofactor.create_challenge(user)})

        security.clear_failures(email)
        return _token_response(user)


class MfaLoginView(AuthView):
    """Segunda etapa do login: código do app autenticador ou de recuperação."""

    def post(self, request: Request) -> Response:
        serializer = MfaLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        challenge = twofactor.read_challenge(serializer.validated_data["mfa_token"])
        if challenge is None:
            return Response(
                {"detail": "A verificação expirou. Entre com e-mail e senha de novo.", "code": "mfa_expired"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user, nonce = challenge
        locked = security.lock_remaining(user.email)
        if locked:
            return _locked_response(locked)

        if not twofactor.verify_any(user, serializer.validated_data["code"]):
            exhausted = twofactor.challenge_failed(nonce)
            response = _failure_response(request, user.email, "Código inválido.")
            if exhausted and response.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
                return Response(
                    {"detail": "Muitos códigos errados. Entre com e-mail e senha de novo.", "code": "mfa_expired"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            return response

        twofactor.challenge_done(nonce)
        security.clear_failures(user.email)
        security_log.info("Login com 2FA user_id=%s ip=%s", user.pk, _client_ip(request))
        return _token_response(user)


class TwoFactorView(APIView):
    """Status, cadastro e remoção do 2FA (usuário logado)."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "code"

    def get(self, request: Request) -> Response:
        user = request.user
        return Response(
            {"enabled": user.totp_enabled, "recovery_codes_left": twofactor.recovery_codes_left(user)}
        )


class TwoFactorSetupView(TwoFactorView):
    def post(self, request: Request) -> Response:
        if request.user.totp_enabled:
            return Response({"detail": "O 2FA já está ativo."}, status=400)
        return Response(twofactor.start_setup(request.user))


class TwoFactorEnableView(TwoFactorView):
    def post(self, request: Request) -> Response:
        serializer = TotpCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if request.user.totp_enabled:
            return Response({"detail": "O 2FA já está ativo."}, status=400)
        codes = twofactor.enable(request.user, serializer.validated_data["code"])
        if codes is None:
            return Response(
                {"detail": "Código inválido ou cadastro expirado. Confira o horário do celular e tente de novo."},
                status=400,
            )
        security_log.info("2FA ativado user_id=%s", request.user.pk)
        return Response({"recovery_codes": codes})


class TwoFactorDisableView(TwoFactorView):
    def post(self, request: Request) -> Response:
        serializer = TwoFactorConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["password"]) or not twofactor.verify_any(
            user, serializer.validated_data["code"]
        ):
            security_log.warning("Falha ao desativar 2FA user_id=%s", user.pk)
            return Response({"detail": "Senha ou código inválidos."}, status=400)
        twofactor.disable(user)
        security_log.info("2FA desativado user_id=%s", user.pk)
        return Response({"detail": "Autenticação em dois fatores desativada."})


class RecoveryCodesView(TwoFactorView):
    def post(self, request: Request) -> Response:
        serializer = TotpCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not twofactor.verify_totp(request.user, serializer.validated_data["code"]):
            return Response({"detail": "Código inválido."}, status=400)
        return Response({"recovery_codes": twofactor.regenerate_recovery_codes(request.user)})


class PasswordResetRequestView(AuthView):
    """Envia o código de redefinição. Resposta sempre igual (não revela contas)."""

    def post(self, request: Request) -> Response:
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True).first()
        if user:
            security.issue_code(user, EmailCode.Purpose.RESET)
            security_log.info("Pedido de redefinição de senha user_id=%s ip=%s", user.pk, _client_ip(request))
        return Response(
            {
                "detail": "Se existir uma conta com esse e-mail, enviamos um código para redefinir a senha.",
                "cooldown": settings.EMAIL_CODE_RESEND_SECONDS,
            }
        )


class PasswordResetConfirmView(AuthView):
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.filter(email__iexact=data["email"], is_active=True).first()
        if user is None:
            return Response({"detail": security.CODE_ERRORS[security.CodeResult.EXPIRED]}, status=400)
        try:
            password_validation.validate_password(data["password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc

        check = security.check_code(user, EmailCode.Purpose.RESET, data["code"])
        if check.result is not security.CodeResult.OK:
            return Response({"detail": security.code_error_message(check)}, status=400)

        user.set_password(data["password"])
        # Quem recebeu o código no e-mail provou que é dono dele
        user.email_verified = True
        user.save(update_fields=["password", "email_verified"])
        _revoke_all_sessions(user)
        security.clear_failures(user.email)
        security_log.info("Senha redefinida user_id=%s ip=%s", user.pk, _client_ip(request))
        return Response({"detail": "Senha alterada. Entre com a nova senha."})


class RefreshView(AuthView):
    throttle_scope = "refresh"

    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw:
            return Response({"detail": "Sessão expirada."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            old = RefreshToken(raw)
            user = User.objects.get(pk=old["user_id"], is_active=True)
            old.blacklist()
        except (TokenError, User.DoesNotExist, KeyError):
            response = Response({"detail": "Sessão expirada."}, status=status.HTTP_401_UNAUTHORIZED)
            response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH)
            return response
        return _token_response(user)


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []

    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH)
        return response


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self) -> User:
        return self.request.user
