from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.guard.models import GuardVerificationLog
from apps.notifications.models import Notification
from apps.profile.models import UserProfile
from apps.restrictions.models import (
    PersonRestrictionRequest, RestrictedPerson, RestrictedVehicle, VehicleRestrictionRequest)
from apps.user_settings.models import UserSettings


class ErdTableNamesTests(TestCase):
    def test_tables_are_named_like_the_erd(self):
        expected = {
            UserProfile: "user_profile", UserSettings: "user_settings", Notification: "notification",
            AuditLog: "audit_log", PersonRestrictionRequest: "person_restriction_request",
            VehicleRestrictionRequest: "vehicle_restriction_request", RestrictedPerson: "restricted_person",
            RestrictedVehicle: "restricted_vehicle", GuardVerificationLog: "guard_verification_log",
        }
        for model, table in expected.items():
            self.assertEqual(model._meta.db_table, table)


class ErdRelationshipTests(TestCase):
    def setUp(self):
        self.resident = User.objects.create_user("res", password="x")
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.guard = User.objects.create_user("gate", password="x")

    def test_person_request_to_restricted_person_to_guard_log(self):
        req = PersonRestrictionRequest.objects.create(
            resident=self.resident, first_name="R.", last_name="Villanueva", reason="Repeated trespassing")
        self.assertEqual(req.status, "PENDING")
        person = RestrictedPerson.objects.create(
            request=req, approved_by=self.admin, first_name="R.", last_name="Villanueva",
            restriction_reason="Trespassing", start_date=date.today())
        self.assertEqual(person.status, "ACTIVE")
        self.assertIsNone(person.end_date)  # permanent
        log = GuardVerificationLog.objects.create(
            guard=self.guard, verification_type="PERSON_SEARCH", query_input="villanueva",
            matched_person=person, match_result="RESTRICTED_MATCH", gate_location="MAIN_GATE",
            action_taken="DENIED_ENTRY")
        self.assertEqual(list(req.restricted_people.all()), [person])
        self.assertEqual(list(person.verification_logs.all()), [log])

    def test_vehicle_request_to_restricted_vehicle_to_guard_log(self):
        req = VehicleRestrictionRequest.objects.create(
            resident=self.resident, license_plate="NBX 4471", vehicle_type="SUV", reason="Blocks the fire lane")
        veh = RestrictedVehicle.objects.create(
            request=req, approved_by=self.admin, license_plate="NBX 4471", vehicle_type="SUV",
            restriction_reason="Fire lane", start_date=date.today())
        log = GuardVerificationLog.objects.create(
            guard=self.guard, verification_type="VEHICLE_SEARCH", query_input="NBX 4471", matched_vehicle=veh,
            match_result="RESTRICTED_MATCH", gate_location="SERVICE_GATE", action_taken="ESCALATED_TO_ADMIN")
        self.assertEqual(list(req.restricted_vehicles.all()), [veh])
        self.assertEqual(list(veh.verification_logs.all()), [log])

    def test_restricted_records_can_exist_without_a_request(self):
        RestrictedPerson.objects.create(first_name="A", last_name="B", restriction_reason="x", start_date=date.today())
        RestrictedVehicle.objects.create(license_plate="ZZZ 1", vehicle_type="VAN", restriction_reason="x",
                                         start_date=date.today())

    def test_clear_search_has_no_match(self):
        log = GuardVerificationLog.objects.create(
            guard=self.guard, verification_type="PERSON_SEARCH", query_input="nobody",
            match_result="CLEAR_NO_MATCH", gate_location="BASEMENT_GATE", action_taken="ALLOWED_ENTRY")
        self.assertIsNone(log.matched_person)
        self.assertIsNone(log.matched_vehicle)

    def test_audit_log_survives_deleting_its_user(self):
        AuditLog.record(self.admin, "REVOKE_RESTRICTION", "RestrictedPerson", 1, "Revoked")
        self.admin.delete()
        self.assertIsNone(AuditLog.objects.get().user)

    def test_notification_and_settings_link_to_user(self):
        Notification.objects.create(recipient=self.resident, title="Hi", message="m", notification_type="NEW_RESTRICTION")
        UserSettings.objects.create(user=self.resident)
        self.assertEqual(self.resident.notifications.count(), 1)
        self.assertEqual(self.resident.settings.dark_mode, False)


# ====================================================================== Phase 3: request flow
import io
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.restrictions import services

MEDIA = tempfile.mkdtemp(prefix="entrysafe-test-media-")


def png(name="face.png"):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "green").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def make_resident(username="res@example.com", name="Rita Resident", unit="Tower 2, Unit 1408"):
    user = User.objects.create_user(username, email=username, password="x")
    UserProfile.objects.create(user=user, full_name=name, unit_number=unit, approval_status="APPROVED")
    return user


PERSON_DATA = {"first_name": "Ramon", "last_name": "Villanueva", "alias_nickname": "Mon",
               "relationship_to_resident": "Ex-tenant", "reason": "Repeated trespassing", "consent": "on"}
VEHICLE_DATA = {"license_plate": " nbx  4471 ", "vehicle_type": "SUV", "make_model": "Toyota Fortuner",
                "color": "Black", "reason": "Blocks the fire lane", "consent": "on"}


@override_settings(MEDIA_ROOT=MEDIA)
class FlowBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.resident = make_resident()
        self.other = make_resident("other@example.com", "Otto Other", "Tower 1, Unit 101")
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.guard = User.objects.create_user("gate", password="x")
        UserProfile.objects.create(user=self.guard, role="GUARD", approval_status="APPROVED")

    def person_request(self, resident=None, **extra):
        obj, _, error = services.submit("person", resident or self.resident, {**PERSON_DATA, **extra}, consent=True)
        self.assertIsNone(error)
        return obj

    def vehicle_request(self, resident=None):
        obj, _, error = services.submit("vehicle", resident or self.resident, VEHICLE_DATA, consent=True)
        self.assertIsNone(error)
        return obj


class AccessTests(FlowBase):
    def test_anonymous_is_sent_to_login(self):
        for url in (reverse("restrictions:mine"), reverse("restrictions:new", args=["person"]),
                    reverse("restrictions:queue"), reverse("restrictions:restricted")):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertIn(reverse("login:login"), r["Location"])

    def test_resident_cannot_open_admin_pages_or_review(self):
        req = self.person_request()
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(reverse("restrictions:queue")).status_code, 302)
        self.assertEqual(self.client.get(reverse("restrictions:restricted")).status_code, 302)
        self.assertEqual(self.client.get(reverse("restrictions:review", args=["person", req.pk])).status_code, 302)
        self.client.post(reverse("restrictions:approve", args=["person", req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, "PENDING")
        self.assertEqual(RestrictedPerson.objects.count(), 0)

    def test_admin_and_guard_cannot_submit_requests(self):
        for user in (self.admin, self.guard):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("restrictions:new", args=["person"])).status_code, 302)
            self.client.post(reverse("restrictions:new", args=["person"]), PERSON_DATA)
        self.assertEqual(PersonRestrictionRequest.objects.count(), 0)

    def test_unapproved_resident_cannot_submit(self):
        self.resident.profile.approval_status = "PENDING"
        self.resident.profile.save()
        self.client.force_login(self.resident)
        self.client.post(reverse("restrictions:new", args=["person"]), PERSON_DATA)
        self.assertEqual(PersonRestrictionRequest.objects.count(), 0)

    def test_unknown_kind_is_404_and_actions_need_post(self):
        req = self.person_request()
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(reverse("restrictions:new", args=["boat"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("restrictions:cancel", args=["person", req.pk])).status_code, 405)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("restrictions:approve", args=["person", req.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("restrictions:reject", args=["person", req.pk])).status_code, 405)

    def test_nav_links_per_role(self):
        self.client.force_login(self.resident)
        self.assertContains(self.client.get(reverse("home:home")), reverse("restrictions:mine"))
        self.client.force_login(self.guard)
        self.assertNotContains(self.client.get(reverse("home:home"), follow=True), reverse("restrictions:mine"))
        self.client.force_login(self.admin)
        page = self.client.get(reverse("approvals:overview"))
        self.assertContains(page, reverse("restrictions:queue"))
        self.assertContains(page, "Pending restriction requests")


class SubmitTests(FlowBase):
    def test_person_request_with_photo(self):
        self.client.force_login(self.resident)
        self.assertContains(self.client.get(reverse("restrictions:new", args=["person"])), "Restrict a person")
        resp = self.client.post(reverse("restrictions:new", args=["person"]), {**PERSON_DATA, "photo": png()},
                                follow=True)
        self.assertContains(resp, "was sent for review")
        req = PersonRestrictionRequest.objects.get()
        self.assertEqual((req.resident, req.status, req.first_name, req.alias_nickname),
                         (self.resident, "PENDING", "Ramon", "Mon"))
        self.assertTrue(req.photo.name.startswith("restriction_photos/persons/"))
        log = AuditLog.objects.get()
        self.assertEqual((log.action, log.target_entity, log.target_id, log.user),
                         ("SUBMIT_REQUEST", "PersonRestrictionRequest", req.pk, self.resident))
        self.assertContains(resp, "PR-%04d" % req.pk)

    def test_vehicle_request_normalises_plate(self):
        self.client.force_login(self.resident)
        self.client.post(reverse("restrictions:new", args=["vehicle"]), VEHICLE_DATA)
        req = VehicleRestrictionRequest.objects.get()
        self.assertEqual((req.license_plate, req.vehicle_type, req.status), ("NBX 4471", "SUV", "PENDING"))

    def test_validation_errors_keep_the_form(self):
        self.client.force_login(self.resident)
        cases = [
            ("person", {**PERSON_DATA, "last_name": ""}, "first and last name"),
            ("person", {**PERSON_DATA, "reason": " "}, "explain why"),
            ("person", {k: v for k, v in PERSON_DATA.items() if k != "consent"}, "confirm you have the right"),
            ("person", {**PERSON_DATA, "photo": SimpleUploadedFile("x.pdf", b"%PDF")}, "PNG or JPG"),
            ("person", {**PERSON_DATA, "photo": SimpleUploadedFile("x.png", b"not an image")}, "could not be read"),
            ("vehicle", {**VEHICLE_DATA, "license_plate": ""}, "plate number"),
            ("vehicle", {**VEHICLE_DATA, "vehicle_type": "BOAT"}, "vehicle type"),
        ]
        for kind, data, message in cases:
            resp = self.client.post(reverse("restrictions:new", args=[kind]), data)
            self.assertContains(resp, message)
        self.assertEqual(PersonRestrictionRequest.objects.count() + VehicleRestrictionRequest.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)
        resp = self.client.post(reverse("restrictions:new", args=["person"]), {**PERSON_DATA, "last_name": ""})
        self.assertContains(resp, 'value="Ramon"')

    def test_oversized_photo_is_refused(self):
        big = png()
        big.size = services.MAX_PHOTO_BYTES + 1
        _, _, error = services.submit("person", self.resident, PERSON_DATA, photo=big, consent=True)
        self.assertIn("larger than 5MB", error)


class MyRequestsTests(FlowBase):
    def test_lists_only_my_requests(self):
        self.person_request()
        self.vehicle_request(self.other)
        self.client.force_login(self.resident)
        page = self.client.get(reverse("restrictions:mine"))
        self.assertContains(page, "Ramon Villanueva")
        self.assertNotContains(page, "NBX 4471")

    def test_cancel_pending_request(self):
        req = self.person_request()
        self.client.force_login(self.resident)
        resp = self.client.post(reverse("restrictions:cancel", args=["person", req.pk]), follow=True)
        self.assertContains(resp, "was cancelled")
        req.refresh_from_db()
        self.assertEqual(req.status, "CANCELLED")
        self.assertTrue(AuditLog.objects.filter(action="CANCEL_REQUEST", target_id=req.pk).exists())

    def test_cannot_cancel_someone_elses_or_a_reviewed_request(self):
        theirs = self.person_request(self.other)
        mine = self.person_request()
        services.approve_request("person", mine.pk, self.admin)
        self.client.force_login(self.resident)
        self.client.post(reverse("restrictions:cancel", args=["person", theirs.pk]))
        resp = self.client.post(reverse("restrictions:cancel", args=["person", mine.pk]), follow=True)
        self.assertContains(resp, "Only a pending request can be cancelled")
        theirs.refresh_from_db(); mine.refresh_from_db()
        self.assertEqual((theirs.status, mine.status), ("PENDING", "APPROVED"))

    def test_cancelled_request_cannot_be_approved(self):
        req = self.person_request()
        services.cancel_request("person", req.pk, self.resident)
        with self.assertRaises(services.RestrictionError):
            services.approve_request("person", req.pk, self.admin)
        self.assertEqual(RestrictedPerson.objects.count(), 0)


class ReviewTests(FlowBase):
    def test_queue_and_review_pages(self):
        req = self.person_request()
        self.vehicle_request(self.other)
        self.client.force_login(self.admin)
        page = self.client.get(reverse("restrictions:queue"))
        self.assertContains(page, "Ramon Villanueva")
        self.assertContains(page, "NBX 4471")
        self.assertContains(page, "Rita Resident, Tower 2, Unit 1408")
        self.assertEqual(page.context["counts"], {"pending": 2, "approved": 0, "rejected": 0, "cancelled": 0})
        detail = self.client.get(reverse("restrictions:review", args=["person", req.pk]))
        self.assertContains(detail, "Repeated trespassing")
        self.assertContains(detail, "Guard instructions")

    def test_approve_person_creates_active_restriction(self):
        obj, _, _ = services.submit("person", self.resident, PERSON_DATA, photo=png(), consent=True)
        self.client.force_login(self.admin)
        end = timezone.localdate() + timedelta(days=30)
        resp = self.client.post(reverse("restrictions:approve", args=["person", obj.pk]), {
            "end_date": end.isoformat(), "guard_instructions": "Call the admin office.", "admin_remarks": "Verified."},
            follow=True)
        self.assertContains(resp, "is now on the restricted list")
        obj.refresh_from_db()
        self.assertEqual((obj.status, obj.reviewed_by, obj.admin_remarks), ("APPROVED", self.admin, "Verified."))
        self.assertIsNotNone(obj.reviewed_at)
        person = RestrictedPerson.objects.get()
        self.assertEqual((person.request, person.approved_by, person.first_name, person.last_name, person.alias_nickname),
                         (obj, self.admin, "Ramon", "Villanueva", "Mon"))
        self.assertEqual((person.status, person.start_date, person.end_date, person.restriction_reason,
                          person.guard_instructions),
                         ("ACTIVE", timezone.localdate(), end, "Repeated trespassing", "Call the admin office."))
        self.assertTrue(person.photo.name.startswith("restricted/persons/"))
        self.assertNotEqual(person.photo.name, obj.photo.name)
        log = AuditLog.objects.get(action="APPROVE_REQUEST")
        self.assertEqual((log.user, log.target_entity, log.target_id, log.ip_address),
                         (self.admin, "PersonRestrictionRequest", obj.pk, "127.0.0.1"))
        note = Notification.objects.get(recipient=self.resident)
        self.assertEqual((note.notification_type, note.target_entity, note.target_id),
                         ("REQUEST_STATUS", "PersonRestrictionRequest", obj.pk))
        guard_note = Notification.objects.get(recipient=self.guard)
        self.assertEqual((guard_note.notification_type, guard_note.target_entity, guard_note.target_id),
                         ("NEW_RESTRICTION", "RestrictedPerson", person.pk))

    def test_approve_vehicle_is_permanent_by_default(self):
        req = self.vehicle_request()
        self.client.force_login(self.admin)
        self.client.post(reverse("restrictions:approve", args=["vehicle", req.pk]))
        veh = RestrictedVehicle.objects.get()
        self.assertEqual((veh.license_plate, veh.vehicle_type, veh.make_model, veh.color, veh.status, veh.end_date),
                         ("NBX 4471", "SUV", "Toyota Fortuner", "Black", "ACTIVE", None))

    def test_past_or_bad_end_date_is_refused_and_form_kept(self):
        req = self.person_request()
        self.client.force_login(self.admin)
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        for bad, message in ((yesterday, "cannot be in the past"), ("soon", "valid end date")):
            resp = self.client.post(reverse("restrictions:approve", args=["person", req.pk]),
                                    {"end_date": bad, "guard_instructions": "Hold at gate"}, follow=True)
            self.assertContains(resp, message)
            self.assertContains(resp, "Hold at gate")
        req.refresh_from_db()
        self.assertEqual(req.status, "PENDING")
        self.assertEqual(RestrictedPerson.objects.count(), 0)

    def test_reject_with_remarks(self):
        req = self.vehicle_request()
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("restrictions:reject", args=["vehicle", req.pk]), {"reason": "Not enough detail"},
                                follow=True)
        self.assertContains(resp, "was rejected")
        req.refresh_from_db()
        self.assertEqual((req.status, req.admin_remarks, req.reviewed_by), ("REJECTED", "Not enough detail", self.admin))
        self.assertEqual(RestrictedVehicle.objects.count(), 0)
        self.assertTrue(AuditLog.objects.filter(action="REJECT_REQUEST", target_id=req.pk).exists())
        self.assertEqual(Notification.objects.get(recipient=self.resident).message, "Not enough detail")
        self.assertFalse(Notification.objects.filter(recipient=self.guard).exists())

    def test_a_request_cannot_be_reviewed_twice(self):
        req = self.person_request()
        self.client.force_login(self.admin)
        self.client.post(reverse("restrictions:approve", args=["person", req.pk]))
        again = self.client.post(reverse("restrictions:approve", args=["person", req.pk]), follow=True)
        self.assertContains(again, "already been reviewed")
        self.client.post(reverse("restrictions:reject", args=["person", req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, "APPROVED")
        self.assertEqual(RestrictedPerson.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action__in=["APPROVE_REQUEST", "REJECT_REQUEST"]).count(), 1)


class RemovalAndExpiryTests(FlowBase):
    def approved(self, kind="person", resident=None, **kw):
        req = self.person_request(resident) if kind == "person" else self.vehicle_request(resident)
        return services.approve_request(kind, req.pk, self.admin, **kw)

    def test_resident_removes_own_restriction_without_admin(self):
        person = self.approved()
        Notification.objects.all().delete()
        self.client.force_login(self.resident)
        self.assertContains(self.client.get(reverse("restrictions:mine")), "Active restrictions")
        resp = self.client.post(reverse("restrictions:remove", args=["person", person.pk]), follow=True)
        self.assertContains(resp, "was removed")
        person.refresh_from_db()
        self.assertEqual(person.status, "REVOKED")
        log = AuditLog.objects.get(action="REVOKE_RESTRICTION")
        self.assertEqual((log.user, log.target_entity, log.target_id), (self.resident, "RestrictedPerson", person.pk))
        self.assertEqual(set(Notification.objects.values_list("recipient__username", flat=True)), {"boss", "gate"})
        self.assertEqual(resp.context["restrictions"], [])

    def test_resident_cannot_remove_someone_elses_restriction(self):
        theirs = self.approved(resident=self.other)
        self.client.force_login(self.resident)
        resp = self.client.post(reverse("restrictions:remove", args=["person", theirs.pk]), follow=True)
        self.assertContains(resp, "was not found")
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, "ACTIVE")

    def test_guard_cannot_remove_a_restriction(self):
        person = self.approved()
        self.client.force_login(self.guard)
        self.client.post(reverse("restrictions:remove", args=["person", person.pk]))
        person.refresh_from_db()
        self.assertEqual(person.status, "ACTIVE")

    def test_admin_revokes_and_resident_is_told(self):
        veh = self.approved("vehicle")
        Notification.objects.all().delete()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("restrictions:restricted")), "NBX 4471")
        resp = self.client.post(reverse("restrictions:remove", args=["vehicle", veh.pk]), follow=True)
        self.assertRedirects(resp, reverse("restrictions:restricted"))
        veh.refresh_from_db()
        self.assertEqual(veh.status, "REVOKED")
        self.assertTrue(Notification.objects.filter(recipient=self.resident, title="Restriction removed").exists())
        again = self.client.post(reverse("restrictions:remove", args=["vehicle", veh.pk]), follow=True)
        self.assertContains(again, "no longer active")
        ended = self.client.get(reverse("restrictions:restricted") + "?status=ended")
        self.assertContains(ended, "Revoked")

    def test_expired_restrictions_flip_on_read(self):
        today = timezone.localdate()
        past = self.approved()
        last_day = self.approved("vehicle", end_date=today)
        RestrictedPerson.objects.filter(pk=past.pk).update(end_date=today - timedelta(days=1))
        self.client.force_login(self.admin)
        page = self.client.get(reverse("restrictions:restricted"))
        past.refresh_from_db(); last_day.refresh_from_db()
        self.assertEqual((past.status, last_day.status), ("EXPIRED", "ACTIVE"))
        self.assertEqual(page.context["counts"], {"active": 1, "ended": 1})
        self.client.force_login(self.resident)
        mine = self.client.get(reverse("restrictions:mine"))
        self.assertEqual([x["title"] for x in mine.context["restrictions"]], ["NBX 4471"])


class PhotoAccessTests(FlowBase):
    def test_photos_are_private_to_owner_and_admin(self):
        req, _, _ = services.submit("person", self.resident, PERSON_DATA, photo=png(), consent=True)
        person = services.approve_request("person", req.pk, self.admin)
        urls = [reverse("restrictions:request_photo", args=["person", req.pk]),
                reverse("restrictions:restricted_photo", args=["person", person.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)  # anonymous -> login
        for user, code in ((self.resident, 200), (self.admin, 200), (self.other, 404)):
            self.client.force_login(user)
            for url in urls:
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, code)
                if code == 200:
                    self.assertEqual(resp["Content-Type"], "image/png")
                    resp.close()

    def test_missing_photo_is_404(self):
        req = self.person_request()
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(reverse("restrictions:request_photo", args=["person", req.pk])).status_code, 404)
