from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from apps.profile.models import Profile


class RegisterViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse("register:register")
        self.login_url = reverse("login:login")

    def test_register_get_renders_template(self):
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "register/register.html")

    def test_register_post_creates_user_and_profile(self):
        data = {
            "fullName": "Alexandra Vance",
            "emailAddress": "alexandra.v@domain.com",
            "password": "SecurePassword123!",
        }
        response = self.client.post(self.register_url, data)
        self.assertRedirects(response, self.login_url)
        
        user = User.objects.filter(email="alexandra.v@domain.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, "Alexandra Vance")
        
        profile = Profile.objects.filter(user=user).first()
        self.assertIsNotNone(profile)
        self.assertEqual(profile.full_name, "Alexandra Vance")

    def test_register_duplicate_email_fails(self):
        User.objects.create_user(username="alexandra.v@domain.com", email="alexandra.v@domain.com", password="pass")
        data = {
            "fullName": "Alexandra Duplicate",
            "emailAddress": "alexandra.v@domain.com",
            "password": "AnotherPassword123!",
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
