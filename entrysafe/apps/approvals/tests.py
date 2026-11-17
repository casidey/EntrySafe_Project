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


class AuditLogPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.resident = User.objects.create_user("res", password="x")
        UserProfile.objects.create(user=self.resident, full_name="Rita Reyes", approval_status="APPROVED")
        self.url = reverse("approvals:audit")
        AuditLog.record(self.admin, AuditLog.Action.APPROVE_REQUEST, "PersonRestrictionRequest", 1,
                        "Approved the person restriction request for Ramon Villanueva.")
        AuditLog.record(self.resident, AuditLog.Action.SUBMIT_REQUEST, "VehicleRestrictionRequest", 2,
                        "Submitted a vehicle restriction request for NBX 4471.")
        AuditLog.record(None, AuditLog.Action.REVOKE_RESTRICTION, "RestrictedPerson", 3, "")

    def test_admin_only(self):
        self.assertIn(reverse("login:login"), self.client.get(self.url)["Location"])
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_lists_everything_newest_first_with_nav(self):
        self.client.force_login(self.admin)
        page = self.client.get(self.url)
        self.assertEqual(page.context["total"], 3)
        self.assertEqual([x["who"] for x in page.context["items"]], ["System", "Rita Reyes", "boss"])
        self.assertContains(page, "Submitted a vehicle restriction request for NBX 4471.")
        self.assertContains(page, "Revoke restriction")  # falls back to the action name when there is no summary
        self.assertContains(page, 'href="%s"' % self.url)

    def test_filter_by_action_and_text(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url, {"action": "SUBMIT_REQUEST"}).context["total"], 1)
        self.assertEqual(self.client.get(self.url, {"q": "villanueva"}).context["total"], 1)
        self.assertEqual(self.client.get(self.url, {"q": "rita"}).context["total"], 1)  # user's full name
        self.assertEqual(self.client.get(self.url, {"q": "restricted person"}).context["total"], 1)
        self.assertEqual(self.client.get(self.url, {"q": "nothing-like-this"}).context["total"], 0)
        self.assertEqual(self.client.get(self.url, {"action": "BOGUS"}).context["total"], 3)


class AdminSearchTests(TestCase):
    def setUp(self):
        from apps.guard import services as gate
        from apps.restrictions import services

        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.resident = User.objects.create_user("rita@example.com", email="rita@example.com", password="x")
        UserProfile.objects.create(user=self.resident, full_name="Rita Reyes", unit_number="Tower 2, Unit 1408",
                                   approval_status="APPROVED")
        guard = User.objects.create_user("gate", password="x")
        UserProfile.objects.create(user=guard, role="GUARD", approval_status="APPROVED")
        req, _, _ = services.submit("person", self.resident, {
            "first_name": "Ramon", "last_name": "Villanueva", "reason": "Trespassing"}, consent=True)
        self.person = services.approve_request("person", req.pk, self.admin)
        services.submit("vehicle", self.resident, {"license_plate": "NBX 4471", "vehicle_type": "SUV",
                                                   "make_model": "Toyota Fortuner", "reason": "Fire lane"}, consent=True)
        gate.record_match(guard, "person", self.person.pk, "villanueva", "MAIN_GATE", "DENIED_ENTRY", "Left calmly")
        self.url = reverse("approvals:search")

    def totals(self, q):
        self.client.force_login(self.admin)
        page = self.client.get(self.url, {"q": q})
        return {g["title"]: g["total"] for g in page.context["groups"] if g["total"]}

    def test_admin_only(self):
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_name_finds_restriction_request_and_gate_log(self):
        self.assertEqual(self.totals("villanueva"),
                         {"Restricted people": 1, "Person requests": 1, "Gate log": 1})

    def test_plate_ignores_spaces_and_case(self):
        self.assertEqual(self.totals("nbx4471"), {"Vehicle requests": 1})
        self.assertEqual(self.totals("fortuner"), {"Vehicle requests": 1})

    def test_resident_by_unit_email_and_requests_by_resident_name(self):
        self.assertEqual(self.totals("1408")["Residents"], 1)
        self.assertEqual(self.totals("rita@example.com")["Residents"], 1)
        self.assertEqual(self.totals("rita reyes"), {"Person requests": 1, "Vehicle requests": 1, "Residents": 1})

    def test_links_and_short_or_empty_queries(self):
        self.client.force_login(self.admin)
        page = self.client.get(self.url, {"q": "villanueva"})
        self.assertContains(page, reverse("restrictions:restricted") + "?status=active")
        self.assertContains(page, reverse("guard:log"))
        self.assertTrue(self.client.get(self.url, {"q": "v"}).context["too_short"])
        self.assertContains(self.client.get(self.url, {"q": "zzzz"}), "Nothing matches")
        self.assertEqual(self.client.get(self.url).context["groups"], [])

    def test_top_bar_search_submits_here_for_admins_only(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("approvals:overview")), f'action="{self.url}"')
        self.client.force_login(self.resident)
        self.assertNotContains(self.client.get(reverse("profile:profile")), f'action="{self.url}"')
