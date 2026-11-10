"""Backend de e-mail do Django que envia pela API HTTP do Brevo (porta 443).

Necessário no plano gratuito do Render, que bloqueia SMTP (25/465/587).
Usa a chave de API v3 do Brevo (xkeysib-...), não a chave SMTP.
"""
import json
import logging
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage, EmailMultiAlternatives

log = logging.getLogger("mail")
API_URL = "https://api.brevo.com/v3/smtp/email"


def _address(raw: str) -> dict:
    name, email = parseaddr(raw)
    return {"email": email, "name": name} if name else {"email": email}


class BrevoAPIBackend(BaseEmailBackend):
    def send_messages(self, email_messages: list[EmailMessage]) -> int:
        sent = 0
        for message in email_messages:
            try:
                self._send(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
                log.exception("Falha ao enviar pelo Brevo")
        return sent

    def _send(self, message: EmailMessage) -> None:
        payload: dict = {
            "sender": _address(message.from_email or settings.DEFAULT_FROM_EMAIL),
            "to": [_address(addr) for addr in message.to],
            "subject": message.subject,
            "textContent": message.body,
        }
        if isinstance(message, EmailMultiAlternatives):
            for content, mimetype in message.alternatives:
                if mimetype == "text/html":
                    payload["htmlContent"] = content
        tag = message.extra_headers.get("X-Mailin-Tag")
        if tag:
            payload["tags"] = [tag]

        request = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "api-key": settings.BREVO_API_KEY,
                "accept": "application/json",
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            # O corpo explica o motivo (remetente não verificado, chave inválida...)
            detail = exc.read().decode(errors="replace")[:300]
            raise RuntimeError(f"Brevo respondeu {exc.code}: {detail}") from exc
