import io
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.guard.models import GuardVerificationLog
from apps.guard.views import plate_key
from apps.notifications.models import Notification
from apps.profile.models import UserProfile
from apps.restrictions import services
from apps.restrictions.models import RestrictedPerson, RestrictedVehicle

MEDIA = tempfile.mkdtemp(prefix="entrysafe-guard-media-")


def png():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, "PNG")
    return SimpleUploadedFile("p.png", buf.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA)
class GuardSearchTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.resident = User.objects.create_user("res", password="x")
        UserProfile.objects.create(user=self.resident, full_name="Rita", approval_status="APPROVED")
        self.guard = User.objects.create_user("gate", password="x")
        UserProfile.objects.create(user=self.guard, role="GUARD", approval_status="APPROVED")
        self.url = reverse("guard:search")

    def restrict_person(self, photo=None, **data):
        base = {"first_name": "Ramon", "last_name": "Villanueva", "alias_nickname": "Mon", "reason": "Trespassing"}
        req, _, err = services.submit("person", self.resident, {**base, **data}, photo=photo, consent=True)
        self.assertIsNone(err)
        return services.approve_request("person", req.pk, self.admin, guard_instructions="Call the admin office.")

    def restrict_vehicle(self, plate="NBX 4471"):
        req, _, err = services.submit("vehicle", self.resident, {
            "license_plate": plate, "vehicle_type": "SUV", "color": "Black", "reason": "Fire lane"}, consent=True)
        self.assertIsNone(err)
        return services.approve_request("vehicle", req.pk, self.admin)

    def search(self, q):
        return self.client.get(self.url, {"q": q})

    # ---- access
    def test_only_guards_can_open_gate_check(self):
        self.assertIn(reverse("login:login"), self.client.get(self.url)["Location"])
        for user in (self.resident, self.admin):
            self.client.force_login(user)
            self.assertRedirects(self.client.get(self.url), reverse("home:home"), fetch_redirect_response=False)

    def test_guard_home_goes_to_gate_check_and_nav(self):
        self.client.force_login(self.guard)
        self.assertRedirects(self.client.get(reverse("home:home")), self.url)
        page = self.client.get(self.url)
        self.assertContains(page, "Gate check")
        self.assertNotContains(page, reverse("restrictions:mine"))
        self.assertEqual(page.context["shell_role_label"], "Guard")

    def test_guard_cannot_file_requests(self):
        self.client.force_login(self.guard)
        self.assertEqual(self.client.get(reverse("restrictions:new", args=["person"])).status_code, 302)

    # ---- searching
    def test_person_found_by_last_name_alias_and_full_name(self):
        self.restrict_person()
        self.client.force_login(self.guard)
        for q in ("villanueva", "mon", "Ramon Villanueva", "  RAMON  "):
            page = self.search(q)
            self.assertEqual([r["title"] for r in page.context["results"]], ["Ramon Villanueva"], q)
            self.assertContains(page, "Restricted:")
            self.assertContains(page, "Call the admin office.")

    def test_every_word_must_match(self):
        self.restrict_person()
        self.client.force_login(self.guard)
        self.assertEqual(self.search("Ramon Santos").context["results"], [])

    def test_plate_matches_ignoring_case_spaces_and_dashes(self):
        self.restrict_vehicle("NBX 4471")
        self.client.force_login(self.guard)
        for q in ("nbx4471", "NBX-4471", "nbx 4471", "4471"):
            self.assertEqual([r["title"] for r in self.search(q).context["results"]], ["NBX 4471"], q)
        self.assertEqual(plate_key(" nb-x 44 71 "), "NBX4471")

    def test_no_match_is_clear(self):
        self.restrict_person()
        self.client.force_login(self.guard)
        page = self.search("Santos")
        self.assertContains(page, "Clear:")
        self.assertEqual(page.context["results"], [])

    def test_short_query_is_not_searched(self):
        self.restrict_person()
        self.client.force_login(self.guard)
        page = self.search("r")
        self.assertTrue(page.context["too_short"])
        self.assertContains(page, "at least 2 characters")

    def test_revoked_and_expired_restrictions_do_not_match(self):
        revoked = self.restrict_person()
        services.revoke_restriction("person", revoked.pk, self.admin)
        veh = self.restrict_vehicle()
        RestrictedVehicle.objects.filter(pk=veh.pk).update(end_date=timezone.localdate() - timedelta(days=1))
        self.client.force_login(self.guard)
        self.assertContains(self.search("villanueva"), "Clear:")
        self.assertContains(self.search("NBX4471"), "Clear:")
        veh.refresh_from_db()
        self.assertEqual(veh.status, "EXPIRED")

    def test_empty_query_lists_all_active(self):
        self.restrict_person()
        self.restrict_vehicle()
        revoked = self.restrict_person(first_name="Ana", last_name="Cruz", alias_nickname="")
        services.revoke_restriction("person", revoked.pk, self.admin)
        self.client.force_login(self.guard)
        page = self.client.get(self.url)
        self.assertEqual(sorted(r["title"] for r in page.context["results"]), ["NBX 4471", "Ramon Villanueva"])
        self.assertEqual(page.context["active_total"], 2)

    # ---- photos
    def test_guard_sees_photo_of_active_restriction_only(self):
        person = self.restrict_person(photo=png())
        url = reverse("restrictions:restricted_photo", args=["person", person.pk])
        self.client.force_login(self.guard)
        self.assertContains(self.search("villanueva"), url)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        resp.close()
        RestrictedPerson.objects.filter(pk=person.pk).update(status="REVOKED")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_guard_cannot_see_request_photos(self):
        req, _, _ = services.submit("person", self.resident, {"first_name": "A", "last_name": "B", "reason": "x"},
                                    photo=png(), consent=True)
        self.client.force_login(self.guard)
        self.assertEqual(self.client.get(reverse("restrictions:request_photo", args=["person", req.pk])).status_code, 404)


@override_settings(MEDIA_ROOT=MEDIA)
class GateRecordTests(TestCase):
    """Phase 4 part 2: the guard records what happened at the gate."""

    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.resident = User.objects.create_user("res", password="x")
        UserProfile.objects.create(user=self.resident, full_name="Rita", approval_status="APPROVED")
        self.guard = User.objects.create_user("gate", password="x")
        UserProfile.objects.create(user=self.guard, role="GUARD", full_name="Gerry Gate", approval_status="APPROVED")
        self.other_guard = User.objects.create_user("gate2", password="x")
        UserProfile.objects.create(user=self.other_guard, role="GUARD", approval_status="APPROVED")
        self.url = reverse("guard:record")

    def restrict_person(self):
        req, _, err = services.submit("person", self.resident, {
            "first_name": "Ramon", "last_name": "Villanueva", "reason": "Trespassing"}, consent=True)
        self.assertIsNone(err)
        return services.approve_request("person", req.pk, self.admin)

    def restrict_vehicle(self):
        req, _, err = services.submit("vehicle", self.resident, {
            "license_plate": "NBX 4471", "vehicle_type": "SUV", "reason": "Fire lane"}, consent=True)
        self.assertIsNone(err)
        return services.approve_request("vehicle", req.pk, self.admin)

    def post(self, user=None, **data):
        self.client.force_login(user or self.guard)
        base = {"q": "villanueva", "gate_location": "MAIN_GATE", "action_taken": "DENIED_ENTRY", "guard_notes": ""}
        return self.client.post(self.url, {**base, **data})

    def gate_notes(self, user):
        return Notification.objects.filter(recipient=user, notification_type="GATE_ACTIVITY")

    # ---- restricted matches
    def test_denied_match_is_logged_and_resident_notified(self):
        person = self.restrict_person()
        resp = self.post(kind="person", pk=person.pk, guard_notes="Turned away at 3pm")
        self.assertRedirects(resp, reverse("guard:search") + "?q=villanueva", fetch_redirect_response=False)
        log = GuardVerificationLog.objects.get()
        self.assertEqual((log.guard, log.matched_person, log.matched_vehicle), (self.guard, person, None))
        self.assertEqual(log.verification_type, "PERSON_SEARCH")
        self.assertEqual(log.match_result, "RESTRICTED_MATCH")
        self.assertEqual((log.gate_location, log.action_taken), ("MAIN_GATE", "DENIED_ENTRY"))
        self.assertEqual((log.query_input, log.guard_notes), ("villanueva", "Turned away at 3pm"))
        note = self.gate_notes(self.resident).get()
        self.assertIn("Ramon Villanueva", note.message)
        self.assertIn("denied entry", note.message)
        self.assertEqual((note.target_entity, note.target_id), ("GuardVerificationLog", log.pk))
        self.assertFalse(self.gate_notes(self.admin).exists())  # a plain denial does not bother the admins
        audit = AuditLog.objects.get(action="RECORD_VERIFICATION")
        self.assertEqual((audit.user, audit.target_id), (self.guard, log.pk))

    def test_escalated_vehicle_match_notifies_resident_and_admins(self):
        vehicle = self.restrict_vehicle()
        self.post(q="nbx4471", kind="vehicle", pk=vehicle.pk, gate_location="BASEMENT_GATE",
                  action_taken="ESCALATED_TO_ADMIN", guard_notes="Driver insists he lives here")
        log = GuardVerificationLog.objects.get()
        self.assertEqual((log.matched_vehicle, log.verification_type), (vehicle, "VEHICLE_SEARCH"))
        self.assertTrue(self.gate_notes(self.resident).exists())
        admin_note = self.gate_notes(self.admin).get()
        self.assertTrue(admin_note.title.startswith("Gate escalation"))
        self.assertIn("Gerry Gate", admin_note.message)
        self.assertIn("Driver insists he lives here", admin_note.message)
        self.assertFalse(self.gate_notes(self.other_guard).exists())

    def test_allowing_a_restricted_match_alerts_admins(self):
        person = self.restrict_person()
        self.post(kind="person", pk=person.pk, action_taken="ALLOWED_ENTRY")
        self.assertTrue(self.gate_notes(self.admin).get().title.startswith("Restricted entry allowed"))

    def test_gate_is_remembered_for_the_next_check(self):
        person = self.restrict_person()
        self.post(kind="person", pk=person.pk, gate_location="SERVICE_GATE")
        page = self.client.get(reverse("guard:search"), {"q": "villanueva"})
        self.assertEqual(page.context["gate"], "SERVICE_GATE")
        self.assertContains(page, '<option value="SERVICE_GATE" selected>')
        self.assertContains(page, "Recorded: denied entry for Ramon Villanueva at the Service gate.")

    def test_ended_restriction_cannot_be_recorded(self):
        person = self.restrict_person()
        services.revoke_restriction("person", person.pk, self.admin)
        resp = self.post(kind="person", pk=person.pk)
        self.assertFalse(GuardVerificationLog.objects.exists())
        self.assertContains(self.client.get(resp["Location"]), "no longer active")

    def test_bad_input_is_refused(self):
        person = self.restrict_person()
        for data in ({"gate_location": "ROOF"}, {"action_taken": "WAVED"}, {"guard_notes": "x" * 1001},
                     {"kind": "boat"}, {"pk": "abc"}, {"pk": 9999}):
            self.post(**{"kind": "person", "pk": person.pk, **data})
        self.assertFalse(GuardVerificationLog.objects.exists())

    def test_list_mode_uses_the_name_as_the_search(self):
        person = self.restrict_person()
        self.client.force_login(self.guard)
        page = self.client.get(reverse("guard:search"))
        self.assertContains(page, 'name="query_input" value="Ramon Villanueva"')
        self.post(q="", query_input="Ramon Villanueva", kind="person", pk=person.pk)
        self.assertEqual(GuardVerificationLog.objects.get().query_input, "Ramon Villanueva")

    # ---- clear checks
    def test_clear_check_is_logged_without_notifications(self):
        self.restrict_person()
        resp = self.post(q="Santos", kind="person", action_taken="ALLOWED_ENTRY")
        self.assertRedirects(resp, reverse("guard:search") + "?q=Santos", fetch_redirect_response=False)
        log = GuardVerificationLog.objects.get()
        self.assertEqual((log.match_result, log.verification_type), ("CLEAR_NO_MATCH", "PERSON_SEARCH"))
        self.assertIsNone(log.matched_person)
        self.assertFalse(Notification.objects.filter(notification_type="GATE_ACTIVITY").exists())
        self.assertTrue(AuditLog.objects.filter(action="RECORD_VERIFICATION", target_id=log.pk).exists())

    def test_escalated_clear_check_notifies_admins(self):
        self.post(q="ABC 123", kind="vehicle", action_taken="ESCALATED_TO_ADMIN")
        self.assertEqual(GuardVerificationLog.objects.get().verification_type, "VEHICLE_SEARCH")
        self.assertTrue(self.gate_notes(self.admin).exists())

    def test_clear_check_refused_when_the_search_matches(self):
        self.restrict_person()
        self.post(q="villanueva", kind="person", action_taken="ALLOWED_ENTRY")
        self.assertFalse(GuardVerificationLog.objects.exists())

    def test_clear_form_guesses_vehicle_for_plates(self):
        self.client.force_login(self.guard)
        page = self.client.get(reverse("guard:search"), {"q": "ABC 123"})
        self.assertEqual(page.context["clear_kind"], "vehicle")
        self.assertContains(page, "Record this check")
        self.assertEqual(self.client.get(reverse("guard:search"), {"q": "Santos"}).context["clear_kind"], "person")

    # ---- access
    def test_only_guards_can_record(self):
        person = self.restrict_person()
        for user in (self.resident, self.admin):
            resp = self.post(user=user, kind="person", pk=person.pk)
            self.assertRedirects(resp, reverse("home:home"), fetch_redirect_response=False)
        self.client.force_login(self.guard)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertFalse(GuardVerificationLog.objects.exists())

    # ---- log pages
    def test_my_checks_lists_only_my_own(self):
        person = self.restrict_person()
        self.post(kind="person", pk=person.pk)
        self.post(user=self.other_guard, q="Santos", kind="person", action_taken="ALLOWED_ENTRY")
        self.client.force_login(self.guard)
        page = self.client.get(reverse("guard:my_checks"))
        self.assertEqual(len(page.context["items"]), 1)
        self.assertEqual((page.context["today_total"], page.context["today_restricted"]), (1, 1))
        self.assertContains(page, "matched Ramon Villanueva")
        self.assertEqual([x["obj"].query_input for x in page.context["items"]], ["villanueva"])
        self.assertContains(page, reverse("guard:my_checks"))  # nav item
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(reverse("guard:my_checks")).status_code, 302)

    def test_admin_gate_log_filters(self):
        person = self.restrict_person()
        self.post(kind="person", pk=person.pk, action_taken="ESCALATED_TO_ADMIN", gate_location="SERVICE_GATE")
        self.post(q="Santos", kind="person", action_taken="ALLOWED_ENTRY")
        self.post(user=self.other_guard, q="Reyes", kind="person", action_taken="DENIED_ENTRY")
        self.client.force_login(self.admin)
        url = reverse("guard:log")
        page = self.client.get(url)
        self.assertEqual(page.context["counts"], {"all": 3, "restricted": 1, "clear": 2})
        self.assertContains(page, "Guard: Gerry Gate")
        self.assertEqual(len(self.client.get(url, {"result": "clear"}).context["items"]), 2)
        self.assertEqual(len(self.client.get(url, {"action": "DENIED_ENTRY"}).context["items"]), 1)
        filtered = self.client.get(url, {"gate": "SERVICE_GATE"})
        self.assertEqual([x["matched"] for x in filtered.context["items"]], ["Ramon Villanueva"])
        self.assertEqual(self.client.get(url, {"result": "nope", "gate": "ROOF"}).context["counts"]["all"], 3)
        self.assertContains(page, url)  # nav item

    def test_gate_log_is_admin_only(self):
        for user in (self.guard, self.resident):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("guard:log")).status_code, 302)
