from decimal import Decimal

from django.core import mail
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import GoalInvite, GoalMember


class GoalTests(APITestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user("dono@exemplo.com", "Senha#Forte2026", name="Dono")
        self.friend = User.objects.create_user("amiga@exemplo.com", "Senha#Forte2026", name="Amiga")
        self.stranger = User.objects.create_user("estranho@exemplo.com", "Senha#Forte2026", name="Estranho")
        self.client.force_authenticate(self.owner)
        res = self.client.post(
            "/api/goals/", {"name": "Viagem", "target_amount": "6000", "deadline": "2027-07-01"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.goal_id = res.data["id"]

    def as_user(self, user: User) -> None:
        self.client.force_authenticate(user)

    def invite_and_accept(self) -> None:
        self.client.post(f"/api/goals/{self.goal_id}/invite/", {"email": "Amiga@exemplo.com"}, format="json")
        self.as_user(self.friend)
        invite_id = self.client.get("/api/invites/").data[0]["id"]
        self.client.post(f"/api/invites/{invite_id}/accept/")

    def test_owner_becomes_member(self) -> None:
        self.assertTrue(GoalMember.objects.filter(goal_id=self.goal_id, user=self.owner, role="owner").exists())

    def test_contributions_update_progress(self) -> None:
        self.client.post(f"/api/goals/{self.goal_id}/contributions/", {"amount": "1500"}, format="json")
        data = self.client.get(f"/api/goals/{self.goal_id}/").data
        self.assertEqual(data["progress"]["saved"], Decimal("1500"))
        self.assertEqual(data["progress"]["missing"], Decimal("4500"))
        self.assertEqual(data["progress"]["percent"], 25)

    def test_cannot_withdraw_more_than_contributed(self) -> None:
        self.client.post(f"/api/goals/{self.goal_id}/contributions/", {"amount": "100"}, format="json")
        res = self.client.post(f"/api/goals/{self.goal_id}/contributions/", {"amount": "-150"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_shared_goal_flow(self) -> None:
        self.client.post(f"/api/goals/{self.goal_id}/contributions/", {"amount": "1000"}, format="json")
        self.invite_and_accept()
        res = self.client.post(f"/api/goals/{self.goal_id}/contributions/", {"amount": "500"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        detail = self.client.get(f"/api/goals/{self.goal_id}/").data
        self.assertEqual(detail["members_count"], 2)
        self.assertEqual(detail["progress"]["saved"], Decimal("1500"))
        contributed = {m["email"]: m["contributed"] for m in detail["members"]}
        self.assertEqual(contributed, {"dono@exemplo.com": Decimal("1000"), "amiga@exemplo.com": Decimal("500")})
        self.assertFalse(detail["is_owner"])
        self.assertEqual(detail["invites"], [])

    def test_member_cannot_manage_goal(self) -> None:
        self.invite_and_accept()
        self.assertEqual(
            self.client.patch(f"/api/goals/{self.goal_id}/", {"name": "Meu"}, format="json").status_code, 403
        )
        self.assertEqual(self.client.delete(f"/api/goals/{self.goal_id}/").status_code, 403)
        self.assertEqual(
            self.client.post(f"/api/goals/{self.goal_id}/invite/", {"email": "x@y.com"}, format="json").status_code,
            403,
        )

    def test_stranger_cannot_see_goal(self) -> None:
        self.as_user(self.stranger)
        self.assertEqual(self.client.get(f"/api/goals/{self.goal_id}/").status_code, 404)
        self.assertEqual(
            self.client.post(f"/api/goals/{self.goal_id}/contributions/", {"amount": "1"}, format="json").status_code,
            404,
        )
        self.assertEqual(self.client.get("/api/goals/").data, [])

    def test_stranger_cannot_accept_invite_for_someone_else(self) -> None:
        self.client.post(f"/api/goals/{self.goal_id}/invite/", {"email": "amiga@exemplo.com"}, format="json")
        invite = GoalInvite.objects.get()
        self.as_user(self.stranger)
        self.assertEqual(self.client.post(f"/api/invites/{invite.id}/accept/").status_code, 404)

    def test_invite_sends_email(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/api/goals/{self.goal_id}/invite/", {"email": "novo@exemplo.com"}, format="json")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["novo@exemplo.com"])
        self.assertIn("Viagem", msg.subject)
        self.assertIn("6.000,00", msg.body)
        self.assertIn("Crie sua conta", msg.body)

    def test_duplicate_and_member_invites_rejected(self) -> None:
        url = f"/api/goals/{self.goal_id}/invite/"
        self.assertEqual(self.client.post(url, {"email": "amiga@exemplo.com"}, format="json").status_code, 201)
        self.assertEqual(self.client.post(url, {"email": "amiga@exemplo.com"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"email": "dono@exemplo.com"}, format="json").status_code, 400)

    def test_member_can_leave_and_owner_can_remove(self) -> None:
        self.invite_and_accept()
        self.assertEqual(self.client.post(f"/api/goals/{self.goal_id}/leave/").status_code, 204)
        self.assertEqual(self.client.get(f"/api/goals/{self.goal_id}/").status_code, 404)
        self.as_user(self.owner)
        self.assertEqual(self.client.post(f"/api/goals/{self.goal_id}/leave/").status_code, 400)

    def test_dashboard_includes_goals(self) -> None:
        self.client.post(f"/api/goals/{self.goal_id}/contributions/", {"amount": "600"}, format="json")
        data = self.client.get("/api/dashboard/").data
        self.assertEqual(data["saved_in_goals"], Decimal("600"))
        self.assertEqual(data["missing_for_goals"], Decimal("5400"))
        self.assertEqual(data["goals"][0]["percent"], 10)
