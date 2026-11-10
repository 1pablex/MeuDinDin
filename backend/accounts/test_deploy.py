import json
from unittest import mock

from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, TestCase, override_settings

from .brevo import BrevoAPIBackend


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return b'{"messageId":"x"}'


@override_settings(BREVO_API_KEY="xkeysib-teste", DEFAULT_FROM_EMAIL="MeuDinDin <nao-responda@exemplo.com>")
class BrevoBackendTests(SimpleTestCase):
    def test_sends_json_with_sender_tag_and_html(self) -> None:
        msg = EmailMultiAlternatives(
            "Assunto", "Texto", None, ["ana@exemplo.com"], headers={"X-Mailin-Tag": "meudindin"}
        )
        msg.attach_alternative("<p>HTML</p>", "text/html")
        with mock.patch("accounts.brevo.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            sent = BrevoAPIBackend().send_messages([msg])
        self.assertEqual(sent, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(request.get_header("Api-key"), "xkeysib-teste")
        body = json.loads(request.data)
        self.assertEqual(body["sender"], {"email": "nao-responda@exemplo.com", "name": "MeuDinDin"})
        self.assertEqual(body["to"], [{"email": "ana@exemplo.com"}])
        self.assertEqual(body["tags"], ["meudindin"])
        self.assertEqual(body["htmlContent"], "<p>HTML</p>")
        self.assertEqual(body["textContent"], "Texto")


class HealthTests(TestCase):
    def test_health_ignores_host_validation(self) -> None:
        res = self.client.get("/api/health/", HTTP_HOST="10.0.0.5:10000")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_unknown_front_route_without_build_is_404(self) -> None:
        with override_settings(FRONTEND_DIST=__import__("pathlib").Path("nao-existe")):
            self.assertEqual(self.client.get("/metas").status_code, 404)
