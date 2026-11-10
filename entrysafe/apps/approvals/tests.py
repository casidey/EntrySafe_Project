from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.profile.models import UserProfile


def make_pending(username="pat@example.com", name="Pat Pending"):
    user = User.objects.create_user(username, email=username, password="SecurePassword123!", is_active=False)
    return UserProfile.objects.create(user=user, full_name=name, unit_number="Tower 1, Unit 101",
                                      id_proof_image="id_proofs/x.pdf")


class ApprovalsAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.resident = User.objects.create_user("res", password="x")
        self.profile = make_pending()

    def test_anonymous_redirected_to_login(self):
        for name in ("approvals:overview", "approvals:registrations"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302)
            self.assertIn(reverse("login:login"), r["Location"])

    def test_resident_cannot_open_approvals_or_approve(self):
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(reverse("approvals:registrations")).status_code, 302)
        self.client.post(reverse("approvals:approve", args=[self.profile.pk]))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.approval_status, "PENDING")
        self.assertFalse(self.profile.user.is_active)

    def test_approve_requires_post(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("approvals:approve", args=[self.profile.pk])).status_code, 405)

    def test_admin_lists_and_approves(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("approvals:registrations")), "Pat Pending")
        resp = self.client.post(reverse("approvals:approve", args=[self.profile.pk]), follow=True)
        self.assertContains(resp, "was approved")
        self.profile.user.refresh_from_db()
        self.assertTrue(self.profile.user.is_active)
        log = AuditLog.objects.get()
        self.assertEqual(log.ip_address, "127.0.0.1")

    def test_admin_disapproves_with_reason(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("approvals:disapprove", args=[self.profile.pk]), {"reason": "Blurry ID"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.approval_status, "DISAPPROVED")
        self.assertEqual(self.profile.disapproval_reason, "Blurry ID")
        self.assertFalse(self.profile.user.is_active)

    def test_admins_own_profile_is_not_listed_as_a_registration(self):
        UserProfile.for_user(self.admin)
        self.client.force_login(self.admin)
        page = self.client.get(reverse("approvals:registrations") + "?status=approved")
        self.assertEqual(page.context["counts"], {"pending": 1, "approved": 0, "disapproved": 0})

    def test_staff_home_redirects_to_approvals(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse("home:home")), reverse("approvals:overview"))

    def test_overview_renders(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("approvals:overview")), "Pending registrations")


class StaffAccountTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.resident = User.objects.create_user("res", password="x")
        self.url = reverse("approvals:accounts")
        self.data = {"role": "GUARD", "full_name": "Gina Gate", "username": "gina", "email": "gina@example.com",
                     "contact_number": "0917 000 0000", "password": "Gatehouse2026!"}

    def test_only_admins_can_open_or_create(self):
        self.assertIn(reverse("login:login"), self.client.get(self.url)["Location"])
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.post(self.url, self.data)
        self.assertFalse(User.objects.filter(username="gina").exists())

    def test_admin_creates_guard_who_can_sign_in_to_gate_check(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.url), "New account")
        resp = self.client.post(self.url, self.data, follow=True)
        self.assertContains(resp, "Guard account gina was created")
        self.assertContains(resp, "Gina Gate")
        guard = User.objects.get(username="gina")
        self.assertTrue(guard.is_active)
        self.assertFalse(guard.is_staff)
        self.assertEqual((guard.profile.role, guard.profile.approval_status, guard.profile.reviewed_by),
                         ("GUARD", "APPROVED", self.admin))
        log = AuditLog.objects.get(action="CREATE_ACCOUNT")
        self.assertEqual((log.user, log.target_entity, log.target_id), (self.admin, "UserProfile", guard.profile.pk))
        self.client.logout()
        self.client.post(reverse("login:login"), {"username": "gina", "password": "Gatehouse2026!"})
        self.assertRedirects(self.client.get(reverse("home:home")), reverse("guard:search"))

    def test_admin_creates_administrator(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {**self.data, "role": "ADMIN", "username": "ana", "email": "ana@example.com"})
        ana = User.objects.get(username="ana")
        self.assertTrue(ana.is_staff)
        self.assertEqual(ana.profile.role, "ADMIN")

    def test_validation(self):
        User.objects.create_user("taken", email="taken@example.com", password="x")
        self.client.force_login(self.admin)
        cases = [
            ({"role": "RESIDENT"}, "choose Guard or Administrator"),
            ({"full_name": ""}, "full name, username and password"),
            ({"username": "bad name"}, "Usernames may contain only"),
            ({"email": "nope"}, "valid email"),
            ({"username": "TAKEN"}, "already exists"),
            ({"email": "taken@example.com"}, "already exists"),
            ({"password": "12345678"}, "too common"),
        ]
        for change, message in cases:
            resp = self.client.post(self.url, {**self.data, **change})
            self.assertContains(resp, message)
        self.assertFalse(User.objects.filter(username="gina").exists())
        self.assertContains(self.client.post(self.url, {**self.data, "email": "nope"}), 'value="Gina Gate"')

    def test_nav_shows_accounts_for_admin(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("approvals:overview")), self.url)
