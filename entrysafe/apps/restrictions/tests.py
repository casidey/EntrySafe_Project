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
