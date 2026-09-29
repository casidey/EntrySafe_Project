from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User


class LoginViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.login_url = reverse("login:login")
        self.logout_url = reverse("login:logout")
        self.home_url = reverse("home:home")
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="SecurePassword123!"
        )

    def test_login_get_renders_template(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "login/login.html")

    def test_login_post_valid_username_success(self):
        response = self.client.post(self.login_url, {
            "username": "testuser",
            "password": "SecurePassword123!"
        })
        self.assertRedirects(response, self.home_url)

    def test_login_post_valid_email_success(self):
        response = self.client.post(self.login_url, {
            "username": "testuser@example.com",
            "password": "SecurePassword123!"
        })
        self.assertRedirects(response, self.home_url)

    def test_login_post_invalid_password_fails(self):
        response = self.client.post(self.login_url, {
            "username": "testuser",
            "password": "WrongPassword"
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)

    def test_logout_redirects_to_login(self):
        self.client.force_login(self.user)
        response = self.client.get(self.logout_url)
        self.assertRedirects(response, self.login_url)

    def test_unauthenticated_user_redirected_from_home(self):
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 302)


class PendingLoginTests(TestCase):
    def setUp(self):
        from apps.profile.models import UserProfile
        self.user = User.objects.create_user(
            "pat@example.com", email="pat@example.com", password="SecurePassword123!", is_active=False)
        self.profile = UserProfile.objects.create(
            user=self.user, full_name="Pat Pending", unit_number="Tower 1, Unit 101", approval_status="PENDING")
        self.url = reverse("login:login")

    def test_pending_user_cannot_sign_in_and_is_told_why(self):
        response = self.client.post(self.url, {"username": "pat@example.com", "password": "SecurePassword123!"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("waiting for administrator approval", response.context["error"])

    def test_wrong_password_does_not_reveal_pending_status(self):
        response = self.client.post(self.url, {"username": "pat@example.com", "password": "nope"})
        self.assertEqual(response.context["error"], "Invalid username/email or password.")

    def test_disapproved_user_is_told_so_with_reason(self):
        self.profile.approval_status = "DISAPPROVED"
        self.profile.disapproval_reason = "Unit not found"
        self.profile.save()
        response = self.client.post(self.url, {"username": "pat@example.com", "password": "SecurePassword123!"})
        self.assertIn("not approved", response.context["error"])
        self.assertIn("Unit not found", response.context["error"])

    def test_approved_user_can_sign_in(self):
        admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.profile.approve(admin)
        response = self.client.post(self.url, {"username": "pat@example.com", "password": "SecurePassword123!"})
        self.assertRedirects(response, reverse("home:home"))
