from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.profile.models import UserProfile
from apps.profile.models import ReviewError

import shutil
import tempfile

TMP_MEDIA = tempfile.mkdtemp(prefix="entrysafe-test-media-")


def valid_payload(**over):
    data = {
        "fullName": "Alexandra Vance",
        "contactNumber": "+63 917 000 0000",
        "emailAddress": "alexandra.v@domain.com",
        "password": "SecurePassword123!",
        "tower": "2",
        "unitNumber": "1408",
        "consent": "on",
        "proofDocument": SimpleUploadedFile("proof.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
    }
    data.update(over)
    return data


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class RegisterViewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.client = Client()
        self.register_url = reverse("register:register")
        self.login_url = reverse("login:login")

    def test_register_get_renders_template(self):
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "register/register.html")

    def test_register_post_creates_inactive_user_with_pending_profile(self):
        response = self.client.post(self.register_url, valid_payload())
        self.assertRedirects(response, self.login_url)

        user = User.objects.get(email="alexandra.v@domain.com")
        self.assertFalse(user.is_active)  # cannot sign in until an admin approves
        profile = user.profile
        self.assertEqual(profile.approval_status, "PENDING")
        self.assertEqual(profile.role, "RESIDENT")
        self.assertEqual(profile.unit_number, "Tower 2, Unit 1408")
        self.assertTrue(profile.id_proof_image.name.startswith("id_proofs/"))
        self.assertNotEqual(user.password, "SecurePassword123!")  # stored hashed

    def test_submitted_modal_shows_on_login_page_once(self):
        self.client.post(self.register_url, valid_payload())
        first = self.client.get(self.login_url)
        self.assertContains(first, "Registration Submitted for Review")
        self.assertContains(first, "ES-0001")
        second = self.client.get(self.login_url)
        self.assertNotContains(second, "Registration Submitted for Review")

    def test_register_duplicate_email_fails(self):
        User.objects.create_user(username="alexandra.v@domain.com", email="alexandra.v@domain.com", password="pass")
        response = self.client.post(self.register_url, valid_payload())
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertEqual(User.objects.filter(email="alexandra.v@domain.com").count(), 1)

    def test_second_registration_with_same_email_fails(self):
        self.client.post(self.register_url, valid_payload())
        response = self.client.post(self.register_url, valid_payload())
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertEqual(User.objects.filter(email="alexandra.v@domain.com").count(), 1)

    def test_missing_document_is_rejected_on_step_two(self):
        payload = valid_payload()
        del payload["proofDocument"]
        response = self.client.post(self.register_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["start_step"], 2)
        self.assertFalse(User.objects.filter(email="alexandra.v@domain.com").exists())

    def test_bad_document_type_is_rejected(self):
        bad = SimpleUploadedFile("proof.exe", b"MZ", content_type="application/octet-stream")
        response = self.client.post(self.register_url, valid_payload(proofDocument=bad))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)

    def test_weak_password_is_rejected(self):
        response = self.client.post(self.register_url, valid_payload(password="12345678"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["start_step"], 1)

    def test_consent_required(self):
        payload = valid_payload()
        del payload["consent"]
        response = self.client.post(self.register_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class ProfileReviewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.client.post(reverse("register:register"), valid_payload())
        self.profile = UserProfile.objects.get(user__email="alexandra.v@domain.com")

    def test_approve_activates_user_and_keeps_password(self):
        user = self.profile.approve(self.admin)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("SecurePassword123!"))
        self.assertEqual(self.profile.approval_status, "APPROVED")
        self.assertEqual(self.profile.reviewed_by, self.admin)
        self.assertIsNotNone(self.profile.reviewed_at)

    def test_approve_writes_audit_log_and_notification(self):
        user = self.profile.approve(self.admin)
        log = AuditLog.objects.get()
        self.assertEqual((log.action, log.user, log.target_entity, log.target_id),
                         ("APPROVE_ACCOUNT", self.admin, "UserProfile", self.profile.pk))
        note = Notification.objects.get(recipient=user)
        self.assertEqual(note.notification_type, "ACCOUNT_STATUS")
        self.assertFalse(note.is_read)

    def test_cannot_review_twice(self):
        self.profile.approve(self.admin)
        with self.assertRaises(ReviewError):
            self.profile.approve(self.admin)
        with self.assertRaises(ReviewError):
            self.profile.disapprove(self.admin)

    def test_disapprove_keeps_user_inactive_and_stores_reason(self):
        self.profile.disapprove(self.admin, reason="ID unreadable")
        self.profile.user.refresh_from_db()
        self.assertFalse(self.profile.user.is_active)
        self.assertEqual(self.profile.approval_status, "DISAPPROVED")
        self.assertEqual(self.profile.disapproval_reason, "ID unreadable")
        self.assertEqual(AuditLog.objects.get().action, "DISAPPROVE_ACCOUNT")
