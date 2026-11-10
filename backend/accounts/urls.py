from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify-email"),
    path("resend-code/", views.ResendCodeView.as_view(), name="resend-code"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("login/2fa/", views.MfaLoginView.as_view(), name="login-2fa"),
    path("2fa/", views.TwoFactorView.as_view(), name="2fa-status"),
    path("2fa/setup/", views.TwoFactorSetupView.as_view(), name="2fa-setup"),
    path("2fa/enable/", views.TwoFactorEnableView.as_view(), name="2fa-enable"),
    path("2fa/disable/", views.TwoFactorDisableView.as_view(), name="2fa-disable"),
    path("2fa/recovery-codes/", views.RecoveryCodesView.as_view(), name="2fa-recovery-codes"),
    path("password-reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path("password-reset/confirm/", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("refresh/", views.RefreshView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
]
