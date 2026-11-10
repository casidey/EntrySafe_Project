import io
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.guard.views import plate_key
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
