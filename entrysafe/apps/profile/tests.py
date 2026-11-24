from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog

from .models import ResidentVehicle, UserProfile


class ProfilePageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        UserProfile.objects.create(user=self.admin, role="ADMIN", full_name="Ana Admin", approval_status="APPROVED")
        self.resident = User.objects.create_user("rita", password="RitaPass!2026", email="rita@example.com")
        UserProfile.objects.create(user=self.resident, full_name="Rita Reyes", unit_number="Tower 2, Unit 1408",
                                   approval_status="APPROVED", reviewed_by=self.admin,
                                   reviewed_at=timezone.now())
        self.guard = User.objects.create_user("gate", password="x")
        UserProfile.objects.create(user=self.guard, role="GUARD", full_name="Gerry Gate", approval_status="APPROVED")
        self.url = reverse("profile:profile")
        self.client.force_login(self.resident)

    def details(self, **data):
        base = {"full_name": "Rita Reyes", "contact_number": "", "emergency_contact_name": "",
                "emergency_contact_relationship": "", "emergency_contact_number": ""}
        return self.client.post(self.url, {**base, **data})

    # ---- overview
    def test_overview_shows_account_facts(self):
        page = self.client.get(self.url)
        for text in ("Resident", "rita", "Tower 2, Unit 1408", "rita@example.com", "Member since", "Last sign-in",
                     "ES-", "by Ana Admin", "My vehicles", "Change password", "Recent activity"):
            self.assertContains(page, text)

    def test_staff_see_no_vehicle_section(self):
        self.client.force_login(self.guard)
        page = self.client.get(self.url)
        self.assertContains(page, "Guard")
        self.assertNotContains(page, "My vehicles")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.url), "Administrator")

    def test_login_required(self):
        self.client.logout()
        self.assertIn(reverse("login:login"), self.client.get(self.url)["Location"])

    # ---- details and emergency contact
    def test_save_contact_and_emergency_contact(self):
        resp = self.details(contact_number="0917 123 4567", emergency_contact_name="Maria Reyes",
                            emergency_contact_relationship="Mother", emergency_contact_number="+63 917 765 4321")
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        p = UserProfile.objects.get(user=self.resident)
        self.assertEqual((p.contact_number, p.emergency_contact_name, p.emergency_contact_relationship,
                          p.emergency_contact_number),
                         ("0917 123 4567", "Maria Reyes", "Mother", "+63 917 765 4321"))
        audit = AuditLog.objects.get(action="UPDATE_PROFILE")
        self.assertIn("emergency contact name", audit.change_summary)
        self.assertNotIn("Maria", audit.change_summary)  # field names only, never values

    def test_detail_validation(self):
        self.assertContains(self.details(full_name=""), "Please enter your full name")
        self.assertContains(self.details(contact_number="call me"), "Phone numbers may contain only")
        self.assertContains(self.details(emergency_contact_name="Maria"), "both a name and a number")
        self.assertFalse(AuditLog.objects.filter(action="UPDATE_PROFILE").exists())

    def test_unit_and_email_cannot_be_changed_here(self):
        self.details(unit_number="Penthouse", email="evil@example.com")
        self.resident.refresh_from_db()
        self.assertEqual((self.resident.profile.unit_number, self.resident.email), ("Tower 2, Unit 1408", "rita@example.com"))

    # ---- password
    def test_change_password_keeps_session_and_signs_out_others(self):
        other = self.client_class()
        other.force_login(self.resident)
        resp = self.client.post(reverse("profile:password"), {
            "old_password": "RitaPass!2026", "new_password1": "Brand-New-Pass-88", "new_password2": "Brand-New-Pass-88"})
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        self.resident.refresh_from_db()
        self.assertTrue(self.resident.check_password("Brand-New-Pass-88"))
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(other.get(self.url).status_code, 302)
        self.assertTrue(AuditLog.objects.filter(action="CHANGE_PASSWORD", user=self.resident).exists())

    def test_change_password_errors(self):
        page = self.client.post(reverse("profile:password"), {
            "old_password": "wrong", "new_password1": "Brand-New-Pass-88", "new_password2": "Brand-New-Pass-88"})
        self.assertContains(page, "old password was entered incorrectly")
        page = self.client.post(reverse("profile:password"), {
            "old_password": "RitaPass!2026", "new_password1": "Brand-New-Pass-88", "new_password2": "different-99"})
        self.assertContains(page, "didn’t match")
        self.resident.refresh_from_db()
        self.assertTrue(self.resident.check_password("RitaPass!2026"))

    # ---- vehicles
    def add(self, **data):
        base = {"license_plate": "nbx 4471", "vehicle_type": "SUV", "make_model": "Toyota Fortuner", "color": "Black"}
        return self.client.post(reverse("profile:vehicle_add"), {**base, **data})

    def test_add_and_remove_vehicle(self):
        self.assertRedirects(self.add(), self.url, fetch_redirect_response=False)
        v = ResidentVehicle.objects.get()
        self.assertEqual((v.resident, v.license_plate, v.vehicle_type), (self.resident, "NBX 4471", "SUV"))
        self.assertContains(self.client.get(self.url), "NBX 4471")
        self.client.post(reverse("profile:vehicle_remove", args=[v.pk]))
        self.assertFalse(ResidentVehicle.objects.exists())
        self.assertEqual(set(AuditLog.objects.values_list("action", flat=True)), {"ADD_VEHICLE", "REMOVE_VEHICLE"})

    def test_vehicle_validation_and_limits(self):
        self.assertContains(self.add(license_plate="!"), "Enter a plate number")
        self.assertContains(self.add(vehicle_type="BOAT"), "choose the vehicle type")
        self.add()
        self.assertContains(self.add(license_plate="NBX-4471"), "already registered")
        for i in range(4):
            self.add(license_plate=f"ABC {100 + i}")
        self.assertEqual(ResidentVehicle.objects.count(), 5)
        self.assertNotContains(self.client.get(self.url), 'aria-label="Add a vehicle"')
        self.assertContains(self.add(license_plate="XYZ 999"), "up to 5 vehicles")
        self.assertEqual(ResidentVehicle.objects.count(), 5)

    def test_only_residents_add_and_only_owner_removes(self):
        self.client.force_login(self.guard)
        self.add()
        self.assertFalse(ResidentVehicle.objects.exists())
        v = ResidentVehicle.objects.create(resident=self.resident, license_plate="NBX 4471", vehicle_type="SUV")
        self.client.post(reverse("profile:vehicle_remove", args=[v.pk]))
        self.assertTrue(ResidentVehicle.objects.filter(pk=v.pk).exists())
        self.assertEqual(self.client.get(reverse("profile:vehicle_add")).status_code, 405)

    def test_gate_check_shows_resident_vehicle(self):
        ResidentVehicle.objects.create(resident=self.resident, license_plate="NBX 4471", vehicle_type="SUV",
                                       make_model="Toyota Fortuner", color="Black")
        self.client.force_login(self.guard)
        page = self.client.get(reverse("guard:search"), {"q": "nbx4471"})
        self.assertContains(page, "Resident vehicle:")
        self.assertContains(page, "registered to Rita Reyes (Tower 2, Unit 1408)")
        self.resident.is_active = False  # deactivated residents' cars are no longer vouched for
        self.resident.save()
        self.assertNotContains(self.client.get(reverse("guard:search"), {"q": "nbx4471"}), "Resident vehicle:")

    # ---- recent activity
    def test_recent_activity_shows_my_last_five_actions_only(self):
        for i in range(7):
            AuditLog.record(self.resident, AuditLog.Action.SUBMIT_REQUEST, "PersonRestrictionRequest", i, f"Mine {i}.")
        AuditLog.record(self.admin, AuditLog.Action.APPROVE_REQUEST, "PersonRestrictionRequest", 1, "Not mine.")
        page = self.client.get(self.url)
        self.assertEqual(len(page.context["activity"]), 5)
        self.assertNotContains(page, "Not mine.")
