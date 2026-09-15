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
