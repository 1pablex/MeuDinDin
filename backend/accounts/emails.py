"""Envio de e-mails transacionais (Brevo SMTP em produção, console em dev)."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

log = logging.getLogger("mail")


def _html(title: str, paragraphs: list[str], highlight: str | None = None, button: tuple[str, str] | None = None) -> str:
    """Layout simples com estilos inline (clientes de e-mail ignoram <style>)."""
    body = "".join(
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#13201A">{escape(p)}</p>' for p in paragraphs
    )
    if highlight:
        body += (
            '<p style="margin:8px 0 24px;font-size:34px;letter-spacing:8px;font-weight:700;'
            f'font-family:Consolas,monospace;color:#17663F">{escape(highlight)}</p>'
        )
    if button:
        label, url = button
        body += (
            f'<p style="margin:8px 0 24px"><a href="{escape(url)}" style="display:inline-block;padding:12px 22px;'
            'background:#17663F;color:#ffffff;border-radius:10px;text-decoration:none;font-weight:600">'
            f"{escape(label)}</a></p>"
        )
    return (
        '<div style="background:#F4F6F2;padding:32px 16px;font-family:Inter,Segoe UI,Arial,sans-serif">'
        '<div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:16px;padding:32px;'
        'border:1px solid #E1E6E0">'
        '<p style="margin:0 0 24px;font-weight:700;font-size:18px;color:#13201A">MeuDinDin</p>'
        f'<h1 style="margin:0 0 16px;font-size:22px;color:#13201A">{escape(title)}</h1>'
        f"{body}"
        '<p style="margin:24px 0 0;font-size:12px;color:#4F5E56">'
        "Se você não esperava este e-mail, pode ignorá-lo.</p></div></div>"
    )


def send(to: str, subject: str, text: str, html: str) -> bool:
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
        headers={"X-Mailin-Tag": settings.EMAIL_TAG},
    )
    msg.attach_alternative(html, "text/html")
    try:
        msg.send()
    except Exception:  # SMTP fora do ar não pode derrubar a requisição
        log.exception("Falha ao enviar e-mail '%s'", subject)
        return False
    log.info("E-mail '%s' enviado", subject)
    return True


def send_code(to: str, name: str, code: str, purpose: str) -> bool:
    minutes = settings.EMAIL_CODE_TTL_SECONDS // 60
    if purpose == "verify":
        subject = f"{code} é seu código de confirmação"
        title = "Confirme seu e-mail"
        intro = f"Olá, {name}! Use o código abaixo para ativar sua conta no MeuDinDin."
    else:
        subject = f"{code} é seu código para redefinir a senha"
        title = "Redefinir senha"
        intro = f"Olá, {name}! Recebemos um pedido para redefinir sua senha. Use o código abaixo."
    expire = f"O código vale por {minutes} minutos."
    text = f"{intro}\n\n{code}\n\n{expire}\n\nSe você não pediu isso, ignore este e-mail."
    return send(to, subject, text, _html(title, [intro, expire], highlight=code))


def send_goal_invite(to: str, inviter: str, goal_name: str, target: str, has_account: bool) -> bool:
    url = f"{settings.FRONTEND_URL}/login"
    if has_account:
        action = "Entre no MeuDinDin para aceitar ou recusar o convite."
        label = "Ver convite"
    else:
        action = "Crie sua conta no MeuDinDin com este e-mail para participar."
        label = "Criar conta"
    intro = f"{inviter} convidou você para a meta “{goal_name}” (R$ {target}) no MeuDinDin."
    subject = f"{inviter} convidou você para a meta {goal_name}"
    text = f"{intro}\n\n{action}\n{url}"
    return send(to, subject, text, _html("Convite para meta em conjunto", [intro, action], button=(label, url)))
