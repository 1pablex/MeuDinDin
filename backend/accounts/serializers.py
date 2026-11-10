from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import User


def _clean_name(value: str) -> str:
    value = value.strip()
    if len(value) < 2:
        raise serializers.ValidationError("Informe seu nome.")
    return value


class UserSerializer(serializers.ModelSerializer):
    two_factor_enabled = serializers.BooleanField(source="totp_enabled", read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "name", "two_factor_enabled"]
        read_only_fields = ["id", "email"]

    def validate_name(self, value: str) -> str:
        return _clean_name(value)


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, write_only=True)

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        # Conta já confirmada bloqueia o cadastro; conta pendente pode ser
        # refeita (evita que alguém "reserve" um e-mail que não é dele)
        if User.objects.filter(email__iexact=value, email_verified=True).exists():
            raise serializers.ValidationError("Já existe uma conta com este e-mail.")
        return value

    def validate_name(self, value: str) -> str:
        return _clean_name(value)

    def validate(self, attrs: dict) -> dict:
        password_validation.validate_password(attrs["password"], User(email=attrs["email"], name=attrs["name"]))
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128)


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class CodeSerializer(EmailSerializer):
    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "O código tem 6 dígitos."})


class PasswordResetConfirmSerializer(CodeSerializer):
    password = serializers.CharField(max_length=128, write_only=True)


class TotpCodeSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "O código do app tem 6 dígitos."})


class MfaLoginSerializer(serializers.Serializer):
    mfa_token = serializers.CharField(max_length=500)
    # 6 dígitos do app ou código de recuperação (xxxxx-xxxxx)
    code = serializers.CharField(max_length=20)


class TwoFactorConfirmSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=128, write_only=True)
    code = serializers.CharField(max_length=20)
